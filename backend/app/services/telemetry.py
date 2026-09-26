"""Хранение текущего состояния ТС по телеметрии.

Временное in-memory состояние для демки; при подключении БД сюда же
добавится запись history. API и ML-пайплайн читают события только через
нормализованный TelemetryEvent.
"""

import asyncio
from collections import OrderedDict, deque
from datetime import timedelta
from threading import RLock

from app.ndtp.schemas import TelemetryEvent


class TelemetryService:
    """In-memory реестр последних телеметрия-событий по каждому устройству."""

    def __init__(self, max_units: int = 500, max_points: int = 150) -> None:
        self._latest: OrderedDict[int, TelemetryEvent] = OrderedDict()
        self._history: OrderedDict[int, deque[TelemetryEvent]] = OrderedDict()
        self._max_units = max_units
        self._max_points = max_points
        self._lock = RLock()
        self._subscribers: set[asyncio.Queue[TelemetryEvent]] = set()

    def record(self, event: TelemetryEvent) -> None:
        """Сохранить последнее событие устройства."""
        with self._lock:
            self._latest.pop(event.unit_id, None)
            self._latest[event.unit_id] = event
            points = self._history.pop(event.unit_id, deque(maxlen=self._max_points))
            points.append(event)
            cutoff = event.event_time - timedelta(minutes=20)
            while points and points[0].event_time < cutoff:
                points.popleft()
            self._history[event.unit_id] = points
            if len(self._latest) > self._max_units:
                evicted, _ = self._latest.popitem(last=False)
                self._history.pop(evicted, None)
            for queue in self._subscribers:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(event)

    async def handle_event(self, event: TelemetryEvent) -> None:
        """Callback для NDTP-сервера."""
        self.record(event)

    def get_latest(self, unit_id: int) -> TelemetryEvent | None:
        with self._lock:
            return self._latest.get(unit_id)

    def get_recent(self, unit_id: int) -> list[TelemetryEvent]:
        """Snapshot at most 150 packets for one device."""
        with self._lock:
            return list(self._history.get(unit_id, ()))

    def list_latest(self) -> list[TelemetryEvent]:
        with self._lock:
            return list(self._latest.values())

    def count(self) -> int:
        with self._lock:
            return len(self._latest)

    def subscribe(self) -> asyncio.Queue[TelemetryEvent]:
        """Subscribe to bounded live updates without blocking the NDTP receiver."""
        queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[TelemetryEvent]) -> None:
        with self._lock:
            self._subscribers.discard(queue)
