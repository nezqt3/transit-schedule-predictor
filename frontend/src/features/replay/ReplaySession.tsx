import { useEffect, useMemo, useRef } from 'react'

import { useDashboardStore } from '@/store/dashboard'
import { predictReplayPoint, useReplayFleet } from './api'
import { janMs, replayBounds } from './fleetClock'

const TICK_MS = 250
const MAX_CONCURRENT_PREDICTIONS = 6

/** Keep the January clock and forecasts running while navigating between map and table. */
export function ReplaySession() {
  const { data: fleet } = useReplayFleet()
  const timeMs = useDashboardStore((state) => state.replayTimeMs)
  const revision = useDashboardStore((state) => state.replayRevision)
  const playing = useDashboardStore((state) => state.replayPlaying)
  const speed = useDashboardStore((state) => state.replaySpeed)
  const predictions = useDashboardStore((state) => state.replayPredictions)
  const failures = useDashboardStore((state) => state.replayFailures)
  const requested = useRef(new Set([...Object.keys(predictions), ...Object.keys(failures)]))
  const inFlight = useRef(0)
  const generation = useRef(revision)
  const lastTick = useRef(Date.now())

  const points = useMemo(() => fleet?.vehicles.flatMap((vehicle) => vehicle.points)
    .sort((a, b) => janMs(b.T) - janMs(a.T)) ?? [], [fleet])

  useEffect(() => {
    generation.current = revision
    requested.current.clear()
    inFlight.current = 0
  }, [revision])

  useEffect(() => {
    if (!fleet) return
    const { startMs, endMs } = replayBounds(fleet)
    if (!(endMs > startMs)) return
    const state = useDashboardStore.getState()
    if (state.replayTimeMs === null) state.setReplayTime(startMs)
    lastTick.current = Date.now()
    const tick = () => {
      const now = Date.now()
      const elapsed = Math.max(0, now - lastTick.current)
      lastTick.current = now
      const current = useDashboardStore.getState()
      if (!current.replayPlaying || current.replayTimeMs === null) return
      const next = Math.min(endMs, current.replayTimeMs + elapsed * current.replaySpeed)
      current.setReplayTime(next)
      if (next >= endMs) current.setReplayPlaying(false)
    }
    const timer = window.setInterval(tick, TICK_MS)
    return () => window.clearInterval(timer)
  }, [fleet, revision, playing, speed])

  useEffect(() => {
    if (!fleet || timeMs === null) return
    const capacity = Math.max(0, MAX_CONCURRENT_PREDICTIONS - inFlight.current)
    if (!capacity) return
    const due = points.filter((point) => janMs(point.T) <= timeMs
      && !requested.current.has(point.sample_id)).slice(0, capacity)
    for (const point of due) {
      requested.current.add(point.sample_id)
      inFlight.current += 1
      const requestGeneration = generation.current
      predictReplayPoint(point.sample_id)
        .then((prediction) => {
          if (generation.current === requestGeneration) useDashboardStore.getState().setReplayPrediction(prediction)
        })
        .catch((error: Error) => {
          if (generation.current === requestGeneration) useDashboardStore.getState().setReplayFailure(point.sample_id, error.message)
        })
        .finally(() => { if (generation.current === requestGeneration) inFlight.current -= 1 })
    }
  }, [fleet, timeMs, points, predictions, failures])

  return null
}
