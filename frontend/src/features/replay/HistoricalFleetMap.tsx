import * as maplibregl from 'maplibre-gl'
import type { Map, Marker } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'

import { markerElement } from '@/features/vehicles/markerIcon'
import { bindMarkerZoom, createRouteOverlay, fitMap, mapStyle, type MapLine, type MapPosition } from '@/lib/map/maplibre'
import { statusLabel } from '@/lib/telemetry/vehicleStatus'
import type { ReplayFleetVehicle } from '@/types/replay'
import { currentRun, displaySpeedKmh, janMs, stopLabel, type ReplayFleetItem } from './fleetClock'

type RouteLineProperties = {
  kind: 'background' | 'planned' | 'track'
  color: string
}

type RouteFeature = {
  type: 'Feature'
  properties: RouteLineProperties
  geometry: { type: 'LineString'; coordinates: MapPosition[] }
}

type Props = {
  visible: ReplayFleetItem[]
  selected: ReplayFleetVehicle | null
  timeMs: number
  onSelect: (trId: number) => void
}

function stopElement(label: string) {
  const element = document.createElement('span')
  element.className = 'map-circle-marker'
  element.setAttribute('aria-label', label)
  Object.assign(element.style, {
    width: '8px', height: '8px', borderColor: '#d36b21',
    background: '#f29a42', opacity: '0.9',
  })
  const tooltip = document.createElement('span')
  tooltip.className = 'map-stop-tooltip'
  tooltip.textContent = label
  element.append(tooltip)
  return element
}

export function HistoricalFleetMap({ visible, selected, timeMs, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const markersRef = useRef<Marker[]>([])
  const routeOverlayRef = useRef<ReturnType<typeof createRouteOverlay> | null>(null)
  const fittedCountRef = useRef(0)
  const userMovedRef = useRef(false)
  const selectedRef = useRef<string | null>(null)
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
    const markUserMoved = () => { userMovedRef.current = true }
    map.getContainer().addEventListener('pointerdown', markUserMoved)
    map.getContainer().addEventListener('wheel', markUserMoved)
    const resize = new ResizeObserver(() => map.resize())
    resize.observe(containerRef.current)
    return () => {
      resize.disconnect()
      map.getContainer().removeEventListener('pointerdown', markUserMoved)
      map.getContainer().removeEventListener('wheel', markUserMoved)
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
        const marker = new maplibregl.Marker({ element: stopElement(`Плановая остановка · ${stopLabel(vehicle, stop.stop_id)}`) })
          .setLngLat([stop.lon, stop.lat]).addTo(map)
        markersRef.current.push(marker)
      }
    }

    if (selected) drawRun(selected, true)
    if (selected) {
      const run = currentRun(selected, timeMs)
      const since = run ? janMs(run.start_at) - 5 * 60_000 : timeMs - 2 * 60 * 60_000
      const traveled = selected.telemetry.filter((point) =>
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
    for (const { vehicle, gps, status, late, forecast } of visible) {
      if (!gps) continue
      const point: MapPosition = [gps.lon, gps.lat]
      points.push(point)
      const picked = vehicle.tr_id === selected?.tr_id
      const speed = displaySpeedKmh(gps.speed)
      const delaySeconds = late ? forecast?.predicted_delay_s : null
      const element = markerElement(status, picked, gps.heading, { delaySeconds, speedKmh: speed })
      element.setAttribute('aria-label', `ТС ${vehicle.tr_id}: ${statusLabel[status]}${late && forecast ? `, прогноз опоздания ${Math.round(forecast.predicted_delay_s)} секунд` : ''}${status === 'moving' && speed !== null ? `, ${Math.round(speed)} км/ч` : ''}`)
      element.addEventListener('click', () => onSelect(vehicle.tr_id))
      const tooltip = document.createElement('span')
      tooltip.className = 'vehicle-tooltip'
      const title = document.createElement('strong')
      title.textContent = `ТС ${vehicle.tr_id}`
      const detail = document.createElement('span')
      detail.textContent = `${statusLabel[status]}${late ? ' · прогноз опоздания' : ''}`
      tooltip.append(title, detail)
      element.append(tooltip)
      const marker = new maplibregl.Marker({ element }).setLngLat(point).addTo(map)
      markersRef.current.push(marker)
    }
    const selectedRun = selected ? currentRun(selected, timeMs) : null
    if (!userMovedRef.current && !selectedRun && points.length > fittedCountRef.current) {
      fitMap(map, points, 45, 12)
      fittedCountRef.current = points.length
    }
    const selectedKey = selected ? `${selected.tr_id}:${selectedRun?.run_id ?? ''}` : null
    if (selected && selectedRef.current !== selectedKey) {
      selectedRef.current = selectedKey
      const gps = visible.find((item) => item.vehicle.tr_id === selected.tr_id)?.gps
      if (selectedRun) {
        const ids = new Set(selectedRun.stop_ids)
        const stops = selected.stops.filter((stop) => ids.has(stop.stop_id))
        if (stops.length > 1) fitMap(map, [
          ...stops.map((stop): MapPosition => [stop.lon, stop.lat]),
          ...(gps ? [[gps.lon, gps.lat] as MapPosition] : []),
        ], 50, 13)
        else if (gps) map.easeTo({ center: [gps.lon, gps.lat] })
      } else if (gps && fittedCountRef.current === 0) map.easeTo({ center: [gps.lon, gps.lat] })
    }
    return () => {
      markersRef.current.forEach((marker) => marker.remove())
      markersRef.current = []
    }
  }, [visible, selected, timeMs, onSelect, mapLoaded])

  return <div aria-label="Карта транспорта" className="historical-map" ref={containerRef} role="application" />
}
