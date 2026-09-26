from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import app
from app.schemas.auth import CurrentUser
from app.schemas.what_if import WhatIfRequest, WhatIfVehicle
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
