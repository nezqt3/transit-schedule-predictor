"""FastAPI service for residual delay predictions."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from service.config import settings
from service.schemas import HealthResponse, PredictRequest, PredictResponse
from src.inference.predictor import Predictor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_path = Path(settings.artifacts_dir) / "catboost_residual_mae.cbm"
    app.state.predictor = Predictor(model_path)
    logger.info("ML model loaded: %s", model_path)
    yield
    logger.info("ML service stopped")


app = FastAPI(title="Transport Delay ML", version="1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", model="catboost_residual_mae")


@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest, request: Request) -> PredictResponse:
    predictor: Predictor = request.app.state.predictor
    prediction = predictor.predict(
        tr_id=payload.tr_id,
        T=payload.T,
        cur_dev_s=payload.cur_dev_s,
        target_stop_info={
            "stop_lat": payload.stop_lat,
            "stop_lon": payload.stop_lon,
            "target_time_begin": payload.target_time_begin,
        },
        telemetry=[point.model_dump(exclude_none=True) for point in payload.telemetry],
    )
    logger.info("prediction generated for tr_id=%s", payload.tr_id)
    return PredictResponse(
        prediction=prediction, model="catboost", model_version=predictor.metadata["model_version"]
    )
