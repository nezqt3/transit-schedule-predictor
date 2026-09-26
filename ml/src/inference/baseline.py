"""Artifact-free fallback model for a runnable demo environment."""


class BaselinePredictor:
    """Use the current deviation as the 10–15 minute delay forecast."""

    def __init__(self, model_version: str = "cur-dev-1.0") -> None:
        self.metadata = {"model_version": model_version}

    def predict(
        self,
        *,
        tr_id: int,
        T,
        cur_dev_s: float,
        target_stop_info: dict,
        telemetry: list[dict],
    ) -> float:
        """Return the competition's known ``prediction = cur_dev_s`` baseline."""
        del tr_id, T, target_stop_info, telemetry
        return float(cur_dev_s)
