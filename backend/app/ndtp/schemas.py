from datetime import datetime, timezone
from typing import Literal, Self

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
    pdop: int | None = Field(None, description="Показатель геометрии спутников, как передан NDTP")
    battery_voltage_mv: int | None = Field(
        None,
        description="Напряжение батареи, мВ (1 единица NDTP = 20 мВ)",
    )
    alert_flag: bool = False
    sos_flag: bool = False
    internal_battery_power: bool = Field(False, description="Терминал питается от внутреннего АКБ")


class CanData(BaseModel):
    """Данные CAN-шины."""

    speed_kmh: float | None = Field(None, description="Скорость ТС, км/ч")
    engine_rpm: int | None = None
    engine_temp_c: int | None = None
    odometer_km: float | None = Field(None, description="Полный пробег, км")
    engine_hours: float | None = Field(None, description="Моточасы, ч")
    alarm_flags: int = 0
    module_available: bool = True
    fuel_level_value: int | None = None
    fuel_level_unit: Literal["liters", "percent"] | None = Field(
        None, description="Литры или проценты согласно биту CAN"
    )


class InternalSensorData(BaseModel):
    """Связь терминала по внутренней ячейке NDTP 02."""

    gsm_csq: int = Field(..., description="Исходный показатель CSQ терминала")
    gprs_state: int = Field(..., description="Исходный код состояния GPRS")


class FuelSensorData(BaseModel):
    """Показания одного топливного датчика Usi08."""

    sensor_number: int
    status: int
    level_l: int
    level_mm: int
    temperature: int


class TemperatureSensorData(BaseModel):
    """Показания одного термодатчика Termo16."""

    sensor_number: int
    status: int
    temperature_c: int


class PassengerSensorData(BaseModel):
    """Счётчики проходов Crown03/Irma04 без оценки заполненности салона."""

    sensor_type: Literal["crown", "irma"]
    sensor_number: int
    zone: int
    boardings: tuple[int, int, int, int]
    alightings: tuple[int, int, int, int]
    doors_present: tuple[bool, bool, bool, bool] | None = None
    doors_closed: tuple[bool, bool, bool, bool] | None = None


class TelemetryEvent(BaseModel):
    """Нормализованная телеметрия одного устройства.

    Единый внутренний формат: остальное приложение работает только с этой
    моделью и не знает ничего о протоколе NDTP.
    """

    unit_id: int = Field(..., description="ID терминала (peerAddress NDTP)")
    received_at: datetime
    nav: NavData | None = None
    can: CanData | None = None
    internal_sensor: InternalSensorData | None = None
    fuel_sensors: list[FuelSensorData] = Field(default_factory=list)
    temperature_sensors: list[TemperatureSensorData] = Field(default_factory=list)
    passenger_sensors: list[PassengerSensorData] = Field(default_factory=list)

    @property
    def event_time(self) -> datetime:
        """Время события: телеметрия устройства, иначе момент приёма."""
        if self.nav is not None:
            return datetime.fromtimestamp(self.nav.timestamp, tz=timezone.utc)
        return self.received_at

    @classmethod
    def now(cls, unit_id: int) -> Self:
        return cls(unit_id=unit_id, received_at=datetime.now(timezone.utc))
