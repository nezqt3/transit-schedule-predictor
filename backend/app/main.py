import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.ndtp.server import NdtServer
from app.repositories.auth import AuthRepository
from app.services.auth import AuthService
from app.services.runtime_lookup import RuntimeLookup
from app.services.telemetry import TelemetryService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    telemetry = TelemetryService()
    app.state.telemetry = telemetry
    app.state.runtime_lookup = RuntimeLookup(
        settings.runtime_schedule_path,
        settings.runtime_traffic_path,
    )
    app.state.ml_client = httpx.AsyncClient(
        timeout=settings.ml_request_timeout_s,
        trust_env=False,
    )

    auth_repository = AuthRepository(
        settings.database_url,
        settings.auth_database_connect_timeout_s,
    )
    auth_service = AuthService(auth_repository)
    app.state.auth_service = auth_service
    app.state.auth_available = False
    try:
        await auth_repository.initialize()
        created = await auth_service.bootstrap(
            settings.auth_bootstrap_username,
            settings.auth_bootstrap_password,
        )
        app.state.auth_available = True
        if created:
            logging.getLogger(__name__).info(
                "Created bootstrap dispatcher account %s",
                settings.auth_bootstrap_username,
            )
    except Exception:
        logging.getLogger(__name__).exception(
            "Authentication database is unavailable; login is disabled"
        )

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
    await app.state.ml_client.aclose()
    await auth_repository.close()


app = FastAPI(
    title="Transport Delay Predictor API",
    description=(
        "Backend API системы раннего прогнозирования задержек "
        "наземного транспорта.\n\n"
        "1. Получите токен через `POST /api/v1/auth/token`.\n"
        "2. В Swagger UI нажмите **Authorize** и введите учётные данные.\n"
        "3. Health check остаётся публичным; telemetry и prediction API защищены."
    ),
    version="0.2.0",
    openapi_tags=[
        {"name": "Health", "description": "Публичная проверка готовности Backend."},
        {"name": "Authentication", "description": "Вход и сведения о текущем диспетчере."},
        {"name": "Vehicles", "description": "Актуальная NDTP-телеметрия транспорта."},
        {"name": "Predictions", "description": "Прогноз отклонения на горизонте 10–15 минут."},
    ],

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
