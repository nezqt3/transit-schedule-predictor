"""Evaluate weighting vehicles shared with the real test/validate split.

No future schedule facts or validate labels are used. Run from the repo root:
python scripts/exp_real_vehicle_weighting.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from exp_simple_target_mode import ITERATIONS, load_features  # noqa: E402
from src.features_simple import CAT_FEATURES, FEATURE_COLUMNS  # noqa: E402

VARIANTS = {"all": 1.0, "real_x2": 2.0, "real_x4": 4.0, "real_x8": 8.0,
            "real_only": float("inf")}


def predict_variant(
    points: pd.DataFrame,
    features: pd.DataFrame,
    query_points: pd.DataFrame,
    query_features: pd.DataFrame,
    real_ids: set[int],
    real_weight: float,
) -> np.ndarray:
    is_real = points["tr_id"].isin(real_ids).to_numpy()
    if np.isinf(real_weight):
        keep = is_real
        weights = np.ones(int(keep.sum()))
    else:
        keep = np.ones(len(points), dtype=bool)
        weights = np.where(is_real, real_weight, 1.0)
    y = points.loc[keep, "target_delay_s"].to_numpy(float)
    cur = points.loc[keep, "cur_dev_s"].to_numpy(float)
    train_x = features.loc[keep, FEATURE_COLUMNS]
    query_x = query_features[FEATURE_COLUMNS]
    predictions = []
    for mode in ("residual", "direct"):
        label = y - cur if mode == "residual" else y
        model = CatBoostRegressor(
            iterations=ITERATIONS[mode], learning_rate=0.03, depth=6,
            loss_function="MAE", random_seed=42, task_type="CPU",
            allow_writing_files=False, verbose=False,
        )
        model.fit(Pool(train_x, label, weight=weights, cat_features=CAT_FEATURES))
        pred = np.asarray(model.predict(query_x), dtype=float)
        if mode == "residual":
            pred += query_points["cur_dev_s"].to_numpy(float)
        predictions.append(pred)
    return (predictions[0] + predictions[1]) / 2


def main() -> None:
    train, train_features = load_features("train")
    test, test_features = load_features("test")
    real_ids = set(test["tr_id"])
    times = pd.to_datetime(train["T"], format="mixed")
    results: dict[str, dict] = {name: {"folds": []} for name in VARIANTS}
    for start_fraction in (0.35, 0.50, 0.65, 0.80):
        cutoff = times.sort_values().iloc[int(start_fraction * len(times))]
        end = (times.sort_values().iloc[int((start_fraction + 0.15) * len(times))]
               if start_fraction < 0.80 else times.max() + pd.Timedelta(seconds=1))
        fit = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
        valid = ((times >= cutoff) & (times < end)
                 & train["tr_id"].isin(real_ids)).to_numpy()
        print(f"fold {cutoff} fit={fit.sum()} real_valid={valid.sum()}", flush=True)
        for name, weight in VARIANTS.items():
            pred = predict_variant(
                train.loc[fit], train_features.loc[fit],
                train.loc[valid], train_features.loc[valid], real_ids, weight,
            )
            error = np.abs(pred - train.loc[valid, "target_delay_s"].to_numpy(float))
            results[name]["folds"].append({"n": len(error), "mae": float(error.mean())})
            print(f"  {name}: {error.mean():.2f}", flush=True)

    for name, result in results.items():
        folds = result["folds"]
        result["cv_mae_real_vehicles"] = float(
            sum(fold["n"] * fold["mae"] for fold in folds) / sum(fold["n"] for fold in folds)
        )
    selected = min(results, key=lambda name: results[name]["cv_mae_real_vehicles"])
    test_y = test["target_delay_s"].to_numpy(float)
    for name in ("all", selected):
        pred = predict_variant(train, train_features, test, test_features, real_ids, VARIANTS[name])
        results[name]["test_mae"] = float(np.abs(pred - test_y).mean())
    report = {"selected_by_cv": selected, "real_vehicle_train_rows": int(train.tr_id.isin(real_ids).sum()),
              "results": results}
    output = ROOT / "data" / "processed" / "exp_real_vehicle_weighting.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
