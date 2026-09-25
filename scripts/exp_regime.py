"""Regime model: P(very_late) и P(early) как вспомогательный сигнал.

Не заменяет регрессию, а даёт честные OOF-вероятности хвостовых режимов:
  is_very_late = target_delay_s > 180
  is_early     = target_delay_s < -60

OOF собираются chronological-фолдами (модель обучается строго на прошлом и
предсказывает будущий фолд), поэтому в стекинг регрессора не попадает
leakage. Второй вариант применения — risk-сигнал дашборда: скорим test-
предсказания по децилям p_very_late.

Запуск из корня:  python scripts/exp_regime.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor, Pool
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from exp_blend_errors import G_PARAMS, TAIL_FRACTION  # noqa: E402
from exp_catboost_archive import ARCHIVE_FEATURES, BASE_NUMERIC, CAT_FEATURES  # noqa: E402
from exp_models_defg import DYNAMIC_FEATURES, mae, paired_stats  # noqa: E402
from exp_precursor_k import PRECURSOR  # noqa: E402
from exp_segment_ensemble import SEGMENT_FEATURES, read  # noqa: E402
from src.features import build_features, make_stops_lookup  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
N_FOLDS = 5
CLF_PARAMS = {
    "iterations": 400,
    "learning_rate": 0.06,
    "depth": 6,
    "loss_function": "Logloss",
    "eval_metric": "AUC",
    "verbose": 0,
    "random_seed": 42,
    "allow_writing_files": False,
}
SEEDS_REG = [42, 1337, 2026]

TARGETS = {
    "p_very_late": lambda y: (y > 180).astype(int),
    "p_early": lambda y: (y < -60).astype(int),
}


def make_pools(f_train: pd.DataFrame, f_test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    champ = BASE_NUMERIC + ARCHIVE_FEATURES
    feats = champ + [
        f for f in DYNAMIC_FEATURES + SEGMENT_FEATURES + PRECURSOR
        if f in f_train.columns
    ]
    return feats


def clf_fit_predict(
    fit_df: pd.DataFrame,
    fit_label: np.ndarray,
    pred_df: pd.DataFrame,
    features: list[str],
) -> np.ndarray:
    model = CatBoostClassifier(**CLF_PARAMS)
    model.fit(
        Pool(fit_df[features + CAT_FEATURES], fit_label, cat_features=CAT_FEATURES)
    )
    return np.asarray(model.predict_proba(Pool(pred_df[features + CAT_FEATURES],
                                                cat_features=CAT_FEATURES))[:, 1], float)


def oof_probabilities(
    f_sorted: pd.DataFrame,
    label: np.ndarray,
    features: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Chronological walk-forward OOF: фолд i предсказывается моделью на 0..i-1.

    Возвращает (oof по всему train, mask_oof) и метрики по фолдам.
    """
    n = len(f_sorted)
    edges = [int(n * i / N_FOLDS) for i in range(N_FOLDS + 1)]
    oof = np.full(n, np.nan)
    fold_auc = {}
    for i in range(1, N_FOLDS):
        fit_idx = slice(edges[0], edges[i])
        pred_idx = slice(edges[i], edges[i + 1])
        p = clf_fit_predict(
            f_sorted.iloc[fit_idx], label[fit_idx], f_sorted.iloc[pred_idx], features
        )
        oof[pred_idx] = p
        y = label[pred_idx]
        fold_auc[f"fold{i}"] = (
            round(float(roc_auc_score(y, p)), 3) if 0 < y.sum() < len(y) else None
        )
    return oof, fold_auc


def reg_fit_predict(
    fit_df: pd.DataFrame,
    inner_eval_df: pd.DataFrame,
    pred_dfs: list[pd.DataFrame],
    features: list[str],
    seeds: list[int],
) -> list[np.ndarray]:
    """Seed-усреднённый MAE-регрессор; returns предикт на каждый pred_df."""
    feats = [f for f in features if f in fit_df.columns]
    preds = [[] for _ in pred_dfs]
    for seed in seeds:
        params = {
            **G_PARAMS,
            "iterations": 800,
            "loss_function": "MAE",
            "eval_metric": "MAE",
            "early_stopping_rounds": 50,
            "verbose": 0,
            "random_seed": seed,
            "allow_writing_files": False,
        }
        model = CatBoostRegressor(**params)
        model.fit(
            Pool(fit_df[feats + CAT_FEATURES],
                 fit_df["target_delay_s"].to_numpy(float),
                 cat_features=CAT_FEATURES),
            eval_set=Pool(inner_eval_df[feats + CAT_FEATURES],
                          inner_eval_df["target_delay_s"].to_numpy(float),
                          cat_features=CAT_FEATURES),
        )
        for j, df in enumerate(pred_dfs):
            preds[j].append(
                np.asarray(model.predict(Pool(df[feats + CAT_FEATURES],
                                              cat_features=CAT_FEATURES)), float)
            )
    return [np.mean(p, axis=0) for p in preds]


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

    f_train = f_train.sort_values("T", kind="stable").reset_index(drop=True)
    features = make_pools(f_train, f_test)
    y_train = f_train["target_delay_s"].to_numpy(float)

    results: dict = {"n_features": len(features)}

    # --- 1. OOF вероятности режимов + качество классификаторов ---
    proba_train = {}
    proba_test = {}
    for name, fn in TARGETS.items():
        label = fn(y_train)
        oof, fold_auc = oof_probabilities(f_train, label, features)
        label_test = fn(y_test)
        p_test = clf_fit_predict(f_train, label, f_test, features)
        results[name] = {
            "train_pos_rate": round(float(label.mean()), 3),
            "test_pos_rate": round(float(label_test.mean()), 3),
            "fold_auc": fold_auc,
            "oof_auc_folds1plus": round(
                float(
                    roc_auc_score(
                        label[~np.isnan(oof)], oof[~np.isnan(oof)]
                    )
                ),
                3,
            ),
            "test_auc": round(float(roc_auc_score(label_test, p_test)), 3),
        }
        proba_train[name] = oof
        proba_test[name] = p_test
        # decile table на test: ловит ли p_very_late недопрогнозированный хвост
        dec = pd.qcut(p_test, 5, duplicates="drop")
        results[name]["test_deciles"] = {
            str(d): {
                "n": int((dec == d).sum()),
                "mean_p": round(float(p_test[dec == d].mean()), 3),
                "pos_rate": round(float(label_test[dec == d].mean()), 3),
                "mean_target": round(float(y_test[dec == d].mean()), 1),
            }
            for d in dec.categories
        }

    # --- 2. Stack: p_very_late/p_early как доп. признаки регрессора ---
    n_tail = int(len(f_train) * TAIL_FRACTION)
    # OOF есть только для fold1..4 (fold0 — без истории); строки fold0 исключаем
    # из BOTH вариантов, чтобы сравнение base/stack осталось честным.
    m = ~np.isnan(proba_train["p_very_late"])
    fit_rows = f_train.iloc[:int(n_tail * 0.85)]
    fit_rows = fit_rows[m[: len(fit_rows)]]
    eval_rows = f_train.iloc[int(n_tail * 0.85):n_tail]
    eval_rows = eval_rows[m[int(n_tail * 0.85):n_tail]]
    tail = f_train.iloc[n_tail:]
    tail = tail[m[n_tail:]]

    stack_cols = pd.DataFrame({k: proba_train[k] for k in TARGETS}, index=f_train.index)

    def with_proba(df: pd.DataFrame) -> pd.DataFrame:
        extra = stack_cols.loc[df.index].reset_index(drop=True)
        return pd.concat([df.reset_index(drop=True), extra], axis=1)

    fit_stack, eval_stack, tail_stack = (with_proba(d) for d in (fit_rows, eval_rows, tail))
    test_stack = pd.concat(
        [f_test.reset_index(drop=True),
         pd.DataFrame({k: proba_test[k] for k in TARGETS})],
        axis=1,
    )

    base_feats = features
    stack_feats = features + list(TARGETS.keys())
    y_tail = tail["target_delay_s"].to_numpy(float)
    p_plain_tail, p_plain_test = reg_fit_predict(
        fit_rows, eval_rows, [tail, f_test], base_feats, SEEDS_REG
    )
    p_stack_tail, p_stack_test = reg_fit_predict(
        fit_stack, eval_stack, [tail_stack, test_stack], stack_feats, SEEDS_REG
    )
    results["stacking"] = {
        "plain_tail_mae": round(mae(p_plain_tail, y_tail), 2),
        "stack_tail_mae": round(mae(p_stack_tail, y_tail), 2),
        "plain_test_mae": round(mae(p_plain_test, y_test), 2),
        "stack_test_mae": round(mae(p_stack_test, y_test), 2),
        "stack_vs_plain_test_paired": paired_stats(p_stack_test, p_plain_test, y_test),
    }
    # gain именно на very_late-подвыборке test
    vl = y_test > 180
    results["stacking"]["mae_on_test_very_late"] = {
        "plain": round(mae(p_plain_test[vl], y_test[vl]), 2),
        "stack": round(mae(p_stack_test[vl], y_test[vl]), 2),
        "n": int(vl.sum()),
    }

    out = PROCESSED / "exp_regime.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=float))
    print(json.dumps(
        {k: v for k, v in results.items() if k not in ("p_very_late", "p_early")},
        indent=2, ensure_ascii=False, default=float,
    ))
    for k in TARGETS:
        print(k, "test_auc:", results[k]["test_auc"],
              "oof_auc:", results[k]["oof_auc_folds1plus"],
              "deciles:", json.dumps(results[k]["test_deciles"], ensure_ascii=False))
    print("saved ->", out)


if __name__ == "__main__":
    main()
