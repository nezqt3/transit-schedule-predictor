from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from app.schemas.prediction import (
    PredictionRequest,
    PredictionResponse,
    StoredPrediction,
)
from app.services.prediction import predict_delay

router = APIRouter()


@router.get("", response_model=list[StoredPrediction],
            summary="Последние прогнозы по транспортным средствам")
async def list_predictions(http_request: Request) -> list[StoredPrediction]:
    return http_request.app.state.predictions.list_latest()


@router.get("/{tr_id}/latest", response_model=StoredPrediction,
            summary="Последний прогноз транспортного средства")
async def latest_prediction(tr_id: int, http_request: Request) -> StoredPrediction:
    prediction = http_request.app.state.predictions.get_latest(tr_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    return prediction


@router.post(
    "",
    response_model=PredictionResponse,
    summary="Получить прогноз задержки",
    description=(
        "Возвращает прогноз отклонения транспортного средства "
        "от расписания на горизонте 10–15 минут."
    ),
)
async def predict(
    request: PredictionRequest,
    http_request: Request,
) -> PredictionResponse:
    """
    Выполняет прогноз задержки транспортного средства.

    Передаёт текущую точку и накопленную NDTP-историю в ML Service.

    Args:
        request:
            Текущее состояние транспортного средства.

    Returns:
        PredictionResponse:
            Прогноз задержки в секундах.
    """

    result = await predict_delay(
        http_request.app.state.telemetry,
        http_request.app.state.ml_client,
        tr_id=request.tr_id,
        unit_id=request.unit_id or request.tr_id,
        T=request.timestamp,
        cur_dev_s=request.cur_dev_s,
        target_stop_id=request.target_stop_id,
        target_time_begin=request.target_time_begin,
        stop_lat=request.stop_lat,
        stop_lon=request.stop_lon,
        current_point={
            "event_time": request.timestamp.isoformat(),
            "receive_time": request.timestamp.isoformat(),
            "location_valid": True,
            "lat": request.lat,
            "lon": request.lon,
            "speed": request.speed,
        },
    )
    http_request.app.state.predictions.record(StoredPrediction(
        tr_id=request.tr_id,
        unit_id=request.unit_id or request.tr_id,
        prediction_time=request.timestamp,
        target_stop_id=request.target_stop_id,
        target_time=request.target_time_begin,
        current_delay_s=request.cur_dev_s,
        predicted_delay_s=result["prediction"],
        model_version=result["model_version"],
    ))
    return PredictionResponse(
        tr_id=request.tr_id,
        prediction=result["prediction"],
        model_version=result["model_version"],
    )


@router.get("/predict", response_model=PredictionResponse,
            summary="Прогноз по накопленной NDTP-телеметрии")
async def predict_from_buffer(
    http_request: Request,
    tr_id: int,
    T: datetime,
    cur_dev_s: float,
    target_stop_id: int,
    unit_id: int | None = None,
    target_time_begin: datetime | None = None,
    stop_lat: float | None = None,
    stop_lon: float | None = None,
) -> PredictionResponse:
    lookup = http_request.app.state.runtime_lookup
    stop = lookup.stops.get(target_stop_id)
    explicit_stop = (target_time_begin, stop_lat, stop_lon)
    if any(value is not None for value in explicit_stop):
        if not all(value is not None for value in explicit_stop):
            raise HTTPException(
                status_code=422,
                detail="provide target_time_begin, stop_lat and stop_lon together",
            )
        stop = {
            "tr_id": tr_id,
            "target_time_begin": target_time_begin,
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
        }
    if stop is None or stop["tr_id"] != tr_id:
        raise HTTPException(status_code=404, detail="target stop not found for vehicle")
    resolved_unit = unit_id or lookup.units.get(tr_id) or tr_id
    if resolved_unit is None:
        raise HTTPException(status_code=404, detail="NDTP unit mapping not found for vehicle")
    result = await predict_delay(
        http_request.app.state.telemetry,
        http_request.app.state.ml_client,
        tr_id=tr_id,
        unit_id=resolved_unit,
        T=T,
        cur_dev_s=cur_dev_s,
        target_stop_id=target_stop_id,
        target_time_begin=(
            stop["target_time_begin"] if isinstance(stop["target_time_begin"], datetime)
            else datetime.fromisoformat(stop["target_time_begin"])
        ),
        stop_lat=stop["stop_lat"],
        stop_lon=stop["stop_lon"],
    )
    http_request.app.state.predictions.record(StoredPrediction(
        tr_id=tr_id,
        unit_id=resolved_unit,
        prediction_time=T,
        target_stop_id=target_stop_id,
        target_time=(stop["target_time_begin"] if isinstance(stop["target_time_begin"], datetime)
                     else datetime.fromisoformat(stop["target_time_begin"])),
        current_delay_s=cur_dev_s,
        predicted_delay_s=result["prediction"],
        model_version=result["model_version"],
    ))
    return PredictionResponse(
        tr_id=tr_id,
        prediction=result["prediction"],
        model_version=result["model_version"],
    )
