import type { VehicleStatus } from '@/lib/telemetry/vehicleStatus'
import type { ReplayFleet, ReplayFleetVehicle, ReplayPoint, ReplayPrediction, ReplayRun, ReplayTelemetry } from '@/types/replay'

// Competition timestamps are Moscow local time without a timezone suffix.
export function janMs(value: string): number {
  return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}+03:00`)
}

export function janClock(value: string | number): string {
  return new Date(typeof value === 'string' ? janMs(value) : value).toLocaleTimeString('ru-RU', {
    timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
  })
}

export function stopLabel(vehicle: ReplayFleetVehicle, stopId: number): string {
  const stop = vehicle.stops.find((item) => item.stop_id === stopId)
  if (stop?.address) return stop.address
  const run = vehicle.runs.find((item) => item.stop_ids.includes(stopId))
  const position = run?.stop_ids.indexOf(stopId) ?? -1
  return position >= 0 ? `Остановка ${position + 1}` : 'Остановка'
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
  return row ?? null
}

/** Hide implausible raw speed spikes in the dispatcher view without changing ML inputs. */
export function displaySpeedKmh(speed: number | null): number | null {
  return speed !== null && Number.isFinite(speed) && speed >= 0 && speed <= 120 ? speed : null
}

export function currentRun(vehicle: ReplayFleetVehicle, timeMs: number): ReplayRun | null {
  // A recovered route is known from the published plan at departure. Waiting for
  // five passed stops hides the entire beginning of an otherwise verified run.
  return vehicle.runs.find((run) => run.valid &&
    janMs(run.start_at) - 5 * 60_000 <= timeMs &&
    timeMs <= janMs(run.end_at) + 5 * 60_000) ?? null
}

export function currentPoint(vehicle: ReplayFleetVehicle, timeMs: number): ReplayPoint | null {
  return vehicle.points.findLast((point) => janMs(point.T) <= timeMs &&
    timeMs - janMs(point.T) <= 20 * 60_000) ?? null
}

export type ReplayFleetItem = {
  vehicle: ReplayFleetVehicle
  gps: ReplayTelemetry | null
  status: VehicleStatus
  run: ReplayRun | null
  point: ReplayPoint | null
  forecast: ReplayPrediction | undefined
  late: boolean
}

// Fleet positions are sampled into 45-second buckets for playback.
const REPLAY_STALE_AFTER_MS = 2 * 60_000
const REPLAY_ON_LINE_AFTER_MS = 15 * 60_000

/** Dispatcher snapshot: only positions and forecasts available by the replay clock. */
export function fleetSnapshot(fleet: ReplayFleet | undefined, timeMs: number | null,
  predictions: Record<string, ReplayPrediction>): ReplayFleetItem[] {
  if (!fleet || timeMs === null) return []
  const items: ReplayFleetItem[] = []
  for (const vehicle of fleet.vehicles) {
    const gps = latestTelemetry(vehicle, timeMs)
    if (!gps || timeMs - janMs(gps.available_at) > REPLAY_ON_LINE_AFTER_MS) continue
    const status: VehicleStatus = timeMs - janMs(gps.available_at) > REPLAY_STALE_AFTER_MS ? 'stale'
      : gps.speed === null ? 'unknown' : gps.speed > 2 ? 'moving' : 'stopped'
    const run = currentRun(vehicle, timeMs)
    const point = currentPoint(vehicle, timeMs)
    const forecast = point ? predictions[point.sample_id] : undefined
    items.push({ vehicle, gps, status, run, point, forecast,
      late: Boolean(forecast && forecast.predicted_delay_s >= 120) })
  }
  return items.sort((a, b) => Number(b.late) - Number(a.late) || a.vehicle.tr_id - b.vehicle.tr_id)
}
