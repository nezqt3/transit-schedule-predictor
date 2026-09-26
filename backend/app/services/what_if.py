"""Deterministic operational what-if estimates for dispatchers."""

from statistics import fmean

from app.schemas.what_if import (
    WhatIfAssignment,
    WhatIfMetrics,
    WhatIfRequest,
    WhatIfResponse,
)


def _metrics(delays: list[float], late_threshold_s: int) -> WhatIfMetrics:
    positive_delays = [max(0.0, delay) for delay in delays]
    late_runs = sum(delay >= late_threshold_s for delay in delays)
    return WhatIfMetrics(
        average_delay_s=round(fmean(positive_delays), 1),
        maximum_delay_s=round(max(positive_delays, default=0.0), 1),
        late_runs=late_runs,
        on_time_runs=len(delays) - late_runs,
    )


def analyze_additional_vehicles(request: WhatIfRequest) -> WhatIfResponse:
    """Estimate replacing the most delayed active runs with reserve vehicles.

    A reserve vehicle can cover one active run. Its resulting deviation equals
    the configured dispatch lead time, so assignments with no positive benefit
    are excluded. This intentionally remains separate from the ML delay model.
    """
    lead_s = float(request.dispatch_lead_minutes * 60)
    projected = [vehicle.predicted_delay_s for vehicle in request.vehicles]
    candidates = sorted(
        enumerate(request.vehicles),
        key=lambda item: item[1].predicted_delay_s - lead_s,
        reverse=True,
    )
    assignments: list[WhatIfAssignment] = []
    for index, vehicle in candidates:
        reduction = vehicle.predicted_delay_s - lead_s
        if reduction <= 0 or len(assignments) >= request.additional_vehicles:
            continue
        projected[index] = lead_s
        assignments.append(WhatIfAssignment(
            reserve_vehicle=len(assignments) + 1,
            tr_id=vehicle.tr_id,
            run_id=vehicle.run_id,
            target_stop_id=vehicle.target_stop_id,
            before_delay_s=round(vehicle.predicted_delay_s, 1),
            after_delay_s=round(lead_s, 1),
            reduction_s=round(reduction, 1),
        ))

    original = [vehicle.predicted_delay_s for vehicle in request.vehicles]
    return WhatIfResponse(
        baseline=_metrics(original, request.late_threshold_s),
        scenario=_metrics(projected, request.late_threshold_s),
        assignments=assignments,
        total_delay_reduction_s=round(sum(item.reduction_s for item in assignments), 1),
        methodology=(
            "Each additional vehicle covers one active run with the greatest avoidable delay; "
            "the replacement run starts after the configured dispatch lead time."
        ),
    )
