"""Read competition traffic CSV without exposing future rows to the sender."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .models import ScenarioSummary, TelemetryRow


def _number(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _boolean(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


class TrafficDataset:
    """In-memory, time-sorted telemetry grouped by trip ID."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"traffic dataset not found: {path}")
        grouped: dict[int, list[TelemetryRow]] = defaultdict(list)
        units: dict[int, int] = {}
        with path.open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                tr_id = int(raw["tr_id"])
                unit_id = int(raw["unit_id"])
                previous = units.setdefault(tr_id, unit_id)
                if previous != unit_id:
                    raise ValueError(f"tr_id={tr_id} has multiple unit_id values")
                latitude = _number(raw.get("lat"))
                longitude = _number(raw.get("lon"))
                valid = (
                    _boolean(raw.get("location_valid"))
                    and latitude is not None
                    and longitude is not None
                    and -90 <= latitude <= 90
                    and -180 <= longitude <= 180
                )
                grouped[tr_id].append(TelemetryRow(
                    tr_id=tr_id,
                    unit_id=unit_id,
                    event_time=datetime.fromisoformat(raw["event_time"]),
                    receive_time=datetime.fromisoformat(raw["receive_time"]),
                    latitude=latitude,
                    longitude=longitude,
                    altitude_m=_number(raw.get("alt")),
                    speed_kmh=_number(raw.get("speed")),
                    heading=_number(raw.get("heading")),
                    location_valid=valid,
                ))
        self.path = path
        self._rows = dict(grouped)
        for rows in self._rows.values():
            rows.sort(key=lambda row: (row.available_at, row.event_time))

    def scenarios(self) -> list[ScenarioSummary]:
        result = []
        for tr_id, rows in self._rows.items():
            if not rows:
                continue
            result.append(ScenarioSummary(
                tr_id=tr_id,
                unit_id=rows[0].unit_id,
                packets=len(rows),
                valid_packets=sum(row.location_valid for row in rows),
                starts_at=rows[0].available_at,
                ends_at=rows[-1].available_at,
                duration_s=(rows[-1].available_at - rows[0].available_at).total_seconds(),
            ))
        return sorted(result, key=lambda item: (-item.valid_packets, item.tr_id))

    def select(
        self,
        tr_ids: list[int],
        *,
        valid_locations_only: bool,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> list[TelemetryRow]:
        missing = sorted(set(tr_ids) - self._rows.keys())
        if missing:
            raise ValueError(f"unknown tr_id values: {missing}")
        selected = []
        for tr_id in tr_ids:
            for row in self._rows[tr_id]:
                if valid_locations_only and not row.location_valid:
                    continue
                if start_at and row.available_at < start_at:
                    continue
                if end_at and row.available_at > end_at:
                    continue
                selected.append(row)
        selected.sort(key=lambda row: (row.available_at, row.tr_id))
        if not selected:
            raise ValueError("the selected replay interval contains no packets")
        return selected
