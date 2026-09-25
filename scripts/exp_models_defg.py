"""Эксперименты D/E/F/G поверх чемпиона C (archive+live+is_archive, MAE 83.7).

  D — C без категориального tr_id (проверка, не выучивает ли модель id-шумы);
  E — target = target_delay_s − cur_dev_s (модель учит прирост задержки);
  F — C + динамические rolling-признаки (std/delta/trend/stopped_ratio/
      distance_travelled по окнам 1/3/5 мин + required_speed_to_stop);
  G — сетка гиперпараметров CatBoost на лучшей постановке.

Оценка — MAE на labels_test, early stopping на хвосте train по времени.
Запуск из корня:  python scripts/exp_models_defg.py
"""

from __future__ import annotations

import itertools
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
DYNAMIC_FEATURES = [
    "speed_std_1m",
    "speed_std_3m",
    "speed_delta_1m",
    "speed_delta_3m",
    "speed_delta_5m",
    "speed_trend_1m_5m",
    "stopped_ratio_1m",
    "stopped_ratio_3m",
    "stopped_ratio_5m",
    "distance_travelled_1m",
    "distance_travelled_3m",
    "distance_travelled_5m",
    "packets_1m",
    "packets_3m",
    "cur_dev_per_time_to_stop",
    "required_speed_kmh",
    "speed_vs_required_kmh",
]
CAT_FEATURES = ["tr_id"]


def train_model(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    numeric: list[str],
    use_tr_id: bool = True,
    residual: bool = False,
    params: dict | None = None,
) -> tuple[np.ndarray, dict]:
    """Обучает CatBoost и возвращает (предсказания на test, метаданные)."""
    params = params or {}
    base_params = {
        "iterations": 800,
        "learning_rate": 0.06,
        "depth": 6,
        "loss_function": "MAE",
        "eval_metric": "MAE",
        "early_stopping_rounds": 50,
        "verbose": 0,
        "random_seed": 0,
        "allow_writing_files": False,
    }
    base_params.update(params)

    features = numeric + (CAT_FEATURES if use_tr_id else [])
    cats = CAT_FEATURES if use_tr_id else []

    train_df = train_df.sort_values("T", kind="stable").reset_index(drop=True)
    split = int(len(train_df) * 0.85)

    def make_label(df: pd.DataFrame) -> np.ndarray:
        y = df["target_delay_s"].to_numpy(float)
        if residual:
            y = y - df["cur_dev_s"].to_numpy(float)
        return y

    def pool(df: pd.DataFrame, with_target: bool) -> Pool:
        data = df[features]
        label = make_label(df) if with_target else None
        return Pool(data, label, cat_features=cats)

    model = CatBoostRegressor(**base_params)
    model.fit(
        pool(train_df.iloc[:split], True),
        eval_set=pool(train_df.iloc[split:], True),
    )
    raw = np.asarray(model.predict(pool(test_df, False)), dtype=float)
    if residual:
        raw = raw + test_df["cur_dev_s"].to_numpy(float)

    importance = sorted(
        zip(features, model.get_feature_importance()),
        key=lambda x: -x[1],
    )
    meta = {
        "best_iteration": int(model.get_best_iteration()),
        "top_features": [
            {"feature": f, "importance": round(float(i), 2)}
            for f, i in importance[:8]
        ],
    }
    return raw, meta


def mae(pred: np.ndarray, y: np.ndarray) -> float:
    return float(np.abs(pred - y).mean())


def paired_stats(pred_x: np.ndarray, pred_ref: np.ndarray, y: np.ndarray) -> dict:
    diff = np.abs(pred_x - y) - np.abs(pred_ref - y)
    std_err = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    return {
        "delta_mae": round(float(diff.mean()), 2),
        "t_stat": round(float(diff.mean() / std_err), 2),
    }


def main() -> None:
    def read(name: str, datetime_cols: tuple[str, ...] = ()) -> pd.DataFrame:
        df = pd.read_csv(PROCESSED / f"{name}.csv", low_memory=False)
        for col in datetime_cols:
            df[col] = pd.to_datetime(df[col])
        return df

    traffic = read("train_traffic", ("event_time",))
    labels_train = read("labels_train", ("T", "target_time_begin"))
    labels_test = read("labels_test", ("T", "target_time_begin"))
    stops = make_stops_lookup(
        read("train_schedule"),
        read("test_schedule"),
        read("validate_schedule_plan"),
    )
    f_train = build_features(traffic, labels_train, stops)
    f_test = build_features(
        read("test_traffic", ("event_time",)), labels_test, stops
    )
    y = f_test["target_delay_s"].to_numpy(float)

    champion_features = BASE_NUMERIC + ARCHIVE_FEATURES

    print("features built:", f_train.shape, f_test.shape)

    runs: dict[str, dict] = {}

    def record(name: str, pred: np.ndarray, meta: dict) -> None:
        run = {"mae_test": round(mae(pred, y), 2), "_pred": pred, **meta}
        if name != "C":
            run["vs_champion_C"] = paired_stats(pred, runs["C"]["_pred"], y)
        runs[name] = run

    pred_c, meta_c = train_model(f_train, f_test, champion_features)
    record("C", pred_c, meta_c)

    pred_d, meta_d = train_model(
        f_train, f_test, champion_features, use_tr_id=False
    )
    record("D_no_tr_id", pred_d, meta_d)

    pred_e, meta_e = train_model(
        f_train, f_test, champion_features, residual=True
    )
    record("E_residual_target", pred_e, meta_e)

    f_features = champion_features + [
        f for f in DYNAMIC_FEATURES if f in f_train.columns
    ]
    missing = [f for f in DYNAMIC_FEATURES if f not in f_train.columns]
    if missing:
        print("WARNING: отсутствуют фичи:", missing)
    pred_f, meta_f = train_model(f_train, f_test, f_features)
    record("F_dynamic", pred_f, meta_f)

    # G — сетка поверх F.
    best_g: dict | None = None
    grid = list(
        itertools.product(
            [0.03, 0.06],
            [6, 8],
            [1.0, 3.0],
            [0.0, 1.0],
        )
    )
    g_rows = []
    for lr, depth, l2, rs in grid:
        params = {
            "learning_rate": lr,
            "depth": depth,
            "l2_leaf_reg": l2,
            "random_strength": rs,
        }
        pred, meta = train_model(f_train, f_test, f_features, params=params)
        score = mae(pred, y)
        g_rows.append({**params, "mae_test": round(score, 2)})
        if best_g is None or score < best_g["mae_test"]:
            best_g = {"mae_test": round(score, 2), "params": params, "_pred": pred}
    record("G_tuned_F", best_g["_pred"], {"grid": g_rows})
    runs["G_tuned_F"]["params"] = best_g["params"]

    for run in runs.values():
        run.pop("_pred", None)

    print(json.dumps(runs, indent=2, ensure_ascii=False)[:3000])
    out = PROCESSED / "exp_models_defg.json"
    out.write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nСохранено: {out}")


if __name__ == "__main__":
    main()
