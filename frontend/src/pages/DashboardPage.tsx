import { Activity, Bus, Gauge, Timer } from 'lucide-react'

import { VehicleFocus } from '@/features/vehicles/VehicleFocus'
import { VehiclesTable } from '@/features/vehicles/VehiclesTable'
import { useVehicleFeed } from '@/features/vehicles/hooks'
import { formatClock } from '@/lib/format/time'
import { isStale, speedKmh } from '@/lib/telemetry/readEvent'
import { useTelemetryStore } from '@/store/telemetry'

export function DashboardPage() {
  const { data: events = [], isPending, isError, error, dataUpdatedAt } = useVehicleFeed()
  const selectedUnitId = useTelemetryStore((state) => state.selectedUnitId)

  const selectedEvent =
    events.find((event) => event.unit_id === selectedUnitId) ?? events[0]

  const active = events.filter((event) => !isStale(event)).length
  const speeds = events.map(speedKmh).filter((speed): speed is number => speed !== null)
  const avgSpeed = speeds.length > 0 ? speeds.reduce((a, b) => a + b, 0) / speeds.length : null

  return (
    <div className="page">
      <section className="kpis">
        <div className="kpi">
          <Bus size={15} />
          <span className="kpi__label">терминалов видит backend</span>
          <span className="kpi__value">{events.length}</span>
        </div>
        <div className="kpi">
          <Activity size={15} />
          <span className="kpi__label">активных (&lt;30 с)</span>
          <span className="kpi__value">{active}</span>
        </div>
        <div className="kpi">
          <Gauge size={15} />
          <span className="kpi__label">средняя скорость</span>
          <span className="kpi__value">
            {avgSpeed === null ? '—' : `${avgSpeed.toFixed(1)} км/ч`}
          </span>
        </div>
        <div className="kpi">
          <Timer size={15} />
          <span className="kpi__label">последний опрос REST</span>
          <span className="kpi__value">
            {dataUpdatedAt ? formatClock(dataUpdatedAt) : '—'}
          </span>
        </div>
      </section>

      <div className="grid-2">
        <section className="panel">
          <header className="panel__head">
            <h2>Последняя телеметрия</h2>
            <span className="panel__meta">
              {isPending
                ? 'загрузка…'
                : isError
                  ? `ошибка: ${error?.message ?? 'нет ответа'}`
                  : `${events.length} строк`}
            </span>
          </header>
          <VehiclesTable events={events} limit={8} />
        </section>

        <section className="panel">
          <header className="panel__head">
            <h2>Разбор пакета</h2>
          </header>
          <VehicleFocus event={selectedEvent} />
        </section>
      </div>
    </div>
  )
}
