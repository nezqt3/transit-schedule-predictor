"""Хранение текущего состояния ТС по телеметрии.

Временное in-memory состояние для демки; при подключении БД сюда же
добавится запись history. API и ML-пайплайн читают события только через
нормализованный TelemetryEvent.
"""

from collections import OrderedDict

from app.ndtp.schemas import TelemetryEvent


class TelemetryService:
    """In-memory реестр последних телеметрия-событий по каждому устройству."""

    def __init__(self, max_units: int = 500) -> None:
        self._latest: OrderedDict[int, TelemetryEvent] = OrderedDict()
        self._max_units = max_units

    def record(self, event: TelemetryEvent) -> None:
        """Сохранить последнее событие устройства."""
        self._latest.pop(event.unit_id, None)
        self._latest[event.unit_id] = event
        if len(self._latest) > self._max_units:
            self._latest.popitem(last=False)

    async def handle_event(self, event: TelemetryEvent) -> None:
        """Callback для NDTP-сервера."""
        self.record(event)

    def get_latest(self, unit_id: int) -> TelemetryEvent | None:
        return self._latest.get(unit_id)

    def list_latest(self) -> list[TelemetryEvent]:
        return list(self._latest.values())

    def count(self) -> int:
        return len(self._latest)
