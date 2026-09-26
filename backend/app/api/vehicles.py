from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_telemetry_service
from app.ndtp.schemas import TelemetryEvent
from app.services.telemetry import TelemetryService

router = APIRouter()


@router.get(
    "",
    response_model=list[TelemetryEvent],
    summary="Список ТС с последней телеметрией",
)
async def list_vehicles(
    service: TelemetryService = Depends(get_telemetry_service),
) -> list[TelemetryEvent]:
    return service.list_latest()


@router.get(
    "/{unit_id}",
    response_model=TelemetryEvent,
    summary="Последняя телеметрия ТС",
)
async def get_vehicle(
    unit_id: int,
    service: TelemetryService = Depends(get_telemetry_service),
) -> TelemetryEvent:
    event = service.get_latest(unit_id)
    if event is None:
        raise HTTPException(status_code=404, detail="unit not found")
    return event


@router.get(
    "/{unit_id}/history",
    response_model=list[TelemetryEvent],
    summary="Недавняя NDTP-телеметрия терминала",
)
async def get_vehicle_history(
    unit_id: int,
    service: TelemetryService = Depends(get_telemetry_service),
) -> list[TelemetryEvent]:
    """Return the buffered packets used for the terminal's speed history."""
    if service.get_latest(unit_id) is None:
        raise HTTPException(status_code=404, detail="unit not found")
    return service.get_recent(unit_id)
