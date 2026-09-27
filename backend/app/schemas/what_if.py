"""API contracts for dispatcher what-if scenarios."""

from pydantic import BaseModel, ConfigDict, Field


class WhatIfRotationRun(BaseModel):
    """A subsequent run assigned to the same physical vehicle."""

    run_id: str
    departure_minutes: float = Field(..., ge=0, le=1440)
    duration_minutes: float = Field(..., ge=0, le=720)
    turnaround_minutes: float | None = Field(None, ge=0, le=180)


class WhatIfVehicle(BaseModel):
    """One active run and its current delay forecast."""

    model_config = ConfigDict(allow_inf_nan=False)

    tr_id: int = Field(..., description="Vehicle identifier")
    predicted_delay_s: float = Field(..., description="Forecast schedule deviation in seconds")
    run_id: str | None = Field(None, description="Active run identifier when known")
    target_stop_id: int | None = Field(None, description="Forecast target stop when known")
    passenger_count: int = Field(0, ge=0, le=500, description="Passengers on the run")
    vehicle_capacity: int = Field(100, ge=1, le=500)
    remaining_trip_minutes: float = Field(0, ge=0, le=360)
    next_run_departure_minutes: float | None = Field(None, ge=0, le=720)
    turnaround_minutes: float = Field(0, ge=0, le=180)
    rotation_runs: list[WhatIfRotationRun] = Field(default_factory=list, max_length=20)


class WhatIfRequest(BaseModel):
    """Parameters of an additional-vehicle dispatch scenario."""

    vehicles: list[WhatIfVehicle] = Field(..., min_length=1, max_length=500)
    additional_vehicles: int = Field(1, ge=1, le=10)
    dispatch_lead_minutes: int = Field(3, ge=0, le=30)
    late_threshold_s: int = Field(120, ge=1, le=3600)
    traffic_multiplier: float = Field(1.0, ge=0.5, le=3.0)
    reserve_capacity: int = Field(100, ge=1, le=500)
    passenger_transfer_minutes: float = Field(0, ge=0, le=30)


class WhatIfMetrics(BaseModel):
    average_delay_s: float
    maximum_delay_s: float
    late_runs: int
    on_time_runs: int
    passenger_delay_minutes: float
    affected_passengers: int
    missed_next_runs: int
    rotation_delay_s: float


class WhatIfAssignment(BaseModel):
    reserve_vehicle: int
    tr_id: int
    run_id: str | None
    target_stop_id: int | None
    before_delay_s: float
    after_delay_s: float
    reduction_s: float
    passenger_count: int
    served_passengers: int
    overflow_passengers: int
    passenger_delay_reduction_minutes: float
    downstream_delay_reduction_s: float
    traffic_adjusted_delay_s: float
    rotation_feasible: bool


class WhatIfResponse(BaseModel):
    baseline: WhatIfMetrics
    scenario: WhatIfMetrics
    assignments: list[WhatIfAssignment]
    total_delay_reduction_s: float
    total_passenger_delay_reduction_minutes: float
    total_downstream_delay_reduction_s: float
    methodology: str
