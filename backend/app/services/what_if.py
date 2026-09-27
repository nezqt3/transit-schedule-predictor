"""Deterministic operational what-if estimates for dispatchers."""

from statistics import fmean

from app.schemas.what_if import (
    WhatIfAssignment,
    WhatIfMetrics,
    WhatIfRequest,
    WhatIfResponse,
    WhatIfVehicle,
)


def _metrics(delays: list[float], passenger_counts: list[int], rotation_delays: list[float],
             rotation_missed: list[int], passenger_delay_minutes: list[float],
             late_threshold_s: int) -> WhatIfMetrics:
    positive_delays = [max(0.0, delay) for delay in delays]
    late_runs = sum(delay >= late_threshold_s for delay in delays)
    return WhatIfMetrics(
        average_delay_s=round(fmean(positive_delays), 1),
        maximum_delay_s=round(max(positive_delays, default=0.0), 1),
        late_runs=late_runs,
        on_time_runs=len(delays) - late_runs,
        passenger_delay_minutes=round(sum(passenger_delay_minutes), 1),
        affected_passengers=sum(
            passengers for delay, passengers in zip(delays, passenger_counts)
            if delay >= late_threshold_s
        ),
        missed_next_runs=sum(rotation_missed),
        rotation_delay_s=round(sum(rotation_delays), 1),
    )


def _rotation_impact(vehicle: WhatIfVehicle, current_delay_s: float, traffic_multiplier: float,
                     late_threshold_s: int, released: bool = False) -> tuple[float, int]:
    """Propagate availability through every subsequent run in the rotation."""
    ready_at = vehicle.turnaround_minutes
    if not released:
        ready_at += (
            max(0.0, current_delay_s) / 60
            + vehicle.remaining_trip_minutes * traffic_multiplier
        )
    rotation = sorted(vehicle.rotation_runs, key=lambda run: run.departure_minutes)
    if not rotation and vehicle.next_run_departure_minutes is not None:
        delay_s = max(0.0, ready_at - vehicle.next_run_departure_minutes) * 60
        return delay_s, int(delay_s >= late_threshold_s)
    total_delay_s = 0.0
    missed = 0
    for run in rotation:
        delay_minutes = max(0.0, ready_at - run.departure_minutes)
        delay_s = delay_minutes * 60
        total_delay_s += delay_s
        missed += int(delay_s >= late_threshold_s)
        actual_departure = run.departure_minutes + delay_minutes
        ready_at = (
            actual_departure
            + run.duration_minutes * traffic_multiplier
            + (run.turnaround_minutes
               if run.turnaround_minutes is not None else vehicle.turnaround_minutes)
        )
    return total_delay_s, missed


def analyze_additional_vehicles(request: WhatIfRequest) -> WhatIfResponse:
    """Estimate replacing the most delayed active runs with reserve vehicles.

    The deterministic simulation accounts for congestion, passenger capacity
    and knock-on delay of the vehicle's next run. It remains separate from the
    competition ML target and never mutates live dispatcher state.
    """
    lead_s = float(
        request.dispatch_lead_minutes * 60 * request.traffic_multiplier
        + request.passenger_transfer_minutes * 60
    )
    original = [
        vehicle.predicted_delay_s * request.traffic_multiplier
        if vehicle.predicted_delay_s > 0 else vehicle.predicted_delay_s
        for vehicle in request.vehicles
    ]
    projected = list(original)
    passenger_counts = [vehicle.passenger_count for vehicle in request.vehicles]
    baseline_rotation_impacts = [
        _rotation_impact(
            vehicle, delay, request.traffic_multiplier, request.late_threshold_s,
        )
        for vehicle, delay in zip(request.vehicles, original)
    ]
    baseline_rotations = [impact[0] for impact in baseline_rotation_impacts]
    baseline_rotation_missed = [impact[1] for impact in baseline_rotation_impacts]
    scenario_rotations = list(baseline_rotations)
    scenario_rotation_missed = list(baseline_rotation_missed)
    baseline_passenger_delay = [
        max(0.0, delay) * passengers / 60
        for delay, passengers in zip(original, passenger_counts)
    ]
    scenario_passenger_delay = list(baseline_passenger_delay)
    candidates = sorted(
        enumerate(request.vehicles),
        key=lambda item: (
            (original[item[0]] - lead_s) * (1 + item[1].passenger_count / 100)
            + baseline_rotations[item[0]]
        ),
        reverse=True,
    )
    assignments: list[WhatIfAssignment] = []
    for index, vehicle in candidates:
        before_delay = original[index]
        reduction = before_delay - lead_s
        if reduction <= 0 or len(assignments) >= request.additional_vehicles:
            continue
        projected[index] = lead_s
        served = min(vehicle.passenger_count, request.reserve_capacity)
        overflow = max(0, vehicle.passenger_count - served)
        passenger_before = max(0.0, before_delay) * vehicle.passenger_count / 60
        passenger_after = (
            max(0.0, lead_s) * served + max(0.0, before_delay) * overflow
        ) / 60
        scenario_passenger_delay[index] = passenger_after
        # The original vehicle is released from the current trip; only its
        # turnaround remains before the linked next run.
        next_rotation, next_missed = _rotation_impact(
            vehicle, lead_s, request.traffic_multiplier,
            request.late_threshold_s, released=True,
        )
        downstream_reduction = baseline_rotations[index] - next_rotation
        scenario_rotations[index] = next_rotation
        scenario_rotation_missed[index] = next_missed
        assignments.append(WhatIfAssignment(
            reserve_vehicle=len(assignments) + 1,
            tr_id=vehicle.tr_id,
            run_id=vehicle.run_id,
            target_stop_id=vehicle.target_stop_id,
            before_delay_s=round(before_delay, 1),
            after_delay_s=round(lead_s, 1),
            reduction_s=round(reduction, 1),
            passenger_count=vehicle.passenger_count,
            served_passengers=served,
            overflow_passengers=overflow,
            passenger_delay_reduction_minutes=round(passenger_before - passenger_after, 1),
            downstream_delay_reduction_s=round(downstream_reduction, 1),
            traffic_adjusted_delay_s=round(before_delay, 1),
            rotation_feasible=next_rotation < request.late_threshold_s,
        ))

    return WhatIfResponse(
        baseline=_metrics(
            original, passenger_counts, baseline_rotations,
            baseline_rotation_missed, baseline_passenger_delay, request.late_threshold_s,
        ),
        scenario=_metrics(
            projected, passenger_counts, scenario_rotations,
            scenario_rotation_missed, scenario_passenger_delay, request.late_threshold_s,
        ),
        assignments=assignments,
        total_delay_reduction_s=round(sum(item.reduction_s for item in assignments), 1),
        total_passenger_delay_reduction_minutes=round(sum(
            item.passenger_delay_reduction_minutes for item in assignments
        ), 1),
        total_downstream_delay_reduction_s=round(sum(
            item.downstream_delay_reduction_s for item in assignments
        ), 1),
        methodology=(
            "Reserve assignments maximize avoidable direct and downstream delay. "
            "The simulation applies the traffic multiplier, reserve capacity, passenger "
            "transfer time, remaining trip time and vehicle turnaround before the next run."
        ),
    )
