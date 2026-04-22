import type { ReactNode } from 'react'

import type { User } from '@/types/user'

import Sidebar, { type LayoutShop } from './Sidebar'
import Topbar from './Topbar'

type AppLayoutProps = {
  title: string
  description?: string
  user: User | null
  shops?: LayoutShop[]
  onLogout?: () => void | Promise<void>
  children: ReactNode
  actions?: ReactNode
}

export default function AppLayout({ 
  title, 
  description, 
  user, 
  shops = [], 
  onLogout, 
  children,
  actions 
}: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_85%_10%,rgba(20,184,166,0.12),transparent_30%),radial-gradient(circle_at_5%_90%,rgba(251,146,60,0.12),transparent_25%),#020617] text-slate-100">
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px]">
        <aside className="hidden w-72 border-r border-slate-800/90 bg-slate-950/70 backdrop-blur lg:block">
          <Sidebar shops={shops} user={user} />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar 
            description={description} 
            onLogout={onLogout} 
            title={title} 
            user={user} 
            actions={actions}
          />
          <div className="border-b border-slate-800/90 bg-slate-950/70 lg:hidden">
            <Sidebar compact shops={shops} user={user} />
          </div>
          <main className="flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
        </div>
      </div>
    </div>
  )
}
