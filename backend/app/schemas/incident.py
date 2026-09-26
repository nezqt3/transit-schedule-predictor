"""Dispatcher incident contract."""

from datetime import datetime

from pydantic import BaseModel


class Incident(BaseModel):
    incident_id: str
    tr_id: int
    unit_id: int
    target_stop_id: int
    target_time: datetime
    previous_stop_id: int | None = None
    segment: str
    predicted_delay_s: float
    p_late: float | None = None
    risk: str
    risk_source: str
    cause: str
    evidence: str
    recommendation: str
    status: str
    created_at: datetime
    updated_at: datetime
