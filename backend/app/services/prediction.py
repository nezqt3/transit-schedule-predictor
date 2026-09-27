"""Prepare a causal NDTP window and call the ML inference service."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta, timezone
from threading import RLock
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.prediction import StoredPrediction
from app.services.ml_client import request_prediction
from app.services.telemetry import TelemetryService

logger = logging.getLogger(__name__)


class PredictionStore:
    """Keep the latest successful ML result for each vehicle in memory."""

    def __init__(self, max_vehicles: int = 500, *,
                 initial: Iterable[StoredPrediction] = (),
                 persist: Callable[[StoredPrediction], Awaitable[None]] | None = None) -> None:
        self._latest: OrderedDict[int, StoredPrediction] = OrderedDict()
        self._lock = RLock()
        self._max_vehicles = max_vehicles
        self._persist = persist
        self._persistence_tasks: set[asyncio.Task] = set()
        for prediction in sorted(initial, key=lambda item: item.prediction_time):
            self._latest[prediction.tr_id] = prediction

    def _schedule_persistence(self, prediction: StoredPrediction) -> None:
        if self._persist is None:
            return
        try:
            task = asyncio.get_running_loop().create_task(self._persist(prediction))
        except RuntimeError:
            return
        self._persistence_tasks.add(task)
        task.add_done_callback(self._persistence_done)

    def _persistence_done(self, task: asyncio.Task) -> None:
        self._persistence_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("prediction persistence failed: %s", task.exception())

    async def flush(self) -> None:
        if self._persistence_tasks:
            await asyncio.gather(*tuple(self._persistence_tasks), return_exceptions=True)

    def record(self, prediction: StoredPrediction) -> bool:
        with self._lock:
            previous = self._latest.get(prediction.tr_id)
            if previous and prediction.prediction_time <= previous.prediction_time:
                return False
            self._latest.pop(prediction.tr_id, None)
            self._latest[prediction.tr_id] = prediction
            if len(self._latest) > self._max_vehicles:
                self._latest.popitem(last=False)
        self._schedule_persistence(prediction)
        return True

    def list_latest(self) -> list[StoredPrediction]:
        with self._lock:
            return [self._with_freshness(value) for value in self._latest.values()]

    def get_latest(self, tr_id: int) -> StoredPrediction | None:
        with self._lock:
            prediction = self._latest.get(tr_id)
            return self._with_freshness(prediction) if prediction else None

    def mark_stale(self, tr_id: int) -> StoredPrediction | None:
        with self._lock:
            prediction = self._latest.get(tr_id)
            if prediction is None or prediction.freshness == "stale":
                return None
            stale = prediction.model_copy(update={"freshness": "stale"})
            self._latest[tr_id] = stale
        self._schedule_persistence(stale)
        return stale

    @staticmethod
    def _with_freshness(prediction: StoredPrediction) -> StoredPrediction:
        produced = prediction.produced_at or prediction.prediction_time
        if produced.tzinfo is None:
            produced = produced.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - produced > timedelta(minutes=2):
            return prediction.model_copy(update={"freshness": "stale"})
        return prediction


async def predict_delay(
    telemetry: TelemetryService,
    ml_client: httpx.AsyncClient,
    *,
    tr_id: int,
    unit_id: int,
    T: datetime,
    cur_dev_s: float,
    target_stop_id: int,
    target_time_begin: datetime,
    stop_lat: float,
    stop_lon: float,
    current_point: dict | None = None,
    replay: bool = False,
    planned_stops: list[dict] | None = None,
) -> dict:
    """Call ML with at most 150 normalized packets for the target vehicle."""
    source_zone = ZoneInfo(settings.source_timezone)
    normalized_t = (T.replace(tzinfo=source_zone) if T.tzinfo is None
                    else T).astimezone(timezone.utc)
    normalized_target = (target_time_begin.replace(tzinfo=source_zone)
                         if target_time_begin.tzinfo is None
                         else target_time_begin).astimezone(timezone.utc)
    horizon_s = (normalized_target - normalized_t).total_seconds()
    if not 600 < horizon_s <= 900:
        raise HTTPException(status_code=422, detail="target stop must be in (T+10m, T+15m]")
    points = []
    for event in telemetry.get_recent(unit_id):
        nav = event.nav
        if nav is None:
            continue
        event_time = event.event_time.astimezone(timezone.utc)
        receive_time = (event_time if replay else event.received_at.astimezone(timezone.utc))
        if event_time > normalized_t or receive_time > normalized_t:
            continue
        points.append({
            "event_time": event_time.isoformat(),
            "receive_time": receive_time.isoformat(),
            "location_valid": nav.coordinates_valid,
            "lat": nav.latitude,
            "lon": nav.longitude,
            "speed": nav.speed_avg,
            "heading": nav.course,
        })
    if current_point is not None:
        points.append(current_point)
    if not points:
        raise HTTPException(status_code=404, detail=f"no telemetry for unit_id={unit_id}")
    payload = {
        "tr_id": tr_id,
        "T": T.isoformat(),
        "cur_dev_s": cur_dev_s,
        "target_stop_id": target_stop_id,
        "target_time_begin": target_time_begin.isoformat(),
        "stop_lat": stop_lat,
        "stop_lon": stop_lon,
        "telemetry": points,
        "planned_stops": planned_stops or [],
    }
    return await request_prediction(payload, ml_client)
