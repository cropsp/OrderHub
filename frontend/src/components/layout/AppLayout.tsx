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
    <div className="min-h-screen bg-zinc-950 text-zinc-100 overflow-x-hidden selection:bg-teal-500/30">
      {/* Background Orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] right-[-10%] size-[500px] rounded-full bg-teal-500/10 blur-[120px] animate-pulse" />
        <div className="absolute bottom-[-10%] left-[-10%] size-[500px] rounded-full bg-indigo-500/5 blur-[120px]" />
      </div>

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-[1600px]">
        <aside className="hidden w-72 border-r border-zinc-800 bg-zinc-950 lg:block shrink-0">
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
          <div className="border-b border-zinc-800 bg-zinc-950 lg:hidden">
            <Sidebar compact shops={shops} user={user} />
          </div>
          <main className="flex-1 p-4 sm:p-6 lg:p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
