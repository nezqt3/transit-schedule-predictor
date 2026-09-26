import { LocateFixed, ZoomIn, ZoomOut } from 'lucide-react'
import L, { type LatLngTuple, type Map as LeafletMap } from 'leaflet'
import { useCallback, useEffect, useRef } from 'react'
import 'leaflet/dist/leaflet.css'

import { hasValidPosition, speedKmh } from '@/lib/telemetry/readEvent'
import { statusLabel, vehicleStatus } from '@/lib/telemetry/vehicleStatus'
import type { TelemetryEvent } from '@/types/api'
import { markerIcon } from './markerIcon'

type VehicleMapProps = {
  events: readonly TelemetryEvent[]
  selectedUnitId: number | null
  onSelect: (unitId: number) => void
}

const DEFAULT_CENTER: LatLngTuple = [55.7512, 37.6184]
function coordinates(event: TelemetryEvent): LatLngTuple | null {
  if (!hasValidPosition(event) || !event.nav) return null
  const { latitude, longitude } = event.nav
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null
  return [latitude, longitude]
}

export function VehicleMap({ events, selectedUnitId, onSelect }: VehicleMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)
  const fittedCountRef = useRef(0)
  const userMovedRef = useRef(false)
  const centeredUnitRef = useRef<number | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const map = L.map(container, { zoomControl: false, minZoom: 3 }).setView(DEFAULT_CENTER, 11)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map)
    const layer = L.layerGroup().addTo(map)
    map.on('dragstart', () => { userMovedRef.current = true })
    mapRef.current = map
    layerRef.current = layer
    const resize = new ResizeObserver(() => map.invalidateSize())
    resize.observe(container)
    return () => {
      resize.disconnect()
      mapRef.current = null
      layerRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return
    layer.clearLayers()
    const now = Date.now()
    const points: LatLngTuple[] = []
    for (const event of events) {
      const point = coordinates(event)
      if (!point) continue
      points.push(point)
      const status = vehicleStatus(event, now)
      const marker = L.marker(point, {
        icon: markerIcon(status, event.unit_id === selectedUnitId, event.nav?.course ?? null),
        alt: `Терминал ${event.unit_id}: ${statusLabel[status]}`,
        keyboard: true,
        zIndexOffset: event.unit_id === selectedUnitId ? 1000 : 0,
      })
      const speed = speedKmh(event)
      marker.bindTooltip(
        `<strong>#${event.unit_id}</strong><span>${statusLabel[status]}${speed === null ? '' : ` · ${speed.toFixed(0)} км/ч`}</span>`,
        { className: 'vehicle-tooltip', direction: 'right', offset: [15, 0], permanent: true },
      )
      marker.on('click', () => onSelect(event.unit_id))
      marker.addTo(layer)
      marker.getElement()?.setAttribute('aria-label', `Терминал ${event.unit_id}: ${statusLabel[status]}`)
    }
    if (!userMovedRef.current && points.length > fittedCountRef.current) {
      fittedCountRef.current = points.length
      if (points.length === 1) map.setView(points[0]!, 13)
      else map.fitBounds(L.latLngBounds(points), { padding: [60, 60], maxZoom: 13 })
    }
  }, [events, selectedUnitId, onSelect])

  useEffect(() => {
    if (selectedUnitId === centeredUnitRef.current) return
    const selected = events.find((event) => event.unit_id === selectedUnitId)
    const point = selected && coordinates(selected)
    if (point && mapRef.current) {
      centeredUnitRef.current = selectedUnitId
      mapRef.current.panTo(point, { animate: true })
    }
  }, [events, selectedUnitId])

  const fitAll = useCallback(() => {
    const points = events.map(coordinates).filter((point): point is LatLngTuple => point !== null)
    const map = mapRef.current
    if (!map || points.length === 0) return
    fittedCountRef.current = points.length
    if (points.length === 1) map.setView(points[0]!, 13)
    else map.fitBounds(L.latLngBounds(points), { padding: [60, 60], maxZoom: 13 })
  }, [events])

  return (
    <div className="fleet-map">
      <div aria-label="Карта терминалов" className="fleet-map__canvas" ref={containerRef} role="application" />
      <div aria-label="Управление картой" className="fleet-map__controls">
        <button aria-label="Приблизить" onClick={() => { userMovedRef.current = true; mapRef.current?.zoomIn() }} title="Приблизить" type="button"><ZoomIn size={20} /></button>
        <button aria-label="Отдалить" onClick={() => { userMovedRef.current = true; mapRef.current?.zoomOut() }} title="Отдалить" type="button"><ZoomOut size={20} /></button>
        <button aria-label="Показать все терминалы" onClick={() => { userMovedRef.current = false; fitAll() }} title="Показать все терминалы" type="button"><LocateFixed size={19} /></button>
      </div>
    </div>
  )
}
