import * as maplibregl from 'maplibre-gl'
import type { Map, Marker } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'

import { markerElement } from '@/features/vehicles/markerIcon'
import { bindMarkerZoom, createRouteOverlay, fitMap, mapStyle, textElement, type MapLine, type MapPosition } from '@/lib/map/maplibre'
import { statusLabel, type VehicleStatus } from '@/lib/telemetry/vehicleStatus'
import type { ReplayFleetVehicle, ReplayTelemetry } from '@/types/replay'
import { currentRun, janMs } from './fleetClock'

type RouteLineProperties = {
  kind: 'background' | 'planned' | 'track'
  color: string
}

type RouteFeature = {
  type: 'Feature'
  properties: RouteLineProperties
  geometry: { type: 'LineString'; coordinates: MapPosition[] }
}

export type VisibleVehicle = {
  vehicle: ReplayFleetVehicle
  gps: ReplayTelemetry | null
  status: VehicleStatus
  late: boolean
}

type Props = {
  visible: VisibleVehicle[]
  selected: ReplayFleetVehicle | null
  timeMs: number
  showAllRoutes: boolean
  receivedTrack: ReplayTelemetry[] | null
  onSelect: (trId: number) => void
}

function stopElement(confirmed: boolean) {
  const element = document.createElement('span')
  element.className = 'map-circle-marker'
  Object.assign(element.style, {
    width: confirmed ? '8px' : '6px', height: confirmed ? '8px' : '6px',
    borderColor: confirmed ? '#d36b21' : '#8092aa',
    background: confirmed ? '#f29a42' : '#fff', opacity: '0.9',
  })
  return element
}

function attachTooltip(map: Map, marker: Marker, label: string) {
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 })
    .setDOMContent(textElement(label, 'map-hover-tooltip'))
  const element = marker.getElement()
  element.addEventListener('mouseenter', () => popup.setLngLat(marker.getLngLat()).addTo(map))
  element.addEventListener('mouseleave', () => popup.remove())
}

export function HistoricalFleetMap({ visible, selected, timeMs, showAllRoutes, receivedTrack, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const markersRef = useRef<Marker[]>([])
  const routeOverlayRef = useRef<ReturnType<typeof createRouteOverlay> | null>(null)
  const fittedRef = useRef(false)
  const selectedRef = useRef<number | null>(null)
  const routeDataRef = useRef('')
  const [mapLoaded, setMapLoaded] = useState(false)

  useEffect(() => {
    if (!containerRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current, style: mapStyle, center: [37.62, 55.75], zoom: 10, minZoom: 3,
    })
    const unbindMarkerZoom = bindMarkerZoom(map)
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => {
      routeOverlayRef.current = createRouteOverlay(map)
      setMapLoaded(true)
    })
    mapRef.current = map
    const resize = new ResizeObserver(() => map.resize())
    resize.observe(containerRef.current)
    return () => {
      resize.disconnect()
      unbindMarkerZoom()
      routeOverlayRef.current?.remove()
      routeOverlayRef.current = null
      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    const routeFeatures: RouteFeature[] = []

    const pushLine = (coordinates: MapPosition[], kind: RouteLineProperties['kind'], color: string) => {
      if (coordinates.length < 2) return
      routeFeatures.push({
        type: 'Feature', properties: { kind, color },
        geometry: { type: 'LineString', coordinates },
      })
    }

    const drawRun = (vehicle: ReplayFleetVehicle, selectedLine: boolean) => {
      const run = currentRun(vehicle, timeMs)
      if (!run) return
      const ids = new Set(run.stop_ids)
      const stops = vehicle.stops.filter((stop) => ids.has(stop.stop_id))
      if (stops.length < 2) return
      const coordinates: MapPosition[] = stops.map((stop) => [stop.lon, stop.lat])
      pushLine(coordinates, selectedLine ? 'planned' : 'background', selectedLine ? '#d96f1c' : '#809fc7')
      if (!selectedLine) return
      for (const stop of stops) {
        const marker = new maplibregl.Marker({ element: stopElement(stop.gps_confirmed) })
          .setLngLat([stop.lon, stop.lat]).addTo(map)
        attachTooltip(map, marker, `Плановая точка ${stop.stop_id} · ${stop.gps_confirmed ? 'GPS подтверждён' : 'GPS не подтверждён'}`)
        markersRef.current.push(marker)
      }
    }

    if (showAllRoutes) {
      for (const item of visible) if (item.vehicle.tr_id !== selected?.tr_id) drawRun(item.vehicle, false)
    }
    if (selected) drawRun(selected, true)
    if (selected) {
      const run = currentRun(selected, timeMs)
      const since = run ? janMs(run.start_at) - 5 * 60_000 : timeMs - 2 * 60 * 60_000
      const traveled = (receivedTrack ?? selected.telemetry).filter((point) =>
        janMs(point.available_at) <= timeMs && janMs(point.event_time) >= since)
      let segment: MapPosition[] = []
      let previousTime = 0
      const addSegment = () => {
        pushLine(segment, 'track', run ? '#164ea7' : '#7554a6')
      }
      for (const point of traveled) {
        const eventTime = janMs(point.event_time)
        if (previousTime && (eventTime < previousTime || eventTime - previousTime > 5 * 60_000)) {
          addSegment()
          segment = []
        }
        segment.push([point.lon, point.lat])
        previousTime = eventTime
      }
      addSegment()
    }

    const routeDataSignature = JSON.stringify(routeFeatures)
    if (routeDataSignature !== routeDataRef.current) {
      routeDataRef.current = routeDataSignature
      const lines: MapLine[] = routeFeatures.map((feature) => {
        const { kind, color } = feature.properties
        return {
          points: feature.geometry.coordinates,
          color,
          width: kind === 'background' ? 2 : kind === 'planned' ? 5 : 4,
          opacity: kind === 'background' ? 0.5 : 0.95,
          ...(kind === 'background' ? { dash: [4, 5] } : {}),
          ...(kind === 'planned' ? { casingColor: '#fff', casingWidth: 2 } : {}),
        }
      })
      routeOverlayRef.current?.update(lines)
    }

    const points: MapPosition[] = []
    for (const { vehicle, gps, status, late } of visible) {
      if (!gps) continue
      const point: MapPosition = [gps.lon, gps.lat]
      points.push(point)
      const picked = vehicle.tr_id === selected?.tr_id
      const element = markerElement(status, picked, gps.heading, late)
      element.setAttribute('aria-label', `ТС ${vehicle.tr_id}: ${statusLabel[status]}${late ? ', прогноз опоздания' : ''}`)
      element.addEventListener('click', () => onSelect(vehicle.tr_id))
      const marker = new maplibregl.Marker({ element }).setLngLat(point).addTo(map)
      attachTooltip(map, marker, `ТС ${vehicle.tr_id} · ${statusLabel[status]}${late ? ' · прогноз опоздания' : ''}`)
      markersRef.current.push(marker)
    }
    if (!fittedRef.current && points.length) {
      fitMap(map, points, 45, 12)
      fittedRef.current = true
    }
    if (selected && selectedRef.current !== selected.tr_id) {
      const firstSelection = selectedRef.current === null
      selectedRef.current = selected.tr_id
      const gps = visible.find((item) => item.vehicle.tr_id === selected.tr_id)?.gps
      const run = currentRun(selected, timeMs)
      if (!firstSelection && run) {
        const ids = new Set(run.stop_ids)
        const stops = selected.stops.filter((stop) => ids.has(stop.stop_id))
        if (stops.length > 1) fitMap(map, stops.map((stop): MapPosition => [stop.lon, stop.lat]), 50, 13)
        else if (gps) map.easeTo({ center: [gps.lon, gps.lat] })
      } else if (gps) map.easeTo({ center: [gps.lon, gps.lat] })
    }
    return () => {
      markersRef.current.forEach((marker) => marker.remove())
      markersRef.current = []
    }
  }, [visible, selected, timeMs, showAllRoutes, receivedTrack, onSelect, mapLoaded])

  return <div aria-label="Карта январского транспорта и подтверждённых маршрутов" className="historical-map" ref={containerRef} role="application" />
}
