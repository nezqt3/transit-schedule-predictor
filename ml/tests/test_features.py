"""Critical causal feature and residual prediction checks."""

import math

import pandas as pd

from src.features import extract_features_for_point
from src.inference.predictor import Predictor


STOP = {
    "stop_lat": 55.76,
    "stop_lon": 37.62,
    "target_time_begin": "2026-01-06 02:22:00",
}
T = "2026-01-06 02:10:00"


def test_features_exclude_future_invalid_and_unreceived_points():
    points = pd.DataFrame([
        {"event_time": "2026-01-06 02:09:00", "receive_time": "2026-01-06 02:09:01",
         "location_valid": True, "lat": 55.75, "lon": 37.61, "speed": 12},
        {"event_time": "2026-01-06 02:10:01", "receive_time": "2026-01-06 02:10:01",
         "location_valid": True, "lat": 55.76, "lon": 37.62, "speed": 120},
        {"event_time": "2026-01-06 02:09:30", "receive_time": "2026-01-06 02:09:31",
         "location_valid": False, "lat": 55.76, "lon": 37.62, "speed": 90},
        {"event_time": "2026-01-06 02:09:45", "receive_time": "2026-01-06 02:10:05",
         "location_valid": True, "lat": 55.76, "lon": 37.62, "speed": 80},
    ])
    features = extract_features_for_point(points, STOP, 30, T)
    from_records = extract_features_for_point(points.to_dict("records"), STOP, 30, T)
    for name, value in features.items():
        if math.isfinite(value):
            assert math.isclose(value, from_records[name], rel_tol=1e-12)
    assert features["points_15m"] == 1
    assert features["speed_last_kmh"] == 12
    assert features["speed_mean_5m"] == 12
    assert features["time_to_target_plan_s"] == 720
    assert features["dist_to_target_m"] > 0
    assert math.isclose(features["required_speed_kmh"],
                        features["dist_to_target_m"] / 720 * 3.6)


def test_predictor_adds_residual_to_current_delay():
    class FakeModel:
        def predict(self, frame):
            assert frame.iloc[0]["cur_dev_s"] == 30
            return [12.5]

    predictor = Predictor.__new__(Predictor)
    predictor.model = FakeModel()
    predictor.metadata = {"feature_columns": ["tr_id", "cur_dev_s"]}
    result = predictor.predict(
        tr_id=123, T=T, cur_dev_s=30, target_stop_info=STOP, telemetry=[]
    )
    assert result == 42.5
