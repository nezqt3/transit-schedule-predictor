"""Operational counters for a bounded hackathon load test."""

from fastapi import APIRouter, Request

from app.schemas.metrics import MetricsResponse

router = APIRouter()


@router.get("", response_model=MetricsResponse,
            summary="NDTP and prediction pipeline measurements")
async def metrics(request: Request) -> MetricsResponse:
    telemetry = request.app.state.telemetry
    ndtp = request.app.state.ndtp_server
    return MetricsResponse.model_validate({
        "ndtp": {
            "connections_total": ndtp.connections_total,
            "active_connections": ndtp.active_connections,
            "parsed_packets": ndtp.parsed_packets,
            "invalid_packets": ndtp.invalid_packets,
            "accepted_packets": telemetry.accepted_packets,
            "ignored_packets": telemetry.ignored_packets,
            "ws_dropped_events": telemetry.ws_dropped_events,
            "subscriber_queue_peak": telemetry.subscriber_queue_peak,
            "vehicles": telemetry.count(),
        },
        "prediction": request.app.state.runtime_prediction.stats(),
    })
