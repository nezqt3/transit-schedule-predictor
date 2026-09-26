import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { env } from '@/config/env'
import { queryKeys } from '@/lib/api/queryClient'
import { eventTimeMs } from '@/lib/telemetry/readEvent'
import { useTelemetryStore } from '@/store/telemetry'
import type { Incident, StoredPrediction, TelemetryEvent, TelemetryStreamMessage } from '@/types/api'

import { useVehicles } from './api'

/** REST snapshot with live NDTP updates from the backend WebSocket. */
export function useVehicleFeed() {
  const query = useVehicles()
  const queryClient = useQueryClient()
  const [streamConnected, setStreamConnected] = useState(false)
  const appendSamples = useTelemetryStore((state) => state.appendSamples)
  const events = query.data

  useEffect(() => {
    let stopped = false
    let socket: WebSocket | null = null
    let reconnect: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      const url = new URL(`${env.apiBaseUrl.replace(/\/$/u, '')}/ws`, window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(url)
      socket.onopen = () => {
        setStreamConnected(true)
        void queryClient.invalidateQueries({ queryKey: queryKeys.vehicles })
        void queryClient.invalidateQueries({ queryKey: queryKeys.predictions })
        void queryClient.invalidateQueries({ queryKey: queryKeys.incidents })
      }
      socket.onmessage = ({ data }) => {
        try {
          const message = JSON.parse(String(data)) as TelemetryStreamMessage
          if (message.type === 'vehicle_snapshot' && Array.isArray(message.data)) {
            queryClient.setQueryData<TelemetryEvent[]>(queryKeys.vehicles, (current = []) => {
              const merged = new Map(current.map((event) => [event.unit_id, event]))
              for (const event of message.data) {
                const old = merged.get(event.unit_id)
                if (!old || eventTimeMs(event) >= eventTimeMs(old)) merged.set(event.unit_id, event)
              }
              return [...merged.values()]
            })
          } else if (message.type === 'vehicle_update' && typeof message.data?.unit_id === 'number') {
            queryClient.setQueryData<TelemetryEvent[]>(queryKeys.vehicles, (current = []) => {
              const old = current.find((event) => event.unit_id === message.data.unit_id)
              if (old && eventTimeMs(old) > eventTimeMs(message.data)) return current
              const remaining = current.filter((event) => event.unit_id !== message.data.unit_id)
              return [...remaining, message.data]
            })
          } else if (message.type === 'prediction_update') {
            queryClient.setQueryData<StoredPrediction[]>(queryKeys.predictions, (current = []) => {
              const old = current.find((item) => item.tr_id === message.data.tr_id)
              if (old && Date.parse(old.prediction_time) > Date.parse(message.data.prediction_time)) return current
              if (old && old.prediction_time === message.data.prediction_time
                  && old.freshness === 'stale' && message.data.freshness !== 'stale') return current
              return [...current.filter((item) => item.tr_id !== message.data.tr_id), message.data]
            })
            void queryClient.invalidateQueries({ queryKey: queryKeys.predictionStatuses })
          } else if (message.type === 'incident') {
            queryClient.setQueryData<Incident[]>(queryKeys.incidents, (current = []) => {
              const old = current.find((item) => item.incident_id === message.data.incident_id)
              if (old && Date.parse(old.updated_at) > Date.parse(message.data.updated_at)) return current
              return [message.data, ...current.filter((item) => item.incident_id !== message.data.incident_id)]
            })
          }
        } catch {
          // Ignore malformed stream messages; REST polling remains available.
        }
      }
      socket.onclose = () => {
        if (stopped) return
        setStreamConnected(false)
        reconnect = setTimeout(connect, 2_000)
      }
    }

    connect()
    return () => {
      stopped = true
      if (reconnect) clearTimeout(reconnect)
      socket?.close()
    }
  }, [queryClient])

  useEffect(() => {
    if (events) appendSamples(events)
  }, [events, appendSamples])

  return { ...query, streamConnected }
}
