import { type ReactNode, useEffect } from 'react'

import { getCurrentUser } from '@/features/auth/api'
import { useAuthStore } from '@/store/auth'

export function AuthBootstrap({ children }: { children: ReactNode }) {
  const finishRestore = useAuthStore((state) => state.finishRestore)

  useEffect(() => {
    let active = true
    getCurrentUser()
      .then((user) => {
        if (active) finishRestore(user)
      })
      .catch(() => {
        if (active) finishRestore(null)
      })
    return () => {
      active = false
    }
  }, [finishRestore])

  return children
}
