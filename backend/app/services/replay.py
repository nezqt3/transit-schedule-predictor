"""Load the labelled January test drive for causal historical playback.

The model payload uses only plan, point inputs and telemetry observed by T.
Ground truth is retained solely for the dashboard's later comparison.
"""

from __future__ import annotations

import csv
import math
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from app.schemas.replay import (
    ReplayFleet, ReplayFleetVehicle, ReplayPoint, ReplayRun, ReplayScenario,
    ReplayStop, ReplayTelemetry, ReplayVehicle,
)


POINT = re.compile(r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)")


def _coordinates(geom: str) -> tuple[float, float] | None:
    match = POINT.fullmatch(geom)
    if match is None:
        return None
    return float(match.group(2)), float(match.group(1))


def _number(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 12_742_000 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _repeat_period(stops: list[ReplayStop]) -> int | None:
    """Find the shortest strongly repeated planned stop sequence."""
    places = [stop.place_id for stop in stops]
    for period in range(8, min(200, len(places) // 2) + 1):
        comparable = len(places) - period
        if comparable < 20:
            continue
        matches = sum(places[index] == places[index + period]
                      for index in range(comparable))
        if matches / comparable >= 0.85:
            return period
    return None


class ReplayDataset:
    """Immutable CSV snapshot for a separate historical playback source."""

    def __init__(self, schedule_path: str, traffic_path: str, labels_path: str) -> None:
        self.stops: dict[int, list[ReplayStop]] = defaultdict(list)
        self.traffic: dict[int, list[dict]] = defaultdict(list)
        self.points: dict[int, list[ReplayPoint]] = defaultdict(list)
        self.by_sample: dict[str, tuple[int, ReplayPoint]] = {}
        self.units: dict[int, int] = {}
        self._fleet: ReplayFleet | None = None

        # Deliberately ignore time_fact_begin: only the published plan enters ML.
        with Path(schedule_path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                coords = _coordinates(row["geom"])
                if coords is None:
                    continue
                tr_id = int(row["tr_id"])
                self.stops[tr_id].append(ReplayStop(
                    stop_id=int(row["tt_action_item_id"]),
                    planned_at=datetime.fromisoformat(row["time_begin"]),
                    lat=coords[0], lon=coords[1],
                    place_id=f"{coords[0]:.5f},{coords[1]:.5f}",
                    address=(row.get("building_address") or "").strip() or None,
                ))
        for stops in self.stops.values():
            stops.sort(key=lambda stop: (stop.planned_at, stop.stop_id))

        with Path(traffic_path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                tr_id = int(row["tr_id"])
                unit_id = int(row["unit_id"])
                previous = self.units.setdefault(tr_id, unit_id)
                if previous != unit_id:
                    raise ValueError(f"multiple unit IDs for tr_id={tr_id}")
                lat, lon = _number(row["lat"]), _number(row["lon"])
                if (row["location_valid"].lower() not in ("true", "1")
                        or lat is None or lon is None
                        or not -90 <= lat <= 90 or not -180 <= lon <= 180):
                    continue
                event_time = datetime.fromisoformat(row["event_time"])
                receive_time = datetime.fromisoformat(row["receive_time"])
                self.traffic[tr_id].append({
                    "event_time": event_time,
                    "receive_time": receive_time,
                    "lat": lat, "lon": lon,
                    "speed": _number(row["speed"]),
                    "heading": _number(row["heading"]),
                })
        for traffic in self.traffic.values():
            traffic.sort(key=lambda row: row["event_time"])

        stop_by_id = {
            (tr_id, stop.stop_id): stop
            for tr_id, stops in self.stops.items() for stop in stops
        }
        with Path(labels_path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                tr_id = int(row["tr_id"])
                stop_id = int(row["target_stop_id"])
                stop = stop_by_id.get((tr_id, stop_id))
                if stop is None:
                    raise ValueError(f"test target stop missing from plan: {tr_id}/{stop_id}")
                planned = datetime.fromisoformat(row["target_time_begin"])
                if stop.planned_at != planned:
                    raise ValueError(f"test target time differs from plan: {tr_id}/{stop_id}")
                actual_delay = float(row["target_delay_s"])
                point = ReplayPoint(
                    sample_id=row["sample_id"], T=datetime.fromisoformat(row["T"]),
                    target_stop_id=stop_id, target_time_begin=planned,
                    cur_dev_s=float(row["cur_dev_s"]),
                    actual_delay_s=actual_delay,
                    actual_at=planned + timedelta(seconds=actual_delay),
                    lat=stop.lat, lon=stop.lon,
                )
                self.points[tr_id].append(point)
                self.by_sample[point.sample_id] = (tr_id, point)
        for points in self.points.values():
            points.sort(key=lambda point: point.T)

        self._confirm_stops()

    def _confirm_stops(self) -> None:
        """Retrospectively verify planned stop geometry against recorded GPS."""
        for tr_id, stops in self.stops.items():
            rows = self.traffic.get(tr_id, [])
            times = [row["event_time"] for row in rows]
            for stop in stops:
                left = bisect_left(times, stop.planned_at - timedelta(minutes=8))
                right = bisect_right(times, stop.planned_at + timedelta(minutes=8))
                nearest = min((
                    _distance_m(stop.lat, stop.lon, row["lat"], row["lon"])
                    for row in rows[left:right]
                ), default=None)
                stop.gps_distance_m = round(nearest, 1) if nearest is not None else None
                stop.gps_confirmed = nearest is not None and nearest <= 120

    def _runs(self, tr_id: int) -> list[ReplayRun]:
        stops = self.stops.get(tr_id, [])
        if not stops:
            return []
        period = _repeat_period(stops)
        groups: list[list[ReplayStop]] = []
        if period is not None:
            groups = [stops[index:index + period]
                      for index in range(0, len(stops), period)]
        else:
            current: list[ReplayStop] = []
            for stop in stops:
                if current and stop.planned_at - current[-1].planned_at > timedelta(minutes=20):
                    groups.append(current)
                    current = []
                current.append(stop)
            if current:
                groups.append(current)
        result = []
        for index, group in enumerate(groups, 1):
            confirmed = sum(stop.gps_confirmed for stop in group)
            result.append(ReplayRun(
                run_id=f"{tr_id}-{index}", tr_id=tr_id,
                start_at=group[0].planned_at, end_at=group[-1].planned_at,
                stop_ids=[stop.stop_id for stop in group],
                confirmed_stops=confirmed,
                valid=len(group) >= 8 and confirmed >= 5
                and confirmed / len(group) >= 0.5,
            ))
        return result

    def fleet(self) -> ReplayFleet:
        """Return one shared January timeline for all recorded GPS vehicles."""
        if self._fleet is not None:
            return self._fleet
        vehicles = []
        bounds = []
        for tr_id in sorted(self.units):
            rows = self.traffic.get(tr_id, [])
            sampled: dict[int, ReplayTelemetry] = {}
            for row in rows:
                available = max(row["event_time"], row["receive_time"])
                bounds.append(available)
                sampled[int(available.timestamp()) // 45] = ReplayTelemetry(
                    available_at=available, event_time=row["event_time"],
                    lat=row["lat"], lon=row["lon"], speed=row["speed"],
                    heading=row["heading"],
                )
            vehicles.append(ReplayFleetVehicle(
                tr_id=tr_id, unit_id=self.units[tr_id],
                telemetry=sorted(sampled.values(), key=lambda point: point.available_at),
                stops=self.stops.get(tr_id, []), runs=self._runs(tr_id),
                points=self.points.get(tr_id, []),
            ))
        if not bounds:
            raise ValueError("historical replay has no valid GPS")
        self._fleet = ReplayFleet(
            start_at=min(bounds), end_at=max(bounds), vehicles=vehicles,
        )
        return self._fleet

    def vehicles(self) -> list[ReplayVehicle]:
        result = []
        for tr_id, points in self.points.items():
            result.append(ReplayVehicle(
                tr_id=tr_id, unit_id=self.units[tr_id], samples=len(points),
                start_at=points[0].T - timedelta(minutes=30),
                end_at=max(point.actual_at for point in points) + timedelta(minutes=2),
            ))
        return sorted(result, key=lambda vehicle: (-vehicle.samples, vehicle.tr_id))

    def scenario(self, tr_id: int) -> ReplayScenario | None:
        points = self.points.get(tr_id)
        if not points:
            return None
        vehicle = next(vehicle for vehicle in self.vehicles() if vehicle.tr_id == tr_id)
        visible = []
        by_bucket = {}
        for row in self.traffic[tr_id]:
            available = max(row["event_time"], row["receive_time"])
            if vehicle.start_at <= available <= vehicle.end_at:
                bucket = int(available.timestamp()) // 30
                by_bucket[bucket] = ReplayTelemetry(
                    available_at=available, event_time=row["event_time"],
                    lat=row["lat"], lon=row["lon"], speed=row["speed"],
                    heading=row["heading"],
                )
        visible.extend(by_bucket.values())
        visible.sort(key=lambda row: row.available_at)
        stops = [stop for stop in self.stops[tr_id]
                 if vehicle.start_at <= stop.planned_at <= vehicle.end_at]
        return ReplayScenario(vehicle=vehicle, telemetry=visible,
                              stops=stops, points=points)

    def prediction_payload(self, sample_id: str) -> dict | None:
        selected = self.by_sample.get(sample_id)
        if selected is None:
            return None
        tr_id, point = selected
        t = point.T
        observed = [row for row in self.traffic[tr_id]
                    if t - timedelta(minutes=30) <= row["event_time"] <= t
                    and row["receive_time"] <= t][-150:]
        return {
            "tr_id": tr_id, "T": t.isoformat(),
            "cur_dev_s": point.cur_dev_s,
            "target_stop_id": point.target_stop_id,
            "target_time_begin": point.target_time_begin.isoformat(),
            "stop_lat": point.lat, "stop_lon": point.lon,
            "telemetry": [{
                "event_time": row["event_time"].isoformat(),
                "receive_time": row["receive_time"].isoformat(),
                "location_valid": True,
                "lat": row["lat"], "lon": row["lon"],
                "speed": row["speed"], "heading": row["heading"],
            } for row in observed],
        }
