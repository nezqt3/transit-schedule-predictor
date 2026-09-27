"""Persistence hooks remain compatible with the synchronous runtime stores."""

import asyncio
from datetime import datetime, timezone

from app.schemas.incident import Incident
from app.schemas.prediction import StoredPrediction
from app.services.incident import IncidentStore
from app.services.prediction import PredictionStore


def _prediction(delay: float = 90) -> StoredPrediction:
    now = datetime.now(timezone.utc)
    return StoredPrediction(
        tr_id=1, unit_id=2, prediction_time=now,
        target_stop_id=3, target_time=now,
        current_delay_s=20, predicted_delay_s=delay,
        model_version="test", risk="medium",
    )


def test_prediction_store_restores_and_persists_updates() -> None:
    async def scenario() -> None:
        saved = []

        async def save(item: StoredPrediction) -> None:
            saved.append(item)

        initial = _prediction()
        store = PredictionStore(initial=[initial], persist=save)
        assert store.get_latest(1) is not None
        newer = initial.model_copy(update={
            "prediction_time": initial.prediction_time.replace(microsecond=999999),
            "predicted_delay_s": 150,
        })
        assert store.record(newer)
        await store.flush()
        assert saved[-1].predicted_delay_s == 150

    asyncio.run(scenario())


def test_incident_store_restores_active_index_and_persists_resolution() -> None:
    async def scenario() -> None:
        saved = []
        now = datetime.now(timezone.utc)
        incident = Incident(
            incident_id="persisted", tr_id=1, unit_id=2,
            target_stop_id=3, target_time=now, segment="2 → 3",
            predicted_delay_s=90, risk="medium", risk_source="threshold",
            cause="test", evidence="test", recommendation="test",
            status="active", created_at=now, updated_at=now,
        )

        async def save(item: Incident) -> None:
            saved.append(item)

        store = IncidentStore(initial=[incident], persist=save)
        resolved = store.evaluate(
            _prediction(0).model_copy(update={"risk": "low"}),
            speed_kmh=20,
            previous_stop_id=2,
        )
        assert resolved is not None and resolved.status == "resolved"
        await store.flush()
        assert saved[-1].status == "resolved"

    asyncio.run(scenario())
