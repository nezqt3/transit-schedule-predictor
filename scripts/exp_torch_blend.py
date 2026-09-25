"""Leakage-safe PyTorch tabular experiment and CatBoost/PyTorch blend.

Run: python scripts/exp_torch_blend.py
Weights and PyTorch target mode are selected on chronological folds only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from exp_simple_target_mode import fit_model, load_features  # noqa: E402
from src.models.ensemble import CatBoostTorchEnsemble, blend_predictions  # noqa: E402
from src.models.torch_model import TorchTabularRegressor  # noqa: E402

MODES = ("direct", "residual")
WEIGHTS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40)


def mae(actual: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - prediction)))


def fit_torch_for_fold(
    mode: str, points: pd.DataFrame, features: pd.DataFrame, times: pd.Series,
) -> tuple[TorchTabularRegressor, int]:
    """Select epochs inside the training period, then refit on all of it."""
    cutoff = times.sort_values().iloc[int(0.8 * len(times))]
    inner_train = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
    inner_valid = (times >= cutoff).to_numpy()
    selector = TorchTabularRegressor(mode)
    result = selector.fit(
        features.loc[inner_train], points.loc[inner_train, "target_delay_s"].to_numpy(float),
        valid_features=features.loc[inner_valid],
        valid_y=points.loc[inner_valid, "target_delay_s"].to_numpy(float),
        epochs=120,
    )
    epochs = int(result["best_epoch"])
    model = TorchTabularRegressor(mode)
    model.fit(features, points["target_delay_s"].to_numpy(float), epochs=epochs)
    return model, epochs


def export_submission(weight: float, filename: str) -> Path:
    """Export aligned CatBoost/PyTorch predictions using saved model weights."""
    if not 0 < weight <= 1:
        raise ValueError("Torch weight must be in (0, 1]")
    validate, validate_features = load_features("validate")
    artifacts = ROOT / "ml" / "artifacts"
    model = CatBoostTorchEnsemble(
        str(artifacts / "catboost_processed.cbm"),
        str(artifacts / "catboost_processed_direct.cbm"),
        str(artifacts / "torch_tabular.pt"), weight,
    )
    prediction = model.predict(validate_features)
    sample = pd.read_csv(ROOT / "data" / "submissions" / "sample_submission.csv",
                         sep=";", dtype={"sample_id": str})
    submission = sample[["sample_id"]].merge(
        pd.DataFrame({"sample_id": validate["sample_id"], "prediction": prediction}),
        on="sample_id", how="left", sort=False, validate="one_to_one",
    )
    assert submission["prediction"].notna().all()
    output = ROOT / "data" / "submissions" / filename
    submission.to_csv(output, sep=";", index=False)
    print(f"submission {output} rows={len(submission)}")
    return output


def main() -> None:
    train, train_features = load_features("train")
    test, test_features = load_features("test")
    times = pd.to_datetime(train["T"], format="mixed")
    train_y = train["target_delay_s"].to_numpy(float)
    oof: dict[str, list[np.ndarray]] = {"y": [], "catboost": [], **{mode: [] for mode in MODES}}
    fold_details = []
    epoch_choices: dict[str, list[int]] = {mode: [] for mode in MODES}
    for start_fraction in (0.35, 0.50, 0.65, 0.80):
        cutoff = times.sort_values().iloc[int(start_fraction * len(times))]
        end = (times.sort_values().iloc[int((start_fraction + 0.15) * len(times))]
               if start_fraction < 0.80 else times.max() + pd.Timedelta(seconds=1))
        fit = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
        valid = ((times >= cutoff) & (times < end)).to_numpy()
        fit_points, fit_features = train.loc[fit], train_features.loc[fit]
        valid_features = train_features.loc[valid]
        y = train_y[valid]
        residual_cb = fit_model("residual", fit_points, fit_features)
        direct_cb = fit_model("direct", fit_points, fit_features)
        cb_pred = blend_predictions([
            train.loc[valid, "cur_dev_s"].to_numpy(float) + residual_cb.predict(valid_features),
            direct_cb.predict(valid_features),
        ], [0.5, 0.5])
        oof["y"].append(y)
        oof["catboost"].append(cb_pred)
        detail = {"cutoff": str(cutoff), "rows": int(valid.sum()), "catboost_mae": mae(y, cb_pred)}
        for mode in MODES:
            model, epochs = fit_torch_for_fold(mode, fit_points, fit_features, times.loc[fit])
            pred = model.predict(valid_features)
            oof[mode].append(pred)
            epoch_choices[mode].append(epochs)
            detail[f"torch_{mode}_mae"] = mae(y, pred)
            detail[f"torch_{mode}_epochs"] = epochs
        fold_details.append(detail)
        print(json.dumps(detail), flush=True)

    arrays = {name: np.concatenate(parts) for name, parts in oof.items()}
    baseline_cv = mae(arrays["y"], arrays["catboost"])
    options = []
    weight_curves = {}
    for mode in MODES:
        weight_curves[mode] = {}
        for weight in WEIGHTS:
            pred = blend_predictions(
                [arrays["catboost"], arrays[mode]], [1 - weight, weight]
            )
            score = mae(arrays["y"], pred)
            weight_curves[mode][str(weight)] = score
            options.append((score, mode, weight))
    cv_mae, best_mode, best_weight = min(options)
    print(f"selected {best_mode=} {best_weight=} {baseline_cv=:.2f} {cv_mae=:.2f}", flush=True)

    test_y = test["target_delay_s"].to_numpy(float)
    cb_test = blend_predictions([
        test["cur_dev_s"].to_numpy(float)
        + fit_model("residual", train, train_features).predict(test_features),
        fit_model("direct", train, train_features).predict(test_features),
    ], [0.5, 0.5])
    epochs = int(np.median(epoch_choices[best_mode]))
    torch_model = TorchTabularRegressor(best_mode)
    torch_model.fit(train_features, train_y, epochs=epochs)
    torch_test = torch_model.predict(test_features)
    blend_test = blend_predictions([cb_test, torch_test], [1 - best_weight, best_weight])
    results = {
        "folds": fold_details, "catboost_cv_mae": baseline_cv,
        "torch_direct_cv_mae": mae(arrays["y"], arrays["direct"]),
        "torch_residual_cv_mae": mae(arrays["y"], arrays["residual"]),
        "selected_mode": best_mode, "torch_weight": best_weight,
        "selected_cv_mae": cv_mae, "weight_curves_cv": weight_curves,
        "catboost_test_mae": mae(test_y, cb_test),
        "torch_test_mae": mae(test_y, torch_test),
        "blend_test_mae": mae(test_y, blend_test), "final_epochs": epochs,
    }
    processed = ROOT / "data" / "processed" / "exp_torch_blend.json"
    processed.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False), flush=True)

    artifacts = ROOT / "ml" / "artifacts"
    torch_path = artifacts / "torch_tabular.pt"
    torch_model.save(torch_path)
    loaded = TorchTabularRegressor.load(torch_path)
    assert np.allclose(loaded.predict(test_features), torch_test, atol=1e-4)
    (artifacts / "torch_tabular_metadata.json").write_text(json.dumps({
        "model": "torch_tabular", "data_source": "processed", "target_mode": best_mode,
        "epochs": epochs, "train_rows": len(train), "catboost_cv_mae": baseline_cv,
        "torch_weight_by_cv": best_weight, "blend_cv_mae": cv_mae,
        "catboost_test_mae": results["catboost_test_mae"],
        "blend_test_mae": results["blend_test_mae"],
    }, indent=2), encoding="utf-8")

    if best_weight == 0 or results["blend_test_mae"] >= results["catboost_test_mae"]:
        print("PyTorch did not clear both validation gates; no new submission generated.")
        return
    export_submission(best_weight, "catboost_torch_blend_submission.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-experimental-weight", type=float)
    args = parser.parse_args()
    if args.export_experimental_weight is None:
        main()
    else:
        weight = args.export_experimental_weight
        label = f"{weight:.0%}".replace("%", "pct")
        filename = ("torch_tabular_100pct_submission.csv" if weight == 1
                    else f"catboost_torch_{label}_experimental_submission.csv")
        export_submission(weight, filename)
