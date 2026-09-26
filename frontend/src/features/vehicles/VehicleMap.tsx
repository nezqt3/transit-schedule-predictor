import { LocateFixed, ZoomIn, ZoomOut } from 'lucide-react'
import * as maplibregl from 'maplibre-gl'
import type { Map, Marker } from 'maplibre-gl'
import { useCallback, useEffect, useRef, useState } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'

import { addLine, bindMarkerZoom, fitMap, mapStyle, type MapPosition } from '@/lib/map/maplibre'
import { eventTimeMs, hasValidPosition, speedKmh } from '@/lib/telemetry/readEvent'
import { statusLabel, vehicleStatus } from '@/lib/telemetry/vehicleStatus'
import type { TelemetryEvent } from '@/types/api'
import { markerElement } from './markerIcon'

type VehicleMapProps = {
  events: readonly TelemetryEvent[]
  selectedHistory: readonly TelemetryEvent[]
  selectedUnitId: number | null
  onSelect: (unitId: number) => void
}

const DEFAULT_CENTER: MapPosition = [37.6184, 55.7512]

function coordinates(event: TelemetryEvent): MapPosition | null {
  if (!hasValidPosition(event) || !event.nav) return null
  const { latitude, longitude } = event.nav
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null
  return [longitude, latitude]
}

export function VehicleMap({ events, selectedHistory, selectedUnitId, onSelect }: VehicleMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const markersRef = useRef<Marker[]>([])
  const fittedCountRef = useRef(0)
  const userMovedRef = useRef(false)
  const centeredUnitRef = useRef<number | null>(null)
  const [mapLoaded, setMapLoaded] = useState(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const map = new maplibregl.Map({ container, style: mapStyle, center: DEFAULT_CENTER, zoom: 11, minZoom: 3 })
    const unbindMarkerZoom = bindMarkerZoom(map)
    map.on('load', () => setMapLoaded(true))
    map.on('dragstart', () => { userMovedRef.current = true })
    mapRef.current = map
    const resize = new ResizeObserver(() => map.resize())
    resize.observe(container)
    return () => {
      resize.disconnect()
      unbindMarkerZoom()
      markersRef.current = []
      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    const cleanups: Array<() => void> = []
    const trace = selectedHistory
      .filter((event) => event.unit_id === selectedUnitId)
      .map((event) => ({ point: coordinates(event), time: eventTimeMs(event) }))
      .filter((sample): sample is { point: MapPosition; time: number } => sample.point !== null)
      .sort((a, b) => a.time - b.time)
    let segment: MapPosition[] = []
    let previous: (typeof trace)[number] | null = null
    const drawSegment = () => {
      cleanups.push(addLine(map, segment, { color: '#1766ce', width: 4, opacity: 0.85 }))
    }
    for (const sample of trace) {
      if (previous && (sample.time - previous.time > 3 * 60_000 ||
        new maplibregl.LngLat(...previous.point).distanceTo(new maplibregl.LngLat(...sample.point)) > 5_000)) {
        drawSegment()
        segment = []
      }
      segment.push(sample.point)
      previous = sample
    }
    drawSegment()

    const points: MapPosition[] = []
    const now = Date.now()
    for (const event of events) {
      const point = coordinates(event)
      if (!point) continue
      points.push(point)
      const status = vehicleStatus(event, now)
      const speed = speedKmh(event)
      const element = markerElement(status, event.unit_id === selectedUnitId, event.nav?.course ?? null)
      element.setAttribute('aria-label', `Терминал ${event.unit_id}: ${statusLabel[status]}`)
      element.addEventListener('click', () => onSelect(event.unit_id))
      const tooltip = document.createElement('span')
      tooltip.className = 'vehicle-tooltip'
      tooltip.innerHTML = `<strong>#${event.unit_id}</strong><span>${statusLabel[status]}${speed === null ? '' : ` · ${speed.toFixed(0)} км/ч`}</span>`
      element.append(tooltip)
      markersRef.current.push(new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(point).addTo(map))
    }
    if (!userMovedRef.current && points.length > fittedCountRef.current) {
      fittedCountRef.current = points.length
      fitMap(map, points, 60, 13)
    }
    return () => {
      cleanups.forEach((cleanup) => cleanup())
      markersRef.current.forEach((marker) => marker.remove())
      markersRef.current = []
    }
  }, [events, selectedHistory, selectedUnitId, onSelect, mapLoaded])

  useEffect(() => {
    if (selectedUnitId === centeredUnitRef.current) return
    const selected = events.find((event) => event.unit_id === selectedUnitId)
    const point = selected && coordinates(selected)
    if (point && mapRef.current) {
      centeredUnitRef.current = selectedUnitId
      mapRef.current.easeTo({ center: point })
    }
  }, [events, selectedUnitId])

  const fitAll = useCallback(() => {
    const points = events.map(coordinates).filter((point): point is MapPosition => point !== null)
    const map = mapRef.current
    if (!map || points.length === 0) return
    fittedCountRef.current = points.length
    fitMap(map, points, 60, 13)
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
