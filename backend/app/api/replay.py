"""Historical CSV playback API; isolated from the random NDTP stream."""

from fastapi import APIRouter, HTTPException, Request

from app.schemas.replay import ReplayPrediction, ReplayScenario, ReplayVehicle
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


@router.get("/vehicles/{tr_id}", response_model=ReplayScenario,
            summary="Телеметрия, план и точки прогноза для исторического прогона")
async def get_replay_scenario(tr_id: int, request: Request) -> ReplayScenario:
    scenario = _dataset(request).scenario(tr_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="replay vehicle not found")
    return scenario


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
