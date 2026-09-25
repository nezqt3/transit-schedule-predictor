"""End-to-end тест NDTP TCP-сервера: байты -> TelemetryEvent."""

import asyncio

from app.ndtp import parser
from app.ndtp.server import NdtServer
from app.services.telemetry import TelemetryService


async def _send_frames(server: NdtServer) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(parser.build_handshake(unit_id=777))
    writer.write(
        parser.build_realtime(
            unit_id=777,
            nav_payload=parser.build_nav00_payload(
                timestamp=1725000000,
                latitude=55.76,
                longitude=37.62,
                speed_avg=16,
            ),
        )
    )
    await writer.drain()
    await asyncio.sleep(0.2)
    writer.close()
    await writer.wait_closed()


def test_server_emits_telemetry_event():
    service = TelemetryService()

    async def run() -> None:
        server = NdtServer(on_event=service.handle_event, host="127.0.0.1", port=0)
        await server.start()
        try:
            await _send_frames(server)
            await asyncio.sleep(0.1)
        finally:
            await server.stop()

        event = service.get_latest(777)
        assert event is not None
        assert event.unit_id == 777
        assert event.nav is not None
        assert event.nav.latitude == 55.76
        assert event.nav.speed_avg == 16

    asyncio.run(run())
