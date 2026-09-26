"""Causal time-scaled replay scheduler."""

from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from time import monotonic

from .client import NdtpClient
from .config import Settings
from .models import (
    ReplayStartRequest,
    ReplayState,
    ReplayStatus,
    TelemetryRow,
    TimeMode,
    UnitReplayStatus,
)

logger = logging.getLogger(__name__)


def _distance_m(a: TelemetryRow | None, b: TelemetryRow) -> int:
    if a is None or not a.location_valid or not b.location_valid:
        return 0
    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return 0
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(b.longitude - a.longitude)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return int(6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)))


class ReplayManager:
    """Own a single replay session and expose concurrency-safe controls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._task: asyncio.Task | None = None
        self._continue = asyncio.Event()
        self._continue.set()
        self._stop = asyncio.Event()
        self._status = ReplayStatus()
        self._clients: dict[int, NdtpClient] = {}

    def status(self) -> ReplayStatus:
        snapshot = self._status.model_copy(deep=True)
        snapshot.sent_packets = sum(unit.sent_packets for unit in snapshot.units)
        if snapshot.total_packets:
            snapshot.progress = min(1.0, snapshot.sent_packets / snapshot.total_packets)
        return snapshot

    async def start(self, request: ReplayStartRequest, rows: list[TelemetryRow]) -> ReplayStatus:
        if self._task is not None and not self._task.done():
            raise RuntimeError("a replay is already running")
        await self._close_clients()
        counts: dict[tuple[int, int], int] = defaultdict(int)
        for row in rows:
            counts[(row.tr_id, row.unit_id)] += 1
        self._status = ReplayStatus(
            state=ReplayState.RUNNING,
            dataset=request.dataset,
            time_mode=request.time_mode,
            started_at=datetime.now(timezone.utc),
            total_packets=len(rows),
            units=[
                UnitReplayStatus(tr_id=tr_id, unit_id=unit_id, total_packets=count)
                for (tr_id, unit_id), count in sorted(counts.items())
            ],
        )
        host = request.target_host or self.settings.ndtp_target_host
        port = request.target_port or self.settings.ndtp_target_port
        self._clients = {
            unit.unit_id: NdtpClient(unit.unit_id, host, port, self.settings)
            for unit in self._status.units
        }
        self._stop.clear()
        self._continue.set()
        self._task = asyncio.create_task(self._run(request, rows), name="dataset-ndtp-replay")
        return self.status()

    async def pause(self) -> ReplayStatus:
        if self._status.state != ReplayState.RUNNING:
            raise RuntimeError("only a running replay can be paused")
        self._continue.clear()
        self._status.state = ReplayState.PAUSED
        return self.status()

    async def resume(self) -> ReplayStatus:
        if self._status.state != ReplayState.PAUSED:
            raise RuntimeError("only a paused replay can be resumed")
        self._status.state = ReplayState.RUNNING
        self._continue.set()
        return self.status()

    async def stop(self) -> ReplayStatus:
        if self._task is not None and not self._task.done():
            self._stop.set()
            self._continue.set()
            await self._task
        elif self._status.state not in {ReplayState.IDLE, ReplayState.COMPLETED}:
            self._status.state = ReplayState.STOPPED
        await self._close_clients()
        return self.status()

    async def shutdown(self) -> None:
        await self.stop()

    async def _run(self, request: ReplayStartRequest, rows: list[TelemetryRow]) -> None:
        try:
            while True:
                await self._run_cycle(request, rows)
                if self._stop.is_set() or not request.loop:
                    break
                for unit in self._status.units:
                    unit.sent_packets = 0
                    unit.source_time = None
                    unit.emulated_time = None
            self._status.state = ReplayState.STOPPED if self._stop.is_set() else ReplayState.COMPLETED
        except asyncio.CancelledError:
            self._status.state = ReplayState.STOPPED
            raise
        except Exception as exc:
            logger.exception("dataset replay failed")
            self._status.state = ReplayState.FAILED
            self._status.error = str(exc)
        finally:
            self._status.finished_at = datetime.now(timezone.utc)
            await self._close_clients()

    async def _run_cycle(self, request: ReplayStartRequest, rows: list[TelemetryRow]) -> None:
        source_start = rows[0].available_at
        wall_start = datetime.now(timezone.utc)
        clock_start = monotonic()
        paused_s = 0.0
        tracks: dict[int, int] = defaultdict(int)
        previous: dict[int, TelemetryRow] = {}
        statuses = {(unit.tr_id, unit.unit_id): unit for unit in self._status.units}

        for row in rows:
            if self._stop.is_set():
                return
            target_elapsed = (row.available_at - source_start).total_seconds()
            while True:
                if not self._continue.is_set():
                    pause_started = monotonic()
                    await self._continue.wait()
                    paused_s += monotonic() - pause_started
                    if self._stop.is_set():
                        return
                remaining = target_elapsed - (monotonic() - clock_start - paused_s)
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=min(remaining, 0.5))
                    return
                except asyncio.TimeoutError:
                    pass

            source_delta = row.event_time - source_start
            emulated_time = (
                row.event_time
                if request.time_mode == TimeMode.ORIGINAL
                else wall_start.replace(tzinfo=None) + source_delta
            )
            tracks[row.unit_id] += _distance_m(previous.get(row.unit_id), row)
            previous[row.unit_id] = row
            status = statuses[(row.tr_id, row.unit_id)]
            client = self._clients[row.unit_id]
            while not self._stop.is_set():
                await self._continue.wait()
                try:
                    await client.send(row, emulated_time, tracks[row.unit_id])
                    status.connected = client.connected
                    status.sent_packets += 1
                    status.source_time = row.event_time
                    status.emulated_time = emulated_time
                    status.last_error = None
                    break
                except (OSError, asyncio.TimeoutError, ConnectionError) as exc:
                    status.connected = False
                    status.last_error = str(exc)
                    logger.warning(
                        "packet send failed for unit_id=%d; retrying: %s",
                        row.unit_id,
                        exc,
                    )
                    try:
                        await asyncio.wait_for(
                            self._stop.wait(), timeout=self.settings.reconnect_delay_s,
                        )
                    except asyncio.TimeoutError:
                        pass

    async def _close_clients(self) -> None:
        if self._clients:
            await asyncio.gather(*(client.close() for client in self._clients.values()))
        self._clients = {}
