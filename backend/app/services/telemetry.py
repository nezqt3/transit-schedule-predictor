"""Хранение текущего состояния ТС по телеметрии.

Временное in-memory состояние для демки; при подключении БД сюда же
добавится запись history. API и ML-пайплайн читают события только через
нормализованный TelemetryEvent.
"""

import asyncio
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
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
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self.accepted_packets = 0
        self.ignored_packets = 0
        self.ws_dropped_events = 0
        self.subscriber_queue_peak = 0

    def record(self, event: TelemetryEvent) -> bool:
        """Сохранить последнее событие устройства."""
        with self._lock:
            previous = self._latest.get(event.unit_id)
            if previous is not None and previous.nav is not None and event.nav is None:
                merged = previous.model_copy(update={
                    "can": event.can, "received_at": event.received_at,
                })
                self._latest[event.unit_id] = merged
                self.publish("vehicle_update", merged.model_dump(mode="json"))
                return False
            if previous is not None and event.event_time <= previous.event_time:
                self.ignored_packets += 1
                return False
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
            self.accepted_packets += 1
        self.publish("vehicle_update", event.model_dump(mode="json"))
        return True

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

    def publish(self, event_type: str, data: dict) -> None:
        """Fan out one bounded real-time event without blocking NDTP."""
        message = {
            "type": event_type,
            "event_id": str(uuid.uuid4()),
            "emitted_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        with self._lock:
            for queue in self._subscribers:
                if queue.full():
                    queue.get_nowait()
                    self.ws_dropped_events += 1
                queue.put_nowait(message)
                self.subscriber_queue_peak = max(self.subscriber_queue_peak, queue.qsize())

    def subscribe(self) -> asyncio.Queue[dict]:
        """Subscribe to bounded live updates without blocking the NDTP receiver."""
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        with self._lock:
            self._subscribers.discard(queue)
