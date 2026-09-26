"""Historical CSV playback API; isolated from the random NDTP stream."""

from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.schemas.replay import (
    ReplayFleet,
    ReplayOutcome,
    ReplayPrediction,
    ReplayScenario,
    ReplayStreamStatus,
    ReplayVehicle,
)
from app.services.ml_client import request_prediction

router = APIRouter()


def _dataset(request: Request):
    dataset = request.app.state.replay
    if dataset is None:
        raise HTTPException(status_code=503, detail="historical replay CSV unavailable")
    return dataset


@router.get("/vehicles", response_model=list[ReplayVehicle],
            summary="Транспорт с известным фактом в январской записи")
async def list_replay_vehicles(request: Request) -> list[ReplayVehicle]:
    return _dataset(request).vehicles()


@router.get("/fleet", response_model=ReplayFleet,
            summary="Общая январская шкала, GPS и проверенные рейсы")
async def get_replay_fleet(request: Request) -> ReplayFleet:
    return _dataset(request).public_fleet()


@router.get("/outcomes", response_model=list[ReplayOutcome],
            summary="Факты прибытия, уже наступившие к моменту replay")
async def get_replay_outcomes(as_of: datetime, request: Request) -> list[ReplayOutcome]:
    status = await get_replay_stream_status(request)
    if status.state not in {"running", "paused", "completed"} or status.source_at is None:
        return []
    to_utc = request.app.state.runtime_lookup.to_utc
    observed_until = min(to_utc(as_of), to_utc(status.source_at))
    return _dataset(request).outcomes(observed_until)


@router.get("/stream-status", response_model=ReplayStreamStatus,
            summary="Исходные часы активного NDTP-воспроизведения")
async def get_replay_stream_status(request: Request) -> ReplayStreamStatus:
    if not settings.dataset_replay_url:
        raise HTTPException(status_code=503, detail="dataset NDTP replay is not configured")
    try:
        response = await request.app.state.ml_client.get(
            f"{settings.dataset_replay_url.rstrip('/')}/api/status",
        )
        response.raise_for_status()
        status = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="dataset NDTP replay unavailable") from exc
    source_times = [datetime.fromisoformat(unit["source_time"])
                    for unit in status.get("units", []) if unit.get("source_time")]
    return ReplayStreamStatus(
        state=status["state"], source_at=max(source_times, default=None),
        time_mode=status.get("time_mode"),
        speed_multiplier=status.get("speed_multiplier", 1),
        sent_packets=status.get("sent_packets", 0),
        total_packets=status.get("total_packets", 0),
    )


@router.get("/vehicles/{tr_id}", response_model=ReplayScenario,
            summary="Телеметрия, план и точки прогноза для исторического прогона")
async def get_replay_scenario(tr_id: int, request: Request) -> ReplayScenario:
    scenario = _dataset(request).scenario(tr_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="replay vehicle not found")
    safe = scenario.model_copy(deep=True)
    for point in safe.points:
        point.actual_delay_s = None
        point.actual_at = None
    for stop in safe.stops:
        stop.gps_confirmed = False
        stop.gps_distance_m = None
        stop.gps_confirmed_at = None
    return safe


@router.post("/predict/{sample_id}", response_model=ReplayPrediction,
             summary="Прогноз по январским данным, доступным к моменту T")
async def predict_replay_point(sample_id: str, request: Request) -> ReplayPrediction:
    dataset = _dataset(request)
    payload = dataset.prediction_payload(sample_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="replay sample not found")
    result = await request_prediction(payload, request.app.state.ml_client)
    return ReplayPrediction(
        sample_id=sample_id,
        predicted_delay_s=result["prediction"],
        baseline_delay_s=payload["cur_dev_s"],
        model_version=result["model_version"],
    )
