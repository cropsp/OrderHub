import { Navigate, Route, Routes } from 'react-router-dom'

import { RequireAuth, RequireRole } from '@/components/auth/RouteGuards'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import OrdersPage from '@/pages/OrdersPage'
import ShopsPage from '@/pages/ShopsPage'
import UsersPage from '@/pages/UsersPage'
import ArchivePage from '@/pages/ArchivePage'
import ImportsPage from '@/pages/ImportsPage'
import FeaturePlaceholderPage from '@/pages/FeaturePlaceholderPage'
import { UserRole } from '@/types/user'

function App() {
  return (
    <Routes>
      <Route element={<LoginPage />} path="/login" />

      <Route element={<RequireAuth />}>
        <Route element={<DashboardPage />} path="/dashboard" />

        <Route element={<OrdersPage />} path="/orders" />
        <Route
          element={
            <FeaturePlaceholderPage
              description="Per-shop order views are planned in Sprint 4."
              title="Shop Orders"
            />
          }
          path="/shops/:shopId/orders"
        />
        <Route
          element={
            <FeaturePlaceholderPage
              description="Profile and password controls continue in Sprint 5."
              title="Settings"
            />
          }
          path="/settings"
        />

        <Route element={<RequireRole allowedRoles={[UserRole.OWNER, UserRole.MANAGER]} />}>
          <Route element={<ImportsPage />} path="/imports" />
          <Route element={<ArchivePage />} path="/archive" />
        </Route>

        <Route element={<RequireRole allowedRoles={[UserRole.OWNER]} />}>
          <Route element={<ShopsPage />} path="/shops" />
          <Route element={<UsersPage />} path="/users" />
        </Route>
      </Route>

      <Route element={<Navigate replace to="/dashboard" />} path="*" />
    </Routes>
  )
}

export default App
