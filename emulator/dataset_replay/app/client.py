"""Persistent NDTP connections, one per emulated terminal."""

from __future__ import annotations

import asyncio
import logging

from . import ndtp
from .config import Settings
from .models import TelemetryRow

logger = logging.getLogger(__name__)


class NdtpClient:
    """Send one vehicle's packets and reconnect after transport failures."""

    def __init__(self, unit_id: int, host: str, port: int, settings: Settings) -> None:
        self.unit_id = unit_id
        self.host = host
        self.port = port
        self.settings = settings
        self.writer: asyncio.StreamWriter | None = None
        self.request_id = 0
        self.connected = False

    def _next_request_id(self) -> int:
        self.request_id = (self.request_id + 1) & 0xFFFFFFFF
        return self.request_id

    async def connect(self) -> None:
        if self.writer is not None and not self.writer.is_closing():
            return
        _, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.settings.connect_timeout_s,
        )
        self.writer.write(ndtp.build_handshake(self.unit_id, self._next_request_id()))
        await self.writer.drain()
        await asyncio.sleep(self.settings.handshake_delay_s)
        self.connected = True
        logger.info("NDTP connected: unit_id=%d target=%s:%d", self.unit_id, self.host, self.port)

    async def send(self, row: TelemetryRow, emulated_time, track_m: int) -> None:
        for attempt in range(2):
            try:
                await self.connect()
                assert self.writer is not None
                self.writer.write(ndtp.build_realtime(
                    row, emulated_time, self._next_request_id(), track_m,
                ))
                await self.writer.drain()
                return
            except (OSError, asyncio.TimeoutError, ConnectionError):
                await self.close()
                if attempt == 1:
                    raise
                await asyncio.sleep(self.settings.reconnect_delay_s)

    async def close(self) -> None:
        writer, self.writer = self.writer, None
        self.connected = False
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ConnectionError):
                pass

