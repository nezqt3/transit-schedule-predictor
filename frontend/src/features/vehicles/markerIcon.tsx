import { AlertTriangle, CircleHelp, Clock3, MapPinOff, Navigation2, OctagonAlert, Square } from 'lucide-react'
import { renderToStaticMarkup } from 'react-dom/server'

import type { VehicleStatus } from '@/lib/telemetry/vehicleStatus'

export const fleetStatusIcons = {
  alarm: AlertTriangle,
  'no-position': MapPinOff,
  stale: Clock3,
  moving: Navigation2,
  stopped: Square,
  unknown: Clock3,
} as const

const mapStatusIcons = {
  alarm: OctagonAlert,
  'no-position': CircleHelp,
  stale: Clock3,
  moving: Navigation2,
  stopped: Square,
  unknown: CircleHelp,
} as const

type MarkerDetails = {
  delaySeconds?: number | null
  speedKmh?: number | null
  risk?: 'low' | 'medium' | 'high' | null
}

function delayLabel(seconds: number): string {
  const rounded = Math.round(seconds)
  const minutes = Math.floor(rounded / 60)
  const remainingSeconds = rounded % 60
  return minutes ? `+${minutes} мин${remainingSeconds ? ` ${remainingSeconds} с` : ''}` : `+${remainingSeconds} с`
}

export function markerElement(status: VehicleStatus, selected: boolean, heading: number | null,
  { delaySeconds, speedKmh, risk }: MarkerDetails = {}) {
  const Icon = mapStatusIcons[status]
  const rotation = status === 'moving' && heading !== null ? `transform:rotate(${heading}deg)` : ''
  const late = risk === 'high' || (risk === undefined && delaySeconds !== null && delaySeconds !== undefined && Number.isFinite(delaySeconds) && delaySeconds >= 120)
  const showSpeed = status === 'moving' && speedKmh !== null && speedKmh !== undefined && Number.isFinite(speedKmh) && speedKmh >= 0 && speedKmh <= 120
  const element = document.createElement('button')
  element.className = `vehicle-marker-wrap${selected ? ' vehicle-marker-wrap--selected' : ''}${late ? ' vehicle-marker-wrap--late' : ''}${late || showSpeed ? ' vehicle-marker-wrap--with-badge' : ''}`
  element.type = 'button'
  element.innerHTML = `<span class="vehicle-marker vehicle-marker--${status}${selected ? ' vehicle-marker--selected' : ''}${late ? ' vehicle-marker--late' : ''}${risk ? ` vehicle-marker--risk-${risk}` : ''}"><span class="vehicle-marker__glyph" style="${rotation}">${renderToStaticMarkup(<Icon size={20} strokeWidth={2.8} />)}</span></span>`
  if (late || showSpeed) {
    const badge = document.createElement('span')
    badge.className = `vehicle-marker__badge${late ? ' vehicle-marker__badge--late' : ''}`
    if (late && delaySeconds !== null && delaySeconds !== undefined) {
      const delay = document.createElement('strong')
      delay.className = 'vehicle-marker__delay'
      delay.textContent = delayLabel(delaySeconds)
      badge.append(delay)
    }
    if (showSpeed && speedKmh !== null && speedKmh !== undefined) {
      const speed = document.createElement('span')
      speed.className = 'vehicle-marker__speed'
      speed.textContent = `${Math.round(speedKmh)} км/ч`
      badge.append(speed)
    }
    element.append(badge)
  }
  return element
}
