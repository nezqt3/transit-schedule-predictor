import { useQuery } from '@tanstack/react-query'

import { apiGet, apiPost } from '@/lib/api/http'
import type { ReplayFleet, ReplayPrediction, ReplayScenario, ReplayStreamStatus, ReplayVehicle } from '@/types/replay'

export function useReplayFleet() {
  return useQuery({
    queryKey: ['replay', 'fleet'],
    queryFn: () => apiGet<ReplayFleet>('/replay/fleet'),
    staleTime: Infinity,
  })
}

export function useReplayStreamStatus() {
  return useQuery({
    queryKey: ['replay', 'stream-status'],
    queryFn: () => apiGet<ReplayStreamStatus>('/replay/stream-status'),
    refetchInterval: 1000,
    retry: false,
  })
}

export function useReplayVehicles() {
  return useQuery({
    queryKey: ['replay', 'vehicles'],
    queryFn: () => apiGet<ReplayVehicle[]>('/replay/vehicles'),
  })
}

export function useReplayScenario(trId: number | null) {
  return useQuery({
    queryKey: ['replay', 'scenario', trId],
    queryFn: () => apiGet<ReplayScenario>(`/replay/vehicles/${trId}`),
    enabled: trId !== null,
  })
}

export function predictReplayPoint(sampleId: string) {
  return apiPost<ReplayPrediction, Record<string, never>>(`/replay/predict/${sampleId}`, {})
}
