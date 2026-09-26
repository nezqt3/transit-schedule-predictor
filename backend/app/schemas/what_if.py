"""API contracts for dispatcher what-if scenarios."""

from pydantic import BaseModel, ConfigDict, Field


class WhatIfVehicle(BaseModel):
    """One active run and its current delay forecast."""

    model_config = ConfigDict(allow_inf_nan=False)

    tr_id: int = Field(..., description="Vehicle identifier")
    predicted_delay_s: float = Field(..., description="Forecast schedule deviation in seconds")
    run_id: str | None = Field(None, description="Active run identifier when known")
    target_stop_id: int | None = Field(None, description="Forecast target stop when known")


class WhatIfRequest(BaseModel):
    """Parameters of an additional-vehicle dispatch scenario."""

    vehicles: list[WhatIfVehicle] = Field(..., min_length=1, max_length=500)
    additional_vehicles: int = Field(1, ge=1, le=10)
    dispatch_lead_minutes: int = Field(3, ge=0, le=30)
    late_threshold_s: int = Field(120, ge=1, le=3600)


class WhatIfMetrics(BaseModel):
    average_delay_s: float
    maximum_delay_s: float
    late_runs: int
    on_time_runs: int


class WhatIfAssignment(BaseModel):
    reserve_vehicle: int
    tr_id: int
    run_id: str | None
    target_stop_id: int | None
    before_delay_s: float
    after_delay_s: float
    reduction_s: float


class WhatIfResponse(BaseModel):
    baseline: WhatIfMetrics
    scenario: WhatIfMetrics
    assignments: list[WhatIfAssignment]
    total_delay_reduction_s: float
    methodology: str
