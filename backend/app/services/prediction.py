"""Prepare a causal NDTP window and call the ML inference service."""

from __future__ import annotations

from datetime import datetime, timezone
from collections import OrderedDict
from threading import RLock

import httpx
from fastapi import HTTPException

from app.services.ml_client import request_prediction
from app.services.telemetry import TelemetryService
from app.schemas.prediction import StoredPrediction


class PredictionStore:
    """Keep the latest successful ML result for each vehicle in memory."""

    def __init__(self, max_vehicles: int = 500) -> None:
        self._latest: OrderedDict[int, StoredPrediction] = OrderedDict()
        self._lock = RLock()
        self._max_vehicles = max_vehicles

    def record(self, prediction: StoredPrediction) -> None:
        with self._lock:
            self._latest.pop(prediction.tr_id, None)
            self._latest[prediction.tr_id] = prediction
            if len(self._latest) > self._max_vehicles:
                self._latest.popitem(last=False)

    def list_latest(self) -> list[StoredPrediction]:
        with self._lock:
            return list(self._latest.values())

    def get_latest(self, tr_id: int) -> StoredPrediction | None:
        with self._lock:
            return self._latest.get(tr_id)


async def predict_delay(
    telemetry: TelemetryService,
    ml_client: httpx.AsyncClient,
    *,
    tr_id: int,
    unit_id: int,
    T: datetime,
    cur_dev_s: float,
    target_stop_id: int,
    target_time_begin: datetime,
    stop_lat: float,
    stop_lon: float,
    current_point: dict | None = None,
) -> dict:
    """Call ML with at most 150 normalized packets for the target vehicle."""
    normalized_t = T.replace(tzinfo=timezone.utc) if T.tzinfo is None else T.astimezone(timezone.utc)
    normalized_target = (
        target_time_begin.replace(tzinfo=timezone.utc)
        if target_time_begin.tzinfo is None else target_time_begin.astimezone(timezone.utc)
    )
    horizon_s = (normalized_target - normalized_t).total_seconds()
    if not 600 < horizon_s <= 900:
        raise HTTPException(status_code=422, detail="target stop must be in (T+10m, T+15m]")
    points = []
    for event in telemetry.get_recent(unit_id):
        nav = event.nav
        if nav is None:
            continue
        points.append({
            "event_time": event.event_time.isoformat(),
            "receive_time": event.received_at.isoformat(),
            "location_valid": nav.coordinates_valid,
            "lat": nav.latitude,
            "lon": nav.longitude,
            "speed": nav.speed_avg,
            "heading": nav.course,
        })
    if current_point is not None:
        points.append(current_point)
    if not points:
        raise HTTPException(status_code=404, detail=f"no telemetry for unit_id={unit_id}")
    payload = {
        "tr_id": tr_id,
        "T": T.isoformat(),
        "cur_dev_s": cur_dev_s,
        "target_stop_id": target_stop_id,
        "target_time_begin": target_time_begin.isoformat(),
        "stop_lat": stop_lat,
        "stop_lon": stop_lon,
        "telemetry": points,
    }
    return await request_prediction(payload, ml_client)
