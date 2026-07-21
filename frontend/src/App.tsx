import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { RequireAuth, RequireRole } from '@/components/auth/RouteGuards'
import LoginPage from '@/pages/LoginPage'
import ShopOrdersPage from '@/pages/ShopOrdersPage'
import ArchivePage from '@/pages/ArchivePage'
import ImportsPage from '@/pages/ImportsPage'
import { UserRole } from '@/types/user'

const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const OrdersPage = lazy(() => import('@/pages/OrdersPage'))
const CustomersPage = lazy(() => import('@/pages/CustomersPage'))
const ShopsPage = lazy(() => import('@/pages/ShopsPage'))
const UsersPage = lazy(() => import('@/pages/UsersPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const OrderDetailPage = lazy(() => import('@/pages/OrderDetailPage'))
const CreateOrderPage = lazy(() => import('@/pages/CreateOrderPage'))
const ProductsPage = lazy(() => import('@/pages/ProductsPage'))
const ProductDetailPage = lazy(() => import('@/pages/ProductDetailPage'))
const PackagingPage = lazy(() => import('@/pages/PackagingPage'))
const MaterialsPage = lazy(() => import('@/pages/MaterialsPage'))
const MaterialDetailPage = lazy(() => import('@/pages/MaterialDetailPage'))
const OverheadMaterialsPage = lazy(() => import('@/pages/OverheadMaterialsPage'))
const OverheadMaterialDetailPage = lazy(
  () => import('@/pages/OverheadMaterialDetailPage'),
)
const ShopFinancePage = lazy(() => import('@/pages/ShopFinancePage'))
const SettlementPage = lazy(() => import('@/pages/SettlementPage'))
const WesternBidPage = lazy(() => import('@/pages/WesternBidPage'))

function RouteLoadingFallback() {
  return (
    <div className="flex min-h-[45vh] items-center justify-center rounded-xl border border-zinc-800/60 bg-zinc-900/30">
      <p className="text-sm text-zinc-400">Loading page...</p>
    </div>
  )
}

import { Toaster } from '@/components/ui/Toast'

function App() {
  return (
    <>
      <Toaster />
      <Routes>
      <Route element={<LoginPage />} path="/login" />

      <Route element={<RequireAuth />}>
        <Route
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <DashboardPage />
            </Suspense>
          }
          path="/dashboard"
        />

        <Route
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <OrdersPage />
            </Suspense>
          }
          path="/orders"
        />
        <Route
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <CreateOrderPage />
            </Suspense>
          }
          path="/orders/new"
        />
        <Route
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <OrderDetailPage />
            </Suspense>
          }
          path="/orders/:id"
        />
        <Route
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <CustomersPage />
            </Suspense>
          }
          path="/customers"
        />
        <Route element={<ShopOrdersPage />} path="/shops/:shopId/orders" />

        <Route element={<RequireRole allowedRoles={[UserRole.OWNER, UserRole.MANAGER]} />}>
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <ShopFinancePage />
              </Suspense>
            }
            path="/shops/:shopId/finance"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <SettlementPage />
              </Suspense>
            }
            path="/shops/:shopId/finance/settlement"
          />
        </Route>
        <Route
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <SettingsPage />
            </Suspense>
          }
          path="/settings"
        />
        <Route
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <ProductDetailPage />
            </Suspense>
          }
          path="/products/:id"
        />

        <Route element={<RequireRole allowedRoles={[UserRole.OWNER, UserRole.MANAGER]} />}>
          <Route element={<ImportsPage />} path="/imports" />
          <Route element={<ArchivePage />} path="/archive" />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <ProductsPage />
              </Suspense>
            }
            path="/products"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <PackagingPage />
              </Suspense>
            }
            path="/packaging"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <MaterialsPage />
              </Suspense>
            }
            path="/inventory/materials"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <MaterialDetailPage />
              </Suspense>
            }
            path="/inventory/materials/:id"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <OverheadMaterialsPage />
              </Suspense>
            }
            path="/inventory/overhead-materials"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <OverheadMaterialDetailPage />
              </Suspense>
            }
            path="/inventory/overhead-materials/:id"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <WesternBidPage />
              </Suspense>
            }
            path="/westernbid"
          />
        </Route>

        <Route element={<RequireRole allowedRoles={[UserRole.OWNER]} />}>
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <ShopsPage />
              </Suspense>
            }
            path="/shops"
          />
          <Route
            element={
              <Suspense fallback={<RouteLoadingFallback />}>
                <UsersPage />
              </Suspense>
            }
            path="/users"
          />
        </Route>
      </Route>

      <Route element={<Navigate replace to="/dashboard" />} path="*" />
    </Routes>
    </>
  )
}

export default App
