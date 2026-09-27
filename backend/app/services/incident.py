"""Small in-memory incident lifecycle for the dispatcher demo."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.schemas.incident import Incident
from app.schemas.prediction import StoredPrediction

logger = logging.getLogger(__name__)


class IncidentStore:
    def __init__(self, medium_delay_s: float = 60, high_delay_s: float = 120,
                 medium_probability: float = 0.25,
                 high_probability: float = 0.60, *,
                 initial: Iterable[Incident] = (),
                 persist: Callable[[Incident], Awaitable[None]] | None = None) -> None:
        self._items: dict[str, Incident] = {}
        self._active: dict[tuple[int, int], str] = {}
        self._lock = RLock()
        self.medium_delay_s = medium_delay_s
        self.high_delay_s = high_delay_s
        self.medium_probability = medium_probability
        self.high_probability = high_probability
        self._persist = persist
        self._persistence_tasks: set[asyncio.Task] = set()
        for item in initial:
            self._items[item.incident_id] = item
            if item.status == "active":
                self._active[(item.tr_id, item.target_stop_id)] = item.incident_id

    def _schedule_persistence(self, item: Incident) -> None:
        if self._persist is None:
            return
        try:
            task = asyncio.get_running_loop().create_task(self._persist(item))
        except RuntimeError:
            return
        self._persistence_tasks.add(task)
        task.add_done_callback(self._persistence_done)

    def _persistence_done(self, task: asyncio.Task) -> None:
        self._persistence_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("incident persistence failed: %s", task.exception())

    async def flush(self) -> None:
        if self._persistence_tasks:
            await asyncio.gather(*tuple(self._persistence_tasks), return_exceptions=True)

    def risk(self, predicted_delay_s: float, p_late: float | None = None) -> str:
        if p_late is not None:
            if p_late >= self.high_probability:
                return "high"
            if p_late >= self.medium_probability:
                return "medium"
            return "low"
        if predicted_delay_s >= self.high_delay_s:
            return "high"
        if predicted_delay_s >= self.medium_delay_s:
            return "medium"
        return "low"

    def evaluate(self, prediction: StoredPrediction, *, speed_kmh: float | None,
                 previous_stop_id: int | None) -> Incident | None:
        """Create, update or resolve an incident for one target stop."""
        key = (prediction.tr_id, prediction.target_stop_id)
        now = datetime.now(timezone.utc)
        with self._lock:
            existing_id = self._active.get(key)
            existing = self._items.get(existing_id) if existing_id else None
            if prediction.risk == "low":
                if existing is None:
                    return None
                resolved = existing.model_copy(update={"status": "resolved", "updated_at": now})
                self._items[existing.incident_id] = resolved
                self._active.pop(key, None)
                self._schedule_persistence(resolved)
                return resolved

            if speed_kmh is not None and speed_kmh < 3:
                cause = "Возможная стоянка на участке"
                evidence = f"Последняя скорость {speed_kmh:.0f} км/ч"
                recommendation = (
                    "Связаться с водителем, уточнить причину стоянки и оценить влияние на следующие остановки."
                    if prediction.risk == "high" else
                    "Проверить причину стоянки и повторить оценку при следующем обновлении."
                )
            elif prediction.current_delay_s >= self.high_delay_s:
                cause = "Отклонение уже присутствует в доступных данных"
                evidence = (f"Текущее отклонение {prediction.current_delay_s:.0f} с; "
                            f"источник {prediction.current_delay_source}")
                recommendation = (
                    "Проверить выполнение рейса и предупредить ответственного за следующие остановки."
                    if prediction.risk == "high" else
                    "Сверить движение с планом на следующей остановке."
                )
            else:
                cause = "Прогноз роста отклонения на участке"
                evidence = (f"Прогноз {prediction.predicted_delay_s:.0f} с; "
                            f"текущее отклонение {prediction.current_delay_s:.0f} с")
                recommendation = (
                    "Проверить движение ТС и оценить корректировку интервала на следующих остановках."
                    if prediction.risk == "high" else
                    "Наблюдать следующий пакет и сверить прогноз с планом."
                )
            item = Incident(
                incident_id=existing.incident_id if existing else str(uuid4()),
                tr_id=prediction.tr_id, unit_id=prediction.unit_id,
                target_stop_id=prediction.target_stop_id, target_time=prediction.target_time,
                previous_stop_id=previous_stop_id,
                segment=(f"Остановка {previous_stop_id} → {prediction.target_stop_id}"
                         if previous_stop_id else f"До остановки {prediction.target_stop_id}"),
                predicted_delay_s=prediction.predicted_delay_s,
                p_late=prediction.p_late, risk=prediction.risk,
                risk_source=prediction.risk_source,
                cause=cause, evidence=evidence, recommendation=recommendation,
                status="active", created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._items[item.incident_id] = item
            self._active[key] = item.incident_id
            self._schedule_persistence(item)
            return item

    def list_all(self) -> list[Incident]:
        with self._lock:
            return sorted(self._items.values(), key=lambda item: item.updated_at, reverse=True)

    def resolve_vehicle(self, tr_id: int, except_stop_id: int | None = None) -> list[Incident]:
        now = datetime.now(timezone.utc)
        resolved = []
        with self._lock:
            for key, incident_id in list(self._active.items()):
                if key[0] != tr_id or key[1] == except_stop_id:
                    continue
                item = self._items[incident_id].model_copy(update={
                    "status": "resolved", "updated_at": now,
                })
                self._items[incident_id] = item
                self._active.pop(key)
                resolved.append(item)
        for item in resolved:
            self._schedule_persistence(item)
        return resolved

    def get(self, incident_id: str) -> Incident | None:
        with self._lock:
            return self._items.get(incident_id)
