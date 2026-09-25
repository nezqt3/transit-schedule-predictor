"""Build causal feature tables from the competition CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from src.features import extract_features_for_point

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


def _read_schedule(path: Path) -> dict[int, tuple[float, float]]:
    schedule = pd.read_csv(path, usecols=["tt_action_item_id", "geom"])
    coords = schedule["geom"].astype(str).str.extract(
        r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)"
    )
    schedule["stop_lon"] = pd.to_numeric(coords[0], errors="coerce")
    schedule["stop_lat"] = pd.to_numeric(coords[1], errors="coerce")
    if schedule[["stop_lat", "stop_lon"]].isna().any().any():
        raise ValueError(f"invalid stop geometry in {path}")
    return {
        int(row.tt_action_item_id): (float(row.stop_lat), float(row.stop_lon))
        for row in schedule.itertuples(index=False)
    }


def build_split(split: str, raw_dir: Path = RAW) -> pd.DataFrame:
    """Build a feature row per label or validation point, using only data by T."""
    if split not in {"train", "test", "validate"}:
        raise ValueError(f"unknown split: {split}")
    labels_path = (
        raw_dir / "validate" / "points.csv" if split == "validate"
        else raw_dir / "labels" / f"labels_{split}.csv"
    )
    traffic_path = raw_dir / split / "traffic.csv"
    schedule_path = raw_dir / split / (
        "schedule_plan.csv" if split == "validate" else "schedule.csv"
    )
    labels = pd.read_csv(labels_path)
    labels["T"] = pd.to_datetime(labels["T"], format="mixed", errors="raise")
    labels["target_time_begin"] = pd.to_datetime(
        labels["target_time_begin"], format="mixed", errors="raise"
    )
    horizon = (labels["target_time_begin"] - labels["T"]).dt.total_seconds()
    if not ((horizon > 600) & (horizon <= 900)).all():
        raise ValueError(f"{labels_path} has target stops outside (T+10m, T+15m]")
    if labels["sample_id"].duplicated().any():
        raise ValueError(f"duplicate sample_id in {labels_path}")

    traffic = pl.read_csv(
        traffic_path,
        columns=[
            "tr_id", "event_time", "receive_time", "location_valid",
            "lat", "lon", "speed", "heading",
        ],
        schema_overrides={"event_time": pl.String, "receive_time": pl.String},
    ).to_pandas()
    traffic["event_time"] = pd.to_datetime(
        traffic["event_time"], format="mixed", errors="coerce"
    )
    traffic["receive_time"] = pd.to_datetime(
        traffic["receive_time"], format="mixed", errors="coerce"
    )
    traffic = traffic.dropna(subset=["event_time"]).sort_values(
        ["tr_id", "event_time"], kind="stable"
    )
    by_vehicle = {
        int(tr_id): (group, group["event_time"].to_numpy(dtype="datetime64[ns]"))
        for tr_id, group in traffic.groupby("tr_id", sort=False)
    }
    stops = _read_schedule(schedule_path)
    rows: list[dict] = []
    for point in labels.itertuples(index=False):
        stop_id = int(point.target_stop_id)
        if stop_id not in stops:
            raise ValueError(f"missing target stop {stop_id} in {schedule_path}")
        stop_lat, stop_lon = stops[stop_id]
        vehicle = by_vehicle.get(int(point.tr_id))
        if vehicle is None:
            window = pd.DataFrame()
        else:
            frame, times = vehicle
            t = np.datetime64(point.T, "ns")
            lo = int(np.searchsorted(times, t - np.timedelta64(15, "m"), side="left"))
            hi = int(np.searchsorted(times, t, side="right"))
            window = frame.iloc[lo:hi]
        features = extract_features_for_point(
            window,
            {"stop_lat": stop_lat, "stop_lon": stop_lon,
             "target_time_begin": point.target_time_begin},
            point.cur_dev_s,
            point.T,
        )
        row = {
            "sample_id": str(point.sample_id),
            "tr_id": str(point.tr_id),
            "T": point.T,
            "target_stop_id": stop_id,
            **features,
        }
        if split != "validate":
            row["target_delay_s"] = float(point.target_delay_s)
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["train", "test", "validate", "all"], default="all")
    args = parser.parse_args()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    splits = ("train", "test", "validate") if args.split == "all" else (args.split,)
    for split in splits:
        features = build_split(split)
        path = PROCESSED / f"{split}_features.parquet"
        features.to_parquet(path, index=False)
        print(f"{split}: {len(features)} rows -> {path}")


if __name__ == "__main__":
    main()
