import L, { type LatLngTuple, type Map as LeafletMap } from 'leaflet'
import { useEffect, useRef } from 'react'
import 'leaflet/dist/leaflet.css'

import type { ReplayScenario } from '@/types/replay'

type Props = { scenario: ReplayScenario; timeMs: number }

export function ReplayMap({ scenario, timeMs }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap | null>(null)
  const plannedRef = useRef<L.LayerGroup | null>(null)
  const activeRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const map = L.map(containerRef.current, { zoomControl: true }).setView([55.75, 37.62], 11)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors', maxZoom: 19,
    }).addTo(map)
    mapRef.current = map
    plannedRef.current = L.layerGroup().addTo(map)
    activeRef.current = L.layerGroup().addTo(map)
    const resize = new ResizeObserver(() => map.invalidateSize())
    resize.observe(containerRef.current)
    return () => {
      resize.disconnect()
      mapRef.current = null
      plannedRef.current = null
      activeRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layer = plannedRef.current
    if (!map || !layer) return
    layer.clearLayers()
    const targetIds = new Set(scenario.points.map((point) => point.target_stop_id))
    const bounds: LatLngTuple[] = []
    for (const stop of scenario.stops) {
      const position: LatLngTuple = [stop.lat, stop.lon]
      bounds.push(position)
      const target = targetIds.has(stop.stop_id)
      L.circleMarker(position, {
        radius: target ? 5 : 2.5,
        color: target ? '#d76b31' : '#6b8ead',
        weight: target ? 2 : 1,
        fillOpacity: target ? 0.8 : 0.45,
      }).bindTooltip(`Остановка ${stop.stop_id} · ${new Date(stop.planned_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`)
        .addTo(layer)
    }
    if (bounds.length > 0) map.fitBounds(L.latLngBounds(bounds), { padding: [36, 36], maxZoom: 12 })
  }, [scenario])

  useEffect(() => {
    const layer = activeRef.current
    if (!layer) return
    layer.clearLayers()
    const visible = scenario.telemetry.filter((point) => Date.parse(point.available_at) <= timeMs)
    if (visible.length === 0) return
    const path: LatLngTuple[] = visible.map((point) => [point.lat, point.lon])
    L.polyline(path, { color: '#1459c7', weight: 3, opacity: 0.82 }).addTo(layer)
    const last = visible[visible.length - 1]!
    L.circleMarker([last.lat, last.lon], {
      radius: 9, color: '#fff', weight: 3, fillColor: '#1459c7', fillOpacity: 1,
    }).bindTooltip(`Терминал ${scenario.vehicle.unit_id} · ${new Date(last.event_time).toLocaleTimeString('ru-RU')}`)
      .addTo(layer)
  }, [scenario, timeMs])

  return <div aria-label="Историческая GPS-траектория и плановые остановки" className="replay-map" ref={containerRef} role="application" />
}
