import { useQuery } from '@tanstack/react-query'

import { env } from '@/config/env'
import { apiGet } from '@/lib/api/http'
import { queryKeys } from '@/lib/api/queryClient'
import type { StoredPrediction } from '@/types/api'

export function usePredictions() {
  return useQuery({
    queryKey: queryKeys.predictions,
    queryFn: () => apiGet<StoredPrediction[]>('/predictions'),
    refetchInterval: env.pollIntervalMs,
  })
}
