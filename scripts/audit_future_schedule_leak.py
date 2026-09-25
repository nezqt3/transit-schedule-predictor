"""Audit answer leakage through completed schedules without exporting labels.

Run from the repository root: python scripts/audit_future_schedule_leak.py
Only aggregate counts are printed; this script does not create a submission.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"
KEY = ["tr_id", "target_stop_id"]


def schedule_frame(part: str) -> pd.DataFrame:
    schedule = pd.read_csv(
        ROOT / part / "schedule.csv",
        usecols=["tr_id", "tt_action_item_id", "time_begin", "time_fact_begin"],
    ).rename(columns={"tt_action_item_id": "target_stop_id"})
    if schedule.duplicated(KEY).any():
        raise ValueError(f"Duplicate vehicle/stop keys in {part} schedule")
    return schedule


def audit_points(name: str, points: pd.DataFrame, schedule: pd.DataFrame) -> None:
    joined = points.merge(schedule, on=KEY, how="left", validate="many_to_one")
    prediction_time = pd.to_datetime(joined["T"], format="mixed")
    planned = pd.to_datetime(joined["time_begin"], format="mixed")
    actual = pd.to_datetime(joined["time_fact_begin"], format="mixed")
    target_plan = pd.to_datetime(joined["target_time_begin"], format="mixed")
    counts = {
        "rows": len(joined),
        "matching_stop_with_actual": int(actual.notna().sum()),
        "matching_planned_time": int((planned == target_plan).sum()),
        "actual_arrival_after_prediction_T": int((actual > prediction_time).sum()),
    }
    if "target_delay_s" in joined:
        delay_from_schedule = (actual - planned).dt.total_seconds().to_numpy(float)
        known_label = joined["target_delay_s"].to_numpy(float)
        counts["exact_target_matches"] = int(np.isclose(delay_from_schedule, known_label).sum())
    print(name, counts)


def main() -> None:
    validate = pd.read_csv(ROOT / "validate" / "points.csv")
    labeled_test = pd.read_csv(ROOT / "labels" / "labels_test.csv")
    for part in ("train", "test"):
        schedule = schedule_frame(part)
        audit_points(f"validate vs {part}/schedule", validate, schedule)
        audit_points(f"labels_test vs {part}/schedule", labeled_test, schedule)


if __name__ == "__main__":
    main()
