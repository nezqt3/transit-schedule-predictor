"""Эксперименты J и blend + структурный error analysis.

  J — фичи F(dynamic) + H(segment), параметры лучшей конфигурации G;
  blend — гетерогенная смесь G/H/C, веса подбираются на time-tail OOF
          (последние 15% labels_train по времени), labels_test используется
          ровно один раз для финальной проверки;
  errors — разложение MAE G по бакетам target/horizon/cur_dev/distance и
          разбор топ-20 худших объектов.

Запуск из корня:  python scripts/exp_blend_errors.py
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
sys.path.insert(0, str(ROOT / "scripts"))

from exp_models_defg import (  # noqa: E402
    ARCHIVE_FEATURES,
    BASE_NUMERIC,
    CAT_FEATURES,
    DYNAMIC_FEATURES,
    mae,
    paired_stats,
)
from exp_segment_ensemble import SEGMENT_FEATURES, read  # noqa: E402
from src.features import build_features, make_stops_lookup  # noqa: E402

PROCESSED = ROOT / "data" / "processed"

G_PARAMS = {
    "learning_rate": 0.06,
    "depth": 6,
    "l2_leaf_reg": 1.0,
    "random_strength": 1.0,
}
TAIL_FRACTION = 0.85


def fit_models(
    f_train: pd.DataFrame,
    f_test: pd.DataFrame,
    features: list[str],
    params: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Обучает модель с early stop на time-tail; возвращает (tail_pred, test_pred)."""
    f_train = f_train.sort_values("T", kind="stable").reset_index(drop=True)
    split = int(len(f_train) * TAIL_FRACTION)
    fit, tail = f_train.iloc[:split], f_train.iloc[split:]

    def pool(df: pd.DataFrame, with_target: bool) -> Pool:
        label = (
            df["target_delay_s"].to_numpy(float) if with_target else None
        )
        return Pool(df[features + CAT_FEATURES], label, cat_features=CAT_FEATURES)

    base = {
        "iterations": 800,
        "loss_function": "MAE",
        "eval_metric": "MAE",
        "early_stopping_rounds": 50,
        "verbose": 0,
        "random_seed": 0,
        "allow_writing_files": False,
    }
    base.update(params)
    model = CatBoostRegressor(**base)
    model.fit(pool(fit, True), eval_set=pool(tail, True))
    return (
        np.asarray(model.predict(pool(tail, False)), float),
        np.asarray(model.predict(pool(f_test, False)), float),
    )


def bucket_mae(
    frame: pd.DataFrame,
    pred: np.ndarray,
    by: str,
    edges: list,
    labels: list[str],
) -> dict:
    """MAE и доля ошибок по бакетам признака `by`."""
    y = frame["target_delay_s"].to_numpy(float)
    err = pd.Series(np.abs(pred - y))
    b = pd.cut(frame[by], bins=edges, labels=labels)
    out = {}
    for name, grp in err.groupby(b, observed=True):
        out[str(name)] = {
            "n": int(len(grp)),
            "mae": round(float(grp.mean()), 1),
            "share_of_total_err": round(float(grp.sum() / err.sum()), 3),
        }
    return out


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
    f_feats = champ + [f for f in DYNAMIC_FEATURES if f in f_train.columns]
    h_feats = champ + [f for f in SEGMENT_FEATURES if f in f_train.columns]
    j_feats = f_feats + [f for f in SEGMENT_FEATURES if f in f_train.columns]

    default = {"learning_rate": 0.06, "depth": 6}
    models = {
        "C": fit_models(f_train, f_test, champ, default),
        "G": fit_models(f_train, f_test, f_feats, G_PARAMS),
        "H": fit_models(f_train, f_test, h_feats, default),
        "J": fit_models(f_train, f_test, j_feats, G_PARAMS),
    }

    tail = f_train.sort_values("T", kind="stable").reset_index(drop=True)
    tail = tail.iloc[int(len(tail) * TAIL_FRACTION):]
    y_tail = tail["target_delay_s"].to_numpy(float)

    results: dict = {}
    for name, (tail_pred, test_pred) in models.items():
        results[name] = {
            "oof_tail_mae": round(mae(tail_pred, y_tail), 2),
            "test_mae": round(mae(test_pred, y_test), 2),
        }

    # --- blend: веса по OOF tail, тест только для финальной проверки ---
    tail_stack = np.stack([models[k][0] for k in ("G", "H", "C")])
    test_stack = np.stack([models[k][1] for k in ("G", "H", "C")])

    best = None
    for w in itertools.product(np.arange(0, 1.01, 0.1), repeat=3):
        if abs(sum(w) - 1.0) > 1e-9:
            continue
        score = mae(np.tensordot(w, tail_stack, axes=1), y_tail)
        if best is None or score < best[0]:
            best = (score, w)
    blend_oof_mae, weights = best
    blend_test_pred = np.tensordot(weights, test_stack, axes=1)
    results["blend_GHC"] = {
        "weights_G_H_C": [round(float(x), 2) for x in weights],
        "oof_tail_mae": round(blend_oof_mae, 2),
        "test_mae_one_shot": round(mae(blend_test_pred, y_test), 2),
        "vs_G_test_paired": paired_stats(blend_test_pred, models["G"][1], y_test),
    }

    # --- error analysis модели G на test ---
    g_pred = models["G"][1]
    errors = {
        "by_target_class": bucket_mae(
            f_test, g_pred, "target_delay_s",
            [-1e9, -60, 60, 180, 1e9],
            ["early<-60", "ontime-60..60", "late60..180", "very_late>180"],
        ),
        "by_horizon": bucket_mae(
            f_test, g_pred, "time_to_stop_s",
            [600, 660, 720, 780, 840, 901],
            ["10-11m", "11-12m", "12-13m", "13-14m", "14-15m"],
        ),
        "by_cur_dev": bucket_mae(
            f_test, g_pred, "cur_dev_s",
            [-1e9, -60, 60, 180, 1e9],
            ["early<-60", "ontime-60..60", "late60..180", "very_late>180"],
        ),
        "by_distance": bucket_mae(
            f_test, g_pred, "dist_to_stop_m",
            [-1, 1000, 3000, 5000, 1e9],
            ["<1km", "1-3km", "3-5km", ">5km"],
        ),
    }

    scored = f_test.assign(
        pred=g_pred,
        abs_error=np.abs(g_pred - y_test),
        signed_error=g_pred - y_test,
    )
    total_abs_err = scored["abs_error"].sum()
    worst = scored.nlargest(20, "abs_error")[
        [
            "sample_id", "tr_id", "target_delay_s", "pred", "signed_error",
            "abs_error",
            "cur_dev_s", "time_to_stop_s", "dist_to_stop_m", "packets_5m",
            "gap_since_last_pkt_s", "stopped_ratio_5m", "speed_mean_1m",
            "segment_speed_mean_5m", "hour_of_day",
        ]
    ]
    top20 = {
        "sum_abs_error_share": round(
            float(worst["abs_error"].sum() / total_abs_err), 3
        ),
        "signed_error_mean": round(float(worst["signed_error"].mean()), 1),
        "top_tr_ids": worst["tr_id"].value_counts().head(5).to_dict(),
        "no_telemetry_5m": int((worst["packets_5m"].fillna(0) == 0).sum()),
        "cur_dev_mean": round(float(worst["cur_dev_s"].mean()), 1),
        "target_mean": round(float(worst["target_delay_s"].mean()), 1),
        "dist_km_mean": round(float(worst["dist_to_stop_m"].mean() / 1000), 2),
        "rows": worst.round(2).to_dict(orient="records"),
    }

    results["error_analysis_G"] = {"buckets": errors, "worst_20": top20}

    print(json.dumps(
        {k: v for k, v in results.items() if k != "error_analysis_G"},
        indent=2, ensure_ascii=False,
    ))
    print(json.dumps(errors, indent=2, ensure_ascii=False))
    out = PROCESSED / "exp_blend_errors.json"
    out.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nСохранено: {out}")


if __name__ == "__main__":
    main()
