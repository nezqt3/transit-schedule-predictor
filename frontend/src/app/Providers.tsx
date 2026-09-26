import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'

import { AuthBootstrap } from '@/features/auth/AuthBootstrap'
import { queryClient } from '@/lib/api/queryClient'

import { router } from './router'

export function Providers() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthBootstrap>
        <RouterProvider router={router} />
      </AuthBootstrap>
    </QueryClientProvider>
  )
}
