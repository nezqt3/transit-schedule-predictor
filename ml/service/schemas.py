"""Pydantic contracts for the ML inference boundary."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from service.config import settings


class TelemetryPoint(BaseModel):
    event_time: datetime
    receive_time: datetime | None = None
    location_valid: bool
    lat: float | None = None
    lon: float | None = None
    speed: float | None = None
    heading: float | None = None


class PlannedStop(BaseModel):
    tt_action_item_id: int
    time_begin: datetime
    geom: str


class PredictRequest(BaseModel):
    tr_id: int
    T: datetime = Field(..., description="Prediction timestamp")
    cur_dev_s: float
    target_stop_id: int
    target_time_begin: datetime
    stop_lat: float
    stop_lon: float
    telemetry: list[TelemetryPoint] = Field(default_factory=list)
    planned_stops: list[PlannedStop] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_horizon(self):
        """Enforce the competition's target-stop prediction horizon."""
        source_zone = ZoneInfo(settings.source_timezone)
        t = (self.T.replace(tzinfo=source_zone) if self.T.tzinfo is None
             else self.T).astimezone(timezone.utc)
        target = (
            self.target_time_begin.replace(tzinfo=source_zone)
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
    model_artifact_sha256: str | None = None
    p_late: float | None = Field(None, ge=0, le=1)
    risk_model_version: str | None = None


class HealthResponse(BaseModel):
    status: str
    model: str
    model_version: str
    model_artifact_sha256: str | None = None
    risk_model_version: str | None = None
