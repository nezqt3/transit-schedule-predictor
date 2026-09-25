import { useEffect } from 'react'

import { useTelemetryStore } from '@/store/telemetry'

import { useVehicles } from './api'

/** Опрос REST + накопление локальной истории скорости по каждому ТС. */
export function useVehicleFeed() {
  const query = useVehicles()
  const appendSamples = useTelemetryStore((state) => state.appendSamples)
  const events = query.data

  useEffect(() => {
    if (events) appendSamples(events)
  }, [events, appendSamples])

  return query
}
