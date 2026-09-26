import { useQuery } from '@tanstack/react-query'

import { apiGet, apiPost } from '@/lib/api/http'
import type { ReplayFleet, ReplayOutcome, ReplayPrediction } from '@/types/replay'

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

export function useReplayOutcomes(timeMs: number | null) {
  const bucket = timeMs === null ? null : Math.floor(timeMs / 30_000) * 30_000
  return useQuery({
    queryKey: ['replay', 'outcomes', bucket],
    queryFn: () => apiGet<ReplayOutcome[]>(`/replay/outcomes?as_of=${encodeURIComponent(new Date(bucket!).toISOString())}`),
    enabled: bucket !== null,
  })
}
