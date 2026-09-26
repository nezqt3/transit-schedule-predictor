import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { env } from '@/config/env'
import { queryKeys } from '@/lib/api/queryClient'
import { useTelemetryStore } from '@/store/telemetry'
import type { TelemetryEvent, TelemetryStreamMessage } from '@/types/api'

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
      socket.onopen = () => setStreamConnected(true)
      socket.onmessage = ({ data }) => {
        try {
          const message = JSON.parse(String(data)) as TelemetryStreamMessage
          if (message.type === 'vehicle_snapshot' && Array.isArray(message.data)) {
            queryClient.setQueryData(queryKeys.vehicles, message.data)
          } else if (message.type === 'vehicle_update' && typeof message.data?.unit_id === 'number') {
            queryClient.setQueryData<TelemetryEvent[]>(queryKeys.vehicles, (current = []) => {
              const remaining = current.filter((event) => event.unit_id !== message.data.unit_id)
              return [...remaining, message.data]
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
