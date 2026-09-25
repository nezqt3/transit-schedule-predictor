"""Эксперименты H/I: признаки окружения сегмента и seed-ensemble.

  H  — C + сегментные признаки (скорость/стоп-доля/число ТС в ячейке ~500 м,
       historical speed сегмента) + schedule pressure
       (required_speed против скорости участка, speed_deficit по окнам);
  HF — H + динамические rolling-признаки из эксперимента F;
  I  — seed-ensemble (5 seed) чемпиона C и лучшей модели: mean vs median.

Оценка — MAE на labels_test + paired против одиночной C (seed=0).
Запуск из корня:  python scripts/exp_segment_ensemble.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from exp_models_defg import (  # noqa: E402
    ARCHIVE_FEATURES,
    BASE_NUMERIC,
    DYNAMIC_FEATURES,
    mae,
    paired_stats,
    train_model,
)
from src.features import build_features, make_stops_lookup  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SEEDS = [42, 1337, 2026, 777, 123]

SEGMENT_FEATURES = [
    "segment_speed_mean_5m",
    "segment_speed_median_5m",
    "segment_stopped_ratio_5m",
    "segment_vehicle_count_5m",
    "historical_segment_speed",
    "vehicle_vs_segment_5m",
    "segment_vs_historical_5m",
    "schedule_pressure",
    "required_vs_historical",
    "speed_deficit_mean_1m",
    "speed_deficit_mean_3m",
]


def read(name: str, dt: tuple[str, ...] = ()) -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / f"{name}.csv", low_memory=False)
    for col in dt:
        df[col] = pd.to_datetime(df[col])
    return df


def ensemble(
    f_train: pd.DataFrame,
    f_test: pd.DataFrame,
    features: list[str],
    agg: str,
) -> np.ndarray:
    """Предсказания CatBoost на 5 сид и агрегация mean/median."""
    preds = np.stack(
        [
            train_model(f_train, f_test, features, params={"random_seed": seed})[0]
            for seed in SEEDS
        ]
    )
    return preds.mean(axis=0) if agg == "mean" else np.median(preds, axis=0)


def main() -> None:
    traffic = read("train_traffic", ("event_time",))
    labels_train = read("labels_train", ("T", "target_time_begin"))
    labels_test = read("labels_test", ("T", "target_time_begin"))
    stops = make_stops_lookup(
        read("train_schedule"),
        read("test_schedule"),
        read("validate_schedule_plan"),
    )
    f_train = build_features(traffic, labels_train, stops)
    f_test = build_features(read("test_traffic", ("event_time",)), labels_test, stops)
    y = f_test["target_delay_s"].to_numpy(float)

    champion = BASE_NUMERIC + ARCHIVE_FEATURES
    h_features = champion + [
        f for f in SEGMENT_FEATURES if f in f_train.columns
    ]
    hf_features = h_features + [
        f for f in DYNAMIC_FEATURES if f in f_train.columns
    ]
    print("H-фичи:", len(h_features), "| HF-фичи:", len(hf_features))

    results: dict[str, dict] = {}

    def record(name: str, pred: np.ndarray, meta: dict | None = None) -> None:
        run = {"mae_test": round(mae(pred, y), 2)}
        run["vs_C_single"] = paired_stats(pred, results["C_single"]["pred"], y)
        if meta:
            run.update(meta)
        results[name] = run

    pred_c, meta_c = train_model(f_train, f_test, champion)
    results["C_single"] = {
        "mae_test": round(mae(pred_c, y), 2),
        "pred": pred_c,
        "top_features": meta_c["top_features"][:5],
    }

    pred_h, meta_h = train_model(f_train, f_test, h_features)
    record("H_segment", pred_h, {"top_features": meta_h["top_features"][:6]})

    pred_hf, _ = train_model(f_train, f_test, hf_features)
    record("HF_segment_plus_dynamic", pred_hf)

    for name, features in [("C", champion), ("H", h_features)]:
        for agg in ("mean", "median"):
            pred = ensemble(f_train, f_test, features, agg)
            record(f"I_{name}_ensemble_{agg}", pred)

    for run in results.values():
        run.pop("pred", None)

    print(json.dumps(results, indent=2, ensure_ascii=False)[:2500])
    out = PROCESSED / "exp_segment_ensemble.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nСохранено: {out}")


if __name__ == "__main__":
    main()
