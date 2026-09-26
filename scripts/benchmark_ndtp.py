"""Prepare and run a 100-unit TCP NDTP load test against a running stack."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import platform
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import websockets  # noqa: E402

from emulator.dataset_replay.app import ndtp  # noqa: E402
from emulator.dataset_replay.app.models import TelemetryRow  # noqa: E402

OUTPUT = ROOT / "data" / "processed" / "benchmark"


def prepare(units: int) -> None:
    """Write a clearly synthetic plan and terminal mapping before Compose starts."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    anchor = datetime.now(timezone.utc).replace(microsecond=0)
    with (OUTPUT / "benchmark_schedule.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["tr_id", "tt_action_item_id", "time_begin", "geom"])
        for index in range(units):
            tr_id = 9_100_000 + index
            lon, lat = 37.5 + index * 0.001, 55.7 + index * 0.0005
            for stop_index, minute in enumerate([0, 5, 10] + list(range(13, 79, 5))):
                writer.writerow([
                    tr_id, tr_id * 1000 + stop_index,
                    (anchor + timedelta(minutes=minute)).astimezone(
                        ZoneInfo("Europe/Moscow")
                    ).replace(tzinfo=None).isoformat(),
                    f"POINT ({lon} {lat})",
                ])
    with (OUTPUT / "benchmark_mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["tr_id", "unit_id"])
        for index in range(units):
            writer.writerow([9_100_000 + index, 7_100_000 + index])
    print(f"Prepared {units} synthetic vehicles at {OUTPUT}; anchor={anchor.isoformat()}")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]


async def run(args) -> None:
    base = args.backend_url.rstrip("/")
    async with httpx.AsyncClient(timeout=10, trust_env=False) as http:
        for attempt in range(30):
            login = await http.post(f"{base}/api/v1/auth/token", data={
                "username": args.username, "password": args.password,
            })
            if login.status_code != 503:
                break
            await asyncio.sleep(1)
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        before = (await http.get(f"{base}/api/v1/metrics", headers=headers)).json()

        ws_url = base.replace("https://", "wss://").replace("http://", "ws://")
        latencies = []
        sends: dict[tuple[int, int], float] = {}
        first_send: float | None = None
        first_prediction: float | None = None
        stop = asyncio.Event()

        async def read_ws():
            nonlocal first_prediction
            async with websockets.connect(
                f"{ws_url}/api/v1/ws",
                additional_headers={"Cookie": f"{args.cookie_name}={token}"},
            ) as socket:
                while not stop.is_set():
                    try:
                        event = json.loads(await asyncio.wait_for(socket.recv(), timeout=1))
                    except asyncio.TimeoutError:
                        continue
                    if event.get("type") == "prediction_update":
                        payload = event["data"]
                        unit_id = payload["unit_id"]
                        event_time = payload.get("input_event_time")
                        if not event_time:
                            continue
                        key = (unit_id, int(datetime.fromisoformat(event_time).timestamp()))
                        sent_at = sends.pop(key, None)
                        if sent_at is not None:
                            received = time.monotonic()
                            latencies.append(received - sent_at)
                            if first_prediction is None:
                                first_prediction = received

        async def send_unit(index: int):
            nonlocal first_send
            unit_id, tr_id = 7_100_000 + index, 9_100_000 + index
            lon, lat = 37.5 + index * 0.001, 55.7 + index * 0.0005
            if not args.synchronized:
                # Independent terminals have uniformly distributed send phases.
                await asyncio.sleep(index * args.interval_s / args.units)
            _, writer = await asyncio.open_connection(args.ndtp_host, args.ndtp_port)
            try:
                writer.write(ndtp.build_handshake(unit_id, 1))
                await writer.drain()
                started = time.monotonic()
                packet = 0
                while time.monotonic() - started < args.duration_s:
                    now = datetime.now(timezone.utc)
                    row = TelemetryRow(
                        tr_id=tr_id, unit_id=unit_id, event_time=now,
                        receive_time=now, latitude=lat, longitude=lon,
                        speed_kmh=0, heading=0, location_valid=True,
                    )
                    sent_at = time.monotonic()
                    if first_send is None:
                        first_send = sent_at
                    sends[(unit_id, int(now.timestamp()))] = sent_at
                    writer.write(ndtp.build_realtime(row, now, packet + 2))
                    await writer.drain()
                    packet += 1
                    await asyncio.sleep(args.interval_s)
                return packet
            finally:
                writer.close()
                await writer.wait_closed()

        listener = asyncio.create_task(read_ws())
        await asyncio.sleep(0.2)
        counts = await asyncio.gather(*(send_unit(index) for index in range(args.units)))
        await asyncio.sleep(2)
        stop.set()
        await listener
        after = (await http.get(f"{base}/api/v1/metrics", headers=headers)).json()
        report = {
            "environment": {
                "system": platform.platform(),
                "cpu": platform.processor(),
                "logical_cpus": os.cpu_count(),
                "python": platform.python_version(),
            },
            "units": args.units, "duration_s": args.duration_s,
            "interval_s": args.interval_s, "packets_sent": sum(counts),
            "send_phase": "synchronized" if args.synchronized else "uniform",
            "accepted_delta": after["ndtp"]["accepted_packets"] - before["ndtp"]["accepted_packets"],
            "lost_correct_packets": (sum(counts) - after["ndtp"]["accepted_packets"]
                                     + before["ndtp"]["accepted_packets"]),
            "invalid_delta": after["ndtp"]["invalid_packets"] - before["ndtp"]["invalid_packets"],
            "ignored_delta": after["ndtp"]["ignored_packets"] - before["ndtp"]["ignored_packets"],
            "prediction_delta": after["prediction"]["requests_succeeded"] - before["prediction"]["requests_succeeded"],
            "model_calls_delta": after["prediction"]["requests_started"] - before["prediction"]["requests_started"],
            "model_calls_per_unit": ((after["prediction"]["requests_started"] - before["prediction"]["requests_started"]) / args.units),
            "first_prediction_after_first_send_s": (
                first_prediction - first_send
                if first_prediction is not None and first_send is not None else None
            ),
            "stack_cold_start_s": args.stack_cold_start_s,
            "stack_cold_start_note": (
                "Measured separately from docker compose up --build (cached images) "
                "to healthy HTTP endpoints"
                if args.stack_cold_start_s is not None else "Not measured"
            ),
            "ws_prediction_samples": len(latencies),
            "packet_to_ws_p50_s": percentile(latencies, 0.50),
            "packet_to_ws_p95_s": percentile(latencies, 0.95),
            "packet_to_ws_p99_s": percentile(latencies, 0.99),
            "backend_metrics_after": after,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--units", type=int, default=100)
    parser.add_argument("--duration-s", type=int, default=600)
    parser.add_argument("--interval-s", type=int, default=15)
    parser.add_argument("--synchronized", action="store_true",
                        help="Send all terminals in a burst instead of independent phases")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--ndtp-host", default="127.0.0.1")
    parser.add_argument("--ndtp-port", type=int, default=9201)
    parser.add_argument("--username", default=os.getenv("AUTH_BOOTSTRAP_USERNAME", "dispatcher"))
    parser.add_argument("--password", default=os.getenv("AUTH_BOOTSTRAP_PASSWORD", "transport"))
    parser.add_argument("--cookie-name", default=os.getenv("AUTH_COOKIE_NAME", "transport_session"))
    parser.add_argument("--report")
    parser.add_argument("--stack-cold-start-s", type=float)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.units)
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
