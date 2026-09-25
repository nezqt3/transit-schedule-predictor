"""Protect plan features from the actual-arrival columns in schedule files."""

import pandas as pd

from src.plan_features import build_plan_features


def test_plan_features_ignore_future_actual_arrivals() -> None:
    points = pd.DataFrame([{
        "tr_id": 1, "T": "2026-01-06 12:00:00", "target_stop_id": 12,
        "target_time_begin": "2026-01-06 12:12:00",
    }])
    base = pd.DataFrame([{"last_lon": 37.0, "last_lat": 55.0,
                          "distance_to_target_m": 1000.0}])
    schedule = pd.DataFrame([
        {"tr_id": 1, "tt_action_item_id": 11, "time_begin": "2026-01-06 12:05:00",
         "geom": "POINT (37.005 55.0)", "time_fact_begin": "2026-01-06 12:09:00"},
        {"tr_id": 1, "tt_action_item_id": 12, "time_begin": "2026-01-06 12:12:00",
         "geom": "POINT (37.01 55.0)", "time_fact_begin": "2026-01-06 12:17:00"},
    ])
    with_actual = build_plan_features(points, base, schedule)
    without_actual = build_plan_features(points, base, schedule.drop(columns="time_fact_begin"))
    pd.testing.assert_frame_equal(with_actual, without_actual)
    assert with_actual.loc[0, "planned_stops_to_target"] == 2
    assert with_actual.loc[0, "next_stop_plan_s"] == 300
