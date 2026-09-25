from datetime import datetime, timezone
from typing import Self

from pydantic import BaseModel, Field


class NavData(BaseModel):
    """Навигационные данные telemetry-события."""

    timestamp: int = Field(..., description="Unix time устройства, секунды")
    latitude: float
    longitude: float
    coordinates_valid: bool = True
    speed_avg: float | None = Field(None, description="Средняя скорость, км/ч")
    speed_max: float | None = Field(None, description="Максимальная скорость, км/ч")
    course: int | None = Field(None, description="Курс, 0..360 градусов")
    track_m: int | None = Field(None, description="Пройденный путь, м")
    altitude_m: int | None = None
    satellites: int | None = None
    battery_voltage_mv: int | None = Field(
        None,
        description="Напряжение батареи, мВ (1 единица NDTP = 20 мВ)",
    )
    alert_flag: bool = False
    sos_flag: bool = False


class CanData(BaseModel):
    """Данные CAN-шины."""

    speed_kmh: float | None = Field(None, description="Скорость ТС, км/ч")
    engine_rpm: int | None = None
    engine_temp_c: int | None = None
    odometer_km: int | None = Field(None, description="Полный пробег, км")
    engine_hours: float | None = Field(None, description="Моточасы, ч")
    alarm_flags: int = 0


class TelemetryEvent(BaseModel):
    """Нормализованная телеметрия одного устройства.

    Единый внутренний формат: остальное приложение работает только с этой
    моделью и не знает ничего о протоколе NDTP.
    """

    unit_id: int = Field(..., description="ID терминала (peerAddress NDTP)")
    received_at: datetime
    nav: NavData | None = None
    can: CanData | None = None

    @property
    def event_time(self) -> datetime:
        """Время события: телеметрия устройства, иначе момент приёма."""
        if self.nav is not None:
            return datetime.fromtimestamp(self.nav.timestamp, tz=timezone.utc)
        return self.received_at

    @classmethod
    def now(cls, unit_id: int) -> Self:
        return cls(unit_id=unit_id, received_at=datetime.now(timezone.utc))
