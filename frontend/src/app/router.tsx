import { createBrowserRouter, Navigate } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { RequireAuth } from '@/features/auth/RequireAuth'
import { DashboardPage } from '@/pages/DashboardPage'
import { LoginPage } from '@/pages/LoginPage'
import { VehiclesPage } from '@/pages/VehiclesPage'
import { ReplayPage } from '@/pages/ReplayPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        path: '/',
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: 'vehicles', element: <VehiclesPage /> },
          { path: 'replay', element: <ReplayPage /> },
          { path: '*', element: <Navigate replace to="/" /> },
        ],
      },
    ],
  },
])
