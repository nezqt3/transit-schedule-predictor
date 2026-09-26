"""Check TCP and WebSocket reconnection against the official-demo Compose stack."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import websockets

from emulator.dataset_replay.app import ndtp
from emulator.dataset_replay.app.models import TelemetryRow


BACKEND = "http://127.0.0.1:8000"
UNIT_ID = 1166336


async def send_packet() -> None:
    _, writer = await asyncio.open_connection("127.0.0.1", 9201)
    now = datetime.now(timezone.utc)
    row = TelemetryRow(
        tr_id=9_000_000, unit_id=UNIT_ID, event_time=now,
        receive_time=now, latitude=55.75, longitude=37.62,
        speed_kmh=0, heading=0, location_valid=True,
    )
    writer.write(ndtp.build_handshake(UNIT_ID, 1))
    writer.write(ndtp.build_realtime(row, now, 2))
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def wait_for_prediction(http: httpx.AsyncClient, headers: dict) -> dict:
    for _ in range(60):
        predictions = (await http.get(f"{BACKEND}/api/v1/predictions",
                                      headers=headers)).json()
        selected = [item for item in predictions if item["unit_id"] == UNIT_ID]
        if selected:
            return selected[0]
        await asyncio.sleep(0.25)
    raise RuntimeError("no automatic prediction after TCP packet")


async def main() -> None:
    async with httpx.AsyncClient(timeout=10, trust_env=False) as http:
        login = await http.post(f"{BACKEND}/api/v1/auth/token", data={
            "username": os.getenv("AUTH_BOOTSTRAP_USERNAME", "dispatcher"),
            "password": os.getenv("AUTH_BOOTSTRAP_PASSWORD", "transport"),
        })
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        ws_headers = {"Cookie": f"{os.getenv('AUTH_COOKIE_NAME', 'transport_session')}={token}"}
        async with websockets.connect("ws://127.0.0.1:8000/api/v1/ws",
                                      additional_headers=ws_headers) as socket:
            await socket.recv()  # Initial REST-equivalent vehicle snapshot.
            await send_packet()
            first = await wait_for_prediction(http, headers)
            event_types = set()
            for _ in range(10):
                try:
                    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=1))
                except asyncio.TimeoutError:
                    break
                event_types.add(message.get("type"))
        incidents = (await http.get(f"{BACKEND}/api/v1/incidents",
                                    headers=headers)).json()
        active = [item for item in incidents if item["unit_id"] == UNIT_ID
                  and item["status"] == "active"]
        if len(active) != 1 or "prediction_update" not in event_types or "incident" not in event_types:
            raise RuntimeError("first TCP/WS cycle did not create one visible incident")
        incident_id = active[0]["incident_id"]

        await asyncio.sleep(32)
        vehicles = (await http.get(f"{BACKEND}/api/v1/vehicles",
                                   headers=headers)).json()
        selected = next(item for item in vehicles if item["unit_id"] == UNIT_ID)
        received = datetime.fromisoformat(selected["received_at"])
        age_s = (datetime.now(timezone.utc) - received).total_seconds()
        if age_s < 30:
            raise RuntimeError(f"disconnected TCP state was not retained for 30s: {age_s}")

        async with websockets.connect("ws://127.0.0.1:8000/api/v1/ws",
                                      additional_headers=ws_headers) as socket:
            snapshot = json.loads(await asyncio.wait_for(socket.recv(), timeout=3))
            if snapshot["type"] != "vehicle_snapshot" or not any(
                item["unit_id"] == UNIT_ID for item in snapshot["data"]
            ):
                raise RuntimeError("WebSocket reconnect missed the REST vehicle state")
            await send_packet()
            for _ in range(20):
                message = json.loads(await asyncio.wait_for(socket.recv(), timeout=3))
                if message.get("type") == "prediction_update":
                    break
            else:
                raise RuntimeError("no forecast event after TCP reconnect")

        second = (await http.get(f"{BACKEND}/api/v1/predictions",
                                 headers=headers)).json()
        latest = next(item for item in second if item["unit_id"] == UNIT_ID)
        if latest["prediction_time"] == first["prediction_time"]:
            raise RuntimeError("prediction did not advance after reconnect")
        incidents = (await http.get(f"{BACKEND}/api/v1/incidents",
                                    headers=headers)).json()
        active = [item for item in incidents if item["unit_id"] == UNIT_ID
                  and item["status"] == "active"]
        if len(active) != 1 or active[0]["incident_id"] != incident_id:
            raise RuntimeError("TCP reconnect duplicated the incident")
        print(json.dumps({"unit_id": UNIT_ID, "tcp_age_s": round(age_s, 1),
                          "ws_snapshot": True, "new_prediction": True,
                          "incident_id_preserved": True}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
