"""Minimal NDTP 6.2 encoder used by the independent replay client."""

from __future__ import annotations

import math
import struct
from datetime import datetime, timezone

from .models import TelemetryRow

NPL_SIGNATURE = 0x7E7E
NPL_TYPE_NPH = 0x02
SERVICE_GENERIC_CONTROLS = 0
SERVICE_NAVDATA = 1
NPH_TYPE_CONN_REQUEST = 100
NPH_TYPE_REALTIME = 101
CELL_NAV00 = 0


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _nph(service_id: int, packet_type: int, request_id: int) -> bytes:
    return struct.pack("<HHHI", service_id, packet_type, 1, request_id)


def _frame(unit_id: int, body: bytes) -> bytes:
    crc = crc16_modbus(body)
    swapped_crc = struct.unpack("<H", struct.pack(">H", crc))[0]
    npl = struct.pack(
        "<HHHHBIH", NPL_SIGNATURE, len(body), 0x0002, swapped_crc,
        NPL_TYPE_NPH, unit_id, 0,
    )
    return npl + body


def build_handshake(unit_id: int, request_id: int) -> bytes:
    body = _nph(SERVICE_GENERIC_CONTROLS, NPH_TYPE_CONN_REQUEST, request_id)
    body += struct.pack("<HHHIII", 6, 2, 0, unit_id, 65535, 0)
    return _frame(unit_id, body)


def _uint(value: float | None, maximum: int, default: int = 0) -> int:
    if value is None or not math.isfinite(value):
        return default
    return max(0, min(maximum, round(value)))


def build_realtime(
    row: TelemetryRow,
    emulated_time: datetime,
    request_id: int,
    track_m: int = 0,
) -> bytes:
    latitude = row.latitude or 0.0
    longitude = row.longitude or 0.0
    flags = 0
    if latitude >= 0:
        flags |= 0x20
    if longitude >= 0:
        flags |= 0x40
    if row.location_valid:
        flags |= 0x80
    if emulated_time.tzinfo is None:
        emulated_time = emulated_time.replace(tzinfo=timezone.utc)
    speed = _uint(row.speed_kmh, 65535)
    nav = struct.pack(
        "<IIIBBHHHHHBB",
        int(emulated_time.timestamp()),
        _uint(abs(longitude) * 1e7, 0xFFFFFFFF),
        _uint(abs(latitude) * 1e7, 0xFFFFFFFF),
        flags,
        250,
        speed,
        speed,
        _uint(row.heading, 360),
        track_m % 65536,
        _uint(row.altitude_m, 65535, 150),
        9,
        2,
    )
    body = _nph(SERVICE_NAVDATA, NPH_TYPE_REALTIME, request_id)
    body += bytes((CELL_NAV00, 0)) + nav
    return _frame(row.unit_id, body)
