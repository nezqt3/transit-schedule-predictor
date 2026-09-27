from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import app
from app.schemas.auth import CurrentUser
from app.schemas.what_if import WhatIfRequest, WhatIfRotationRun, WhatIfVehicle
from app.services.what_if import analyze_additional_vehicles


def test_additional_vehicle_covers_worst_delayed_run() -> None:
    result = analyze_additional_vehicles(WhatIfRequest(
        vehicles=[
            WhatIfVehicle(tr_id=1, predicted_delay_s=600, run_id="1-2"),
            WhatIfVehicle(tr_id=2, predicted_delay_s=300, run_id="2-1"),
            WhatIfVehicle(tr_id=3, predicted_delay_s=-30, run_id="3-1"),
        ],
        additional_vehicles=1,
        dispatch_lead_minutes=1,
        late_threshold_s=120,
    ))

    assert [assignment.tr_id for assignment in result.assignments] == [1]
    assert result.assignments[0].reduction_s == 540
    assert result.baseline.late_runs == 2
    assert result.scenario.late_runs == 1
    assert result.scenario.maximum_delay_s == 300


def test_scenario_skips_reserve_when_dispatch_is_slower() -> None:
    result = analyze_additional_vehicles(WhatIfRequest(
        vehicles=[WhatIfVehicle(tr_id=1, predicted_delay_s=60)],
        dispatch_lead_minutes=3,
    ))

    assert result.assignments == []
    assert result.total_delay_reduction_s == 0
    assert result.scenario == result.baseline


def test_scenario_accounts_for_passengers_traffic_and_vehicle_rotation() -> None:
    result = analyze_additional_vehicles(WhatIfRequest(
        vehicles=[WhatIfVehicle(
            tr_id=1,
            predicted_delay_s=600,
            passenger_count=150,
            remaining_trip_minutes=20,
            next_run_departure_minutes=35,
            turnaround_minutes=10,
        )],
        dispatch_lead_minutes=1,
        passenger_transfer_minutes=2,
        traffic_multiplier=1.5,
        reserve_capacity=100,
    ))

    assignment = result.assignments[0]
    assert assignment.traffic_adjusted_delay_s == 900
    assert assignment.after_delay_s == 210
    assert assignment.served_passengers == 100
    assert assignment.overflow_passengers == 50
    assert assignment.passenger_delay_reduction_minutes == 1150
    assert assignment.downstream_delay_reduction_s == 1200
    assert result.scenario.rotation_delay_s == 0


def test_rotation_delay_cascades_through_all_linked_runs() -> None:
    result = analyze_additional_vehicles(WhatIfRequest(
        vehicles=[WhatIfVehicle(
            tr_id=1,
            predicted_delay_s=600,
            remaining_trip_minutes=20,
            turnaround_minutes=5,
            rotation_runs=[
                WhatIfRotationRun(run_id="next-1", departure_minutes=25,
                                  duration_minutes=30),
                WhatIfRotationRun(run_id="next-2", departure_minutes=60,
                                  duration_minutes=30),
            ],
        )],
        dispatch_lead_minutes=0,
    ))

    assert result.baseline.rotation_delay_s == 1200
    assert result.baseline.missed_next_runs == 2
    assert result.scenario.rotation_delay_s == 0
    assert result.scenario.missed_next_runs == 0


def test_what_if_endpoint_exposes_scenario_contract() -> None:
    async def dispatcher() -> CurrentUser:
        return CurrentUser(username="dispatcher", role="dispatcher")

    app.dependency_overrides[get_current_user] = dispatcher
    try:
        response = TestClient(app).post("/api/v1/what-if/analyze", json={
            "vehicles": [{"tr_id": 17, "predicted_delay_s": 420}],
            "additional_vehicles": 1,
            "dispatch_lead_minutes": 1,
            "late_threshold_s": 120,
        })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["assignments"][0]["tr_id"] == 17
