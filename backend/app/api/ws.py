"""Live telemetry events for the dispatcher dashboard."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import decode_access_token

router = APIRouter()


@router.websocket("/ws")
async def vehicle_stream(websocket: WebSocket) -> None:
    token = websocket.cookies.get(settings.auth_cookie_name)
    identity = decode_access_token(token) if token else None
    if identity is None or not websocket.app.state.auth_available:
        await websocket.close(code=1008, reason="authentication required")
        return
    username, token_role = identity
    user = await websocket.app.state.auth_service.get_current_user(username)
    if user is None or user.role != token_role:
        await websocket.close(code=1008, reason="invalid session")
        return

    telemetry = websocket.app.state.telemetry
    queue = telemetry.subscribe()
    await websocket.accept()
    try:
        await websocket.send_json({
            "type": "vehicle_snapshot",
            "data": [event.model_dump(mode="json") for event in telemetry.list_latest()],
        })
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
                await websocket.send_json({
                    "type": "vehicle_update", "data": event.model_dump(mode="json"),
                })
            except TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        telemetry.unsubscribe(queue)
