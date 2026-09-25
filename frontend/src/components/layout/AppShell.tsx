import { Outlet } from 'react-router-dom'

import { NavBar } from './NavBar'

export function AppShell() {
  return (
    <div className="shell">
      <NavBar />
      <main className="shell__body">
        <Outlet />
      </main>
    </div>
  )
}
