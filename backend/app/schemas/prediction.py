from datetime import datetime

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    tr_id: int = Field(
        ...,
        description="Идентификатор транспортного средства",
    )

    timestamp: datetime = Field(
        ...,
        description="Момент построения прогноза T",
    )

    unit_id: int | None = Field(None, description="NDTP terminal ID, if different from tr_id")

    target_stop_id: int = Field(..., description="ID целевой остановки")
    target_time_begin: datetime = Field(..., description="Плановое время прибытия")
    stop_lat: float = Field(..., description="Широта целевой остановки")
    stop_lon: float = Field(..., description="Долгота целевой остановки")

    lat: float = Field(
        ...,
        description="Широта транспортного средства",
    )

    lon: float = Field(
        ...,
        description="Долгота транспортного средства",
    )

    speed: float = Field(
        ...,
        ge=0,
        description="Текущая скорость в км/ч",
    )

    cur_dev_s: float = Field(
        ...,
        description="Текущее отклонение от расписания в секундах",
    )


class PredictionResponse(BaseModel):
    tr_id: int

    prediction: float = Field(
        ...,
        description="Прогноз задержки через 10–15 минут, сек",
    )

    model_version: str
    model: str | None = None
    model_artifact_sha256: str | None = None
    p_late: float | None = None
    risk_model_version: str | None = None


class StoredPrediction(BaseModel):
    tr_id: int
    unit_id: int
    prediction_time: datetime
    input_event_time: datetime | None = None
    input_received_at: datetime | None = None
    target_stop_id: int
    target_time: datetime
    current_delay_s: float
    predicted_delay_s: float
    model_version: str
    model: str | None = None
    model_artifact_sha256: str | None = None
    produced_at: datetime | None = None
    predicted_arrival: datetime | None = None
    current_delay_source: str = "point_input"
    last_confirmed_stop_id: int | None = None
    last_confirmed_at: datetime | None = None
    source: str = "manual"
    p_late: float | None = None
    risk_model_version: str | None = None
    risk: str = "low"
    risk_source: str = "threshold"
    freshness: str = "fresh"
    matched_segment_index: int | None = None
    matched_progress_m: float | None = None
    matched_lat: float | None = None
    matched_lon: float | None = None
    map_match_distance_m: float | None = None
    map_match_confidence: float | None = None
    map_match_graph_source: str | None = None


class PredictionStatus(BaseModel):
    unit_id: int
    tr_id: int | None = None
    code: str
    updated_at: datetime
