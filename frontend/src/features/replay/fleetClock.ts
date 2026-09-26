import type { ReplayFleetVehicle, ReplayPoint, ReplayRun, ReplayTelemetry } from '@/types/replay'

// Competition timestamps are Moscow local time without a timezone suffix.
export function janMs(value: string): number {
  return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}+03:00`)
}

export function janClock(value: string | number): string {
  return new Date(typeof value === 'string' ? janMs(value) : value).toLocaleTimeString('ru-RU', {
    timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
  })
}

export function latestTelemetry(vehicle: ReplayFleetVehicle, timeMs: number): ReplayTelemetry | null {
  const rows = vehicle.telemetry
  let left = 0
  let right = rows.length
  while (left < right) {
    const middle = (left + right) >>> 1
    if (janMs(rows[middle]!.available_at) <= timeMs) left = middle + 1
    else right = middle
  }
  const row = rows[left - 1]
  return row && timeMs - janMs(row.available_at) <= 5 * 60_000 ? row : null
}

export function currentRun(vehicle: ReplayFleetVehicle, timeMs: number): ReplayRun | null {
  return vehicle.runs.find((run) => run.valid &&
    janMs(run.start_at) - 5 * 60_000 <= timeMs &&
    timeMs <= janMs(run.end_at) + 5 * 60_000) ?? null
}

export function currentPoint(vehicle: ReplayFleetVehicle, timeMs: number): ReplayPoint | null {
  return vehicle.points.findLast((point) => janMs(point.T) <= timeMs &&
    timeMs - janMs(point.T) <= 20 * 60_000) ?? null
}
