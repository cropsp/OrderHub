import { Navigate, Route, Routes } from 'react-router-dom'

import { RequireAuth, RequireRole } from '@/components/auth/RouteGuards'
import LoginPage from '@/pages/LoginPage'
import DashBoardPage from '@/pages/DashboardPage'
import OrdersPage from '@/pages/OrdersPage'
import FeaturePlaceholderPage from '@/pages/FeaturePlaceholderPage'
import { UserRole } from '@/types/user'

function App() {
  return (
    <Routes>
      <Route element={<LoginPage />} path="/login" />

      <Route element={<RequireAuth />}>
        <Route element={<DashBoardPage />} path="/dashboard" />

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
          <Route
            element={
              <FeaturePlaceholderPage
                description="CSV import flow is planned in Sprint 4."
                title="Imports"
              />
            }
            path="/imports"
          />
          <Route
            element={
              <FeaturePlaceholderPage
                description="Archive list and export UX are planned in Sprint 5."
                title="Archive"
              />
            }
            path="/archive"
          />
        </Route>

        <Route element={<RequireRole allowedRoles={[UserRole.OWNER]} />}>
          <Route
            element={
              <FeaturePlaceholderPage
                description="Shop management UI is planned in Sprint 5."
                title="Shops"
              />
            }
            path="/shops"
          />
          <Route
            element={
              <FeaturePlaceholderPage
                description="User management UI is planned in Sprint 5."
                title="Users"
              />
            }
            path="/users"
          />
        </Route>
      </Route>

      <Route element={<Navigate replace to="/dashboard" />} path="*" />
    </Routes>
  )
}

export default App
