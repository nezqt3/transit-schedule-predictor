"""Load a trained residual model and apply the shared feature contract."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from catboost import CatBoostRegressor

from src.features import extract_features_for_point


class Predictor:
    """CPU CatBoost predictor for one requested vehicle and target stop."""

    def __init__(self, model_path: Path) -> None:
        metadata_path = model_path.with_suffix(".json")
        if not model_path.is_file() or not metadata_path.is_file():
            raise RuntimeError(
                f"model artifact missing at {model_path}; run 'make train' first"
            )
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.model = CatBoostRegressor()
        try:
            self.model.load_model(str(model_path))
        except Exception as exc:
            raise RuntimeError(f"cannot load model artifact {model_path}: {exc}") from exc

    def predict(self, *, tr_id: int, T, cur_dev_s: float, target_stop_info: dict,
                telemetry: list[dict]) -> float:
        """Return cur_dev_s plus the model's predicted residual in seconds."""
        features = extract_features_for_point(
            telemetry, target_stop_info, cur_dev_s, T
        )
        row = pd.DataFrame([{"tr_id": str(tr_id), **features}])
        delta = float(self.model.predict(row[self.metadata["feature_columns"]])[0])
        return float(cur_dev_s + delta)
