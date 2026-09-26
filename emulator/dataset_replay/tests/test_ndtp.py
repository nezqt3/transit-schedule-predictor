from datetime import datetime, timezone

from dataset_replay.app.models import TelemetryRow
from dataset_replay.app.ndtp import build_handshake, build_realtime


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
