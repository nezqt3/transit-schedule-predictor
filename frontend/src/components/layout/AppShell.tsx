import { Outlet } from 'react-router-dom'

import { NavBar } from './NavBar'

export function AppShell() {
  return (
    <div className="shell">
      <NavBar />
      <main className="shell__body">
        <Outlet />
      </main>
      <footer className="shell__footer">
        <a href="/docs" rel="noreferrer" target="_blank">
          Swagger /docs
        </a>
        <span>NDTP-эмулятор → Backend TCP :9201 → REST /api/v1</span>
      </footer>
    </div>
  )
}
