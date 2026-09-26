import * as maplibregl from 'maplibre-gl'
import type { LngLatBoundsLike, Map, StyleSpecification } from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

import { env } from '@/config/env'

// Vite pre-bundles MapLibre, so an explicit worker asset keeps the worker URL
// valid in both the development server and the production bundle.
maplibregl.setWorkerUrl(maplibreWorkerUrl)

export type MapPosition = [longitude: number, latitude: number]
export type MapLine = {
  points: readonly MapPosition[]
  color: string
  width: number
  opacity: number
  dash?: number[]
  casingColor?: string
  casingWidth?: number
}

const fallbackStyle: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxzoom: 19,
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}

export const mapStyle: string | StyleSpecification =
  env.mapStyleUrl || fallbackStyle

export function fitMap(map: Map, points: readonly MapPosition[], padding: number, maxZoom: number) {
  if (points.length === 0) return
  if (points.length === 1) {
    map.easeTo({ center: points[0], zoom: Math.min(maxZoom, 13) })
    return
  }
  const bounds = new maplibregl.LngLatBounds(points[0], points[0])
  for (const point of points.slice(1)) bounds.extend(point)
  map.fitBounds(bounds as LngLatBoundsLike, { padding, maxZoom })
}

export function bindMarkerZoom(map: Map) {
  const container = map.getContainer()
  const update = () => {
    const zoom = map.getZoom()
    const scale = zoom >= 11 ? 1 : zoom >= 9 ? 0.82 : zoom >= 7 ? 0.62 : 0.45
    container.style.setProperty('--map-marker-scale', String(scale))
    container.classList.toggle('map-markers-hidden', zoom < 6)
  }
  update()
  map.on('zoom', update)
  return () => map.off('zoom', update)
}

export function createRouteOverlay(map: Map) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.classList.add('map-route-overlay')
  svg.setAttribute('aria-hidden', 'true')
  map.getContainer().append(svg)
  let lines: readonly MapLine[] = []

  const render = () => {
    svg.replaceChildren()
    for (const line of lines) {
      if (line.points.length < 2) continue
      const points = line.points.map((point) => {
        const projected = map.project(point)
        return `${projected.x},${projected.y}`
      }).join(' ')
      const appendPolyline = (color: string, width: number, dash?: number[]) => {
        const polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline')
        polyline.setAttribute('points', points)
        polyline.setAttribute('fill', 'none')
        polyline.setAttribute('stroke', color)
        polyline.setAttribute('stroke-width', String(width))
        polyline.setAttribute('stroke-linecap', 'round')
        polyline.setAttribute('stroke-linejoin', 'round')
        polyline.setAttribute('opacity', String(line.opacity))
        if (dash) polyline.setAttribute('stroke-dasharray', dash.join(' '))
        svg.append(polyline)
      }
      if (line.casingColor && line.casingWidth) {
        appendPolyline(line.casingColor, line.width + line.casingWidth * 2)
      }
      appendPolyline(line.color, line.width, line.dash)
    }
  }
  const update = (nextLines: readonly MapLine[]) => {
    lines = nextLines
    render()
  }
  map.on('move', render)
  map.on('resize', render)
  return {
    update,
    remove: () => {
      map.off('move', render)
      map.off('resize', render)
      svg.remove()
    },
  }
}

export function addLine(
  map: Map,
  points: readonly MapPosition[],
  paint: {
    color: string
    width: number
    opacity: number
    dash?: number[]
    casingColor?: string
    casingWidth?: number
  },
) {
  if (points.length < 2) return () => undefined
  const overlay = createRouteOverlay(map)
  overlay.update([{ points, ...paint }])
  return overlay.remove
}

export function textElement(html: string, className?: string) {
  const element = document.createElement('div')
  if (className) element.className = className
  element.innerHTML = html
  return element
}
