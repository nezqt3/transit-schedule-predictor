import type { TelemetryEvent } from '@/types/api'

const STALE_AFTER_MS = 30_000

export function eventTimeMs(event: TelemetryEvent): number {
  return event.nav ? event.nav.timestamp * 1000 : Date.parse(event.received_at)
}

export function speedKmh(event: TelemetryEvent): number | null {
  return event.can?.speed_kmh ?? event.nav?.speed_avg ?? null
}

export function hasValidPosition(event: TelemetryEvent): boolean {
  return event.nav !== null && event.nav.coordinates_valid
}

export function isStale(event: TelemetryEvent, now: number = Date.now()): boolean {
  return now - eventTimeMs(event) > STALE_AFTER_MS
}
