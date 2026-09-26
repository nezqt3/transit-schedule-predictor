import { cn } from '@/lib/cn'
import { formatClock } from '@/lib/format/time'
import { eventTimeMs, speedKmh } from '@/lib/telemetry/readEvent'
import { statusLabel, vehicleStatus } from '@/lib/telemetry/vehicleStatus'
import { useTelemetryStore } from '@/store/telemetry'
import type { StoredPrediction, TelemetryEvent } from '@/types/api'

type VehiclesTableProps = {
  events: readonly TelemetryEvent[]
  predictions: readonly StoredPrediction[]
}

export function VehiclesTable({ events, predictions }: VehiclesTableProps) {
  const selectedUnitId = useTelemetryStore((state) => state.selectedUnitId)
  const selectUnit = useTelemetryStore((state) => state.selectUnit)
  const now = Date.now()

  const rows = [...events].sort((a, b) => eventTimeMs(b) - eventTimeMs(a))

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Транспорт</th>
          <th>Состояние</th>
          <th>Скорость</th>
          <th>Прогноз 10–15 мин</th>
          <th>Последнее обновление</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((event) => {
          const speed = speedKmh(event)
          const prediction = predictions.find((item) => item.unit_id === event.unit_id)
          const status = vehicleStatus(event, now)

          return (
            <tr
              className={cn(selectedUnitId === event.unit_id && 'table__row--selected')}
              key={event.unit_id}
              onClick={() => selectUnit(event.unit_id)}
              onKeyDown={(keyEvent) => {
                if (keyEvent.key === 'Enter' || keyEvent.key === ' ') {
                  keyEvent.preventDefault()
                  selectUnit(event.unit_id)
                }
              }}
              tabIndex={0}
            >
              <td className="table__mono">Терминал #{event.unit_id}</td>
              <td>{statusLabel[status]}</td>
              <td>{speed === null ? '—' : `${speed.toFixed(0)} км/ч`}</td>
              <td>{prediction ? `${prediction.predicted_delay_s > 0 ? '+' : ''}${prediction.predicted_delay_s.toFixed(0)} с` : '—'}</td>
              <td>{formatClock(event.received_at)}</td>
            </tr>
          )
        })}
        {rows.length === 0 && (
          <tr>
            <td className="table__empty" colSpan={5}>
              Данные транспорта пока не поступали.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
