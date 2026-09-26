"""FastAPI service for residual delay predictions."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from service.config import settings
from service.schemas import HealthResponse, PredictRequest, PredictResponse
from src.inference.baseline import BaselinePredictor
from src.inference.lightgbm_plan import LightGBMPlanPredictor
from src.inference.predictor import Predictor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.model_name == "baseline":
        app.state.predictor = BaselinePredictor(settings.model_version)
    elif settings.model_name == "lightgbm_plan":
        app.state.predictor = LightGBMPlanPredictor(
            Path(settings.artifacts_dir), Path(settings.schedule_plan_path),
            settings.source_timezone,
        )
    elif settings.model_name == "catboost":
        app.state.predictor = Predictor(
            Path(settings.artifacts_dir) / "catboost_residual_mae.cbm"
        )
    else:
        raise RuntimeError(f"unsupported MODEL_NAME: {settings.model_name}")
    logger.info("ML model loaded: %s", settings.model_name)
    yield
    logger.info("ML service stopped")


app = FastAPI(title="Transport Delay ML", version="1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    metadata = request.app.state.predictor.metadata
    return HealthResponse(
        status="ok", model=settings.model_name,
        model_version=metadata["model_version"],
        model_artifact_sha256=metadata.get("model_artifact_sha256"),
        risk_model_version=metadata.get("risk_model_version"),
    )


@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest, request: Request) -> PredictResponse:
    predictor: BaselinePredictor | Predictor | LightGBMPlanPredictor = (
        request.app.state.predictor
    )
    inputs = dict(
        tr_id=payload.tr_id,
        T=payload.T,
        cur_dev_s=payload.cur_dev_s,
        target_stop_info={
            "target_stop_id": payload.target_stop_id,
            "stop_lat": payload.stop_lat,
            "stop_lon": payload.stop_lon,
            "target_time_begin": payload.target_time_begin,
        },
        telemetry=[point.model_dump(exclude_none=True) for point in payload.telemetry],
    )
    if isinstance(predictor, LightGBMPlanPredictor):
        inputs["planned_stops"] = [stop.model_dump(mode="json")
                                    for stop in payload.planned_stops]
    prediction = predictor.predict(**inputs)
    logger.info("prediction generated for tr_id=%s", payload.tr_id)
    return PredictResponse(
        prediction=prediction, model=settings.model_name,
        model_version=predictor.metadata["model_version"],
        model_artifact_sha256=predictor.metadata.get("model_artifact_sha256"),
        p_late=(predictor.predict_risk(prediction)
                if isinstance(predictor, LightGBMPlanPredictor) else None),
        risk_model_version=predictor.metadata.get("risk_model_version"),
    )
