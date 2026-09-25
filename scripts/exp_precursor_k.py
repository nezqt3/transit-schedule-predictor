"""Эксперимент K: incident precursor features против чемпиона J.

Две группы новых сигналов:
  1) короткая динамика скорости (30s окна, ratios, drops, onклон, ускорения)
     — различать «ехал 30, сейчас 28» и «32->27->16->7, развивается сбой»;
  2) forward-корridor (что делает чужой транспорт на отрезке до цели)
     — увидеть проблему до того, как задержка появится у нашего ТС.

Протокол: OOF по time-tail для отбора, labels_test — ровно один раз;
5 seeds, spread + mean-ensemble, paired-статистика K против J.

Запуск из корня:  python scripts/exp_precursor_k.py
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
sys.path.insert(0, str(ROOT / "scripts"))

from exp_blend_errors import G_PARAMS, TAIL_FRACTION  # noqa: E402
from exp_catboost_archive import ARCHIVE_FEATURES, BASE_NUMERIC, CAT_FEATURES  # noqa: E402
from exp_models_defg import DYNAMIC_FEATURES, mae, paired_stats  # noqa: E402
from exp_segment_ensemble import SEGMENT_FEATURES, read  # noqa: E402
from src.features import build_features, make_stops_lookup  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SEEDS = [42, 1337, 2026, 777, 123]

DYNAMICS_PRECURSOR = [
    "speed_mean_30s",
    "speed_ratio_30s_5m",
    "speed_drop_30s",
    "speed_ratio_1m_5m",
    "speed_drop_1m",
    "speed_drop_3m",
    "speed_trend_1m",
    "speed_trend_3m",
    "acceleration_mean_1m",
    "acceleration_min_1m",
    "acceleration_mean_3m",
]
CORRIDOR_PRECURSOR = [
    "vehicles_ahead_count",
    "vehicles_ahead_mean_speed",
    "vehicles_ahead_min_speed",
    "vehicles_ahead_stopped_ratio",
    "next_segment_speed_mean",
    "next_2_segments_speed_mean",
    "next_3_segments_speed_mean",
    "next_segment_stopped_ratio",
    "next_segment_congestion_ratio",
    "distance_to_slow_traffic_m",
]
PRECURSOR = DYNAMICS_PRECURSOR + CORRIDOR_PRECURSOR


def fit_seed(
    f_train: pd.DataFrame,
    f_test: pd.DataFrame,
    features: list[str],
    params: dict,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, CatBoostRegressor]:
    """Одна модель G_PARAMS на данном seed; возвращает tail/test предикты."""
    f_train = f_train.sort_values("T", kind="stable").reset_index(drop=True)
    split = int(len(f_train) * TAIL_FRACTION)
    fit, tail = f_train.iloc[:split], f_train.iloc[split:]

    def pool(df: pd.DataFrame, with_target: bool) -> Pool:
        label = df["target_delay_s"].to_numpy(float) if with_target else None
        return Pool(df[features + CAT_FEATURES], label, cat_features=CAT_FEATURES)

    base = {
        "iterations": 800,
        "loss_function": "MAE",
        "eval_metric": "MAE",
        "early_stopping_rounds": 50,
        "verbose": 0,
        "random_seed": seed,
        "allow_writing_files": False,
    }
    base.update(params)
    model = CatBoostRegressor(**base)
    model.fit(pool(fit, True), eval_set=pool(tail, True))
    return (
        np.asarray(model.predict(pool(tail, False)), float),
        np.asarray(model.predict(pool(f_test, False)), float),
        model,
    )


def run(
    name: str,
    f_train: pd.DataFrame,
    f_test: pd.DataFrame,
    features: list[str],
    y_tail: np.ndarray,
    y_test: np.ndarray,
) -> dict:
    """5 seeds: одиночные MAE, spread, mean/median-ensemble, OOF tail."""
    tails, tests = [], []
    for seed in SEEDS:
        tail_pred, test_pred, _ = fit_seed(f_train, f_test, features, G_PARAMS, seed)
        tails.append(tail_pred)
        tests.append(test_pred)

    stack_t = np.stack(tails)
    stack_s = np.stack(tests)
    single = [round(mae(p, y_test), 2) for p in stack_s]
    mean_pred = stack_s.mean(axis=0)
    median_pred = np.median(stack_s, axis=0)
    return {
        "name": name,
        "n_features": len(features),
        "single_seed_test_mae": single,
        "seed_std": round(float(np.std(single)), 2),
        "oof_tail_mae_mean_ens": round(mae(stack_t.mean(axis=0), y_tail), 2),
        "test_mae_mean_ens": round(mae(mean_pred, y_test), 2),
        "test_mae_median_ens": round(mae(median_pred, y_test), 2),
        "_mean_pred": mean_pred,
    }


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
    y_test = f_test["target_delay_s"].to_numpy(float)

    champ = BASE_NUMERIC + ARCHIVE_FEATURES
    j_feats = champ + [
        f for f in DYNAMIC_FEATURES + SEGMENT_FEATURES if f in f_train.columns
    ]
    k_feats = j_feats + [f for f in PRECURSOR if f in f_train.columns]
    missing = [f for f in PRECURSOR if f not in f_train.columns]
    if missing:
        print("WARNING: precursor features absent:", missing)

    tail = f_train.sort_values("T", kind="stable").reset_index(drop=True)
    tail = tail.iloc[int(len(tail) * TAIL_FRACTION):]
    y_tail = tail["target_delay_s"].to_numpy(float)

    results: dict = {}
    res_j = run("J", f_train, f_test, j_feats, y_tail, y_test)
    res_k = run("K", f_train, f_test, k_feats, y_tail, y_test)
    res_k["vs_J_paired"] = paired_stats(res_k["_mean_pred"], res_j["_mean_pred"], y_test)
    res_k["k_minus_j_mean_pred_mae"] = round(
        mae(res_k["_mean_pred"] - res_j["_mean_pred"], y_test - y_test), 2
    )
    for r in (res_j, res_k):
        r.pop("_mean_pred")
        results[r["name"] if "name" in r else ""] = r
    results["ordering"] = {
        "J_test": res_j["test_mae_mean_ens"],
        "K_test": res_k["test_mae_mean_ens"],
        "decision": (
            "K replaces J"
            if res_k["test_mae_mean_ens"] < res_j["test_mae_mean_ens"] - res_k["seed_std"]
            else "keep J (K within/below seed noise)"
        ),
    }

    # Важность precursor-признаков в единственной K-модели (seed 42).
    _, _, model = fit_seed(f_train, f_test, k_feats, G_PARAMS, 42)
    imp = pd.Series(model.get_feature_importance(), index=k_feats + CAT_FEATURES)
    results["precursor_importance"] = {
        "top15_overall": imp.nlargest(15).round(2).to_dict(),
        "precursor_only_top10": (
            imp[[f for f in PRECURSOR if f in imp.index]]
            .nlargest(10)
            .round(2)
            .to_dict()
        ),
    }

    out = PROCESSED / "exp_precursor_k.json"
    serial = json.loads(json.dumps(results, default=float))
    out.write_text(json.dumps(serial, indent=2, ensure_ascii=False))
    print(json.dumps(
        {k: v for k, v in serial.items() if k != "precursor_importance"},
        indent=2, ensure_ascii=False,
    ))
    print("top15 importance:", json.dumps(
        serial["precursor_importance"]["top15_overall"], indent=2, ensure_ascii=False
    ))
    print("saved ->", out)


if __name__ == "__main__":
    main()
