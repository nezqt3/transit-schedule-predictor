"""Pydantic contracts for the ML inference boundary."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


class TelemetryPoint(BaseModel):
    event_time: datetime
    receive_time: datetime | None = None
    location_valid: bool
    lat: float
    lon: float
    speed: float | None = None
    heading: float | None = None


class PredictRequest(BaseModel):
    tr_id: int
    T: datetime = Field(..., description="Prediction timestamp")
    cur_dev_s: float
    target_stop_id: int
    target_time_begin: datetime
    stop_lat: float
    stop_lon: float
    telemetry: list[TelemetryPoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_horizon(self):
        """Enforce the competition's target-stop prediction horizon."""
        t = self.T.replace(tzinfo=timezone.utc) if self.T.tzinfo is None else self.T.astimezone(timezone.utc)
        target = (
            self.target_time_begin.replace(tzinfo=timezone.utc)
            if self.target_time_begin.tzinfo is None
            else self.target_time_begin.astimezone(timezone.utc)
        )
        if not 600 < (target - t).total_seconds() <= 900:
            raise ValueError("target stop must be in (T+10m, T+15m]")
        return self


class PredictResponse(BaseModel):
    prediction: float = Field(..., description="Predicted delay in seconds")
    model: str
    model_version: str


class HealthResponse(BaseModel):
    status: str
    model: str
