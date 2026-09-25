"""Serve the competition LightGBM using its offline feature builders."""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from src.features_simple import build_features
from src.plan_features import build_plan_features


def _utc_naive(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_convert("UTC").tz_localize(None) if timestamp.tzinfo else timestamp


class LightGBMPlanPredictor:
    """Direct and residual LightGBM pair trained on telemetry and stop plans."""

    def __init__(self, artifacts_dir: Path, schedule_plan_path: Path) -> None:
        metadata_path = artifacts_dir / "lightgbm_plan_metadata.json"
        residual_path = artifacts_dir / "lightgbm_plan_residual.txt"
        direct_path = artifacts_dir / "lightgbm_plan_direct.txt"
        for path in (metadata_path, residual_path, direct_path, schedule_plan_path):
            if not path.is_file():
                raise RuntimeError(f"LightGBM runtime input missing: {path}")
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.metadata.setdefault("model_version", "lightgbm-plan-1.0")
        self.residual = lgb.Booster(model_file=str(residual_path))
        self.direct = lgb.Booster(model_file=str(direct_path))
        self.schedule = pd.read_csv(
            schedule_plan_path,
            usecols=["tr_id", "tt_action_item_id", "time_begin", "geom"],
        )

    def predict(self, *, tr_id: int, T, cur_dev_s: float,
                target_stop_info: dict, telemetry: list[dict]) -> float:
        """Predict delay in seconds using the saved offline feature contract."""
        target_id = int(target_stop_info["target_stop_id"])
        target_time = _utc_naive(target_stop_info["target_time_begin"])
        points = pd.DataFrame([{
            "tr_id": tr_id, "T": _utc_naive(T), "cur_dev_s": cur_dev_s,
            "target_stop_id": target_id, "target_time_begin": target_time,
        }])
        traffic = pd.DataFrame(telemetry)
        for column in ("event_time", "receive_time", "location_valid",
                       "lat", "lon", "speed", "heading"):
            if column not in traffic:
                traffic[column] = None
        traffic["tr_id"] = tr_id
        for column in ("event_time", "receive_time"):
            traffic[column] = pd.to_datetime(traffic[column], utc=True).dt.tz_localize(None)

        schedule = self.schedule
        stop_exists = ((schedule["tr_id"] == tr_id)
                       & (schedule["tt_action_item_id"] == target_id)).any()
        if not stop_exists:
            target = pd.DataFrame([{
                "tr_id": tr_id, "tt_action_item_id": target_id,
                "time_begin": target_time,
                "geom": f"POINT ({target_stop_info['stop_lon']} {target_stop_info['stop_lat']})",
            }])
            schedule = pd.concat([schedule, target], ignore_index=True)

        base = build_features(points, traffic, schedule)
        planned = build_plan_features(points, base, schedule)
        features = pd.concat([base, planned], axis=1)[self.metadata["features"]]
        categories = self.metadata["categories"]
        ids = features["tr_id"].astype(str)
        features["tr_id"] = pd.Categorical(
            ids.where(ids.isin(categories)), categories=categories,
        )
        residual = float(self.residual.predict(features)[0])
        direct = float(self.direct.predict(features)[0])
        return (cur_dev_s + residual + direct) / 2
