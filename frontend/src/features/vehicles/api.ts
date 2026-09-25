import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { apiGet } from '@/lib/api/http'
import { queryKeys } from '@/lib/api/queryClient'
import { env } from '@/config/env'
import type { TelemetryEvent } from '@/types/api'

export function fetchVehicles(): Promise<TelemetryEvent[]> {
  return apiGet<TelemetryEvent[]>('/vehicles')
}

export function useVehicles() {
  return useQuery({
    queryKey: queryKeys.vehicles,
    queryFn: fetchVehicles,
    refetchInterval: env.pollIntervalMs,
    placeholderData: keepPreviousData,
  })
}
