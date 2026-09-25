"""Independent LightGBM model on telemetry and published stop-plan features."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from exp_plan_routes import ALL_FEATURES, load_part, ordered_submission  # noqa: E402
from src.models.torch_model import TorchTabularRegressor  # noqa: E402


def model_input(features: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    x = features[ALL_FEATURES].copy()
    ids = x["tr_id"].astype(str)
    x["tr_id"] = pd.Categorical(ids.where(ids.isin(categories), np.nan), categories=categories)
    return x


def train_pair(points: pd.DataFrame, features: pd.DataFrame) -> tuple[list[lgb.LGBMRegressor], list[str]]:
    categories = sorted(features["tr_id"].astype(str).unique())
    x = model_input(features, categories)
    y = points["target_delay_s"].to_numpy(float)
    cur = points["cur_dev_s"].to_numpy(float)
    models = []
    for mode in ("residual", "direct"):
        model = lgb.LGBMRegressor(
            objective="regression_l1", n_estimators=320, learning_rate=0.04,
            num_leaves=15, min_child_samples=35, colsample_bytree=0.9,
            reg_lambda=3.0, random_state=42, n_jobs=4, verbosity=-1,
        )
        model.fit(x, y - cur if mode == "residual" else y,
                  categorical_feature=["tr_id"])
        models.append(model)
    return models, categories


def predict_pair(models: list[lgb.LGBMRegressor], categories: list[str],
                 points: pd.DataFrame, features: pd.DataFrame) -> np.ndarray:
    x = model_input(features, categories)
    return (points["cur_dev_s"].to_numpy(float) + models[0].predict(x)
            + models[1].predict(x)) / 2


def main() -> None:
    train, _, train_features = load_part("train")
    test, test_base, test_features = load_part("test")
    validate, validate_base, validate_features = load_part("validate")
    times = pd.to_datetime(train["T"], format="mixed")
    folds = []
    for fraction in (0.35, 0.50, 0.65, 0.80):
        cutoff = times.sort_values().iloc[int(fraction * len(times))]
        end = (times.sort_values().iloc[int((fraction + 0.15) * len(times))]
               if fraction < 0.80 else times.max() + pd.Timedelta(seconds=1))
        fit = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
        valid = ((times >= cutoff) & (times < end)).to_numpy()
        models, categories = train_pair(train.loc[fit], train_features.loc[fit])
        prediction = predict_pair(models, categories, train.loc[valid], train_features.loc[valid])
        error = np.abs(prediction - train.loc[valid, "target_delay_s"].to_numpy(float))
        folds.append({"n": int(valid.sum()), "mae": float(error.mean())})
        print(f"fold {cutoff} n={valid.sum()} MAE={error.mean():.2f}", flush=True)

    models, categories = train_pair(train, train_features)
    test_pred = predict_pair(models, categories, test, test_features)
    validate_pred = predict_pair(models, categories, validate, validate_features)
    artifacts = ROOT / "ml" / "artifacts"
    models[0].booster_.save_model(str(artifacts / "lightgbm_plan_residual.txt"))
    models[1].booster_.save_model(str(artifacts / "lightgbm_plan_direct.txt"))
    (artifacts / "lightgbm_plan_metadata.json").write_text(json.dumps({
        "features": ALL_FEATURES, "categories": categories, "train_rows": len(train),
    }, indent=2), encoding="utf-8")
    torch = TorchTabularRegressor.load(artifacts / "torch_tabular.pt")
    test_blend = 0.58 * test_pred + 0.42 * torch.predict(test_base)
    validate_blend = 0.58 * validate_pred + 0.42 * torch.predict(validate_base)
    pure_output = ordered_submission(validate, validate_pred,
                                     "lightgbm_plan_submission.csv")
    output = ordered_submission(validate, validate_blend,
                                "lightgbm_plan_torch42_submission.csv")
    report = {
        "folds": folds,
        "cv_mae": sum(x["n"] * x["mae"] for x in folds) / sum(x["n"] for x in folds),
        "test_mae": float(np.abs(test_pred - test["target_delay_s"].to_numpy(float)).mean()),
        "test_blend_mae": float(np.abs(test_blend - test["target_delay_s"].to_numpy(float)).mean()),
        "pure_submission": str(pure_output),
        "submission": str(output),
    }
    (ROOT / "data" / "processed" / "exp_lightgbm_plan.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
