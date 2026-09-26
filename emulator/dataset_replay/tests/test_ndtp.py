from datetime import datetime, timedelta, timezone

from dataset_replay.app.models import TelemetryRow
from dataset_replay.app.ndtp import build_handshake, build_realtime
from dataset_replay.app.models import ReplayStartRequest, TimeMode
from dataset_replay.app.replay import _packet_time


def test_frames_are_accepted_by_backend_parser() -> None:
    # Imported here so this test explicitly guards the cross-service contract.
    from backend.app.ndtp.parser import HandshakeRequest, RealtimePacket, parse_packet

    unit_id = 664030
    _, handshake = parse_packet(build_handshake(unit_id, 1))
    assert isinstance(handshake, HandshakeRequest)
    assert handshake.peer_address == unit_id

    row = TelemetryRow(
        tr_id=115106,
        unit_id=unit_id,
        event_time=datetime(2026, 1, 6, 12, 30, 31, tzinfo=timezone.utc),
        receive_time=datetime(2026, 1, 6, 12, 30, 32, tzinfo=timezone.utc),
        latitude=55.7551234,
        longitude=37.617321,
        altitude_m=150,
        speed_kmh=42.4,
        heading=123,
        location_valid=True,
    )
    _, packet = parse_packet(build_realtime(row, row.event_time, 2, 321))
    assert isinstance(packet, RealtimePacket)
    nav = packet.cells[0]
    assert nav.latitude == 55.7551234
    assert nav.longitude == 37.617321
    assert nav.speed_avg == 42.0
    assert nav.course == 123
    assert nav.track_m == 321
    assert nav.speed_max is None
    assert nav.satellites is None
    assert nav.battery_voltage_mv is None


def test_southern_western_coordinates_keep_sign() -> None:
    from backend.app.ndtp.parser import parse_packet

    row = TelemetryRow(
        tr_id=1,
        unit_id=2,
        event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        receive_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        latitude=-33.9,
        longitude=-151.2,
        location_valid=True,
    )
    _, packet = parse_packet(build_realtime(row, row.event_time, 1))
    assert packet.cells[0].latitude == -33.9
    assert packet.cells[0].longitude == -151.2


def test_original_moscow_clock_survives_ndtp_and_speedup() -> None:
    from backend.app.ndtp.parser import parse_packet

    source_start = datetime(2026, 1, 6, 8, 0)
    row = TelemetryRow(
        tr_id=1, unit_id=2,
        event_time=source_start + timedelta(minutes=10),
        receive_time=source_start + timedelta(minutes=10),
        latitude=55.75, longitude=37.62, location_valid=True,
    )
    request = ReplayStartRequest(
        tr_ids=[1], time_mode=TimeMode.ORIGINAL, speed_multiplier=60,
    )
    emulated = _packet_time(row, source_start, datetime.now(timezone.utc), request)
    _, packet = parse_packet(build_realtime(row, emulated, 1))
    expected_utc = datetime(2026, 1, 6, 5, 10, tzinfo=timezone.utc)
    assert packet.cells[0].timestamp == int(expected_utc.timestamp())
