from src.inference.baseline import BaselinePredictor


def test_baseline_returns_current_deviation():
    predictor = BaselinePredictor()

    prediction = predictor.predict(
        tr_id=1,
        T="2026-01-01T10:00:00",
        cur_dev_s=143.5,
        target_stop_info={},
        telemetry=[],
    )

    assert prediction == 143.5
