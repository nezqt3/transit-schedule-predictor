"""Эксперимент: влияет ли режим источника телеметрии (archive/live) на CatBoost.

Гипотеза: archive-пакеты есть только в train, поэтому модель может
выучить специфичные для archive паттерны, которых нет в test.

Модели:
  A — train-фичи по всей телеметрии (archive + live);
  B — train-фичи только по live-пакетам (совпадает с доменом test);
  C — как A + признаки is_archive_last / archive_frac_5m.

Оценка MAE на labels_test, ориентир — baseline prediction = cur_dev_s.

Запуск из корня:  python scripts/exp_catboost_archive.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from src.features import build_features, make_stops_lookup  # noqa: E402

PROCESSED = ROOT / "data" / "processed"

BASE_NUMERIC = [
    "cur_dev_s",
    "current_speed",
    "speed_mean_1m",
    "speed_mean_3m",
    "speed_mean_5m",
    "speed_std_5m",
    "speed_n_1m",
    "speed_n_3m",
    "speed_n_5m",
    "packets_5m",
    "gap_since_last_pkt_s",
    "last_heading",
    "time_to_stop_s",
    "dist_to_stop_m",
    "hour_of_day",
]
ARCHIVE_FEATURES = ["is_archive_last", "archive_frac_5m"]
CAT_FEATURES = ["tr_id"]


def load_frames() -> dict:
    """Загружает cleaned-таблицы и разбирает datetime-колонки."""
    def read(name: str, datetime_cols: tuple[str, ...] = ()) -> pd.DataFrame:
        df = pd.read_csv(PROCESSED / f"{name}.csv", low_memory=False)
        for col in datetime_cols:
            df[col] = pd.to_datetime(df[col])
        return df

    return {
        "train_traffic": read("train_traffic", ("event_time",)),
        "test_traffic": read("test_traffic", ("event_time",)),
        "labels_train": read("labels_train", ("T", "target_time_begin")),
        "labels_test": read("labels_test", ("T", "target_time_begin")),
        "train_schedule": read("train_schedule"),
        "test_schedule": read("test_schedule"),
        "validate_schedule_plan": read("validate_schedule_plan"),
    }


def train_eval(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    numeric: list[str],
) -> dict:
    """Учит CatBoost с ранним стопом на хвосте train по времени, MAE на test."""
    train_df = train_df.sort_values("T", kind="stable").reset_index(drop=True)
    split = int(len(train_df) * 0.85)
    fit, eval_ = train_df.iloc[:split], train_df.iloc[split:]

    def pool(df: pd.DataFrame, with_target: bool) -> Pool:
        data = df[numeric + CAT_FEATURES]
        label = (
            df["target_delay_s"].to_numpy(float) if with_target else None
        )
        return Pool(data, label, cat_features=CAT_FEATURES)

    model = CatBoostRegressor(
        iterations=800,
        learning_rate=0.06,
        depth=6,
        loss_function="MAE",
        eval_metric="MAE",
        early_stopping_rounds=50,
        verbose=0,
        allow_writing_files=False,
    )
    model.fit(pool(fit, True), eval_set=pool(eval_, True))

    pred = model.predict(pool(test_df, False))
    mae = float(np.abs(pred - test_df["target_delay_s"].to_numpy(float)).mean())
    val_mae = float(
        np.abs(
            model.predict(pool(eval_, False)) - eval_["target_delay_s"].to_numpy(float)
        ).mean()
    )
    return {
        "mae_test": round(mae, 2),
        "mae_train_tail": round(val_mae, 2),
        "best_iteration": int(model.get_best_iteration()),
        "top_features": [
            {"feature": f, "importance": round(i, 3)}
            for f, i in sorted(
                zip(numeric + CAT_FEATURES, model.get_feature_importance()),
                key=lambda x: -x[1],
            )[:6]
        ],
    }


def main() -> None:
    frames = load_frames()
    traffic = frames["train_traffic"]
    live_traffic = traffic[~traffic["is_archive"]]
    test_traffic = frames["test_traffic"]

    stops = make_stops_lookup(
        frames["train_schedule"],
        frames["test_schedule"],
        frames["validate_schedule_plan"],
    )

    features_full = build_features(traffic, frames["labels_train"], stops)
    features_live = build_features(live_traffic, frames["labels_train"], stops)
    features_test = build_features(test_traffic, frames["labels_test"], stops)

    archive_share = float(features_full["is_archive_last"].mean())
    print(f"train-семплы с archive-последним пакетом: {archive_share:.1%}")

    baseline_mae = float(
        np.abs(
            features_test["cur_dev_s"] - frames["labels_test"]["target_delay_s"]
        ).mean()
    )
    results = {"baseline_cur_dev_s": round(baseline_mae, 2)}

    results["A_archive_plus_live"] = train_eval(
        features_full, features_test, BASE_NUMERIC
    )
    results["B_live_only"] = train_eval(
        features_live, features_test, BASE_NUMERIC
    )
    results["C_plus_is_archive"] = train_eval(
        features_full, features_test, BASE_NUMERIC + ARCHIVE_FEATURES
    )

    print(json.dumps(results, indent=2, ensure_ascii=False))
    out = PROCESSED / "exp_catboost_archive.json"
    out.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
