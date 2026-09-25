import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/lib/api/http'
import { queryKeys } from '@/lib/api/queryClient'
import type { HealthResponse } from '@/types/api'

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health')
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
    refetchInterval: 5_000,
  })
}
