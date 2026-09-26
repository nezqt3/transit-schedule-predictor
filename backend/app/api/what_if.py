"""Dispatcher what-if analysis API."""

from fastapi import APIRouter

from app.schemas.what_if import WhatIfRequest, WhatIfResponse
from app.services.what_if import analyze_additional_vehicles

router = APIRouter()


@router.post(
    "/analyze",
    response_model=WhatIfResponse,
    summary="Оценить выпуск дополнительных ТС на активные рейсы",
)
async def analyze_scenario(payload: WhatIfRequest) -> WhatIfResponse:
    """Return a deterministic comparison without changing live dispatch state."""
    return analyze_additional_vehicles(payload)
