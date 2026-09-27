"""Read-only mapping from NDTP terminals to planned stops, without actual arrivals."""

from __future__ import annotations

import csv
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.ndtp.schemas import TelemetryEvent
from app.services.map_matching import RouteGraphRegistry

logger = logging.getLogger(__name__)
POINT = re.compile(r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)")


class RuntimeLookup:
    """Select the first planned stop in the competition horizon for a terminal."""

    def __init__(self, schedule_path: str, traffic_path: str,
                 source_timezone: str = "Europe/Moscow",
                 points_path: str | None = None,
                 demo_units: str = "",
                 demo_initial_delay_s: float = 180,
                 route_graph_path: str | None = None) -> None:
        self.stops: dict[int, dict] = {}
        self.plans: dict[int, list[dict]] = defaultdict(list)
        self.units: dict[int, int] = {}
        self.vehicles_by_unit: dict[int, int] = {}
        self.point_hints: dict[int, list[dict]] = defaultdict(list)
        self.demo_tr_by_unit = {
            int(value.strip()): 9_000_000 + index
            for index, value in enumerate(demo_units.split(",")) if value.strip()
        }
        self.demo_tr_ids = set(self.demo_tr_by_unit.values())
        self.demo_anchor: dict[int, datetime] = {}
        self.demo_initial_delay_s = demo_initial_delay_s
        self.source_timezone = ZoneInfo(source_timezone)
        schedule = Path(schedule_path)
        traffic = Path(traffic_path)
        if schedule.is_file():
            with schedule.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"tr_id", "tt_action_item_id", "time_begin", "geom"}
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError("runtime schedule is missing plan columns")
                for row in reader:
                    match = POINT.fullmatch(row["geom"])
                    if not match:
                        continue
                    planned = self.to_utc(datetime.fromisoformat(row["time_begin"]))
                    stop = {
                        "tr_id": int(row["tr_id"]),
                        "target_stop_id": int(row["tt_action_item_id"]),
                        "stop_lon": float(match.group(1)),
                        "stop_lat": float(match.group(2)),
                        "target_time_begin": planned,
                        "address": (row.get("building_address") or "").strip() or None,
                    }
                    self.stops[stop["target_stop_id"]] = stop
                    self.plans[stop["tr_id"]].append(stop)
            for plan in self.plans.values():
                plan.sort(key=lambda stop: (stop["target_time_begin"], stop["target_stop_id"]))
        else:
            logger.warning("runtime schedule unavailable: %s", schedule)
        if traffic.is_file():
            with traffic.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if not {"tr_id", "unit_id"}.issubset(reader.fieldnames or []):
                    raise ValueError("runtime traffic is missing tr_id/unit_id")
                for row in reader:
                    if not row.get("unit_id") or not row.get("tr_id"):
                        continue
                    tr_id, unit_id = int(row["tr_id"]), int(row["unit_id"])
                    if tr_id in self.plans:
                        previous = self.vehicles_by_unit.get(unit_id)
                        if previous is not None and previous != tr_id:
                            raise ValueError(f"ambiguous unit mapping: {unit_id}")
                        self.units[tr_id] = unit_id
                        self.vehicles_by_unit[unit_id] = tr_id
        else:
            logger.warning("runtime unit mapping unavailable: %s", traffic)
        if points_path and Path(points_path).is_file():
            with Path(points_path).open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"tr_id", "T", "target_stop_id", "cur_dev_s"}
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError("runtime points are missing causal input columns")
                for row in reader:
                    self.point_hints[int(row["tr_id"])].append({
                        "T": self.to_utc(datetime.fromisoformat(row["T"])),
                        "target_stop_id": int(row["target_stop_id"]),
                        "cur_dev_s": float(row["cur_dev_s"]),
                    })
            for hints in self.point_hints.values():
                hints.sort(key=lambda point: point["T"])
        self.route_graphs = RouteGraphRegistry(self.plans, route_graph_path)
        logger.info("runtime lookups: %d stops, %d mapped vehicles",
                    len(self.stops), len(self.vehicles_by_unit))

    def to_utc(self, value: datetime) -> datetime:
        """Interpret source-naive timestamps in the configured source timezone."""
        return (value.replace(tzinfo=self.source_timezone) if value.tzinfo is None
                else value).astimezone(timezone.utc)

    def target_for(self, tr_id: int, prediction_time: datetime) -> dict | None:
        t = self.to_utc(prediction_time)
        lower, upper = t + timedelta(minutes=10), t + timedelta(minutes=15)
        return next((stop for stop in self.plans.get(tr_id, ())
                     if lower < stop["target_time_begin"] <= upper), None)

    def prior_stops(self, tr_id: int, prediction_time: datetime) -> list[dict]:
        t = self.to_utc(prediction_time)
        return [stop for stop in self.plans.get(tr_id, ())
                if stop["target_time_begin"] <= t]

    def point_hint(self, tr_id: int, prediction_time: datetime,
                   target_stop_id: int) -> float | None:
        """Use a supplied competition input only after its prediction time."""
        t = self.to_utc(prediction_time)
        for point in reversed(self.point_hints.get(tr_id, ())):
            if point["T"] <= t:
                if (t - point["T"]).total_seconds() <= 30 and (
                    point["target_stop_id"] == target_stop_id
                ):
                    return point["cur_dev_s"]
                return None
        return None

    def register_demo(self, event: TelemetryEvent) -> int | None:
        """Create a visibly synthetic plan for a configured official emulator unit."""
        tr_id = self.demo_tr_by_unit.get(event.unit_id)
        if tr_id is None or event.nav is None or not event.nav.coordinates_valid:
            return None
        if tr_id in self.plans:
            return tr_id
        anchor = event.received_at.astimezone(timezone.utc)
        self.demo_anchor[tr_id] = anchor
        self.units[tr_id] = event.unit_id
        self.vehicles_by_unit[event.unit_id] = tr_id
        for index, offset_min in enumerate([0] + list(range(13, 134, 5))):
            stop = {
                "tr_id": tr_id,
                "target_stop_id": tr_id * 1000 + index,
                "stop_lon": event.nav.longitude + index * 0.001,
                "stop_lat": event.nav.latitude,
                "target_time_begin": anchor + timedelta(minutes=offset_min),
                "address": "Демонстрационный план эмулятора",
            }
            self.stops[stop["target_stop_id"]] = stop
            self.plans[tr_id].append(stop)
        self.route_graphs.rebuild(tr_id, self.plans[tr_id])
        logger.warning("synthetic demo plan created for unit_id=%s tr_id=%s",
                       event.unit_id, tr_id)
        return tr_id

    def demo_current_delay(self, tr_id: int, prediction_time: datetime) -> float | None:
        anchor = self.demo_anchor.get(tr_id)
        if anchor and self.to_utc(prediction_time) >= anchor:
            return self.demo_initial_delay_s
        return None
