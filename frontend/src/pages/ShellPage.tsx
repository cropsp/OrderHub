import type { ReactNode } from 'react'

import AppLayout from '@/components/layout/AppLayout'
import type { LayoutShop } from '@/components/layout/Sidebar'
import { useAuth } from '@/hooks/useAuth'
import { useShops } from '@/hooks/useShops'

type ShellPageProps = {
  title: string
  description?: string
  children: ReactNode
  actions?: ReactNode
}

function SessionLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="glass rounded-xl p-8 animate-fade-in text-center">
        <p className="text-sm text-slate-300">Preparing workspace...</p>
      </div>
    </div>
  )
}

function toLayoutShops(items: { id: string; name: string }[]): LayoutShop[] {
  const baseShop: LayoutShop = {
    id: 'all',
    name: 'All Orders',
    to: '/orders',
  }

  return [
    baseShop,
    ...items.map((shop) => ({
      id: shop.id,
      name: shop.name,
      to: `/shops/${shop.id}/orders`,
    })),
  ]
}

export default function ShellPage({ title, description, children, actions }: ShellPageProps) {
  const { isLoading, logout, user } = useAuth()
  const shopsQuery = useShops({ enabled: Boolean(user) })

  if (isLoading) {
    return <SessionLoading />
  }

  const layoutShops = toLayoutShops(shopsQuery.data ?? [])

  return (
    <AppLayout
      description={description}
      onLogout={user ? logout : undefined}
      shops={layoutShops}
      title={title}
      user={user}
      actions={actions}
    >
      {children}
    </AppLayout>
  )
}
