"""Generate the competition's two-column, semicolon-separated submission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from src.offline.dataset_builder import PROCESSED, ROOT, build_split
from src.offline.train import MODEL_PATH


def make_submission(model_path: Path = MODEL_PATH, output: Path | None = None) -> Path:
    """Predict validation points and write exactly sample_id;prediction."""
    if output is None:
        output = ROOT / "data" / "submissions" / "submission.csv"
    feature_path = PROCESSED / "validate_features.parquet"
    features = build_split("validate")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    features.to_parquet(feature_path, index=False)
    metadata_path = model_path.with_suffix(".json")
    if not model_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError(f"model or metadata missing: {model_path}; run make train")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model = CatBoostRegressor()
    model.load_model(str(model_path))
    columns = metadata["feature_columns"]
    prediction = np.clip(
        features["cur_dev_s"].to_numpy(float) + model.predict(features[columns]),
        -300, 700,
    )
    if not np.isfinite(prediction).all():
        raise ValueError("submission contains non-finite predictions")
    submission = pd.DataFrame({
        "sample_id": features["sample_id"].astype(str),
        "prediction": prediction.astype(float),
    })
    if submission["sample_id"].duplicated().any():
        raise ValueError("duplicate sample_id in submission")
    output.parent.mkdir(parents=True, exist_ok=True)
    submission.to_csv(output, sep=";", index=False, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(make_submission(output=args.output))


if __name__ == "__main__":
    main()
