import { create } from 'zustand'

import type { TelemetryEvent } from '@/types/api'
import { eventTimeMs, speedKmh } from '@/lib/telemetry/readEvent'

const MAX_POINTS_PER_UNIT = 60

export type SpeedPoint = {
  timeMs: number
  speed: number
}

type TelemetryState = {
  selectedUnitId: number | null
  speedHistory: Record<number, SpeedPoint[]>
  selectUnit: (unitId: number | null) => void
  appendSamples: (events: readonly TelemetryEvent[]) => void
}

export const useTelemetryStore = create<TelemetryState>((set) => ({
  selectedUnitId: null,
  speedHistory: {},
  selectUnit: (unitId) => set({ selectedUnitId: unitId }),
  appendSamples: (events) =>
    set((state) => {
      if (events.length === 0) return state

      const next: Record<number, SpeedPoint[]> = { ...state.speedHistory }
      for (const event of events) {
        const speed = speedKmh(event)
        if (speed === null) continue

        const points = next[event.unit_id] ?? []
        const last = points[points.length - 1]
        const timeMs = eventTimeMs(event)
        if (last && last.timeMs === timeMs && last.speed === speed) continue

        next[event.unit_id] = [...points, { timeMs, speed }].slice(-MAX_POINTS_PER_UNIT)
      }
      return { speedHistory: next }
    }),
}))
