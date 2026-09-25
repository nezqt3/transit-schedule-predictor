"""CatBoost variants with future *planned* stops, excluding actual arrivals."""

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
from src.models.ensemble import CatBoostTorchEnsemble  # noqa: E402
from src.plan_features import PLAN_FEATURE_COLUMNS, build_plan_features  # noqa: E402
from src.models.torch_model import TorchTabularRegressor  # noqa: E402

DATA = ROOT / "data" / "processed"
ALL_FEATURES = FEATURE_COLUMNS + PLAN_FEATURE_COLUMNS


def load_part(part: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    points, base = load_features(part)
    schedule_name = "validate_schedule_plan.csv" if part == "validate" else f"{part}_schedule.csv"
    schedule = pd.read_csv(
        DATA / schedule_name,
        usecols=["tr_id", "tt_action_item_id", "time_begin", "geom"],
    )
    added = build_plan_features(points, base, schedule)
    enriched = pd.concat([base.reset_index(drop=True), added], axis=1)
    return points, base, enriched


def train_pair(points: pd.DataFrame, features: pd.DataFrame) -> tuple[CatBoostRegressor, CatBoostRegressor]:
    models = []
    y = points["target_delay_s"].to_numpy(float)
    cur = points["cur_dev_s"].to_numpy(float)
    for mode in ("residual", "direct"):
        label = y - cur if mode == "residual" else y
        model = CatBoostRegressor(
            iterations=ITERATIONS[mode], learning_rate=0.03, depth=6,
            loss_function="MAE", random_seed=42, task_type="CPU",
            allow_writing_files=False, verbose=False,
        )
        model.fit(Pool(features[ALL_FEATURES], label, cat_features=CAT_FEATURES))
        models.append(model)
    return models[0], models[1]


def predict_pair(models: tuple[CatBoostRegressor, CatBoostRegressor],
                 points: pd.DataFrame, features: pd.DataFrame) -> np.ndarray:
    residual, direct = models
    x = features[ALL_FEATURES]
    return (points["cur_dev_s"].to_numpy(float)
            + np.asarray(residual.predict(x), float)
            + np.asarray(direct.predict(x), float)) / 2


def ordered_submission(points: pd.DataFrame, prediction: np.ndarray, filename: str) -> Path:
    sample = pd.read_csv(ROOT / "data" / "submissions" / "sample_submission.csv",
                         sep=";", dtype={"sample_id": str})
    submission = sample[["sample_id"]].merge(
        pd.DataFrame({"sample_id": points["sample_id"], "prediction": prediction}),
        on="sample_id", how="left", sort=False, validate="one_to_one",
    )
    assert submission["prediction"].notna().all() and np.isfinite(submission["prediction"]).all()
    output = ROOT / "data" / "submissions" / filename
    submission.to_csv(output, sep=";", index=False)
    return output


def main() -> None:
    train, _, train_features = load_part("train")
    test, test_base, test_features = load_part("test")
    times = pd.to_datetime(train["T"], format="mixed")
    fold_metrics = []
    for fraction in (0.35, 0.50, 0.65, 0.80):
        cutoff = times.sort_values().iloc[int(fraction * len(times))]
        end = (times.sort_values().iloc[int((fraction + 0.15) * len(times))]
               if fraction < 0.80 else times.max() + pd.Timedelta(seconds=1))
        fit = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
        valid = ((times >= cutoff) & (times < end)).to_numpy()
        models = train_pair(train.loc[fit], train_features.loc[fit])
        pred = predict_pair(models, train.loc[valid], train_features.loc[valid])
        error = np.abs(pred - train.loc[valid, "target_delay_s"].to_numpy(float))
        fold_metrics.append({"n": int(valid.sum()), "mae": float(error.mean())})
        print(f"fold {cutoff} n={valid.sum()} MAE={error.mean():.2f}", flush=True)

    models = train_pair(train, train_features)
    plan_test = predict_pair(models, test, test_features)
    y = test["target_delay_s"].to_numpy(float)
    artifacts = ROOT / "ml" / "artifacts"
    models[0].save_model(str(artifacts / "catboost_plan_residual.cbm"))
    models[1].save_model(str(artifacts / "catboost_plan_direct.cbm"))
    (artifacts / "catboost_plan_metadata.json").write_text(json.dumps({
        "features": ALL_FEATURES, "schedule_columns": ["tr_id", "tt_action_item_id", "time_begin", "geom"],
        "train_rows": len(train), "iterations": ITERATIONS,
    }, indent=2), encoding="utf-8")

    validate, validate_base, validate_features = load_part("validate")
    plan_validate = predict_pair(models, validate, validate_features)
    baseline = CatBoostTorchEnsemble(
        str(artifacts / "catboost_processed.cbm"),
        str(artifacts / "catboost_processed_direct.cbm"),
        str(artifacts / "torch_tabular.pt"), 0,
    )
    baseline_test = baseline.predict(test_base)
    baseline_validate = baseline.predict(validate_base)
    torch_model = TorchTabularRegressor.load(artifacts / "torch_tabular.pt")
    torch_test = torch_model.predict(test_base)
    torch_validate = torch_model.predict(validate_base)
    candidates = {
        "plan_full": (plan_test, plan_validate),
        "plan_half": ((plan_test + baseline_test) / 2,
                      (plan_validate + baseline_validate) / 2),
    }
    outputs = {}
    for name, (test_cb, validate_cb) in candidates.items():
        test_prediction = 0.58 * test_cb + 0.42 * torch_test
        validate_prediction = 0.58 * validate_cb + 0.42 * torch_validate
        output = ordered_submission(validate, validate_prediction,
                                    f"{name}_torch42_submission.csv")
        outputs[name] = {"test_mae": float(np.abs(test_prediction - y).mean()), "file": str(output)}
    report = {
        "folds": fold_metrics,
        "plan_cv_mae": sum(x["n"] * x["mae"] for x in fold_metrics) / sum(x["n"] for x in fold_metrics),
        "plan_cb_test_mae": float(np.abs(plan_test - y).mean()),
        "baseline_cb_test_mae": float(np.abs(baseline_test - y).mean()),
        "candidates": outputs,
    }
    (DATA / "exp_plan_routes.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
