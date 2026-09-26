"""Calibrate P(delay >= 120s) from chronological out-of-fold forecasts."""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ml"), str(ROOT / "scripts")]

from exp_lightgbm_plan import predict_pair, train_pair  # noqa: E402
from exp_plan_routes import load_part  # noqa: E402


def bins(probabilities: np.ndarray, outcomes: np.ndarray) -> list[dict]:
    result = []
    for low, high in zip(np.linspace(0, 1, 6)[:-1], np.linspace(0, 1, 6)[1:]):
        mask = (probabilities >= low) & (probabilities < high if high < 1 else probabilities <= high)
        if mask.any():
            result.append({
                "range": [round(float(low), 2), round(float(high), 2)],
                "n": int(mask.sum()),
                "mean_probability": float(probabilities[mask].mean()),
                "observed_fraction": float(outcomes[mask].mean()),
            })
    return result


def main() -> None:
    train, _, train_features = load_part("train")
    test, _, test_features = load_part("test")
    times = pd.to_datetime(train["T"], format="mixed")
    predictions = np.full(len(train), np.nan)
    for fraction in (0.35, 0.50, 0.65, 0.80):
        ordered = times.sort_values()
        cutoff = ordered.iloc[int(fraction * len(times))]
        end = (ordered.iloc[int((fraction + 0.15) * len(times))]
               if fraction < 0.80 else times.max() + pd.Timedelta(seconds=1))
        fit = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
        valid = ((times >= cutoff) & (times < end)).to_numpy()
        models, categories = train_pair(train.loc[fit], train_features.loc[fit])
        predictions[valid] = predict_pair(
            models, categories, train.loc[valid], train_features.loc[valid],
        )
    mask = np.isfinite(predictions)
    y = (train.loc[mask, "target_delay_s"].to_numpy(float) >= 120).astype(int)
    calibrator = LogisticRegression(max_iter=1000)
    calibrator.fit(predictions[mask].reshape(-1, 1), y)
    train_p = calibrator.predict_proba(predictions[mask].reshape(-1, 1))[:, 1]

    artifacts = ROOT / "ml" / "artifacts"
    metadata = json.loads((artifacts / "lightgbm_plan_metadata.json").read_text(encoding="utf-8"))
    manifest = json.loads((artifacts / "release_manifest.json").read_text(encoding="utf-8"))
    residual = lgb.Booster(model_file=str(artifacts / "lightgbm_plan_residual.txt"))
    direct = lgb.Booster(model_file=str(artifacts / "lightgbm_plan_direct.txt"))
    x = test_features[metadata["features"]].copy()
    categories = metadata["categories"]
    ids = x["tr_id"].astype(str)
    x["tr_id"] = pd.Categorical(ids.where(ids.isin(categories)), categories=categories)
    test_delay = (test["cur_dev_s"].to_numpy(float)
                  + residual.predict(x) + direct.predict(x)) / 2
    test_y = (test["target_delay_s"].to_numpy(float) >= 120).astype(int)
    test_p = calibrator.predict_proba(test_delay.reshape(-1, 1))[:, 1]
    report = {
        "event": "target_delay_s >= 120",
        "version": "risk-late-120-2026-09-27",
        "source_model_version": manifest["model_version"],
        "source_model_artifact_sha256": hashlib.sha256(
            (artifacts / "lightgbm_plan_direct.txt").read_bytes()
        ).hexdigest(),
        "coefficient": float(calibrator.coef_[0, 0]),
        "intercept": float(calibrator.intercept_[0]),
        "train_oof_rows": int(mask.sum()),
        "train_oof_brier": float(brier_score_loss(y, train_p)),
        "test_rows": len(test),
        "test_brier": float(brier_score_loss(test_y, test_p)),
        "test_constant_prevalence_brier": float(brier_score_loss(
            test_y, np.full(len(test_y), y.mean())
        )),
        "test_bins": bins(test_p, test_y),
    }
    output = artifacts / "risk_calibration.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
