import L, { type LatLngTuple, type Map as LeafletMap } from 'leaflet'
import { useEffect, useRef } from 'react'
import 'leaflet/dist/leaflet.css'

import { markerIcon } from '@/features/vehicles/markerIcon'
import { statusLabel, type VehicleStatus } from '@/lib/telemetry/vehicleStatus'
import { currentRun, janMs } from './fleetClock'
import type { ReplayFleetVehicle, ReplayTelemetry } from '@/types/replay'

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

export function HistoricalFleetMap({ visible, selected, timeMs, showAllRoutes, receivedTrack, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap | null>(null)
  const routesRef = useRef<L.LayerGroup | null>(null)
  const markersRef = useRef<L.LayerGroup | null>(null)
  const fittedRef = useRef(false)
  const selectedRef = useRef<number | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const map = L.map(containerRef.current, { zoomControl: true, minZoom: 3 }).setView([55.75, 37.62], 10)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors', maxZoom: 19,
    }).addTo(map)
    mapRef.current = map
    routesRef.current = L.layerGroup().addTo(map)
    markersRef.current = L.layerGroup().addTo(map)
    const resize = new ResizeObserver(() => map.invalidateSize())
    resize.observe(containerRef.current)
    return () => {
      resize.disconnect()
      routesRef.current = null
      markersRef.current = null
      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const routes = routesRef.current
    const markers = markersRef.current
    if (!map || !routes || !markers) return
    routes.clearLayers()
    markers.clearLayers()

    const drawRun = (vehicle: ReplayFleetVehicle, selectedLine: boolean) => {
      const run = currentRun(vehicle, timeMs)
      if (!run) return
      const ids = new Set(run.stop_ids)
      const stops = vehicle.stops.filter((stop) => ids.has(stop.stop_id))
      if (stops.length < 2) return
      const coordinates: LatLngTuple[] = stops.map((stop) => [stop.lat, stop.lon])
      L.polyline(coordinates, {
        color: selectedLine ? '#1766ce' : '#809fc7',
        weight: selectedLine ? 3 : 1.5,
        opacity: selectedLine ? 0.85 : 0.32,
        dashArray: selectedLine ? '7 5' : '4 6',
      }).addTo(routes)
      if (!selectedLine) return
      for (const stop of stops) {
        L.circleMarker([stop.lat, stop.lon], {
          radius: stop.gps_confirmed ? 4 : 3,
          color: stop.gps_confirmed ? '#d36b21' : '#8092aa',
          fillColor: stop.gps_confirmed ? '#f29a42' : '#fff',
          fillOpacity: 0.9, weight: 1.5,
        }).bindTooltip(`Плановая точка ${stop.stop_id} · ${stop.gps_confirmed ? 'GPS подтверждён' : 'GPS не подтверждён'}`)
          .addTo(routes)
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
      let segment: LatLngTuple[] = []
      let previousTime = 0
      const addSegment = () => {
        if (segment.length > 1) L.polyline(segment, {
          color: run ? '#164ea7' : '#7554a6', weight: 4, opacity: 0.95,
        }).addTo(routes)
      }
      for (const point of traveled) {
        const eventTime = janMs(point.event_time)
        if (previousTime && (eventTime < previousTime || eventTime - previousTime > 5 * 60_000)) {
          addSegment()
          segment = []
        }
        segment.push([point.lat, point.lon])
        previousTime = eventTime
      }
      addSegment()
    }

    const points: LatLngTuple[] = []
    for (const { vehicle, gps, status, late } of visible) {
      if (!gps) continue
      const point: LatLngTuple = [gps.lat, gps.lon]
      points.push(point)
      const picked = vehicle.tr_id === selected?.tr_id
      const marker = L.marker(point, {
        icon: markerIcon(status, picked, gps.heading, late),
        alt: `ТС ${vehicle.tr_id}: ${statusLabel[status]}${late ? ', прогноз опоздания' : ''}`,
        keyboard: true,
        zIndexOffset: picked ? 1000 : 0,
      }).bindTooltip(`ТС ${vehicle.tr_id} · ${statusLabel[status]}${late ? ' · прогноз опоздания' : ''}`)
      marker.on('click', () => onSelect(vehicle.tr_id))
      marker.addTo(markers)
    }
    if (!fittedRef.current && points.length) {
      map.fitBounds(L.latLngBounds(points), { padding: [45, 45], maxZoom: 12 })
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
        if (stops.length > 1) {
          map.fitBounds(L.latLngBounds(stops.map((stop): LatLngTuple => [stop.lat, stop.lon])), {
            padding: [50, 50], maxZoom: 13,
          })
        } else if (gps) map.panTo([gps.lat, gps.lon])
      } else if (gps) map.panTo([gps.lat, gps.lon])
    }
  }, [visible, selected, timeMs, showAllRoutes, receivedTrack, onSelect])

  const fitFleet = () => {
    const points = visible.flatMap((item): LatLngTuple[] => item.gps ? [[item.gps.lat, item.gps.lon]] : [])
    if (mapRef.current && points.length) {
      mapRef.current.fitBounds(L.latLngBounds(points), { padding: [45, 45], maxZoom: 12 })
    }
  }
  return <>
    <div aria-label="Карта январского транспорта и подтверждённых маршрутов" className="historical-map" ref={containerRef} role="application" />
    <button className="historical-map-fit" onClick={fitFleet} type="button">Весь парк</button>
  </>
}
