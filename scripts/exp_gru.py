"""GRU на поминутной траектории скорости (T-5m .. T).

CatBoost видит траекторию только свёрнутой в средние/окна; GRU получает саму
последовательность (32->27->16->7 за минуты до T) и должен распознавать
паттерн «сбой только начинается», когда cur_dev_s ещё нормальный.

Данные модели: 5 поминутных бакетов средней скорости + маска пропуска, плюс
скаляры cur_dev_s / time_to_stop_s / dist_to_stop_m / current_speed.
Протокол прежний: time-tail OOF для отбора и выбора веса blend, labels_test —
один раз.

Запуск из корня:  python scripts/exp_gru.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "scripts"))

from exp_catboost_archive import ARCHIVE_FEATURES, BASE_NUMERIC, CAT_FEATURES  # noqa: E402
from exp_models_defg import DYNAMIC_FEATURES, mae, paired_stats  # noqa: E402
from exp_precursor_k import PRECURSOR, fit_seed  # noqa: E402
from exp_blend_errors import G_PARAMS, TAIL_FRACTION  # noqa: E402
from exp_segment_ensemble import SEGMENT_FEATURES, read  # noqa: E402
from src.features import (  # noqa: E402
    _cell_ids,
    _vehicle_arrays,
    build_features,
    make_stops_lookup,
)

PROCESSED = ROOT / "data" / "processed"
STEPS = 5
SEEDS = [42, 1337, 2026]
torch.manual_seed(42)


def build_sequences(
    traffic: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(seq [n,STEPS,2] = speed+mask, scalars [n,4], present mask [n])."""
    traffic = traffic.copy()
    traffic["event_time"] = pd.to_datetime(traffic["event_time"])
    traffic["_cell"] = _cell_ids(
        pd.to_numeric(traffic["lat"], errors="coerce").to_numpy(float),
        pd.to_numeric(traffic["lon"], errors="coerce").to_numpy(float),
    )
    by_vehicle = {
        tr: _vehicle_arrays(g) for tr, g in traffic.groupby("tr_id", sort=False)
    }
    seqs, scal, present = [], [], []
    for s in labels.itertuples(index=False):
        arr = by_vehicle.get(s.tr_id)
        seq = np.zeros((STEPS, 2), np.float32)
        if arr is None:
            seqs.append(seq)
            scal.append([0.0, 0.0, 0.0, 0.0])
            present.append(False)
            continue
        t_s = int(np.datetime64(s.T, "s").astype(np.int64))
        hi = int(np.searchsorted(arr["times"], t_s, side="right"))
        last = hi - 1
        for k in range(STEPS):
            lo = int(np.searchsorted(arr["times"], t_s - (STEPS - k) * 60, "left"))
            hi_k = int(np.searchsorted(arr["times"], t_s - (STEPS - k - 1) * 60, "left"))
            sp = arr["speed"][lo:hi_k]
            sp = sp[~np.isnan(sp)]
            if len(sp):
                seq[k, 0] = float(sp.mean())
                seq[k, 1] = 1.0
        cur = arr["speed"][last] if last >= 0 else np.nan
        gap = (t_s - arr["times"][last]) if last >= 0 else 300.0
        present.append(last >= 0)
        seqs.append(seq)
        scal.append([
            float(s.cur_dev_s) if pd.notna(s.cur_dev_s) else 0.0,
            (s.target_time_begin - s.T).total_seconds(),
            float(cur) if not np.isnan(cur) else 0.0,
            float(gap),
        ])
    return np.array(seqs), np.array(scal), np.array(present)


class GRUModel(nn.Module):
    def __init__(self, n_scalars: int = 4, hidden: int = 64):
        super().__init__()
        self.gru = nn.GRU(2, hidden, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(hidden + n_scalars, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, seq: torch.Tensor, scal: torch.Tensor) -> torch.Tensor:
        h, _ = self.gru(seq)
        out = self.head(torch.cat([h[:, -1], scal], dim=1))
        return out.squeeze(-1)


def train_gru(
    seq_tr, scl_tr, y_tr, seq_va, scl_va, y_va, seed: int, epochs: int = 120
) -> tuple[nn.Module, dict]:
    torch.manual_seed(seed)
    mu, sd = seq_tr[:, :, 0].mean(), seq_tr[:, :, 0].std()
    smu, ssd = scl_tr.mean(axis=0), np.where(scl_tr.std(axis=0) > 0, scl_tr.std(axis=0), 1)
    ymu, ysd = y_tr.mean(), y_tr.std()

    def prep(seq, scl, y=None):
        s = (seq[:, :, 0] - mu) / sd
        s = np.where(seq[:, :, 1] > 0, s, 0.0)
        x = np.stack([s, seq[:, :, 1]], axis=2).astype(np.float32)
        z = ((scl - smu) / ssd).astype(np.float32)
        ty = (
            torch.tensor(((y - ymu) / ysd).astype(np.float32))
            if y is not None
            else None
        )
        return (torch.tensor(x), torch.tensor(z)), ty

    (xtr, ztr), ytr = prep(seq_tr, scl_tr, y_tr)
    (xva, zva), yva = prep(seq_va, scl_va, y_va)
    model = GRUModel()
    opt = torch.optim.Adam(model.parameters(), lr=3e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    lossf = nn.L1Loss()
    best, best_state, patience = float("inf"), None, 0
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(ytr))
        for i in range(0, len(perm), 256):
            idx = perm[i : i + 256]
            opt.zero_grad()
            loss = lossf(model(xtr[idx], ztr[idx]), ytr[idx])
            loss.backward()
            opt.step()
        sched.step()
        model.eval()
        with torch.no_grad():
            vl = float(lossf(model(xva, zva), yva))
        if vl < best - 1e-4:
            best, patience = vl, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            patience += 1
            if patience >= 15:
                break
    model.load_state_dict(best_state)
    meta = {"mu": mu, "sd": sd, "smu": smu, "ssd": ssd, "ymu": ymu, "ysd": ysd,
            "best_val_loss": best, "epochs_run": ep + 1}
    return model, meta


def predict(model, meta, seq, scl) -> np.ndarray:
    s = (seq[:, :, 0] - meta["mu"]) / meta["sd"]
    s = np.where(seq[:, :, 1] > 0, s, 0.0)
    x = np.stack([s, seq[:, :, 1]], axis=2).astype(np.float32)
    z = ((scl - meta["smu"]) / meta["ssd"]).astype(np.float32)
    model.eval()
    with torch.no_grad():
        out = model(torch.tensor(x), torch.tensor(z)).numpy()
    return out * meta["ysd"] + meta["ymu"]


def main() -> None:
    traffic = read("train_traffic", ("event_time",))
    labels_train = read("labels_train", ("T", "target_time_begin"))
    labels_test = read("labels_test", ("T", "target_time_begin"))
    stops = make_stops_lookup(
        read("train_schedule"), read("test_schedule"), read("validate_schedule_plan")
    )
    f_train = build_features(traffic, labels_train, stops)
    f_test = build_features(read("test_traffic", ("event_time",)), labels_test, stops)

    seq_tr, scl_tr, _ = build_sequences(traffic, labels_train)
    seq_te, scl_te, _ = build_sequences(read("test_traffic", ("event_time",)), labels_test)

    # f_train/f_test: строки в исходном порядке labels, дальше сортируем по T
    f_train = f_train.sort_values("T", kind="stable").reset_index(drop=True)
    y = f_train["target_delay_s"].to_numpy(float)
    split = int(len(y) * TAIL_FRACTION)
    y_te = f_test["target_delay_s"].to_numpy(float)

    # GRU учим на тех же строках: траектории сопоставляем по sample_id
    order = labels_train.sort_values("T", kind="stable").reset_index(drop=True)
    key_tr = {r.sample_id: i for i, r in labels_train.iterrows()}
    idx_tr = np.array([key_tr[s] for s in order["sample_id"]])
    seq_fit, scl_fit, y_fit = seq_tr[idx_tr[:split]], scl_tr[idx_tr[:split]], y[:split]
    seq_val, scl_val, y_val = seq_tr[idx_tr[split:]], scl_tr[idx_tr[split:]], y[split:]

    preds_val, preds_te = [], []
    metas = []
    for seed in SEEDS:
        m, meta = train_gru(seq_fit, scl_fit, y_fit, seq_val, scl_val, y_val, seed)
        preds_val.append(predict(m, meta, seq_val, scl_val))
        preds_te.append(predict(m, meta, seq_te, scl_te))
        metas.append({k: (float(v) if np.isscalar(v) else None) for k, v in meta.items() if k == "epochs_run"})
    gru_val = np.mean(preds_val, axis=0)
    gru_test = np.mean(preds_te, axis=0)

    # CatBoost-референс (тот же K-набор фич, те же seed'ы) для blend
    champ = BASE_NUMERIC + ARCHIVE_FEATURES
    feats = champ + [
        f for f in DYNAMIC_FEATURES + SEGMENT_FEATURES + PRECURSOR
        if f in f_train.columns
    ]
    cb_val, cb_te = [], []
    for seed in SEEDS:
        tv, sv, _ = fit_seed(f_train, f_test, feats, G_PARAMS, seed)
        cb_val.append(tv)
        cb_te.append(sv)
    cb_val = np.mean(cb_val, axis=0)
    cb_te = np.mean(cb_te, axis=0)

    # вес blend только по tail-OOF
    alphas = np.arange(0, 0.55, 0.05)
    tail_scores = [round(mae(a * gru_val + (1 - a) * cb_val, y_val), 2) for a in alphas]
    best_a = float(alphas[int(np.argmin(tail_scores))])
    blend_test = best_a * gru_test + (1 - best_a) * cb_te

    results = {
        "gru_tail_mae": round(mae(gru_val, y_val), 2),
        "catboost_tail_mae": round(mae(cb_val, y_val), 2),
        "gru_test_mae": round(mae(gru_test, y_te), 2),
        "catboost_test_mae": round(mae(cb_te, y_te), 2),
        "blend_alpha_by_tail": best_a,
        "blend_tail_mae": min(tail_scores),
        "blend_test_mae_one_shot": round(mae(blend_test, y_te), 2),
        "blend_vs_catboost_paired": paired_stats(blend_test, cb_te, y_te),
        "gru_vs_catboost_paired": paired_stats(gru_test, cb_te, y_te),
        "alpha_curve_tail": dict(zip([round(float(a), 2) for a in alphas], tail_scores)),
    }

    # фокус: very_late со «нормальным» cur_dev — куда GRU заточен
    y_te_full = y_te
    cur_dev = f_test["cur_dev_s"].to_numpy(float)
    focus = (y_te_full > 180) & (cur_dev < 60)
    results["focus_very_late_dev_normal"] = {
        "n": int(focus.sum()),
        "gru_mae": round(mae(gru_test[focus], y_te_full[focus]), 2) if focus.any() else None,
        "catboost_mae": round(mae(cb_te[focus], y_te_full[focus]), 2) if focus.any() else None,
        "blend_mae": round(mae(blend_test[focus], y_te_full[focus]), 2) if focus.any() else None,
    }

    out = PROCESSED / "exp_gru.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=float))
    print(json.dumps(results, indent=2, ensure_ascii=False, default=float))
    print("saved ->", out)


if __name__ == "__main__":
    main()
