import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuthStore } from '@/store/auth'

export function RequireAuth() {
  const user = useAuthStore((state) => state.user)
  const isReady = useAuthStore((state) => state.isReady)
  const location = useLocation()

  if (!isReady) return <div className="auth-loading">Восстанавливаем сессию…</div>
  if (!user) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />
  }
  return <Outlet />
}
