"""Run a real TCP NDTP packet through backend orchestration and shipped ML API."""

from __future__ import annotations

import asyncio
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "ml")]
os.environ["ARTIFACTS_DIR"] = str(ROOT / "ml" / "artifacts")
os.environ["SCHEDULE_PLAN_PATH"] = str(ROOT / "data" / "raw" / "validate" / "schedule_plan.csv")
os.environ["MODEL_NAME"] = "lightgbm_plan"

import httpx  # noqa: E402

from app.ndtp.server import NdtServer  # noqa: E402
from app.services.incident import IncidentStore  # noqa: E402
from app.services.prediction import PredictionStore  # noqa: E402
from app.services.runtime_lookup import RuntimeLookup  # noqa: E402
from app.services.runtime_prediction import RuntimePrediction  # noqa: E402
from app.services.telemetry import TelemetryService  # noqa: E402
from emulator.dataset_replay.app import ndtp  # noqa: E402
from emulator.dataset_replay.app.models import TelemetryRow  # noqa: E402
from service.main import app as ml_app  # noqa: E402


async def main(demo_delay_s: float) -> None:
    unit_ids = (9_999_999, 9_999_998)
    telemetry = TelemetryService()
    predictions = PredictionStore()
    incidents = IncidentStore()
    lookup = RuntimeLookup(
        str(ROOT / "data" / "raw" / "validate" / "schedule_plan.csv"),
        str(ROOT / "data" / "raw" / "validate" / "traffic.csv"),
        demo_units=",".join(map(str, unit_ids)), demo_initial_delay_s=demo_delay_s,
    )
    async with ml_app.router.lifespan_context(ml_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=ml_app), base_url="http://ml:8001",
        ) as ml_client:
            engine = RuntimePrediction(
                telemetry=telemetry, lookup=lookup, predictions=predictions,
                incidents=incidents, ml_client=ml_client,
            )

            async def on_event(event):
                if telemetry.record(event):
                    engine.on_event(event)

            server = NdtServer(on_event=on_event, host="127.0.0.1", port=0)
            queue = telemetry.subscribe()
            await server.start()
            try:
                for index, unit_id in enumerate(unit_ids):
                    _, writer = await asyncio.open_connection("127.0.0.1", server.port)
                    now = datetime.now(timezone.utc)
                    row = TelemetryRow(
                        tr_id=9_000_000 + index, unit_id=unit_id,
                        event_time=now, receive_time=now,
                        latitude=55.7 + index * 0.01,
                        longitude=37.6 + index * 0.01, speed_kmh=0,
                        heading=0, location_valid=True,
                    )
                    writer.write(ndtp.build_handshake(unit_id, 1))
                    writer.write(ndtp.build_realtime(row, now, 2))
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                for _ in range(100):
                    if all(predictions.get_latest(9_000_000 + index) is not None
                           for index in range(len(unit_ids))):
                        break
                    await asyncio.sleep(0.1)
                events = []
                while not queue.empty():
                    events.append(queue.get_nowait()["type"])
                assert events.count("vehicle_update") >= len(unit_ids)
                assert events.count("prediction_update") >= len(unit_ids)
                assert events.count("incident") >= len(unit_ids)
                for index, unit_id in enumerate(unit_ids):
                    prediction = predictions.get_latest(9_000_000 + index)
                    if prediction is None:
                        raise RuntimeError(f"no prediction for {unit_id}: {engine.statuses()}")
                    assert prediction.model == "lightgbm_plan"
                    assert prediction.source == "demo"
                    assert prediction.risk == "high"
                    print(f"unit={unit_id} TCP NDTP -> real ML -> "
                          f"{prediction.predicted_delay_s:.3f}s -> incident")
            finally:
                await server.stop()
                await engine.stop()
                telemetry.unsubscribe(queue)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-delay-s", type=float, default=1000)
    arguments = parser.parse_args()
    asyncio.run(main(arguments.demo_delay_s))
