"""Live telemetry events for the dispatcher dashboard."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def vehicle_stream(websocket: WebSocket) -> None:
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
