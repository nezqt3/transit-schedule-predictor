"""Critical horizon and automatic NDTP prediction smoke checks."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ndtp.schemas import NavData, TelemetryEvent
from app.ndtp.server import NdtServer
from app.schemas.prediction import StoredPrediction
from app.services.incident import IncidentStore
from app.services.prediction import PredictionStore, predict_delay
from app.services.runtime_lookup import RuntimeLookup
from app.services.runtime_prediction import RuntimePrediction
from app.services.telemetry import TelemetryService
from emulator.dataset_replay.app import ndtp
from emulator.dataset_replay.app.models import TelemetryRow


def _lookup(tmp_path):
    schedule = tmp_path / "schedule.csv"
    schedule.write_text(
        "tr_id,tt_action_item_id,time_begin,geom\n"
        '1,10,2026-01-06 03:30:00,"POINT (37.6 55.7)"\n'
        '1,11,2026-01-06 03:50:00,"POINT (37.7 55.8)"\n',
        encoding="utf-8",
    )
    traffic = tmp_path / "traffic.csv"
    traffic.write_text("tr_id,unit_id\n1,2\n", encoding="utf-8")
    points = tmp_path / "points.csv"
    points.write_text(
        "tr_id,T,target_stop_id,cur_dev_s\n1,2026-01-06 03:35:00,11,130\n",
        encoding="utf-8",
    )
    return RuntimeLookup(str(schedule), str(traffic), "Europe/Moscow", str(points))


def _utc(minute: int, second: int = 0):
    return datetime(2026, 1, 6, 3, minute, second,
                    tzinfo=ZoneInfo("Europe/Moscow")).astimezone(timezone.utc)


def test_first_stop_horizon_boundaries(tmp_path):
    lookup = _lookup(tmp_path)
    assert lookup.target_for(1, _utc(35))['target_stop_id'] == 11
    assert lookup.target_for(1, _utc(40)) is None  # exactly T+10m is excluded
    assert lookup.target_for(1, _utc(34, 59)) is None  # beyond T+15m
    assert lookup.point_hint(1, _utc(34, 59), 11) is None
    assert lookup.point_hint(1, _utc(35, 5), 11) == 130


def test_runtime_schedule_ignores_future_actual_arrival(tmp_path):
    traffic = tmp_path / "traffic.csv"
    traffic.write_text("tr_id,unit_id\n1,2\n", encoding="utf-8")
    schedule = tmp_path / "schedule.csv"
    rows = ('tr_id,tt_action_item_id,time_begin,geom,time_fact_begin\n'
            '1,11,2026-01-06 03:50:00,"POINT (37.7 55.8)",{fact}\n')
    schedule.write_text(rows.format(fact="2026-01-06 03:52:00"), encoding="utf-8")
    before = RuntimeLookup(str(schedule), str(traffic)).target_for(1, _utc(35))
    schedule.write_text(rows.format(fact="2026-01-06 05:00:00"), encoding="utf-8")
    after = RuntimeLookup(str(schedule), str(traffic)).target_for(1, _utc(35))
    assert before == after
    assert "time_fact_begin" not in before


def test_stop_confirmation_rejects_single_and_reverse_heading(tmp_path):
    lookup = _lookup(tmp_path)
    telemetry = TelemetryService()
    service = RuntimePrediction(
        telemetry=telemetry, lookup=lookup,
        predictions=PredictionStore(), incidents=IncidentStore(),
        ml_client=None,
    )
    for second in (0, 30):
        event_time = _utc(50, second)
        telemetry.record(TelemetryEvent(
            unit_id=2, received_at=datetime.now(timezone.utc),
            nav=NavData(timestamp=int(event_time.timestamp()), latitude=55.8,
                        longitude=37.7, speed_avg=5, course=225),
        ))
        assert service._confirmed_delay(1, 2, event_time, historical=True) is None

    forward = TelemetryService()
    service.telemetry = forward
    for second in (0, 30):
        event_time = _utc(50, second)
        forward.record(TelemetryEvent(
            unit_id=2, received_at=datetime.now(timezone.utc),
            nav=NavData(timestamp=int(event_time.timestamp()), latitude=55.8,
                        longitude=37.7, speed_avg=5, course=30),
        ))
    confirmed = service._confirmed_delay(1, 2, _utc(50, 30), historical=True)
    assert confirmed is not None and confirmed[1] == 11


def test_future_packet_is_excluded_from_ml_request():
    async def scenario():
        telemetry = TelemetryService()
        t = _utc(35)
        for offset in (0, 60):
            at = datetime.fromtimestamp(t.timestamp() + offset, tz=timezone.utc)
            telemetry.record(TelemetryEvent(
                unit_id=2, received_at=at,
                nav=NavData(timestamp=int(at.timestamp()), latitude=55.7,
                            longitude=37.6, speed_avg=4),
            ))
        seen = []

        def ml_response(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={"prediction": 100, "model": "test",
                                             "model_version": "test"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(ml_response)) as client:
            await predict_delay(
                telemetry, client, tr_id=1, unit_id=2, T=t,
                cur_dev_s=30, target_stop_id=11,
                target_time_begin=_utc(47), stop_lat=55.8, stop_lon=37.7,
            )
        assert len(seen[0]["telemetry"]) == 1
        assert seen[0]["telemetry"][0]["event_time"] == t.isoformat()

    asyncio.run(scenario())


def test_incident_advice_uses_risk_and_observed_context():
    base = StoredPrediction(
        tr_id=1, unit_id=2, prediction_time=_utc(35),
        target_stop_id=11, target_time=_utc(50),
        current_delay_s=20, predicted_delay_s=90,
        model_version="test", risk="medium",
    )
    store = IncidentStore()
    medium_stop = store.evaluate(base, speed_kmh=0, previous_stop_id=10)
    assert medium_stop is not None
    assert "Последняя скорость 0 км/ч" == medium_stop.evidence
    assert "повторить оценку" in medium_stop.recommendation

    high_stop = store.evaluate(base.model_copy(update={
        "risk": "high", "predicted_delay_s": 150,
    }), speed_kmh=0, previous_stop_id=10)
    assert high_stop is not None
    assert high_stop.incident_id == medium_stop.incident_id
    assert "Связаться с водителем" in high_stop.recommendation

    existing_delay = store.evaluate(base.model_copy(update={
        "target_stop_id": 12, "current_delay_s": 140,
    }), speed_kmh=20, previous_stop_id=11)
    assert existing_delay is not None
    assert "Текущее отклонение 140 с" in existing_delay.evidence
    assert "Сверить движение" in existing_delay.recommendation

    forecast_growth = store.evaluate(base.model_copy(update={
        "target_stop_id": 13, "risk": "high", "predicted_delay_s": 160,
    }), speed_kmh=20, previous_stop_id=11)
    assert forecast_growth is not None
    assert "Прогноз 160 с; текущее отклонение 20 с" == forecast_growth.evidence
    assert "корректировку интервала" in forecast_growth.recommendation


def test_ndtp_event_creates_prediction_and_incident(tmp_path):
    async def scenario():
        lookup = _lookup(tmp_path)
        telemetry = TelemetryService()
        predictions = PredictionStore()
        incidents = IncidentStore()
        sent = []

        def ml_response(request):
            payload = json.loads(request.content)
            sent.append(payload)
            return httpx.Response(200, json={
                "prediction": 150.0, "model": "lightgbm_plan",
                "model_version": "test", "model_artifact_sha256": "abc",
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(ml_response)) as client:
            service = RuntimePrediction(
                telemetry=telemetry, lookup=lookup, predictions=predictions,
                incidents=incidents, ml_client=client,
            )
            t = _utc(35, 5)
            event = TelemetryEvent(
                unit_id=2, received_at=datetime.now(timezone.utc),
                nav=NavData(timestamp=int(t.timestamp()), latitude=55.7,
                            longitude=37.6, speed_avg=4),
            )
            stream = telemetry.subscribe()
            assert telemetry.record(event)
            service.on_event(event)
            await asyncio.sleep(0.05)
            result = predictions.get_latest(1)
            assert result is not None and result.predicted_delay_s == 150
            assert result.current_delay_source == "point_input"
            assert result.source == "replay"
            assert result.map_match_graph_source == "schedule"
            assert result.map_match_distance_m == 0
            assert len(incidents.list_all()) == 1
            assert sent[0]["cur_dev_s"] == 130
            assert all(point["event_time"] <= sent[0]["T"] for point in sent[0]["telemetry"])
            assert [stream.get_nowait()["type"] for _ in range(3)] == [
                "vehicle_update", "prediction_update", "incident",
            ]
            await service.stop()

    asyncio.run(scenario())


def test_explicit_synthetic_emulator_plan_is_labeled(tmp_path):
    async def scenario():
        base = _lookup(tmp_path)
        lookup = RuntimeLookup(
            str(tmp_path / "schedule.csv"), str(tmp_path / "traffic.csv"),
            "Europe/Moscow", demo_units="99", demo_initial_delay_s=180,
        )
        del base
        telemetry = TelemetryService()
        predictions = PredictionStore()
        incidents = IncidentStore()

        def ml_response(request):
            payload = json.loads(request.content)
            assert len(payload["planned_stops"]) > 2
            return httpx.Response(200, json={
                "prediction": 170.0, "p_late": 0.8,
                "risk_model_version": "test-calibration",
                "model": "lightgbm_plan", "model_version": "test",
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(ml_response)) as client:
            service = RuntimePrediction(
                telemetry=telemetry, lookup=lookup, predictions=predictions,
                incidents=incidents, ml_client=client,
            )
            now = datetime.now(timezone.utc)
            event = TelemetryEvent(
                unit_id=99, received_at=now,
                nav=NavData(timestamp=int(now.timestamp()), latitude=55.7,
                            longitude=37.6, speed_avg=4),
            )
            telemetry.record(event)
            service.on_event(event)
            await asyncio.sleep(0.05)
            result = predictions.get_latest(9_000_000)
            assert result is not None
            assert result.source == "demo"
            assert result.current_delay_source == "demo_anchor"
            assert result.risk == "high" and result.risk_source == "calibrated_probability"
            assert 600 < (result.target_time - result.prediction_time).total_seconds() <= 900
            await service.stop()

    asyncio.run(scenario())


def test_tcp_ndtp_packet_reaches_ml_without_manual_api(tmp_path):
    async def scenario():
        _lookup(tmp_path)
        lookup = RuntimeLookup(
            str(tmp_path / "schedule.csv"), str(tmp_path / "traffic.csv"),
            demo_units="99",
        )
        telemetry = TelemetryService()
        predictions = PredictionStore()
        incidents = IncidentStore()

        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={
                "prediction": 180.0, "p_late": 0.75,
                "model": "lightgbm_plan", "model_version": "test",
            })
        )) as client:
            engine = RuntimePrediction(
                telemetry=telemetry, lookup=lookup, predictions=predictions,
                incidents=incidents, ml_client=client,
            )

            async def on_event(event):
                if telemetry.record(event):
                    engine.on_event(event)

            server = NdtServer(on_event=on_event, host="127.0.0.1", port=0)
            await server.start()
            _, writer = await asyncio.open_connection("127.0.0.1", server.port)
            now = datetime.now(timezone.utc)
            row = TelemetryRow(
                tr_id=9_000_000, unit_id=99,
                event_time=now, receive_time=now,
                latitude=55.7, longitude=37.6,
                speed_kmh=4, heading=0, location_valid=True,
            )
            writer.write(ndtp.build_handshake(99, 1))
            writer.write(ndtp.build_realtime(row, now, 2))
            await writer.drain()
            await asyncio.sleep(0.1)
            assert telemetry.count() == 1
            assert predictions.get_latest(9_000_000) is not None
            assert len(incidents.list_all()) == 1
            writer.close()
            await writer.wait_closed()
            await server.stop()
            await engine.stop()

    asyncio.run(scenario())
