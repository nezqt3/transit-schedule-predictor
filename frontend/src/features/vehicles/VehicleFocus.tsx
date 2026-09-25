import { CircuitBoard, Gauge, Radio, Timer } from 'lucide-react'
import type { ReactNode } from 'react'

import { SpeedTrend } from './SpeedTrend'

import { formatAge, formatClock } from '@/lib/format/time'
import { eventTimeMs, speedKmh } from '@/lib/telemetry/readEvent'
import { useTelemetryStore } from '@/store/telemetry'
import type { TelemetryEvent } from '@/types/api'

type VehicleFocusProps = {
  event: TelemetryEvent | undefined
}

function Field({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="field">
      <span className="field__label">
        {icon}
        {label}
      </span>
      <span className="field__value">{value}</span>
    </div>
  )
}

export function VehicleFocus({ event }: VehicleFocusProps) {
  const points = useTelemetryStore((state) =>
    event ? state.speedHistory[event.unit_id] : undefined,
  )

  if (!event) {
    return (
      <p className="panel__hint">
        Выберите терминал в таблице, чтобы разобрать пакет телеметрии.
      </p>
    )
  }

  const speed = speedKmh(event)

  return (
    <div className="focus">
      <div className="focus__head">
        <div>
          <p className="focus__title">Терминал #{event.unit_id}</p>
          <p className="focus__subtitle">
            пакет в {formatClock(eventTimeMs(event))} · {formatAge(eventTimeMs(event))} назад
          </p>
        </div>
        {(event.nav?.sos_flag || event.nav?.alert_flag) && (
          <span className="cell-badge cell-badge--stale">тревога в пакете</span>
        )}
      </div>

      <div className="focus__grid">
        <Field
          icon={<Gauge size={13} />}
          label="скорость"
          value={speed === null ? '—' : `${speed.toFixed(1)} км/ч`}
        />
        <Field
          icon={<Radio size={13} />}
          label="спутники"
          value={event.nav?.satellites?.toString() ?? '—'}
        />
        <Field
          icon={<CircuitBoard size={13} />}
          label="обороты"
          value={event.can?.engine_rpm?.toString() ?? '—'}
        />
        <Field
          icon={<Timer size={13} />}
          label="батарея"
          value={
            event.nav?.battery_voltage_mv
              ? `${(event.nav.battery_voltage_mv / 1000).toFixed(2)} В`
              : '—'
          }
        />
      </div>

      <SpeedTrend points={points ?? []} />
    </div>
  )
}
