"""Read-only lookup of competition stop plans and NDTP unit mappings."""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)
POINT = re.compile(r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)")


class RuntimeLookup:
    """Resolve target stops and terminal IDs from configured CSV files."""

    def __init__(self, schedule_path: str, traffic_path: str) -> None:
        self.stops: dict[int, dict] = {}
        self.units: dict[int, int] = {}
        schedule = Path(schedule_path)
        traffic = Path(traffic_path)
        if schedule.is_file():
            with schedule.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    match = POINT.fullmatch(row["geom"])
                    if match:
                        self.stops[int(row["tt_action_item_id"])] = {
                            "tr_id": int(row["tr_id"]),
                            "stop_lon": float(match.group(1)),
                            "stop_lat": float(match.group(2)),
                            "target_time_begin": row["time_begin"],
                        }
        else:
            logger.warning("runtime schedule unavailable: %s", schedule)
        if traffic.is_file():
            with traffic.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row.get("unit_id") and row.get("tr_id"):
                        self.units[int(row["tr_id"])] = int(row["unit_id"])
        else:
            logger.warning("runtime unit mapping unavailable: %s", traffic)
        logger.info("runtime lookups: %d stops, %d vehicles", len(self.stops), len(self.units))
