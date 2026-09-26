from fastapi import APIRouter, Depends

from app.api.auth import router as auth_router
from app.api.dependencies import get_current_user
from app.api.health import router as health_router
from app.api.predictions import predict_from_buffer
from app.api.predictions import router as predictions_router
from app.api.vehicles import router as vehicles_router

api_router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(get_current_user)])

api_router.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"],
)

protected_router.include_router(
    predictions_router,
    prefix="/predictions",
    tags=["Predictions"],
)

protected_router.add_api_route(
    "/predict", predict_from_buffer, methods=["GET"],
    tags=["Predictions"], summary="Прогноз по накопленной NDTP-телеметрии",
)

protected_router.include_router(
    vehicles_router,
    prefix="/vehicles",
    tags=["Vehicles"],
)

api_router.include_router(protected_router)
