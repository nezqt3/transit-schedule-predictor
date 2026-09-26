import { useQuery } from '@tanstack/react-query'

import { apiGet, apiPost } from '@/lib/api/http'
import type { ReplayFleet, ReplayPrediction } from '@/types/replay'

export function useReplayFleet(enabled = true) {
  return useQuery({
    queryKey: ['replay', 'fleet'],
    queryFn: () => apiGet<ReplayFleet>('/replay/fleet'),
    staleTime: Infinity,
    enabled,
  })
}

export function predictReplayPoint(sampleId: string) {
  return apiPost<ReplayPrediction, Record<string, never>>(`/replay/predict/${sampleId}`, {})
}
