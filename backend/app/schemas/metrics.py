"""Operational measurement contracts exposed through OpenAPI."""

from pydantic import BaseModel


class NdtpMetrics(BaseModel):
    connections_total: int
    active_connections: int
    parsed_packets: int
    invalid_packets: int
    accepted_packets: int
    ignored_packets: int
    ws_dropped_events: int
    subscriber_queue_peak: int
    vehicles: int


class PredictionMetrics(BaseModel):
    requests_started: int
    requests_succeeded: int
    requests_failed: int
    active_tasks: int
    peak_active_tasks: int
    packet_to_publish_p50_s: float | None
    packet_to_publish_p95_s: float | None
    packet_to_publish_p99_s: float | None
    ml_request_p50_s: float | None
    ml_request_p95_s: float | None
    ml_request_p99_s: float | None
    ml_queue_wait_p50_s: float | None
    ml_queue_wait_p95_s: float | None
    ml_queue_wait_p99_s: float | None
    latency_samples: int


class MetricsResponse(BaseModel):
    ndtp: NdtpMetrics
    prediction: PredictionMetrics
