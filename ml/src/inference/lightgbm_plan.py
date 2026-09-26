"""Serve the competition LightGBM using its offline feature builders."""

from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import lightgbm as lgb
import pandas as pd

from src.features_simple import build_features
from src.plan_features import build_plan_features


def _source_naive(value, source_timezone: ZoneInfo) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (timestamp.tz_convert(source_timezone).tz_localize(None)
            if timestamp.tzinfo else timestamp)


class LightGBMPlanPredictor:
    """Direct and residual LightGBM pair trained on telemetry and stop plans."""

    def __init__(self, artifacts_dir: Path, schedule_plan_path: Path,
                 source_timezone: str = "Europe/Moscow") -> None:
        metadata_path = artifacts_dir / "lightgbm_plan_metadata.json"
        residual_path = artifacts_dir / "lightgbm_plan_residual.txt"
        direct_path = artifacts_dir / "lightgbm_plan_direct.txt"
        risk_path = artifacts_dir / "risk_calibration.json"
        for path in (metadata_path, residual_path, direct_path, risk_path, schedule_plan_path):
            if not path.is_file():
                raise RuntimeError(f"LightGBM runtime input missing: {path}")
        manifest_path = artifacts_dir / "release_manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"LightGBM release manifest missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("model") != "lightgbm_plan":
            raise RuntimeError("LightGBM release manifest names a different model")
        for path in (metadata_path, residual_path, direct_path, risk_path, schedule_plan_path):
            expected = manifest["sha256"].get(path.name)
            if not expected:
                raise RuntimeError(f"LightGBM release checksum missing: {path.name}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"LightGBM runtime input checksum mismatch: {path}")
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.metadata["model_version"] = manifest["model_version"]
        self.metadata["model_artifact_sha256"] = manifest["sha256"][direct_path.name]
        self.risk_calibration = json.loads(risk_path.read_text(encoding="utf-8"))
        if self.risk_calibration["source_model_artifact_sha256"] != self.metadata["model_artifact_sha256"]:
            raise RuntimeError("risk calibrator was fitted for a different regression model")
        self.metadata["risk_model_version"] = self.risk_calibration["version"]
        self.source_timezone = ZoneInfo(source_timezone)
        self.residual = lgb.Booster(model_file=str(residual_path))
        self.direct = lgb.Booster(model_file=str(direct_path))
        self.schedule = pd.read_csv(
            schedule_plan_path,
            usecols=["tr_id", "tt_action_item_id", "time_begin", "geom"],
        )

    def predict(self, *, tr_id: int, T, cur_dev_s: float,
                target_stop_info: dict, telemetry: list[dict],
                planned_stops: list[dict] | None = None) -> float:
        """Predict delay in seconds using the saved offline feature contract."""
        target_id = int(target_stop_info["target_stop_id"])
        target_time = _source_naive(target_stop_info["target_time_begin"], self.source_timezone)
        points = pd.DataFrame([{
            "tr_id": tr_id, "T": _source_naive(T, self.source_timezone), "cur_dev_s": cur_dev_s,
            "target_stop_id": target_id, "target_time_begin": target_time,
        }])
        traffic = pd.DataFrame(telemetry)
        for column in ("event_time", "receive_time", "location_valid",
                       "lat", "lon", "speed", "heading"):
            if column not in traffic:
                traffic[column] = None
        traffic["tr_id"] = tr_id
        for column in ("event_time", "receive_time"):
            traffic[column] = traffic[column].map(
                lambda value: _source_naive(value, self.source_timezone)
                if value is not None and pd.notna(value) else pd.NaT
            )

        # Each request concerns one trip. Scanning every trip's stop plan in
        # the shared feature builders makes concurrent CPU inference collapse.
        schedule = self.schedule[self.schedule["tr_id"] == tr_id]
        if planned_stops:
            schedule = pd.DataFrame([{
                "tr_id": tr_id,
                "tt_action_item_id": int(stop["tt_action_item_id"]),
                "time_begin": _source_naive(stop["time_begin"], self.source_timezone),
                "geom": stop["geom"],
            } for stop in planned_stops])
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
        residual = float(self.residual.predict(features, num_threads=1)[0])
        direct = float(self.direct.predict(features, num_threads=1)[0])
        return (cur_dev_s + residual + direct) / 2

    def predict_risk(self, predicted_delay_s: float) -> float:
        """Calibrated probability of arriving at least 120 seconds late."""
        z = (self.risk_calibration["coefficient"] * predicted_delay_s
             + self.risk_calibration["intercept"])
        return 1 / (1 + math.exp(-max(-700, min(700, z))))
