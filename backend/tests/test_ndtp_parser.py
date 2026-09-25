"""Round-trip тесты бинарного парсера NDTP."""

import struct

import pytest

from app.ndtp import parser
from app.ndtp.parser import NdtParseError


def test_crc16_modbus_reference():
    # контрольная сумма "123456789" для CRC-16/Modbus
    assert parser.crc16_modbus(b"123456789") == 0x4B37


def test_parse_handshake():
    frame = parser.build_handshake(unit_id=1166336)
    npl, packet = parser.parse_packet(frame)

    assert npl.peer_address == 1166336
    assert isinstance(packet, parser.HandshakeRequest)
    assert packet.peer_address == 1166336


def test_parse_realtime_nav():
    payload = parser.build_nav00_payload(
        timestamp=1725000000,
        latitude=55.7551234,
        longitude=37.6173210,
        speed_avg=23,
        course=90,
    )
    frame = parser.build_realtime(unit_id=1166336, nav_payload=payload)
    npl, packet = parser.parse_packet(frame)

    assert isinstance(packet, parser.RealtimePacket)
    nav = packet.cells[parser.CELL_NAV00]
    assert nav.timestamp == 1725000000
    assert nav.latitude == pytest.approx(55.7551234, abs=1e-7)
    assert nav.longitude == pytest.approx(37.6173210, abs=1e-7)
    assert nav.coordinates_valid
    assert nav.speed_avg == pytest.approx(23)
    assert nav.course == 90


def test_bad_signature_rejected():
    frame = bytearray(parser.build_handshake(unit_id=1))
    frame[0] = 0x00
    with pytest.raises(NdtParseError, match="сигнатура"):
        parser.parse_packet(bytes(frame))


def test_bad_crc_rejected():
    frame = bytearray(parser.build_handshake(unit_id=1))
    frame[-1] ^= 0xFF  # испортить тело -> CRC не сойдётся
    with pytest.raises(NdtParseError, match="CRC"):
        parser.parse_packet(bytes(frame))


def test_truncated_frame_rejected():
    frame = parser.build_realtime(
        unit_id=1,
        nav_payload=parser.build_nav00_payload(1, 55.7, 37.6),
    )
    with pytest.raises(NdtParseError):
        parser.parse_packet(frame[: len(frame) - 5])


def test_unknown_cell_type_rejected():
    body = parser.build_nph(parser.SERVICE_NAVDATA, parser.NPH_TYPE_REALTIME)
    body += bytes([99, 0]) + b"\x00" * 4
    npl = parser.build_npl(len(body), 1, body)
    with pytest.raises(NdtParseError, match="неизвестный тип ячейки"):
        parser.parse_packet(npl + body)


def test_can10_fields():
    payload = struct.pack(
        parser._CELL_STRUCTS[parser.CELL_CAN10],
        0xFFFFFFFF,  # sec_flag_status
        125,         # engine hours x100 = 1.25 ч
        412000,      # all_track = 4120 км
        0,           # all_fuel_consum
        0,           # fuel_level
        1800,        # rpm
        87,          # t_engine
        42,          # speed km/h
        0, 0, 0, 0, 0,
        0,           # flag_alarm
    )
    decoded = parser.decode_cell(parser.CELL_CAN10, payload)
    assert decoded.speed_kmh == 42
    assert decoded.engine_rpm == 1800
    assert decoded.engine_temp_c == 87
    assert decoded.odometer_km == 4120
    assert decoded.engine_hours == pytest.approx(1.25)


def test_emulator_realtime_cells_follow_published_layout():
    assert parser.CELL_SIZES[parser.CELL_NAV00] == 26
    assert parser.CELL_SIZES[parser.CELL_INT_SENSOR02] == 26
    assert parser.CELL_SIZES[parser.CELL_CAN10] == 37

    body = parser.build_nph(parser.SERVICE_NAVDATA, parser.NPH_TYPE_REALTIME)
    body += bytes([parser.CELL_NAV00, 0]) + parser.build_nav00_payload(
        timestamp=1725000000, latitude=55.7551234,
        longitude=37.6173210, speed_avg=23,
    )
    body += bytes([parser.CELL_USI08, 0]) + struct.pack("<BHHB", 0, 100, 50, 20)
    body += bytes([parser.CELL_TERMO16, 0]) + struct.pack("<Ii", 0, 22)
    body += bytes([parser.CELL_INT_SENSOR02, 0]) + struct.pack(
        parser._CELL_STRUCTS[parser.CELL_INT_SENSOR02],
        0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 1000, 15, 1, 0, 0,
    )
    body += bytes([parser.CELL_CAN10, 0]) + struct.pack(
        parser._CELL_STRUCTS[parser.CELL_CAN10],
        0, 125, 412000, 0, 0, 1800, 87, 42,
        0, 0, 0, 0, 0, 0x10000,
    )
    frame = parser.build_npl(len(body), 1166336, body) + body

    _, packet = parser.parse_packet(frame)
    assert packet.cells[parser.CELL_NAV00].latitude == pytest.approx(55.7551234)
    assert packet.cells[parser.CELL_NAV00].longitude == pytest.approx(37.6173210)
    assert packet.cells[f"{parser.CELL_CAN10}:0"].alarm_flags == 0x10000
