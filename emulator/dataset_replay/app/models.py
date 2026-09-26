from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class TimeMode(StrEnum):
    ORIGINAL = "original"
    SHIFT_TO_NOW = "shift_to_now"


class ReplayState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class TelemetryRow(BaseModel):
    tr_id: int
    unit_id: int
    event_time: datetime
    receive_time: datetime
    latitude: float | None
    longitude: float | None
    altitude_m: float | None = None
    speed_kmh: float | None = None
    heading: float | None = None
    location_valid: bool

    @property
    def available_at(self) -> datetime:
        """Time when the original system could actually observe this row."""
        return max(self.event_time, self.receive_time)


class ScenarioSummary(BaseModel):
    tr_id: int
    unit_id: int
    packets: int
    valid_packets: int
    starts_at: datetime
    ends_at: datetime
    duration_s: float


class ReplayStartRequest(BaseModel):
    dataset: str = Field("validate", pattern=r"^[A-Za-z0-9_-]+$")
    tr_ids: list[int] = Field(..., min_length=1, max_length=100)
    time_mode: TimeMode = TimeMode.SHIFT_TO_NOW
    valid_locations_only: bool = True
    start_at: datetime | None = None
    end_at: datetime | None = None
    loop: bool = False
    target_host: str | None = Field(None, min_length=1)
    target_port: int | None = Field(None, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_range(self) -> "ReplayStartRequest":
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValueError("start_at must be earlier than end_at")
        if len(set(self.tr_ids)) != len(self.tr_ids):
            raise ValueError("tr_ids must be unique")
        return self


class UnitReplayStatus(BaseModel):
    tr_id: int
    unit_id: int
    sent_packets: int = 0
    total_packets: int
    connected: bool = False
    source_time: datetime | None = None
    emulated_time: datetime | None = None
    last_error: str | None = None


class ReplayStatus(BaseModel):
    state: ReplayState = ReplayState.IDLE
    dataset: str | None = None
    time_mode: TimeMode | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    sent_packets: int = 0
    total_packets: int = 0
    progress: float = 0.0
    units: list[UnitReplayStatus] = Field(default_factory=list)
    error: str | None = None
