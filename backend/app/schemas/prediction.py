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
