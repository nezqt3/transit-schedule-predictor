"""Validated weighted blends of delay predictions in seconds."""

from __future__ import annotations

import numpy as np
import pandas as pd


def blend_predictions(predictions: list[np.ndarray], weights: list[float]) -> np.ndarray:
    """Average aligned prediction arrays after checking weights and finite values."""
    if not predictions or len(predictions) != len(weights):
        raise ValueError("Provide one weight for each prediction array")
    weight_array = np.asarray(weights, dtype=float)
    if np.any(weight_array < 0) or not np.isclose(weight_array.sum(), 1):
        raise ValueError("Blend weights must be nonnegative and sum to one")
    arrays = [np.asarray(prediction, dtype=float) for prediction in predictions]
    if any(array.shape != arrays[0].shape or not np.isfinite(array).all() for array in arrays):
        raise ValueError("Predictions must be finite arrays of the same shape")
    return np.average(np.stack(arrays), axis=0, weights=weight_array)


class CatBoostTorchEnsemble:
    """Combine two CatBoost models and an optional PyTorch model on shared features."""

    def __init__(
        self,
        residual_model_path: str,
        direct_model_path: str,
        torch_model_path: str,
        torch_weight: float,
    ) -> None:
        if not 0 <= torch_weight <= 1:
            raise ValueError("torch_weight must be in [0, 1]")
        from src.models.torch_model import TorchTabularRegressor

        if torch_weight < 1:
            from catboost import CatBoostRegressor

            self.residual_model = CatBoostRegressor()
            self.residual_model.load_model(residual_model_path)
            self.direct_model = CatBoostRegressor()
            self.direct_model.load_model(direct_model_path)
        self.torch_model = TorchTabularRegressor.load(torch_model_path)
        self.torch_weight = torch_weight

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Predict schedule deviation in seconds for each feature row."""
        from src.features_simple import FEATURE_COLUMNS

        if self.torch_weight == 1:
            return self.torch_model.predict(features)
        residual = features["cur_dev_s"].to_numpy(float) + self.residual_model.predict(
            features[FEATURE_COLUMNS]
        )
        direct = self.direct_model.predict(features[FEATURE_COLUMNS])
        catboost = blend_predictions([residual, direct], [0.5, 0.5])
        if self.torch_weight == 0:
            return catboost
        return blend_predictions(
            [catboost, self.torch_model.predict(features)],
            [1 - self.torch_weight, self.torch_weight],
        )
