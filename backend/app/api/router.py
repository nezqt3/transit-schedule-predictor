from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.predictions import router as predictions_router
from app.api.vehicles import router as vehicles_router

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

api_router.include_router(
    vehicles_router,
    prefix="/vehicles",
    tags=["Vehicles"],
)