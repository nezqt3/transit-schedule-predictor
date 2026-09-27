import { formatDateTime } from '@/lib/format/time'
import { hasValidPosition } from '@/lib/telemetry/readEvent'
import { telemetryAlerts } from '@/lib/telemetry/vehicleStatus'
import type { TelemetryEvent } from '@/types/api'

function Fact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>
}

export function NdtpTelemetryHighlights({ event, speed }: { event: TelemetryEvent; speed: number | null }) {
  const alert = telemetryAlerts(event)[0]
  const irma = event.passenger_sensors?.find((sensor) => sensor.sensor_type === 'irma')
  const openDoors = irma?.doors_present?.filter((present, index) =>
    present && !irma.doors_closed?.[index]).length

  return <div className="ndtp-highlights" aria-label="Состояние трамвая по NDTP">
    <div><span>Скорость</span><strong>{speed == null ? '—' : `${speed.toFixed(0)} км/ч`}</strong></div>
    <div><span>GPS</span><strong>{hasValidPosition(event) ? `${event.nav?.satellites ?? '—'} спутн.` : 'Нет точки'}</strong></div>
    <div><span>Двери</span><strong>{openDoors == null ? '—' : openDoors ? `${openDoors} открыто` : 'Закрыты'}</strong></div>
    <div><span>Сигналы</span><strong className={alert ? 'ndtp-highlights__alert' : ''}>{alert ?? 'Нет тревог'}</strong></div>
  </div>
}

export function NdtpTelemetryDetails({ event }: { event: TelemetryEvent }) {
  const nav = event.nav
  const can = event.can?.module_available === false ? null : event.can
  const alerts = telemetryAlerts(event)
  const deviceTime = nav ? nav.timestamp * 1000 : null
  const receivedTime = Date.parse(event.received_at)
  const clockGap = deviceTime === null ? null : Math.round((receivedTime - deviceTime) / 1000)
  const archived = clockGap !== null && Math.abs(clockGap) > 24 * 60 * 60

  return <div className="ndtp-details">
    <section className="ndtp-details__section" aria-label="Тревоги и свежесть данных">
      <h3>Тревоги и свежесть</h3>
      <div className="ndtp-details__alerts">
        {alerts.length ? alerts.map((alert) => <span className="ndtp-details__alert" key={alert}>{alert}</span>) : <span className="ndtp-details__ok">Активных сигналов тревоги нет</span>}
        {!hasValidPosition(event) && <span className="ndtp-details__alert">GPS недостоверен</span>}
      </div>
      <div className="vehicle-details__facts">
        <Fact label="Время устройства" value={deviceTime === null ? 'Нет метки GPS' : formatDateTime(deviceTime)} />
        <Fact label="Пакет принят" value={formatDateTime(event.received_at)} />
        {clockGap !== null && <Fact label="Расхождение часов" value={archived ? 'Архивная телеметрия' : `${clockGap > 0 ? '+' : ''}${clockGap} с`} />}
        {event.can?.module_available !== false && Boolean(event.can?.alarm_flags) && <Fact label="Флаги CAN" value={`0x${event.can!.alarm_flags.toString(16).toUpperCase()}`} />}
      </div>
    </section>

    <section className="ndtp-details__section" aria-label="Качество GPS">
      <h3>Качество GPS</h3>
      <div className="vehicle-details__facts">
        <Fact label="Координаты" value={hasValidPosition(event) ? 'Достоверны' : 'Недостоверны или отсутствуют'} />
        <Fact label="Спутники" value={nav?.satellites == null ? 'Нет данных' : String(nav.satellites)} />
        <Fact label="PDOP" value={nav?.pdop == null ? 'Нет данных' : String(nav.pdop)} />
      </div>
    </section>

    <section className="ndtp-details__section" aria-label="Топливо и двигатель">
      <h3>Топливо и двигатель</h3>
      <div className="vehicle-details__facts">
        {event.can?.module_available === false ? <Fact label="CAN" value="Модуль не обнаружен" /> : <>
          <Fact label="Обороты двигателя" value={can?.engine_rpm == null ? 'Нет данных' : `${can.engine_rpm} об/мин`} />
          <Fact label="Температура двигателя" value={can?.engine_temp_c == null ? 'Нет данных' : `${can.engine_temp_c} °C`} />
          <Fact label="Топливо CAN" value={can?.fuel_level_value == null ? 'Нет данных' : `${can.fuel_level_value} ${can.fuel_level_unit === 'percent' ? '%' : 'л'}`} />
        </>}
        {(event.fuel_sensors ?? []).map((sensor) => <Fact key={sensor.sensor_number} label={`ДУТ ${sensor.sensor_number + 1}`} value={`${sensor.level_l} л · ${sensor.level_mm} мм · статус ${sensor.status}`} />)}
        {(event.temperature_sensors ?? []).map((sensor) => <Fact key={`temp-${sensor.sensor_number}`} label={`Термодатчик ${sensor.sensor_number + 1}`} value={sensor.status === 0 ? `${sensor.temperature_c} °C` : `Нет связи · код ${sensor.status}`} />)}
      </div>
    </section>

    <section className="ndtp-details__section" aria-label="Связь терминала">
      <h3>Связь терминала</h3>
      <div className="vehicle-details__facts">
        <Fact label="GSM CSQ" value={event.internal_sensor ? String(event.internal_sensor.gsm_csq) : 'Нет данных'} />
        <Fact label="GPRS, код" value={event.internal_sensor ? String(event.internal_sensor.gprs_state) : 'Нет данных'} />
        <Fact label="Питание" value={nav ? nav.internal_battery_power ? 'Внутренний АКБ' : 'Внешнее' : 'Нет данных'} />
        <Fact label="Батарея терминала" value={nav?.battery_voltage_mv == null ? 'Нет данных' : `${(nav.battery_voltage_mv / 1000).toFixed(2)} В`} />
      </div>
    </section>

    <section className="ndtp-details__section" aria-label="Двери и пассажиропоток">
      <h3>Двери и пассажиропоток</h3>
      {(event.passenger_sensors ?? []).length === 0 ? <p className="ndtp-details__hint">Датчики Crown/IRMA не переданы.</p> : event.passenger_sensors.map((sensor) =>
        <div className="ndtp-passengers" key={`${sensor.sensor_type}-${sensor.sensor_number}`}>
          <strong>{sensor.sensor_type === 'irma' ? 'IRMA' : 'Корона'} · датчик {sensor.sensor_number + 1} · зона {sensor.zone}</strong>
          <table><thead><tr><th>Канал</th><th>Вход</th><th>Выход</th>{sensor.doors_present && <th>Дверь</th>}</tr></thead>
            <tbody>{sensor.boardings.map((count, index) => <tr key={index}><td>{index + 1}</td><td>{count}</td><td>{sensor.alightings[index]}</td>{sensor.doors_present && <td>{!sensor.doors_present[index] ? 'Не установлена' : sensor.doors_closed?.[index] ? 'Закрыта' : 'Открыта'}</td>}</tr>)}</tbody>
          </table>
        </div>)}
    </section>
  </div>
}
