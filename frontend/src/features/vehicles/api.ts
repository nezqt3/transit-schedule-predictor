import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { apiGet } from '@/lib/api/http'
import { queryKeys } from '@/lib/api/queryClient'
import { env } from '@/config/env'
import type { TelemetryEvent } from '@/types/api'

export function fetchVehicles(): Promise<TelemetryEvent[]> {
  return apiGet<TelemetryEvent[]>('/vehicles')
}

export function fetchVehicleHistory(unitId: number): Promise<TelemetryEvent[]> {
  return apiGet<TelemetryEvent[]>(`/vehicles/${unitId}/history`)
}

export function useVehicles() {
  return useQuery({
    queryKey: queryKeys.vehicles,
    queryFn: fetchVehicles,
    refetchInterval: env.pollIntervalMs,
    placeholderData: keepPreviousData,
  })
}

export function useVehicleHistory(unitId: number | null) {
  return useQuery({
    queryKey: queryKeys.vehicleHistory(unitId ?? -1),
    queryFn: () => fetchVehicleHistory(unitId!),
    enabled: unitId !== null,
    refetchInterval: env.pollIntervalMs,
  })
}
