import { useQuery } from '@tanstack/react-query'

import { apiGet, apiPost } from '@/lib/api/http'
import type { ReplayPrediction, ReplayScenario, ReplayVehicle } from '@/types/replay'

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
