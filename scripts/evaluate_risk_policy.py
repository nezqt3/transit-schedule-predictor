"""Measure dispatcher probability thresholds on the labeled local test period."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ml"), str(ROOT / "scripts")]

from exp_plan_routes import load_part  # noqa: E402


def main() -> None:
    points, _, features = load_part("test")
    artifacts = ROOT / "ml" / "artifacts"
    metadata = json.loads((artifacts / "lightgbm_plan_metadata.json").read_text(encoding="utf-8"))
    calibration = json.loads((artifacts / "risk_calibration.json").read_text(encoding="utf-8"))
    x = features[metadata["features"]].copy()
    categories = metadata["categories"]
    ids = x["tr_id"].astype(str)
    x["tr_id"] = pd.Categorical(ids.where(ids.isin(categories)), categories=categories)
    residual = lgb.Booster(model_file=str(artifacts / "lightgbm_plan_residual.txt"))
    direct = lgb.Booster(model_file=str(artifacts / "lightgbm_plan_direct.txt"))
    delay = (points["cur_dev_s"].to_numpy(float)
             + residual.predict(x) + direct.predict(x)) / 2
    z = np.clip(calibration["coefficient"] * delay + calibration["intercept"], -700, 700)
    probability = 1 / (1 + np.exp(-z))
    actual = points["target_delay_s"].to_numpy(float) >= 120

    rows = []
    for threshold, level in ((0.25, "medium_or_high"), (0.60, "high")):
        flagged = probability >= threshold
        tp = int(np.sum(flagged & actual))
        fp = int(np.sum(flagged & ~actual))
        fn = int(np.sum(~flagged & actual))
        tn = int(np.sum(~flagged & ~actual))
        rows.append({
            "risk_level": level, "threshold": threshold,
            "true_positive": tp, "false_positive": fp,
            "false_negative": fn, "true_negative": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
        })
    report = {"dataset": "labeled test, 353 points", "event": calibration["event"],
              "model_version": calibration["source_model_version"], "thresholds": rows}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
