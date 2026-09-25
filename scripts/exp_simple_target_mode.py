"""Compare direct and residual CatBoost targets on chronological folds.

Run from the repository root: python scripts/exp_simple_target_mode.py
This experiment uses the processed data and the features of the 0.80301 submission.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
from src.features_simple import CAT_FEATURES, FEATURE_COLUMNS, build_features  # noqa: E402

DATA = ROOT / "data" / "processed"
ITERATIONS = {"residual": 115, "direct": 187}


def load_features(part: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    points_path = DATA / ("validate_points.csv" if part == "validate" else f"labels_{part}.csv")
    traffic_part = "test" if part == "validate" else part
    schedule_path = ("validate_schedule_plan.csv" if part == "validate"
                     else f"{part}_schedule.csv")
    points = pd.read_csv(points_path, dtype={"sample_id": str})
    traffic = pd.read_csv(
        DATA / f"{traffic_part}_traffic.csv",
        usecols=[
            "tr_id", "event_time", "receive_time", "coords_valid", "lon", "lat", "speed", "heading"
        ],
    ).rename(columns={"coords_valid": "location_valid"})
    schedule = pd.read_csv(
        DATA / schedule_path, usecols=["tt_action_item_id", "tr_id", "geom"]
    )
    features = build_features(points, traffic, schedule)
    return points, features


def fit_model(
    mode: str,
    train_points: pd.DataFrame,
    train_features: pd.DataFrame,
) -> CatBoostRegressor:
    label = train_points["target_delay_s"].to_numpy(float).copy()
    if mode == "residual":
        label -= train_points["cur_dev_s"].to_numpy(float)
    model = CatBoostRegressor(
        iterations=ITERATIONS[mode], learning_rate=0.03, depth=6,
        loss_function="MAE", random_seed=42, task_type="CPU",
        allow_writing_files=False, verbose=False,
    )
    model.fit(Pool(train_features[FEATURE_COLUMNS], label, cat_features=CAT_FEATURES))
    return model


def fit_predict(
    mode: str,
    train_points: pd.DataFrame,
    train_features: pd.DataFrame,
    predict_features: pd.DataFrame,
) -> np.ndarray:
    model = fit_model(mode, train_points, train_features)
    return np.asarray(model.predict(predict_features[FEATURE_COLUMNS]), dtype=float)


def main(write_candidate: bool = False) -> None:
    train, train_features = load_features("train")
    test, test_features = load_features("test")
    times = pd.to_datetime(train["T"], format="mixed")
    y = train["target_delay_s"].to_numpy(float)
    cur = train["cur_dev_s"].to_numpy(float)

    print("fold cutoff fit val baseline residual blend_50 direct")
    for start_fraction in (0.35, 0.50, 0.65, 0.80):
        cutoff = times.sort_values().iloc[int(start_fraction * len(times))]
        end = (times.sort_values().iloc[int((start_fraction + 0.15) * len(times))]
               if start_fraction < 0.80 else times.max() + pd.Timedelta(seconds=1))
        fit = (times < cutoff - pd.Timedelta(minutes=15)).to_numpy()
        valid = ((times >= cutoff) & (times < end)).to_numpy()
        prediction = {}
        for mode in ITERATIONS:
            raw = fit_predict(mode, train.loc[fit], train_features.loc[fit], train_features.loc[valid])
            prediction[mode] = raw + cur[valid] if mode == "residual" else raw
        mae = {mode: np.abs(pred - y[valid]).mean() for mode, pred in prediction.items()}
        blend_mae = np.abs(
            (prediction["residual"] + prediction["direct"]) / 2 - y[valid]
        ).mean()
        baseline = np.abs(cur[valid] - y[valid]).mean()
        print(f"{start_fraction:.2f} {cutoff} {fit.sum()} {valid.sum()} "
              f"{baseline:.2f} {mae['residual']:.2f} {blend_mae:.2f} {mae['direct']:.2f}")

    test_y = test["target_delay_s"].to_numpy(float)
    test_cur = test["cur_dev_s"].to_numpy(float)
    test_prediction = {}
    for mode in ITERATIONS:
        raw = fit_predict(mode, train, train_features, test_features)
        pred = raw + test_cur if mode == "residual" else raw
        test_prediction[mode] = pred
        print(f"test {mode} {np.abs(pred - test_y).mean():.2f}")
    blend = (test_prediction["residual"] + test_prediction["direct"]) / 2
    print(f"test blend_50 {np.abs(blend - test_y).mean():.2f}")

    if write_candidate:
        validate, validate_features = load_features("validate")
        model = fit_model("direct", train, train_features)
        prediction = np.asarray(model.predict(validate_features[FEATURE_COLUMNS]), dtype=float)
        assert np.isfinite(prediction).all()
        submission = pd.DataFrame({"sample_id": validate["sample_id"], "prediction": prediction})
        sample = pd.read_csv(ROOT / "data" / "submissions" / "sample_submission.csv", sep=";")
        submission = sample[["sample_id"]].astype({"sample_id": str}).merge(
            submission, on="sample_id", how="left", sort=False, validate="one_to_one"
        )
        assert len(submission) == len(sample) and submission["prediction"].notna().all()
        artifacts = ROOT / "ml" / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        model_path = artifacts / "catboost_processed_direct.cbm"
        model.save_model(str(model_path))
        metadata = {
            "model": "catboost", "data_source": "processed", "target_mode": "direct",
            "feature_columns": FEATURE_COLUMNS, "cat_features": CAT_FEATURES,
            "iterations": ITERATIONS["direct"], "train_rows": len(train),
            "test_mae_s": float(np.abs(model.predict(test_features[FEATURE_COLUMNS]) - test_y).mean()),
        }
        (artifacts / "catboost_processed_direct_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        output = ROOT / "data" / "submissions" / "catboost_processed_direct_submission.csv"
        submission.to_csv(output, sep=";", index=False)
        print(f"candidate {output} rows={len(submission)}")

        residual_model = fit_model("residual", train, train_features)
        residual_prediction = (
            validate["cur_dev_s"].to_numpy(float)
            + np.asarray(residual_model.predict(validate_features[FEATURE_COLUMNS]), dtype=float)
        )
        champion = pd.read_csv(
            ROOT / "data" / "submissions" / "catboost_processed_submission.csv",
            sep=";", dtype={"sample_id": str},
        )
        assert champion["sample_id"].tolist() == sample["sample_id"].tolist()
        champion_prediction = champion["prediction"].to_numpy(float)
        ordered_residual = sample[["sample_id"]].astype({"sample_id": str}).merge(
            pd.DataFrame({"sample_id": validate["sample_id"], "prediction": residual_prediction}),
            on="sample_id", how="left", sort=False, validate="one_to_one",
        )["prediction"].to_numpy(float)
        assert np.allclose(ordered_residual, champion_prediction, atol=1e-7)
        blend_submission = submission.copy()
        blend_submission["prediction"] = (
            submission["prediction"].to_numpy(float) + champion_prediction
        ) / 2
        blend_output = ROOT / "data" / "submissions" / "catboost_processed_blend50_submission.csv"
        blend_submission.to_csv(blend_output, sep=";", index=False)
        print(f"candidate {blend_output} rows={len(blend_submission)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-candidate", action="store_true")
    main(parser.parse_args().write_candidate)
