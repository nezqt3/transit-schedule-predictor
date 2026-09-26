"""API contracts for the historical CSV playback, separate from live NDTP."""

from datetime import datetime

from pydantic import BaseModel


class ReplayVehicle(BaseModel):
    tr_id: int
    unit_id: int
    samples: int
    start_at: datetime
    end_at: datetime


class ReplayTelemetry(BaseModel):
    available_at: datetime
    event_time: datetime
    lat: float
    lon: float
    speed: float | None
    heading: float | None = None


class ReplayStop(BaseModel):
    stop_id: int
    planned_at: datetime
    lat: float
    lon: float
    place_id: str = ""
    address: str | None = None
    gps_confirmed: bool = False
    gps_distance_m: float | None = None


class ReplayPoint(BaseModel):
    sample_id: str
    T: datetime
    target_stop_id: int
    target_time_begin: datetime
    cur_dev_s: float
    actual_delay_s: float
    actual_at: datetime
    lat: float
    lon: float


class ReplayScenario(BaseModel):
    source: str = "historical_csv_test"
    vehicle: ReplayVehicle
    telemetry: list[ReplayTelemetry]
    stops: list[ReplayStop]
    points: list[ReplayPoint]


class ReplayPrediction(BaseModel):
    sample_id: str
    predicted_delay_s: float
    baseline_delay_s: float
    model_version: str


class ReplayRun(BaseModel):
    run_id: str
    tr_id: int
    start_at: datetime
    end_at: datetime
    stop_ids: list[int]
    confirmed_stops: int
    valid: bool


class ReplayFleetVehicle(BaseModel):
    tr_id: int
    unit_id: int
    telemetry: list[ReplayTelemetry]
    stops: list[ReplayStop]
    runs: list[ReplayRun]
    points: list[ReplayPoint]


class ReplayFleet(BaseModel):
    source: str = "historical_csv_test"
    start_at: datetime
    end_at: datetime
    vehicles: list[ReplayFleetVehicle]


class ReplayStreamStatus(BaseModel):
    state: str
    source_at: datetime | None
    time_mode: str | None
    speed_multiplier: float
    sent_packets: int
    total_packets: int
