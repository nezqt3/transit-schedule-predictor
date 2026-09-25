import { QueryClient } from '@tanstack/react-query'

import { ApiError } from './http'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 1_000,
      retry: (failureCount, error) => {
        const status = error instanceof ApiError ? error.status : null
        const retryable = status === null || status >= 500
        return retryable && failureCount < 2
      },
    },
  },
})

export const queryKeys = {
  health: ['health'] as const,
  vehicles: ['vehicles'] as const,
}
