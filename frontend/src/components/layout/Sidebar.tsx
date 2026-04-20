import { Archive, FileSpreadsheet, LayoutDashboard, Package, Settings, Shield, Store, Users } from 'lucide-react'
import type { ComponentType } from 'react'
import { NavLink } from 'react-router-dom'

import type { User, UserRoleType } from '@/types/user'
import { UserRole } from '@/types/user'
import { cn } from '@/lib/utils'

export type LayoutShop = {
  id: string
  name: string
  to: string
}

type SidebarProps = {
  user: User | null
  shops?: LayoutShop[]
  compact?: boolean
}

type NavItem = {
  key: string
  label: string
  to: string
  icon: ComponentType<{ className?: string }>
  roles: UserRoleType[]
}

const navItems: NavItem[] = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    to: '/dashboard',
    icon: LayoutDashboard,
    roles: [UserRole.OWNER, UserRole.MANAGER, UserRole.DESIGNER],
  },
  {
    key: 'orders',
    label: 'Orders',
    to: '/orders',
    icon: Package,
    roles: [UserRole.OWNER, UserRole.MANAGER, UserRole.DESIGNER],
  },
  {
    key: 'imports',
    label: 'Imports',
    to: '/imports',
    icon: FileSpreadsheet,
    roles: [UserRole.OWNER, UserRole.MANAGER],
  },
  {
    key: 'archive',
    label: 'Archive',
    to: '/archive',
    icon: Archive,
    roles: [UserRole.OWNER, UserRole.MANAGER],
  },
  {
    key: 'shops',
    label: 'Shops',
    to: '/shops',
    icon: Store,
    roles: [UserRole.OWNER],
  },
  {
    key: 'users',
    label: 'Users',
    to: '/users',
    icon: Users,
    roles: [UserRole.OWNER],
  },
  {
    key: 'settings',
    label: 'Settings',
    to: '/settings',
    icon: Settings,
    roles: [UserRole.OWNER, UserRole.MANAGER, UserRole.DESIGNER],
  },
]

function roleLabel(role: UserRoleType | undefined): string {
  if (role === UserRole.OWNER) return 'Owner'
  if (role === UserRole.MANAGER) return 'Manager'
  if (role === UserRole.DESIGNER) return 'Designer'
  return 'Guest'
}

function isAllowed(item: NavItem, role: UserRoleType | undefined): boolean {
  if (!role) return item.to === '/dashboard'
  return item.roles.includes(role)
}

function SidebarLink({ item }: { item: NavItem }) {
  const Icon = item.icon

  return (
    <NavLink
      className={({ isActive }) =>
        cn(
          'group flex items-center gap-2.5 rounded-lg border px-3 py-2 text-sm transition',
          isActive
            ? 'border-teal-400/40 bg-teal-400/15 text-teal-100'
            : 'border-transparent text-slate-300 hover:border-slate-700 hover:bg-slate-800/70 hover:text-slate-100'
        )
      }
      to={item.to}
    >
      <Icon className="size-4 shrink-0" />
      <span>{item.label}</span>
    </NavLink>
  )
}

export default function Sidebar({ user, shops = [], compact = false }: SidebarProps) {
  const role = user?.role
  const allowedItems = navItems.filter((item) => isAllowed(item, role))

  if (compact) {
    return (
      <nav className="flex items-center gap-2 overflow-x-auto px-4 py-3">
        {allowedItems.map((item) => (
          <NavLink
            className={({ isActive }) =>
              cn(
                'shrink-0 rounded-md border px-2.5 py-1.5 text-xs transition',
                isActive
                  ? 'border-teal-400/40 bg-teal-400/15 text-teal-100'
                  : 'border-slate-700 bg-slate-900/70 text-slate-300 hover:text-slate-100'
              )
            }
            key={item.key}
            to={item.to}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    )
  }

  return (
    <aside className="flex h-full w-full flex-col">
      <div className="border-b border-slate-800/90 px-5 py-6">
        <div className="flex items-center gap-2 text-teal-300">
          <Shield className="size-5" />
          <span className="text-sm font-semibold tracking-wide uppercase">OrderHub CRM</span>
        </div>
        <p className="mt-2 text-xs text-slate-400">Role-aware workspace shell for Sprint 3.</p>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-5">
        <div className="space-y-2">
          {allowedItems.map((item) => (
            <SidebarLink item={item} key={item.key} />
          ))}
        </div>

        {shops.length > 0 ? (
          <div className="space-y-2">
            <p className="px-1 text-[11px] font-semibold tracking-[0.16em] uppercase text-slate-500">Shops</p>
            {shops.map((shop) => (
              <NavLink
                className={({ isActive }) =>
                  cn(
                    'block rounded-md px-3 py-2 text-sm transition',
                    isActive ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                  )
                }
                key={shop.id}
                to={shop.to}
              >
                {shop.name}
              </NavLink>
            ))}
          </div>
        ) : null}
      </div>

      <div className="border-t border-slate-800/90 px-5 py-4">
        <p className="text-sm font-medium text-slate-100">{user?.full_name ?? 'Guest user'}</p>
        <p className="text-xs text-slate-400">{roleLabel(role)}</p>
      </div>
    </aside>
  )
}
