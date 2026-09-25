"""Small PyTorch tabular regressor for delay prediction in seconds."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from src.features_simple import FEATURE_COLUMNS


class _DelayNet(nn.Module):
    def __init__(self, input_size: int) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(input_size, 64), nn.ReLU(), nn.Dropout(0.10),
            nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.layers(features).squeeze(1)


class TorchTabularRegressor:
    """Fit a compact MLP on the same point-in-time features as CatBoost."""

    def __init__(self, target_mode: str = "direct", seed: int = 42) -> None:
        if target_mode not in {"direct", "residual"}:
            raise ValueError("target_mode must be 'direct' or 'residual'")
        self.target_mode = target_mode
        self.seed = seed
        self.numeric_columns = [column for column in FEATURE_COLUMNS if column != "tr_id"]
        self.model: _DelayNet | None = None

    def _prepare(self, features: pd.DataFrame, fit: bool = False) -> np.ndarray:
        values = features[self.numeric_columns].apply(pd.to_numeric, errors="coerce").to_numpy(float, copy=True)
        values[~np.isfinite(values)] = np.nan
        missing = np.isnan(values).astype(np.float32)
        if fit:
            with np.errstate(all="ignore"):
                median = np.nanmedian(values, axis=0)
                lower = np.nanpercentile(values, 25, axis=0)
                upper = np.nanpercentile(values, 75, axis=0)
            self.median = np.where(np.isfinite(median), median, 0.0)
            spread = upper - lower
            self.scale = np.where(np.isfinite(spread) & (spread > 1e-6), spread, 1.0)
            self.vehicles = sorted(features["tr_id"].astype(str).unique().tolist())
        scaled = np.clip((np.where(np.isnan(values), self.median, values) - self.median)
                         / self.scale, -12, 12).astype(np.float32)
        ids = features["tr_id"].astype(str).to_numpy()
        vehicle_one_hot = np.column_stack([ids == vehicle for vehicle in self.vehicles]).astype(np.float32)
        return np.concatenate([scaled, missing, vehicle_one_hot], axis=1)

    def _target(self, y: np.ndarray, features: pd.DataFrame) -> np.ndarray:
        target = np.asarray(y, dtype=float).copy()
        if self.target_mode == "residual":
            target -= features["cur_dev_s"].to_numpy(float)
        return target

    def fit(
        self,
        features: pd.DataFrame,
        y: np.ndarray,
        *,
        epochs: int = 120,
        valid_features: pd.DataFrame | None = None,
        valid_y: np.ndarray | None = None,
        patience: int = 20,
    ) -> dict[str, float | int]:
        """Train on earlier observations; optionally select epochs on a later split."""
        torch.set_num_threads(1)
        torch.manual_seed(self.seed)
        x = torch.from_numpy(self._prepare(features, fit=True))
        target = self._target(np.asarray(y), features)
        self.target_center = float(np.median(target))
        self.target_scale = float(max(np.std(target), 1.0))
        t = torch.tensor((target - self.target_center) / self.target_scale, dtype=torch.float32)
        self.model = _DelayNet(x.shape[1])
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=1e-3, weight_decay=1e-3)
        validation = valid_features is not None and valid_y is not None
        if validation:
            vx = torch.from_numpy(self._prepare(valid_features))
            vy = np.asarray(valid_y, dtype=float)
            vcur = valid_features["cur_dev_s"].to_numpy(float)
        best_mae = float("inf")
        best_state = None
        best_epoch = epochs
        stale = 0
        for epoch in range(1, epochs + 1):
            self.model.train()
            for batch in torch.randperm(len(x)).split(128):
                optimizer.zero_grad()
                loss = nn.functional.l1_loss(self.model(x[batch]), t[batch])
                loss.backward()
                optimizer.step()
            if not validation:
                continue
            self.model.eval()
            with torch.no_grad():
                pred = self.model(vx).numpy() * self.target_scale + self.target_center
            if self.target_mode == "residual":
                pred += vcur
            mae = float(np.mean(np.abs(pred - vy)))
            if mae < best_mae - 0.02:
                best_mae = mae
                best_epoch = epoch
                best_state = {key: value.clone() for key, value in self.model.state_dict().items()}
                stale = 0
            else:
                stale += 1
                if stale >= patience:
                    break
        if best_state is not None:
            self.model.load_state_dict(best_state)
        return {"best_epoch": best_epoch, "validation_mae": best_mae}

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return predicted delay in seconds, aligned with input rows."""
        if self.model is None:
            raise RuntimeError("Torch model is not fitted")
        self.model.eval()
        x = torch.from_numpy(self._prepare(features))
        with torch.no_grad():
            pred = self.model(x).numpy().astype(float) * self.target_scale + self.target_center
        if self.target_mode == "residual":
            pred += features["cur_dev_s"].to_numpy(float)
        return pred

    def save(self, path: Path) -> None:
        """Save CPU weights and the feature scaling needed for inference."""
        if self.model is None:
            raise RuntimeError("Torch model is not fitted")
        torch.save({
            "state_dict": self.model.state_dict(), "target_mode": self.target_mode,
            "seed": self.seed, "numeric_columns": self.numeric_columns,
            "median": self.median.tolist(), "scale": self.scale.tolist(), "vehicles": self.vehicles,
            "target_center": self.target_center, "target_scale": self.target_scale,
        }, path)

    @classmethod
    def load(cls, path: Path) -> TorchTabularRegressor:
        """Load an artifact produced by :meth:`save`."""
        state = torch.load(path, map_location="cpu", weights_only=True)
        result = cls(state["target_mode"], state["seed"])
        result.numeric_columns = state["numeric_columns"]
        result.median = np.asarray(state["median"])
        result.scale = np.asarray(state["scale"])
        result.vehicles = state["vehicles"]
        result.target_center = state["target_center"]
        result.target_scale = state["target_scale"]
        result.model = _DelayNet(2 * len(result.numeric_columns) + len(result.vehicles))
        result.model.load_state_dict(state["state_dict"])
        return result
