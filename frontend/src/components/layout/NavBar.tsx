import { List, LogOut, Map, RotateCcw } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { env } from '@/config/env'
import { logout as logoutRequest } from '@/features/auth/api'
import { cn } from '@/lib/cn'
import { queryClient } from '@/lib/api/queryClient'
import { useAuthStore } from '@/store/auth'
import { useDashboardStore, type DashboardSource } from '@/store/dashboard'

const links = [
  { to: '/', label: 'Карта', icon: Map, end: true },
  { to: '/vehicles', label: 'Таблица', icon: List, end: false },
]

export function NavBar() {
  const clearUser = useAuthStore((state) => state.clearUser)
  const source = useDashboardStore((state) => state.source)
  const setSource = useDashboardStore((state) => state.setSource)
  const resetReplay = useDashboardStore((state) => state.resetReplay)

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

      <div className="topbar__source">
        <label htmlFor="dashboard-source">Источник</label>
        <select id="dashboard-source" onChange={(event) => setSource(event.target.value as DashboardSource)} value={source}>
          <option value="ndtp">NDTP · поток</option>
          <option value="historical">Январь · запись</option>
        </select>
        {source === 'historical' && <button aria-label="Перезапустить январскую запись" className="topbar__restart" onClick={resetReplay} title="Начать январскую запись заново" type="button"><RotateCcw size={17} /></button>}
      </div>

      <button className="topbar__logout" onClick={handleLogout} title="Выйти" type="button">
        <LogOut size={16} />
        <span>Выйти</span>
      </button>
    </header>
  )
}
