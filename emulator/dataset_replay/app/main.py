from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, status

from .config import settings
from .dataset import TrafficDataset
from .models import ReplayStartRequest, ReplayStatus, ScenarioSummary
from .replay import ReplayManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

datasets: dict[str, TrafficDataset] = {}
manager = ReplayManager(settings)


def get_dataset(name: str) -> TrafficDataset:
    if not name.replace("-", "_").isalnum():
        raise HTTPException(status_code=400, detail="invalid dataset name")
    if name not in datasets:
        path = settings.data_root / name / "traffic.csv"
        try:
            datasets[name] = TrafficDataset(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return datasets[name]


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await manager.shutdown()


app = FastAPI(
    title="Dataset NDTP Replay Emulator",
    description="Causally replays competition traffic CSV rows over NDTP/TCP.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/scenarios", response_model=list[ScenarioSummary])
async def list_scenarios(
    dataset: str = "validate",
    limit: int = Query(50, ge=1, le=1000),
) -> list[ScenarioSummary]:
    return get_dataset(dataset).scenarios()[:limit]


@app.get("/api/status", response_model=ReplayStatus)
async def replay_status() -> ReplayStatus:
    return manager.status()


@app.post("/api/replay/start", response_model=ReplayStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_replay(request: ReplayStartRequest) -> ReplayStatus:
    dataset = get_dataset(request.dataset)
    try:
        rows = dataset.select(
            request.tr_ids,
            valid_locations_only=request.valid_locations_only,
            start_at=request.start_at,
            end_at=request.end_at,
        )
        return await manager.start(request, rows)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/replay/pause", response_model=ReplayStatus)
async def pause_replay() -> ReplayStatus:
    try:
        return await manager.pause()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/replay/resume", response_model=ReplayStatus)
async def resume_replay() -> ReplayStatus:
    try:
        return await manager.resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/replay/stop", response_model=ReplayStatus)
async def stop_replay() -> ReplayStatus:
    return await manager.stop()
