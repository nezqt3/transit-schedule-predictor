import { List, LogOut, Map, Play } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { env } from '@/config/env'
import { logout as logoutRequest } from '@/features/auth/api'
import { BackendStatus } from '@/features/health/BackendStatus'
import { cn } from '@/lib/cn'
import { queryClient } from '@/lib/api/queryClient'
import { useAuthStore } from '@/store/auth'

const links = [
  { to: '/', label: 'Карта', icon: Map, end: true },
  { to: '/vehicles', label: 'Таблица', icon: List, end: false },
  { to: '/replay', label: 'Январь', icon: Play, end: false },
]

export function NavBar() {
  const clearUser = useAuthStore((state) => state.clearUser)

  async function handleLogout() {
    try {
      await logoutRequest()
    } finally {
      clearUser()
    }
    queryClient.clear()
  }

  return (
    <header className="topbar">
      <div className="topbar__brand">
        {env.appName}
      </div>

      <nav className="topbar__nav">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            className={({ isActive }) => cn('topbar__link', isActive && 'topbar__link--active')}
            end={end}
            key={to}
            to={to}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <BackendStatus />
      <span className="topbar__date">
        {new Date().toLocaleDateString('ru-RU', {
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        })}
      </span>
      <button className="topbar__logout" onClick={handleLogout} title="Выйти" type="button">
        <LogOut size={16} />
        <span>Выйти</span>
      </button>
    </header>
  )
}
