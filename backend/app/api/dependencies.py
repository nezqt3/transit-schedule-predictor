"""DI-зависимости API.

Единственный источник экземпляров сервисов: telemetry-стор живёт в
app.state, NDTP-сервер пишет в него, API читает.
"""

from fastapi import Request

from app.services.telemetry import TelemetryService


def get_telemetry_service(request: Request) -> TelemetryService:
    return request.app.state.telemetry
