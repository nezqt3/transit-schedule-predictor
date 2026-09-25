"""HTTP boundary for the independent ML inference service."""

import logging

import httpx
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


async def request_prediction(payload: dict, client: httpx.AsyncClient) -> dict:
    """Call ML and keep a temporary outage from failing the Backend process."""
    try:
        response = await client.post(f"{settings.ml_service_url}/predict", json=payload)
        response.raise_for_status()
        return response.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("ML request failure for tr_id=%s: %s", payload["tr_id"], exc)
        raise HTTPException(status_code=503, detail="ML service unavailable") from exc
