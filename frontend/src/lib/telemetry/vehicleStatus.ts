import type { TelemetryEvent } from '@/types/api'

import { hasValidPosition, isStale, speedKmh } from './readEvent'

export type VehicleStatus = 'alarm' | 'no-position' | 'stale' | 'moving' | 'stopped' | 'unknown'

export function hasAlarm(event: TelemetryEvent): boolean {
  return Boolean(event.nav?.sos_flag || event.nav?.alert_flag || event.can?.alarm_flags)
}

export function vehicleStatus(event: TelemetryEvent, now = Date.now()): VehicleStatus {
  if (hasAlarm(event)) return 'alarm'
  if (!hasValidPosition(event)) return 'no-position'
  if (isStale(event, now)) return 'stale'
  const speed = speedKmh(event)
  if (speed === null) return 'unknown'
  return speed > 2 ? 'moving' : 'stopped'
}

export function needsAttention(event: TelemetryEvent, now = Date.now()): boolean {
  const status = vehicleStatus(event, now)
  return status === 'alarm' || status === 'stale' || status === 'no-position'
}

export const statusLabel: Record<VehicleStatus, string> = {
  alarm: 'Тревога',
  'no-position': 'Нет координат',
  stale: 'Устарели координаты',
  moving: 'Движется',
  stopped: 'Стоит',
  unknown: 'Скорость неизвестна',
}
