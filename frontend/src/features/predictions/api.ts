import { useQuery } from '@tanstack/react-query'

import { env } from '@/config/env'
import { apiGet } from '@/lib/api/http'
import { queryKeys } from '@/lib/api/queryClient'
import type { Incident, PredictionStatus, StoredPrediction } from '@/types/api'

export function usePredictions() {
  return useQuery({
    queryKey: queryKeys.predictions,
    queryFn: () => apiGet<StoredPrediction[]>('/predictions'),
    refetchInterval: env.pollIntervalMs,
  })
}

export function usePredictionStatuses() {
  return useQuery({
    queryKey: queryKeys.predictionStatuses,
    queryFn: () => apiGet<PredictionStatus[]>('/predictions/statuses'),
    refetchInterval: env.pollIntervalMs,
  })
}

export function useIncidents() {
  return useQuery({
    queryKey: queryKeys.incidents,
    queryFn: () => apiGet<Incident[]>('/incidents'),
    refetchInterval: env.pollIntervalMs,
  })
}
