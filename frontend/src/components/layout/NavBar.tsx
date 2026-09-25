import { Bus, Gauge } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { env } from '@/config/env'
import { BackendStatus } from '@/features/health/BackendStatus'
import { cn } from '@/lib/cn'

const links = [
  { to: '/', label: 'Обзор', icon: Gauge, end: true },
  { to: '/vehicles', label: 'Телеметрия', icon: Bus, end: false },
]

export function NavBar() {
  return (
    <header className="topbar">
      <div className="topbar__brand">
        <span className="topbar__dot" aria-hidden />
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
    </header>
  )
}
