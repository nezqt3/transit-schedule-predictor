import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.ndtp.server import NdtServer
from app.services.telemetry import TelemetryService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    telemetry = TelemetryService()
    app.state.telemetry = telemetry

    ndtp_server = NdtServer(
        on_event=telemetry.handle_event,
        host=settings.ndtp_host,
        port=settings.ndtp_port,
    )
    try:
        await ndtp_server.start()
    except OSError:
        # NDTP-порт может быть занят в локальной разработке —
        # REST-часть должна жить без телеметрии.
        logging.getLogger(__name__).exception(
            "NDTP server failed to start on %s:%s",
            settings.ndtp_host,
            settings.ndtp_port,
        )
    app.state.ndtp_server = ndtp_server

    # Здесь потом запускаем:
    # - подключения к БД

    yield

    # shutdown
    await ndtp_server.stop()


app = FastAPI(
    title="Transport Delay Predictor API",
    description=(
        "Backend API системы раннего прогнозирования "
        "задержек наземного транспорта."
    ),
    version="0.1.0",

    # Swagger UI
    docs_url="/docs",

    # ReDoc
    redoc_url="/redoc",

    # OpenAPI JSON
    openapi_url="/openapi.json",

    lifespan=lifespan,
)

app.include_router(
    api_router,
    prefix="/api/v1",
)