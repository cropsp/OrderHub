import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/store/authStore'
import type { UserRoleType } from '@/types/user'

function GuardLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="glass rounded-xl p-8 animate-fade-in text-center">
        <p className="text-sm text-zinc-300">Checking session...</p>
      </div>
    </div>
  )
}

type RequireRoleProps = {
  allowedRoles: UserRoleType[]
}

export function RequireAuth() {
  const location = useLocation()
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <GuardLoading />
  }

  if (!isAuthenticated) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />
  }

  return <Outlet />
}

export function RequireRole({ allowedRoles }: RequireRoleProps) {
  const user = useAuthStore((state) => state.user)

  if (!user) {
    return <Navigate replace to="/dashboard" />
  }

  if (!allowedRoles.includes(user.role)) {
    return <Navigate replace to="/dashboard" />
  }

  return <Outlet />
}
