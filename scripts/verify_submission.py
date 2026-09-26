"""Verify the exact competition submission contract without reading labels."""

from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS = ROOT / "data" / "submissions"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames != ["sample_id", "prediction"]:
            raise ValueError(f"{path}: expected columns sample_id;prediction")
        return list(reader)


def main() -> None:
    template = read(SUBMISSIONS / "sample_submission.csv")
    submission_path = SUBMISSIONS / "final_submission.csv"
    submission = read(submission_path)
    expected = [row["sample_id"] for row in template]
    actual = [row["sample_id"] for row in submission]
    if len(actual) != len(set(actual)) or actual != expected:
        raise ValueError("submission IDs must match the template exactly and in order")
    if not all(math.isfinite(float(row["prediction"])) for row in submission):
        raise ValueError("every prediction must be a finite number")
    digest = hashlib.sha256(submission_path.read_bytes()).hexdigest()
    print(f"valid: {len(submission)} rows; sha256={digest}")


if __name__ == "__main__":
    main()
