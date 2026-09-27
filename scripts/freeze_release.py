"""Pin current selected weights, calibration, schedule and CSV in one manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_submission import read  # noqa: E402


def sha256(path: Path, *, normalize_text: bool = False) -> str:
    data = path.read_bytes()
    if normalize_text:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    artifacts = ROOT / "ml" / "artifacts"
    submission = ROOT / "data" / "submissions" / "final_submission.csv"
    candidate = ROOT / "data" / "submissions" / "lightgbm_plan_submission.csv"
    if read(submission) != read(candidate):
        raise SystemExit("final CSV differs from the selected pure LightGBM candidate")
    manifest_path = artifacts / "release_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["verified_runtime"] = {
        "python": sys.version.split()[0],
        "lightgbm": version("lightgbm"),
        "pandas": version("pandas"),
        "numpy": version("numpy"),
    }
    manifest["sha256"] = {
        name: sha256(artifacts / name, normalize_text=True)
        for name in ("lightgbm_plan_metadata.json", "lightgbm_plan_direct.txt",
                     "lightgbm_plan_residual.txt", "risk_calibration.json")
    }
    manifest["sha256"]["schedule_plan.csv"] = sha256(
        ROOT / "data" / "raw" / "validate" / "schedule_plan.csv"
    )
    manifest["sha256"]["final_submission.csv"] = sha256(submission)
    calibration = json.loads((artifacts / "risk_calibration.json").read_text(encoding="utf-8"))
    if calibration["source_model_artifact_sha256"] != manifest["sha256"]["lightgbm_plan_direct.txt"]:
        raise SystemExit("risk calibration belongs to different weights; retrain it first")
    experiment = ROOT / "data" / "processed" / "exp_lightgbm_plan.json"
    if experiment.is_file():
        report = json.loads(experiment.read_text(encoding="utf-8"))
        manifest["train_temporal_cv_mae_s"] = report["cv_mae"]
        manifest["test_mae_s"] = report["test_mae"]
    manifest["official_platform_score"] = None
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(f"Frozen {manifest['model_version']} with CSV sha256={manifest['sha256']['final_submission.csv']}")


if __name__ == "__main__":
    main()
