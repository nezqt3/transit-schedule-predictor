"""Compare the shipped ML HTTP model with the saved offline features on test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ml"), str(ROOT / "scripts")]
os.environ["ARTIFACTS_DIR"] = str(ROOT / "ml" / "artifacts")
os.environ["SCHEDULE_PLAN_PATH"] = str(ROOT / "data" / "raw" / "validate" / "schedule_plan.csv")
os.environ["MODEL_NAME"] = "lightgbm_plan"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from exp_plan_routes import load_part  # noqa: E402
from service.main import app  # noqa: E402


def main() -> None:
    points, _, features = load_part("test")
    traffic = pd.read_csv(
        ROOT / "data" / "processed" / "test_traffic.csv",
        usecols=["tr_id", "event_time", "receive_time", "coords_valid",
                 "lon", "lat", "speed", "heading"],
    ).rename(columns={"coords_valid": "location_valid"})
    traffic["event_time"] = pd.to_datetime(traffic["event_time"])
    traffic["receive_time"] = pd.to_datetime(traffic["receive_time"])
    actual = points["target_delay_s"].to_numpy(float)
    responses = []
    expected = []
    with TestClient(app) as client:
        health = client.get("/health").json()
        predictor = app.state.predictor
        x = features[predictor.metadata["features"]].copy()
        categories = predictor.metadata["categories"]
        ids = x["tr_id"].astype(str)
        x["tr_id"] = pd.Categorical(ids.where(ids.isin(categories)), categories=categories)
        expected = (points["cur_dev_s"].to_numpy(float)
                    + predictor.residual.predict(x) + predictor.direct.predict(x)) / 2
        schedule = predictor.schedule.set_index(["tr_id", "tt_action_item_id"])
        for row in points.itertuples(index=False):
            t = pd.Timestamp(row.T)
            window = traffic[
                (traffic["tr_id"] == row.tr_id)
                & (traffic["event_time"].between(t - pd.Timedelta(minutes=30), t))
            ].drop(columns="tr_id").copy()
            for column in ("event_time", "receive_time"):
                window[column] = window[column].dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
            telemetry = window.astype(object).where(pd.notna(window), None).to_dict("records")
            geom = schedule.loc[(row.tr_id, row.target_stop_id), "geom"]
            lon, lat = map(float, geom.removeprefix("POINT (").removesuffix(")").split())
            payload = {
                "tr_id": int(row.tr_id), "T": row.T,
                "cur_dev_s": float(row.cur_dev_s),
                "target_stop_id": int(row.target_stop_id),
                "target_time_begin": row.target_time_begin,
                "stop_lat": lat, "stop_lon": lon,
                "telemetry": telemetry,
            }
            result = client.post("/predict", json=payload)
            result.raise_for_status()
            responses.append(result.json()["prediction"])
    responses = np.asarray(responses, float)
    max_delta = float(np.abs(responses - expected).max())
    mae = float(np.abs(responses - actual).mean())
    print(f"model={health['model']} version={health['model_version']}")
    print(f"rows={len(points)} max_offline_api_delta_s={max_delta:.9f} test_mae_s={mae:.9f}")
    if max_delta > 1e-6 or abs(mae - 58.603345521191955) > 0.01:
        raise SystemExit("release parity check failed")


if __name__ == "__main__":
    main()
