"""Async TCP-сервер приёма NDTP-телеметрии.

Заканчивает знание о протоколе: наружу отдаёт только TelemetryEvent.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.ndtp import parser
from app.ndtp.parser import HandshakeRequest, NdtParseError, RealtimePacket
from app.ndtp.schemas import CanData, NavData, TelemetryEvent

logger = logging.getLogger(__name__)

EventCallback = Callable[[TelemetryEvent], Awaitable[None]]

HEADER_READ_SIZE = 8  # NPL: signature..packet_type, data_size на 2..4
MAX_DATA_SIZE = 65535


class NdtServer:
    """TCP-сервер: читает кадры NDTP и транслирует их в TelemetryEvent."""

    def __init__(
        self,
        on_event: EventCallback,
        host: str = "0.0.0.0",
        port: int = 9201,
    ) -> None:
        self._on_event = on_event
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._units: dict[str, int] = {}  # peer -> unitId после handshake

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
        )
        # при port=0 OS назначает свободный порт — запоминаем фактический
        self.port = self._server.sockets[0].getsockname()[1]
        sockets = ", ".join(str(s.getsockname()) for s in self._server.sockets)
        logger.info("NDTP TCP server listening on %s", sockets)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("NDTP TCP server stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        peer_key = str(peer)
        logger.info("NDTP client connected: %s", peer)
        try:
            while True:
                try:
                    frame = await self._read_frame(reader)
                except asyncio.IncompleteReadError:
                    logger.info("NDTP client disconnected: %s", peer)
                    break

                try:
                    npl, packet = parser.parse_packet(frame)
                except NdtParseError as exc:
                    logger.warning(
                        "invalid NDTP packet from %s: %s", peer, exc
                    )
                    continue

                if isinstance(packet, HandshakeRequest):
                    self._units[peer_key] = packet.peer_address
                    logger.info(
                        "NDTP handshake: unit_id=%d from %s",
                        packet.peer_address,
                        peer,
                    )
                    continue

                event = self._to_event(packet)
                if event is None:
                    continue
                try:
                    await self._on_event(event)
                except Exception:
                    logger.exception(
                        "telemetry consumer failed for unit_id=%d",
                        event.unit_id,
                    )
        except ConnectionResetError:
            logger.info("NDTP connection reset: %s", peer)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("NDTP connection error: %s", peer)
        finally:
            self._units.pop(peer_key, None)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass

    @staticmethod
    async def _read_frame(reader: asyncio.StreamReader) -> bytes:
        """Прочитать ровно один кадр: NPL(15) + dataSize."""
        head = await reader.readexactly(parser.NPL_SIZE)
        data_size = int.from_bytes(head[2:4], "little")
        if data_size > MAX_DATA_SIZE:
            raise NdtParseError(f"подозрительный dataSize: {data_size}")
        body = await reader.readexactly(data_size)
        return head + body

    @staticmethod
    def _to_event(packet: RealtimePacket) -> TelemetryEvent | None:
        event = TelemetryEvent.now(packet.peer_address)

        nav = packet.cells.get(parser.CELL_NAV00)
        if nav is not None:
            event.nav = NavData(
                timestamp=nav.timestamp,
                latitude=nav.latitude,
                longitude=nav.longitude,
                coordinates_valid=nav.coordinates_valid,
                speed_avg=nav.speed_avg,
                speed_max=nav.speed_max,
                course=nav.course,
                track_m=nav.track_m,
                altitude_m=nav.altitude_m,
                satellites=nav.satellites,
                battery_voltage_mv=nav.battery_voltage_mv,
                alert_flag=nav.alert,
                sos_flag=nav.sos,
            )

        can = packet.cells.get(f"{parser.CELL_CAN10}:0")
        if can is not None:
            event.can = CanData(
                speed_kmh=can.speed_kmh,
                engine_rpm=can.engine_rpm,
                engine_temp_c=can.engine_temp_c,
                odometer_km=can.odometer_km,
                engine_hours=can.engine_hours,
                alarm_flags=can.alarm_flags,
            )

        if event.nav is None and event.can is None:
            return None
        return event
