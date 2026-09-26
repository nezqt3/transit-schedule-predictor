import * as maplibregl from 'maplibre-gl'
import type { Map, Marker } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'
import 'maplibre-gl/dist/maplibre-gl.css'

import { addLine, bindMarkerZoom, fitMap, mapStyle, textElement, type MapPosition } from '@/lib/map/maplibre'
import type { ReplayScenario } from '@/types/replay'

type Props = { scenario: ReplayScenario; timeMs: number }

function circleElement(size: number, color: string, fill: string, opacity: number) {
  const element = document.createElement('span')
  element.className = 'map-circle-marker'
  Object.assign(element.style, {
    width: `${size * 2}px`, height: `${size * 2}px`, borderColor: color,
    background: fill, opacity: String(opacity),
  })
  return element
}

function tooltipMarker(map: Map, marker: Marker, label: string) {
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 })
    .setDOMContent(textElement(label, 'map-hover-tooltip'))
  const element = marker.getElement()
  element.addEventListener('mouseenter', () => popup.setLngLat(marker.getLngLat()).addTo(map))
  element.addEventListener('mouseleave', () => popup.remove())
}

export function ReplayMap({ scenario, timeMs }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const plannedMarkersRef = useRef<Marker[]>([])
  const activeMarkerRef = useRef<Marker | null>(null)
  const [mapLoaded, setMapLoaded] = useState(false)

  useEffect(() => {
    if (!containerRef.current) return
    const map = new maplibregl.Map({ container: containerRef.current, style: mapStyle, center: [37.62, 55.75], zoom: 11 })
    const unbindMarkerZoom = bindMarkerZoom(map)
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => setMapLoaded(true))
    mapRef.current = map
    const resize = new ResizeObserver(() => map.resize())
    resize.observe(containerRef.current)
    return () => {
      resize.disconnect()
      unbindMarkerZoom()
      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return
    plannedMarkersRef.current.forEach((marker) => marker.remove())
    plannedMarkersRef.current = []
    const targetIds = new Set(scenario.points.map((point) => point.target_stop_id))
    const bounds: MapPosition[] = []
    for (const stop of scenario.stops) {
      const position: MapPosition = [stop.lon, stop.lat]
      bounds.push(position)
      const target = targetIds.has(stop.stop_id)
      const marker = new maplibregl.Marker({
        element: circleElement(target ? 5 : 2.5, target ? '#d76b31' : '#6b8ead', target ? '#d76b31' : '#6b8ead', target ? 0.8 : 0.45),
      }).setLngLat(position).addTo(map)
      tooltipMarker(map, marker, `Остановка ${stop.stop_id} · ${new Date(stop.planned_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`)
      plannedMarkersRef.current.push(marker)
    }
    const removeRoute = addLine(map, bounds, {
      color: '#1766ce', width: 4, opacity: 0.95, casingColor: '#ffffff', casingWidth: 2,
    })
    fitMap(map, bounds, 36, 12)
    return () => {
      removeRoute()
      plannedMarkersRef.current.forEach((marker) => marker.remove())
      plannedMarkersRef.current = []
    }
  }, [scenario, mapLoaded])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return
    activeMarkerRef.current?.remove()
    activeMarkerRef.current = null
    const visible = scenario.telemetry.filter((point) => Date.parse(point.available_at) <= timeMs)
    if (visible.length === 0) return
    const path: MapPosition[] = visible.map((point) => [point.lon, point.lat])
    const removeLine = addLine(map, path, { color: '#1459c7', width: 3, opacity: 0.82 })
    const last = visible[visible.length - 1]!
    const marker = new maplibregl.Marker({ element: circleElement(9, '#fff', '#1459c7', 1) })
      .setLngLat([last.lon, last.lat]).addTo(map)
    tooltipMarker(map, marker, `Терминал ${scenario.vehicle.unit_id} · ${new Date(last.event_time).toLocaleTimeString('ru-RU')}`)
    activeMarkerRef.current = marker
    return () => {
      removeLine()
      marker.remove()
      if (activeMarkerRef.current === marker) activeMarkerRef.current = null
    }
  }, [scenario, timeMs, mapLoaded])

  return <div aria-label="Историческая GPS-траектория и плановые остановки" className="replay-map" ref={containerRef} role="application" />
}
