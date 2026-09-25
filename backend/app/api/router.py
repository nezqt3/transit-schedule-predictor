from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.predictions import predict_from_buffer
from app.api.predictions import router as predictions_router
from app.api.vehicles import router as vehicles_router
from app.api.replay import router as replay_router
from app.api.ws import router as ws_router

api_router = APIRouter()

api_router.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    predictions_router,
    prefix="/predictions",
    tags=["Predictions"],
)

api_router.add_api_route(
    "/predict", predict_from_buffer, methods=["GET"],
    tags=["Predictions"], summary="Прогноз по накопленной NDTP-телеметрии",
)

api_router.include_router(
    vehicles_router,
    prefix="/vehicles",
    tags=["Vehicles"],
)

api_router.include_router(ws_router)
api_router.include_router(replay_router, prefix="/replay", tags=["Historical replay"])
