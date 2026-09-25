"""Бинарный парсер протокола NDTP.

Каждый кадр NDTP: [NPL 15 байт][NPH 10 байт][тело].
Все поля little-endian. Здесь живёт ВСЁ знание о протоколе: наружу модуль
отдаёт только normalized-объекты из app.ndtp.schemas.
"""

import struct
from dataclasses import dataclass

NPL_SIZE = 15
NPH_SIZE = 10
NPL_SIGNATURE = 0x7E7E
NPL_TYPE_NPH = 0x02

SERVICE_GENERIC_CONTROLS = 0
SERVICE_NAVDATA = 1
NPH_TYPE_CONN_REQUEST = 100
NPH_TYPE_REALTIME = 101

NAV_SATELLITES_WITH_ALTITUDE = 63

CELL_NAV00 = 0
CELL_INT_SENSOR02 = 2
CELL_USI08 = 8
CELL_CAN10 = 10
CELL_TERMO16 = 16

_CELL_STRUCTS: dict[int, str] = {
    # timestamp, longitude, latitude, extra_dop, bat_voltage,
    # speed_avg, speed_max, course, track, altitude, nsat, pdop
    CELL_NAV00: "<IIIBBHHHHHBB",
    # an_in0..3, di_in, di_out, di0..3_counter, odometer, csq, gprs_state,
    # accel_energy, ext_volt
    CELL_INT_SENSOR02: "<HHHHBBHHHHIBBBb",
    CELL_USI08: "<BHHB",
    # sec_flag_status, all_time_engine, all_track, all_fuel_consum,
    # fuel_level, speed_turn_engine, t_engine, speed, pressure_axis(5), flag_alarm
    CELL_CAN10: "<IIIIHHhB5HI",
    CELL_TERMO16: "<Ii",
}

CELL_SIZES: dict[int, int] = {
    cell_type: struct.calcsize(fmt)
    for cell_type, fmt in _CELL_STRUCTS.items()
}

# Типы, которые мы умеем пропускать целиком (размер известен из спеки),
# но не декодируем: не нужны для прогноза задержки.
SKIPPABLE_CELL_SIZES: dict[int, int] = {15: 50}


class NdtParseError(ValueError):
    """Невалидный или неподдерживаемый NDTP-пакет."""


@dataclass(frozen=True)
class NplHeader:
    signature: int
    data_size: int
    crc: int
    crc_enabled: bool
    packet_type: int
    peer_address: int
    request_id: int


@dataclass(frozen=True)
class NphHeader:
    service_id: int
    packet_type: int
    is_request: bool
    request_id: int


@dataclass(frozen=True)
class HandshakeRequest:
    peer_address: int
    proto_major: int
    proto_minor: int


@dataclass(frozen=True)
class Nav00:
    timestamp: int
    latitude: float
    longitude: float
    coordinates_valid: bool
    alert: bool
    sos: bool
    battery_voltage_mv: int
    speed_avg: float
    speed_max: float
    course: int
    track_m: int
    altitude_m: int
    satellites: int
    pdop: int


@dataclass(frozen=True)
class IntSensor02:
    di0_counter: int
    di1_counter: int
    di2_counter: int
    di3_counter: int
    odometer: int
    csq: int
    gprs_state: int


@dataclass(frozen=True)
class Usi08:
    det_status: int
    level_mm: int
    level_l: int
    temperature: int


@dataclass(frozen=True)
class Can10:
    speed_kmh: float
    engine_rpm: int
    engine_temp_c: int
    odometer_km: int
    engine_hours: float
    alarm_flags: int


@dataclass(frozen=True)
class Termo16:
    status: int
    temperature_c: int


@dataclass(frozen=True)
class RealtimePacket:
    peer_address: int
    request_id: int
    cells: dict[int | str, object]


def crc16_modbus(data: bytes) -> int:
    """CRC-16/Modbus (poly 0xA001, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def parse_npl(frame: bytes) -> NplHeader:
    """Распаковать 15-байтный заголовок NPL и проверить CRC."""
    if len(frame) < NPL_SIZE:
        raise NdtParseError(f"NPL короче {NPL_SIZE} байт")

    signature, data_size = struct.unpack_from("<HH", frame, 0)
    if signature != NPL_SIGNATURE:
        raise NdtParseError(f"неверная сигнатура NPL: 0x{signature:04X}")

    flags = struct.unpack_from("<H", frame, 4)[0]
    crc_stored = struct.unpack_from("<H", frame, 6)[0]
    packet_type = frame[8]
    # packed layout: 0..1 signature, 2..3 dataSize, 4..5 flags, 6..7 crc,
    # 8 type, 9..12 peerAddress, 13..14 requestId
    peer_address, request_id = struct.unpack_from("<IH", frame, 9)

    npl_and_body = frame[NPL_SIZE : NPL_SIZE + data_size]
    if len(npl_and_body) < data_size:
        raise NdtParseError("усечённый кадр: не хватает данных тела")

    crc_enabled = bool(flags & 0x02)
    if crc_enabled:
        # в NPL значение кладётся со свапнутыми байтами
        expected = struct.unpack("<H", struct.pack(">H", crc_stored))[0]
        actual = crc16_modbus(npl_and_body)
        if expected != actual:
            raise NdtParseError(
                f"CRC NPL не совпал: 0x{expected:04X} != 0x{actual:04X}"
            )

    return NplHeader(
        signature=signature,
        data_size=data_size,
        crc=crc_stored,
        crc_enabled=crc_enabled,
        packet_type=packet_type,
        peer_address=peer_address,
        request_id=request_id,
    )


def parse_nph(body: bytes) -> NphHeader:
    """Распаковать 10-байтный заголовок NPH."""
    if len(body) < NPH_SIZE:
        raise NdtParseError(f"NPH короче {NPH_SIZE} байт")
    service_id, packet_type, flags, request_id = struct.unpack_from(
        "<HHHI", body, 0
    )
    return NphHeader(
        service_id=service_id,
        packet_type=packet_type,
        is_request=bool(flags & 1),
        request_id=request_id,
    )


def parse_handshake(nph_body: bytes) -> HandshakeRequest:
    """Тело NPH_SGC_CONN_REQUEST: 18 байт."""
    if len(nph_body) < NPH_SIZE + 18:
        raise NdtParseError("усечённое тело handshake")
    (_proto_high, _proto_low, _flags, peer_address, _max_size, _reserved) = (
        struct.unpack_from("<HHHIII", nph_body, NPH_SIZE)
    )
    return HandshakeRequest(
        peer_address=peer_address,
        proto_major=6,
        proto_minor=2,
    )


def decode_cell(cell_type: int, payload: bytes) -> object | None:
    """Декодировать известную ячейку; None — если тип поддерживаем, но не нужен."""
    fmt = _CELL_STRUCTS.get(cell_type)
    if fmt is None:
        raise NdtParseError(f"неизвестный тип ячейки: {cell_type}")
    expected = struct.calcsize(fmt)
    if len(payload) < expected:
        raise NdtParseError(
            f"ячейка {cell_type}: expected {expected} bytes, got {len(payload)}"
        )
    values = struct.unpack_from(fmt, payload, 0)

    if cell_type == CELL_NAV00:
        (
            timestamp, longitude, latitude, extra_dop, bat_voltage,
            speed_avg, speed_max, course, track, altitude, nsat, _pdop,
        ) = values
        north = bool(extra_dop & 0x20)
        east = bool(extra_dop & 0x40)
        valid = bool(extra_dop & 0x80)
        if nsat == NAV_SATELLITES_WITH_ALTITUDE:
            altitude = 0
        return Nav00(
            timestamp=timestamp,
            latitude=latitude / 1e7 if north else -latitude / 1e7,
            longitude=longitude / 1e7 if east else -longitude / 1e7,
            coordinates_valid=valid,
            alert=bool(extra_dop & 0x02),
            sos=bool(extra_dop & 0x04),
            battery_voltage_mv=bat_voltage * 20,
            speed_avg=float(speed_avg),
            speed_max=float(speed_max),
            course=course,
            track_m=track,
            altitude_m=altitude,
            satellites=nsat,
            pdop=_pdop,
        )
    if cell_type == CELL_INT_SENSOR02:
        return IntSensor02(
            di0_counter=values[6],
            di1_counter=values[7],
            di2_counter=values[8],
            di3_counter=values[9],
            odometer=values[10],
            csq=values[11],
            gprs_state=values[12],
        )
    if cell_type == CELL_USI08:
        det_status, level_mm, level_l, temperature = values
        return Usi08(
            det_status=det_status,
            level_mm=level_mm,
            level_l=level_l,
            temperature=temperature,
        )
    if cell_type == CELL_CAN10:
        (
            _sec_flag, all_time_engine, all_track, _all_fuel,
            _fuel_level, rpm, t_engine, speed,
            _p1, _p2, _p3, _p4, _p5, flag_alarm,
        ) = values
        return Can10(
            speed_kmh=speed,
            engine_rpm=rpm,
            engine_temp_c=t_engine,
            odometer_km=all_track // 100,
            engine_hours=all_time_engine / 100,
            alarm_flags=flag_alarm,
        )
    if cell_type == CELL_TERMO16:
        status, temp = values
        return Termo16(status=status, temperature_c=temp)
    raise NdtParseError(f"неизвестный тип ячейки: {cell_type}")


def parse_realtime(npl: NplHeader, nph_body: bytes) -> RealtimePacket:
    """Разобрать тело NPH_SND_REALTIME на ячейки."""
    parse_nph(nph_body)
    offset = NPH_SIZE
    end = len(nph_body)
    cells: dict[int, object] = {}
    seen_counts: dict[int, int] = {}

    while offset < end:
        if end - offset < 2:
            raise NdtParseError("усечённый заголовок ячейки")
        cell_type, number = nph_body[offset], nph_body[offset + 1]
        offset += 2
        expected_count = seen_counts.get(cell_type, 0)
        if number != expected_count:
            raise NdtParseError(
                f"ячейка {cell_type}: unexpected number {number}"
            )
        seen_counts[cell_type] = expected_count + 1

        size = CELL_SIZES.get(cell_type) or SKIPPABLE_CELL_SIZES.get(cell_type)
        if size is None:
            raise NdtParseError(f"неизвестный тип ячейки: {cell_type}")
        payload = nph_body[offset : offset + size]
        if len(payload) < size:
            raise NdtParseError(f"усечённое тело ячейки {cell_type}")
        offset += size

        if cell_type in _CELL_STRUCTS:
            decoded = decode_cell(cell_type, payload)
            key = cell_type if cell_type == CELL_NAV00 else f"{cell_type}:{number}"
            cells[key] = decoded

    return RealtimePacket(
        peer_address=npl.peer_address,
        request_id=npl.request_id,
        cells=cells,
    )


def parse_packet(frame: bytes) -> tuple[NplHeader, HandshakeRequest | RealtimePacket]:
    """Полный разбор одного кадра NDTP в типизированную структуру."""
    npl = parse_npl(frame)
    nph_body = frame[NPL_SIZE : NPL_SIZE + npl.data_size]
    nph = parse_nph(nph_body)

    if nph.service_id == SERVICE_GENERIC_CONTROLS:
        if nph.packet_type != NPH_TYPE_CONN_REQUEST:
            raise NdtParseError(f"неподдерживаемый SGC type: {nph.packet_type}")
        return npl, parse_handshake(nph_body)

    if nph.service_id == SERVICE_NAVDATA:
        if nph.packet_type != NPH_TYPE_REALTIME:
            raise NdtParseError(f"неподдерживаемый NAVDATA type: {nph.packet_type}")
        return npl, parse_realtime(npl, nph_body)

    raise NdtParseError(f"неподдерживаемый serviceId: {nph.service_id}")


# ---------------------------------------------------------------------------
# Конструкторы пакетов — используются в тестах и отладочных скриптах,
# чтобы проверять парсер без запуска эмулятора.
# ---------------------------------------------------------------------------


def build_npl(data_size: int, peer_address: int, payload: bytes) -> bytes:
    """Собрать 15-байтный NPL с корректным CRC по NPH+телу."""
    crc = crc16_modbus(payload)
    swapped = struct.unpack("<H", struct.pack(">H", crc))[0]
    return struct.pack(
        "<HHHHBIH",
        NPL_SIGNATURE,
        data_size,
        0x0002,  # flags: crc enabled
        swapped,
        NPL_TYPE_NPH,
        peer_address,
        0,
    )


def build_nph(service_id: int, packet_type: int, request_id: int = 1) -> bytes:
    return struct.pack("<HHHI", service_id, packet_type, 1, request_id)


def build_handshake(unit_id: int, request_id: int = 1) -> bytes:
    body = build_nph(SERVICE_GENERIC_CONTROLS, NPH_TYPE_CONN_REQUEST, request_id)
    body += struct.pack("<HHHIII", 6, 2, 0, unit_id, 65535, 0)
    npl = build_npl(len(body), unit_id, body)
    return npl + body


def build_nav00_payload(
    timestamp: int,
    latitude: float,
    longitude: float,
    speed_avg: float = 0.0,
    course: int = 0,
) -> bytes:
    extra_dop = 0xE0  # координаты валидны, N/E
    return struct.pack(
        "<IIIBBHHHHHBB",
        timestamp,
        int(abs(longitude) * 1e7),
        int(abs(latitude) * 1e7),
        extra_dop,
        250,
        int(round(speed_avg)),
        int(round(speed_avg)),
        course,
        0,
        150,
        9,
        2,
    )


def build_realtime(
    unit_id: int,
    nav_payload: bytes,
    request_id: int = 1,
) -> bytes:
    body = build_nph(SERVICE_NAVDATA, NPH_TYPE_REALTIME, request_id)
    body += bytes([CELL_NAV00, 0]) + nav_payload
    npl = build_npl(len(body), unit_id, body)
    return npl + body
