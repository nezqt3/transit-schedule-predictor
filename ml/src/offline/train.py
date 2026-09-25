"""Train the CatBoost residual model with a chronological early-stop split."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.metrics import mean_absolute_error

from src.features import POINT_FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[3]
FEATURES = ["tr_id", *POINT_FEATURE_COLUMNS]
MODEL_PATH = ROOT / "ml" / "artifacts" / "catboost_residual_mae.cbm"


def hackathon_score(mae: float, targets: np.ndarray, mae_target: float | None) -> float | None:
    """Return the organizer's normalized score when MAE_TARGET is configured."""
    if mae_target is None:
        return None
    mae_zero = float(np.abs(targets).mean())
    if not 0 <= mae_target < mae_zero:
        raise ValueError("MAE_TARGET must be nonnegative and below zero-predictor MAE")
    return float(np.clip((mae_zero - mae) / (mae_zero - mae_target), 0, 1))


def train(train_frame: pd.DataFrame, test_frame: pd.DataFrame,
          model_path: Path = MODEL_PATH, mae_target: float | None = None) -> dict:
    """Fit on train only; use test labels solely for final local comparison."""
    for name, frame in (("train", train_frame), ("test", test_frame)):
        missing = set(FEATURES + ["T", "target_delay_s"]) - set(frame.columns)
        if missing:
            raise ValueError(f"{name} features missing: {sorted(missing)}")
    ordered = train_frame.sort_values("T", kind="stable").reset_index(drop=True)
    cutoff = int(len(ordered) * 0.85)
    if cutoff < 2 or cutoff >= len(ordered):
        raise ValueError("at least 4 training samples required")

    def target(frame: pd.DataFrame) -> np.ndarray:
        return (frame["target_delay_s"] - frame["cur_dev_s"]).to_numpy(float)

    params = dict(
        loss_function="MAE", eval_metric="MAE", iterations=2000,
        learning_rate=0.03, random_seed=42, verbose=False,
        allow_writing_files=False, thread_count=-1,
    )
    cutoff_time = ordered.loc[cutoff, "T"]
    train_part = ordered[ordered["T"] < cutoff_time]
    early_stop_part = ordered[ordered["T"] >= cutoff_time]
    if len(train_part) < 2 or early_stop_part.empty:
        raise ValueError("not enough distinct training timestamps for a time split")
    selector = CatBoostRegressor(**params, early_stopping_rounds=100)
    selector.fit(
        train_part[FEATURES], target(train_part),
        cat_features=["tr_id"],
        eval_set=(early_stop_part[FEATURES], target(early_stop_part)),
        verbose=False,
    )
    best_iterations = max(1, selector.best_iteration_ + 1)
    model = CatBoostRegressor(**{**params, "iterations": best_iterations})
    model.fit(ordered[FEATURES], target(ordered), cat_features=["tr_id"], verbose=False)

    truth = test_frame["target_delay_s"].to_numpy(float)
    baseline = test_frame["cur_dev_s"].to_numpy(float)
    predicted = baseline + model.predict(test_frame[FEATURES])
    mae_baseline = float(mean_absolute_error(truth, baseline))
    mae_model = float(mean_absolute_error(truth, predicted))
    mae_zero = float(mean_absolute_error(truth, np.zeros_like(truth)))
    importance = sorted(
        zip(FEATURES, model.get_feature_importance(), strict=True),
        key=lambda pair: pair[1], reverse=True,
    )
    metrics = {
        "target": "delta_target = target_delay_s - cur_dev_s",
        "model": "catboost_residual_mae",
        "model_version": "1.0",
        "feature_columns": FEATURES,
        "best_iterations": best_iterations,
        "n_train": len(train_frame),
        "n_test": len(test_frame),
        "mae_baseline_cur_dev_s": mae_baseline,
        "mae_model": mae_model,
        "mae_zero": mae_zero,
        "mae_target": mae_target,
        "hackathon_score": hackathon_score(mae_model, truth, mae_target),
        "top_10_features": [{"name": name, "importance": float(value)}
                            for name, value in importance[:10]],
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(model_path))
    model_path.with_suffix(".json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mae-target", type=float, default=None,
                        help="Organizer MAE_TARGET in seconds; omit if not published")
    args = parser.parse_args()
    mae_target = args.mae_target
    if mae_target is None and os.getenv("MAE_TARGET"):
        mae_target = float(os.environ["MAE_TARGET"])
    processed = ROOT / "data" / "processed"
    train_frame = pd.read_parquet(processed / "train_features.parquet")
    test_frame = pd.read_parquet(processed / "test_features.parquet")
    print(json.dumps(train(train_frame, test_frame, mae_target=mae_target),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
