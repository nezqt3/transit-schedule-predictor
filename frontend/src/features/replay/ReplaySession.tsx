import { useEffect, useMemo, useRef } from 'react'

import { REPLAY_ANCHOR_KEY, useDashboardStore } from '@/store/dashboard'
import { predictReplayPoint, useReplayFleet } from './api'
import { janMs } from './fleetClock'

const TICK_MS = 1000
const MAX_CONCURRENT_PREDICTIONS = 6

/** Keep the January clock and forecasts running while navigating between map and table. */
export function ReplaySession() {
  const { data: fleet } = useReplayFleet()
  const timeMs = useDashboardStore((state) => state.replayTimeMs)
  const revision = useDashboardStore((state) => state.replayRevision)
  const predictions = useDashboardStore((state) => state.replayPredictions)
  const failures = useDashboardStore((state) => state.replayFailures)
  const requested = useRef(new Set([...Object.keys(predictions), ...Object.keys(failures)]))
  const inFlight = useRef(0)
  const generation = useRef(revision)

  const points = useMemo(() => fleet?.vehicles.flatMap((vehicle) => vehicle.points)
    .sort((a, b) => janMs(b.T) - janMs(a.T)) ?? [], [fleet])

  useEffect(() => {
    generation.current = revision
    requested.current.clear()
    inFlight.current = 0
  }, [revision])

  useEffect(() => {
    if (!fleet) return
    const firstVerifiedRunMs = Math.min(...fleet.vehicles.flatMap((vehicle) =>
      vehicle.runs.filter((run) => run.valid).map((run) => janMs(run.start_at))))
    const startMs = Number.isFinite(firstVerifiedRunMs)
      ? Math.max(janMs(fleet.start_at), firstVerifiedRunMs)
      : janMs(fleet.start_at)
    const endMs = janMs(fleet.end_at)
    if (!(endMs > startMs)) return
    const durationMs = endMs - startMs
    const now = Date.now()
    const stored = Number(window.localStorage.getItem(REPLAY_ANCHOR_KEY))
    let anchorMs = Number.isFinite(stored) && stored > 0 && stored <= now
      ? stored : now
    if (now - anchorMs >= durationMs) anchorMs += Math.floor((now - anchorMs) / durationMs) * durationMs
    window.localStorage.setItem(REPLAY_ANCHOR_KEY, String(anchorMs))

    let completed = false
    const tick = () => {
      if (completed) return
      const elapsed = Math.max(0, Date.now() - anchorMs)
      const state = useDashboardStore.getState()
      if (elapsed >= durationMs) {
        completed = true
        state.resetReplay()
      } else {
        state.setReplayTime(startMs + elapsed)
      }
    }
    tick()
    const timer = window.setInterval(tick, TICK_MS)
    return () => window.clearInterval(timer)
  }, [fleet, revision])

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
