import { createBrowserRouter, Navigate } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { VehiclesPage } from '@/pages/VehiclesPage'
import { ReplayPage } from '@/pages/ReplayPage'

export const router = createBrowserRouter([
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
])
