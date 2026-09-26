import { Outlet } from 'react-router-dom'

import { NavBar } from './NavBar'
import { ReplaySession } from '@/features/replay/ReplaySession'
import { useDashboardStore } from '@/store/dashboard'

export function AppShell() {
  const source = useDashboardStore((state) => state.source)
  return (
    <div className="shell">
      {source === 'historical' && <ReplaySession />}
      <NavBar />
      <main className="shell__body">
        <Outlet />
      </main>
    </div>
  )
}
