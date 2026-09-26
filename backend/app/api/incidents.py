"""Dispatcher incident REST endpoints."""

from fastapi import APIRouter, HTTPException, Request

from app.schemas.incident import Incident

router = APIRouter()


@router.get("", response_model=list[Incident], summary="Инциденты диспетчера")
async def list_incidents(request: Request) -> list[Incident]:
    return request.app.state.incidents.list_all()


@router.get("/{incident_id}", response_model=Incident, summary="Карточка инцидента")
async def get_incident(incident_id: str, request: Request) -> Incident:
    item = request.app.state.incidents.get(incident_id)
    if item is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return item
