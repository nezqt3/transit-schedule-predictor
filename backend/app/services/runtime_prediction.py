"""Automatic NDTP-to-ML prediction flow using only observed state."""

from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException

from app.ndtp.schemas import TelemetryEvent
from app.schemas.prediction import PredictionStatus, StoredPrediction
from app.services.incident import IncidentStore
from app.services.map_matching import HmmMapMatcher, MapMatchResult
from app.services.prediction import PredictionStore, predict_delay
from app.services.runtime_lookup import RuntimeLookup
from app.services.telemetry import TelemetryService

logger = logging.getLogger(__name__)


class RuntimePrediction:
    """Schedule at most one ML call per vehicle and publish its result."""

    def __init__(self, *, telemetry: TelemetryService, lookup: RuntimeLookup,
                 predictions: PredictionStore, incidents: IncidentStore,
                 ml_client: httpx.AsyncClient, interval_s: float = 30,
                 max_in_flight: int = 8) -> None:
        self.telemetry = telemetry
        self.lookup = lookup
        self.predictions = predictions
        self.incidents = incidents
        self.ml_client = ml_client
        self.interval_s = interval_s
        self._ml_semaphore = asyncio.Semaphore(max(1, max_in_flight))
        self._tasks: dict[int, asyncio.Task] = {}
        self._last_started: dict[int, datetime] = {}
        self._retry_after_wall: dict[int, datetime] = {}
        self._last_confirmed: dict[int, tuple[int, datetime]] = {}
        self.map_matcher = HmmMapMatcher(lookup.route_graphs)
        self._statuses: dict[int, PredictionStatus] = {}
        self.requests_started = 0
        self.requests_succeeded = 0
        self.requests_failed = 0
        self._latencies_s: deque[float] = deque(maxlen=10_000)
        self._ml_latencies_s: deque[float] = deque(maxlen=10_000)
        self._ml_queue_wait_s: deque[float] = deque(maxlen=10_000)
        self.peak_active_tasks = 0

    def statuses(self) -> list[PredictionStatus]:
        return list(self._statuses.values())

    def _status(self, unit_id: int, tr_id: int | None, code: str) -> None:
        previous = self._statuses.get(unit_id)
        if previous is None or previous.code != code:
            logger.info("prediction status unit_id=%s tr_id=%s: %s", unit_id, tr_id, code)
        self._statuses[unit_id] = PredictionStatus(
            unit_id=unit_id, tr_id=tr_id, code=code,
            updated_at=datetime.now(timezone.utc),
        )
        if tr_id is not None and code not in {"fresh", "pending"}:
            stale = self.predictions.mark_stale(tr_id)
            if stale is not None:
                self.telemetry.publish("prediction_update", stale.model_dump(mode="json"))

    def on_event(self, event: TelemetryEvent) -> None:
        """Called after the packet has been accepted into the telemetry buffer."""
        tr_id = self.lookup.demo_tr_by_unit.get(event.unit_id)
        if tr_id is not None:
            self.lookup.register_demo(event)
        else:
            tr_id = self.lookup.vehicles_by_unit.get(event.unit_id)
        if tr_id is None:
            self._status(event.unit_id, None, "schedule_unmatched")
            return
        if event.nav is None or not event.nav.coordinates_valid:
            self._status(event.unit_id, tr_id, "invalid_telemetry")
            return
        running = self._tasks.get(event.unit_id)
        if running is not None and not running.done():
            return
        retry_after = self._retry_after_wall.get(event.unit_id)
        if retry_after is not None and datetime.now(timezone.utc) < retry_after:
            return
        historical = abs(event.received_at - event.event_time) > timedelta(days=1)
        demo = tr_id in self.lookup.demo_tr_ids
        t = event.event_time if historical else event.received_at
        last = self._last_started.get(event.unit_id)
        if last is not None and 0 <= (t - last).total_seconds() < self.interval_s:
            return
        target = self.lookup.target_for(tr_id, t)
        if target is None:
            self._status(event.unit_id, tr_id, "no_target_in_horizon")
            for item in self.incidents.resolve_vehicle(tr_id):
                self.telemetry.publish("incident", item.model_dump(mode="json"))
            return
        hint = (self.lookup.point_hint(tr_id, t, target["target_stop_id"])
                if historical else None)
        demo_delay = self.lookup.demo_current_delay(tr_id, t) if demo else None
        current = (self._confirmed_delay(tr_id, event.unit_id, t, historical)
                   if hint is None and demo_delay is None else None)
        map_match = self._match_current(tr_id, event.unit_id, t, historical)
        if hint is None and demo_delay is None and current is None:
            self._status(event.unit_id, tr_id, "insufficient_data")
            return
        if hint is not None:
            delay_s, previous_stop_id, confirmed_at, delay_source = (
                hint, None, None, "point_input"
            )
        elif demo_delay is not None:
            delay_s, previous_stop_id, confirmed_at, delay_source = (
                demo_delay, None, None, "demo_anchor"
            )
        else:
            delay_s, previous_stop_id, confirmed_at = current
            delay_source = "confirmed_stop"
        self._last_started[event.unit_id] = t
        self.requests_started += 1
        self._tasks[event.unit_id] = asyncio.create_task(
            self._predict(event, tr_id, t, target, delay_s, previous_stop_id,
                          confirmed_at, delay_source, historical, demo, map_match),
            name=f"ndtp-predict-{event.unit_id}",
        )
        self.peak_active_tasks = max(
            self.peak_active_tasks,
            sum(not task.done() for task in self._tasks.values()),
        )

    def _confirmed_delay(self, tr_id: int, unit_id: int, t: datetime,
                         historical: bool) -> tuple[float, int, datetime] | None:
        points = self._causal_points(unit_id, t, historical)
        plan = self.lookup.plans.get(tr_id, ())
        graph = self.lookup.route_graphs.graphs.get(tr_id)
        matches = self.map_matcher.match_sequence(tr_id, points)
        if graph is None or not matches:
            return None
        last_confirmed = self._last_confirmed.get(unit_id)
        for index in range(len(plan) - 1, -1, -1):
            stop = plan[index]
            planned = stop["target_time_begin"]
            if planned > t or (last_confirmed and index < last_confirmed[0]):
                continue
            stop_chainage = graph.stop_chainages[index]
            nearby = [match for match in matches
                      if -120 <= (match.event.event_time - planned).total_seconds() <= 8 * 60
                      and abs(match.chainage_m - stop_chainage) <= 120
                      and match.distance_m <= 120 and match.confidence >= 0.08]
            if len(nearby) < 2:
                continue
            nearby.sort(key=lambda item: item.event.event_time)
            if not any(item.event.nav.speed_avg is not None and
                       0 <= item.event.nav.speed_avg <= 15 for item in nearby):
                continue
            for first, second in zip(nearby, nearby[1:]):
                gap = (second.event.event_time - first.event.event_time).total_seconds()
                if 0 < gap <= 120:
                    confirmed_at = first.event.event_time
                    self._last_confirmed[unit_id] = (index, confirmed_at)
                    return ((confirmed_at - planned).total_seconds(),
                            stop["target_stop_id"], confirmed_at)
        return None

    def _causal_points(self, unit_id: int, t: datetime,
                       historical: bool) -> list[TelemetryEvent]:
        return [event for event in self.telemetry.get_recent(unit_id)
                if event.nav is not None and event.nav.coordinates_valid
                and event.event_time <= t and (historical or event.received_at <= t)]

    def _match_current(self, tr_id: int, unit_id: int, t: datetime,
                       historical: bool) -> MapMatchResult | None:
        return self.map_matcher.match(
            tr_id, self._causal_points(unit_id, t, historical),
        )

    async def _predict(self, event: TelemetryEvent, tr_id: int, t: datetime,
                       target: dict, delay_s: float, previous_stop_id: int | None,
                       confirmed_at: datetime | None, delay_source: str,
                       historical: bool, demo: bool,
                       map_match: MapMatchResult | None) -> None:
        try:
            queued_at = asyncio.get_running_loop().time()
            async with self._ml_semaphore:
                ml_started = asyncio.get_running_loop().time()
                self._ml_queue_wait_s.append(ml_started - queued_at)
                result = await predict_delay(
                    self.telemetry, self.ml_client,
                    tr_id=tr_id, unit_id=event.unit_id, T=t, cur_dev_s=delay_s,
                    target_stop_id=target["target_stop_id"],
                    target_time_begin=target["target_time_begin"],
                    stop_lat=target["stop_lat"], stop_lon=target["stop_lon"],
                    replay=historical,
                    planned_stops=[{
                        "tt_action_item_id": stop["target_stop_id"],
                        "time_begin": stop["target_time_begin"].isoformat(),
                        "geom": f"POINT ({stop['stop_lon']} {stop['stop_lat']})",
                    } for stop in self.lookup.plans[tr_id]],
                )
                self._ml_latencies_s.append(asyncio.get_running_loop().time() - ml_started)
            predicted_delay = float(result["prediction"])
            if not math.isfinite(predicted_delay):
                raise ValueError("non-finite ML prediction")
            now = datetime.now(timezone.utc)
            p_late = result.get("p_late")
            prediction = StoredPrediction(
                tr_id=tr_id, unit_id=event.unit_id, prediction_time=t,
                input_event_time=event.event_time,
                input_received_at=event.received_at,
                target_stop_id=target["target_stop_id"],
                target_time=target["target_time_begin"],
                current_delay_s=delay_s, predicted_delay_s=predicted_delay,
                model=result["model"], model_version=result["model_version"],
                model_artifact_sha256=result.get("model_artifact_sha256"),
                produced_at=now,
                predicted_arrival=target["target_time_begin"] + timedelta(seconds=predicted_delay),
                current_delay_source=delay_source,
                last_confirmed_stop_id=previous_stop_id,
                last_confirmed_at=confirmed_at,
                source="demo" if demo else "replay" if historical else "live",
                p_late=p_late,
                risk_model_version=result.get("risk_model_version"),
                risk=self.incidents.risk(predicted_delay, p_late),
                risk_source=("calibrated_probability" if p_late is not None
                             else "threshold"),
                matched_segment_index=(map_match.segment_index if map_match else None),
                matched_progress_m=(round(map_match.chainage_m, 1) if map_match else None),
                matched_lat=(map_match.latitude if map_match else None),
                matched_lon=(map_match.longitude if map_match else None),
                map_match_distance_m=(round(map_match.distance_m, 1) if map_match else None),
                map_match_confidence=(map_match.confidence if map_match else None),
                map_match_graph_source=(map_match.graph_source if map_match else None),
            )
            if not self.predictions.record(prediction):
                return
            self.requests_succeeded += 1
            self._latencies_s.append(max(0.0, (now - event.received_at).total_seconds()))
            self._status(event.unit_id, tr_id, "fresh")
            self._retry_after_wall.pop(event.unit_id, None)
            self.telemetry.publish("prediction_update", prediction.model_dump(mode="json"))
            for item in self.incidents.resolve_vehicle(tr_id, target["target_stop_id"]):
                self.telemetry.publish("incident", item.model_dump(mode="json"))
            incident = self.incidents.evaluate(
                prediction, speed_kmh=event.nav.speed_avg if event.nav else None,
                previous_stop_id=previous_stop_id,
            )
            if incident is not None:
                self.telemetry.publish("incident", incident.model_dump(mode="json"))
            logger.info("prediction generated tr_id=%s stop_id=%s delay=%.1f",
                        tr_id, target["target_stop_id"], predicted_delay)
        except HTTPException as exc:
            self.requests_failed += 1
            if exc.status_code == 503:
                self._retry_after_wall[event.unit_id] = (
                    datetime.now(timezone.utc) + timedelta(seconds=5)
                )
            self._status(event.unit_id, tr_id, "ml_unavailable" if exc.status_code == 503
                         else "insufficient_data")
        except (ValueError, KeyError, TypeError):
            self.requests_failed += 1
            self._status(event.unit_id, tr_id, "invalid_prediction")
            logger.exception("automatic prediction failed for unit_id=%s", event.unit_id)

    async def stop(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def stats(self) -> dict:
        """Compact latency and queue measurements for benchmark reporting."""
        ordered = sorted(self._latencies_s)
        ml_ordered = sorted(self._ml_latencies_s)
        queue_ordered = sorted(self._ml_queue_wait_s)

        def percentile(values: list[float], fraction: float) -> float | None:
            if not values:
                return None
            return values[min(len(values) - 1, int(fraction * (len(values) - 1)))]

        return {
            "requests_started": self.requests_started,
            "requests_succeeded": self.requests_succeeded,
            "requests_failed": self.requests_failed,
            "active_tasks": sum(not task.done() for task in self._tasks.values()),
            "peak_active_tasks": self.peak_active_tasks,
            "packet_to_publish_p50_s": percentile(ordered, 0.50),
            "packet_to_publish_p95_s": percentile(ordered, 0.95),
            "packet_to_publish_p99_s": percentile(ordered, 0.99),
            "ml_request_p50_s": percentile(ml_ordered, 0.50),
            "ml_request_p95_s": percentile(ml_ordered, 0.95),
            "ml_request_p99_s": percentile(ml_ordered, 0.99),
            "ml_queue_wait_p50_s": percentile(queue_ordered, 0.50),
            "ml_queue_wait_p95_s": percentile(queue_ordered, 0.95),
            "ml_queue_wait_p99_s": percentile(queue_ordered, 0.99),
            "latency_samples": len(ordered),
        }
