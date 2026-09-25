import { MapPin } from 'lucide-react'

import { cn } from '@/lib/cn'
import { formatAge, formatClock } from '@/lib/format/time'
import { eventTimeMs, hasValidPosition, isStale, speedKmh } from '@/lib/telemetry/readEvent'
import { useTelemetryStore } from '@/store/telemetry'
import type { TelemetryEvent } from '@/types/api'

type VehiclesTableProps = {
  events: readonly TelemetryEvent[]
  limit?: number
}

export function VehiclesTable({ events, limit }: VehiclesTableProps) {
  const selectedUnitId = useTelemetryStore((state) => state.selectedUnitId)
  const selectUnit = useTelemetryStore((state) => state.selectUnit)
  const now = Date.now()

  const rows = [...events].sort((a, b) => eventTimeMs(b) - eventTimeMs(a))
  const visible = limit ? rows.slice(0, limit) : rows

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Терминал</th>
          <th>Скорость</th>
          <th>Курс</th>
          <th>Координаты</th>
          <th>Пакет</th>
        </tr>
      </thead>
      <tbody>
        {visible.map((event) => {
          const speed = speedKmh(event)
          const stale = isStale(event, now)

          return (
            <tr
              className={cn(selectedUnitId === event.unit_id && 'table__row--selected')}
              key={event.unit_id}
              onClick={() => selectUnit(event.unit_id)}
            >
              <td className="table__mono">#{event.unit_id}</td>
              <td
                className={cn(
                  'table__mono',
                  speed !== null && speed < 5 && !stale && 'table__value--warn',
                )}
              >
                {speed === null ? '—' : `${speed.toFixed(1)} км/ч`}
              </td>
              <td className="table__mono">{event.nav?.course ?? '—'}</td>
              <td>
                {hasValidPosition(event) && event.nav ? (
                  <span className="table__coords">
                    <MapPin size={13} />
                    {event.nav.latitude.toFixed(5)}, {event.nav.longitude.toFixed(5)}
                  </span>
                ) : (
                  <span className="table__muted">нет валидных координат</span>
                )}
              </td>
              <td>
                <span className={cn('cell-badge', stale && 'cell-badge--stale')}>
                  {formatClock(eventTimeMs(event))} · {formatAge(eventTimeMs(event))}
                </span>
              </td>
            </tr>
          )
        })}
        {visible.length === 0 && (
          <tr>
            <td className="table__empty" colSpan={5}>
              Телеметрия не поступала: запустите эмулятор NDTP и подключите его к :9201
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
