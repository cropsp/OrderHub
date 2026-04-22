import { Archive, FileSpreadsheet, LayoutDashboard, Package, Settings, Shield, Store, Users } from 'lucide-react'
import type { ComponentType } from 'react'
import { NavLink } from 'react-router-dom'

import type { User, UserRoleType } from '@/types/user'
import { UserRole } from '@/types/user'
import { cn } from '@/lib/utils'
import { getShopTheme } from '@/utils/shopTheme'

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
    key: 'customers',
    label: 'Customers',
    to: '/customers',
    icon: Users,
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
          'group flex items-center gap-2.5 px-3 py-2 text-sm transition-colors duration-150',
          isActive
            ? 'bg-zinc-800 border-l-2 border-teal-400 text-zinc-100'
            : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100'
        )
      }
      to={item.to}
    >
      <Icon className={cn("size-4 shrink-0 transition-colors", "group-hover:text-zinc-100")} />
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
                  : 'border-zinc-700 bg-zinc-900/70 text-zinc-300 hover:text-zinc-100'
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
    <aside className="flex h-full w-full flex-col bg-zinc-950">
      <div className="px-5 py-6">
        <div className="flex items-center gap-2 text-teal-400">
          <Shield className="size-5" />
          <span className="text-sm font-bold tracking-tight uppercase">OrderHub</span>
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto py-2">
        <div className="flex flex-col">
          {allowedItems.map((item) => (
            <SidebarLink item={item} key={item.key} />
          ))}
        </div>

        {shops.length > 0 ? (
          <div className="space-y-1">
            <div className="px-5 py-2">
               <div className="h-px bg-zinc-800 mb-4" />
               <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-[0.1em]">SHOPS</p>
            </div>
            <div className="flex flex-col">
              {shops.map((shop) => {
                const theme = getShopTheme(shop.name);
                return (
                  <NavLink
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2.5 px-5 py-2 text-sm transition-colors duration-150',
                        isActive 
                          ? 'bg-zinc-800 border-l-2 border-teal-400 text-zinc-100' 
                          : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100'
                      )
                    }
                    key={shop.id}
                    to={shop.to}
                  >
                    <span className={cn("size-1.5 rounded-full", theme.dot)} />
                    {shop.name}
                  </NavLink>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>

      <div className="mt-auto border-t border-zinc-800 px-5 py-4">
        <p className="text-sm font-medium text-zinc-100">{user?.full_name ?? 'Guest user'}</p>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wide font-medium">{roleLabel(role)}</p>
      </div>
    </aside>
  )
}
