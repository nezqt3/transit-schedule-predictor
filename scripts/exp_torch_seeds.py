"""Three-seed PyTorch ensemble on the existing leakage-safe features."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from exp_simple_target_mode import load_features  # noqa: E402
from src.models.ensemble import CatBoostTorchEnsemble  # noqa: E402
from src.models.torch_model import TorchTabularRegressor  # noqa: E402

SEEDS = (42, 1337, 2026)
EPOCHS = 28
TORCH_WEIGHT = 0.42


def train_models(features: pd.DataFrame, y: np.ndarray,
                 artifact_dir: Path | None = None) -> list[TorchTabularRegressor]:
    models = []
    for seed in SEEDS:
        model = TorchTabularRegressor("direct", seed=seed)
        model.fit(features, y, epochs=EPOCHS)
        if artifact_dir is not None:
            model.save(artifact_dir / f"torch_tabular_seed{seed}.pt")
        models.append(model)
    return models


def mean_prediction(models: list[TorchTabularRegressor], features: pd.DataFrame) -> np.ndarray:
    return np.mean([model.predict(features) for model in models], axis=0)


def main() -> None:
    train, train_features = load_features("train")
    test, test_features = load_features("test")
    validate, validate_features = load_features("validate")
    y = train["target_delay_s"].to_numpy(float)
    times = pd.to_datetime(train["T"], format="mixed")
    cutoff = times.sort_values().iloc[int(0.8 * len(times))]
    fit = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
    tail = (times >= cutoff).to_numpy()
    tail_models = train_models(train_features.loc[fit], y[fit])
    tail_single = tail_models[0].predict(train_features.loc[tail])
    tail_mean = mean_prediction(tail_models, train_features.loc[tail])
    tail_y = y[tail]

    artifacts = ROOT / "ml" / "artifacts"
    models = train_models(train_features, y, artifacts)
    original = TorchTabularRegressor.load(artifacts / "torch_tabular.pt")
    assert np.allclose(models[0].predict(test_features), original.predict(test_features), atol=1e-4)
    test_single = models[0].predict(test_features)
    test_mean = mean_prediction(models, test_features)
    validate_mean = mean_prediction(models, validate_features)
    baseline = CatBoostTorchEnsemble(
        str(artifacts / "catboost_processed.cbm"),
        str(artifacts / "catboost_processed_direct.cbm"),
        str(artifacts / "torch_tabular.pt"), 0,
    )
    base_test = baseline.predict(test_features)
    base_validate = baseline.predict(validate_features)
    y_test = test["target_delay_s"].to_numpy(float)
    blend_test = (1 - TORCH_WEIGHT) * base_test + TORCH_WEIGHT * test_mean
    blend_validate = (1 - TORCH_WEIGHT) * base_validate + TORCH_WEIGHT * validate_mean
    sample = pd.read_csv(ROOT / "data" / "submissions" / "sample_submission.csv",
                         sep=";", dtype={"sample_id": str})
    submission = sample[["sample_id"]].merge(
        pd.DataFrame({"sample_id": validate["sample_id"], "prediction": blend_validate}),
        on="sample_id", how="left", sort=False, validate="one_to_one",
    )
    assert submission["prediction"].notna().all() and np.isfinite(submission["prediction"]).all()
    output = ROOT / "data" / "submissions" / "torch3seed_catboost42_submission.csv"
    submission.to_csv(output, sep=";", index=False)
    report = {
        "seeds": SEEDS, "epochs": EPOCHS, "torch_weight": TORCH_WEIGHT,
        "tail_single_mae": float(np.abs(tail_single - tail_y).mean()),
        "tail_ensemble_mae": float(np.abs(tail_mean - tail_y).mean()),
        "test_single_mae": float(np.abs(test_single - y_test).mean()),
        "test_ensemble_mae": float(np.abs(test_mean - y_test).mean()),
        "test_blend_mae": float(np.abs(blend_test - y_test).mean()),
        "submission": str(output),
    }
    (ROOT / "data" / "processed" / "exp_torch_seeds.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
