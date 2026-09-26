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

export function markerElement(status: VehicleStatus, selected: boolean, heading: number | null, late = false) {
  const Icon = mapStatusIcons[status]
  const rotation = status === 'moving' && heading !== null ? `transform:rotate(${heading}deg)` : ''
  const element = document.createElement('button')
  element.className = 'vehicle-marker-wrap'
  element.type = 'button'
  element.innerHTML = `<span class="vehicle-marker vehicle-marker--${status}${selected ? ' vehicle-marker--selected' : ''}${late ? ' vehicle-marker--late' : ''}"><span class="vehicle-marker__glyph" style="${rotation}">${renderToStaticMarkup(<Icon size={20} strokeWidth={2.8} />)}</span></span>`
  return element
}
