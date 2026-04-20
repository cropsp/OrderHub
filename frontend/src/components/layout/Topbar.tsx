import { LogOut, Sparkles } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { User, UserRoleType } from '@/types/user'
import { UserRole } from '@/types/user'

type TopbarProps = {
  title: string
  description?: string
  user: User | null
  onLogout?: () => void | Promise<void>
}

function roleLabel(role: UserRoleType | undefined): string {
  if (role === UserRole.OWNER) return 'Owner'
  if (role === UserRole.MANAGER) return 'Manager'
  if (role === UserRole.DESIGNER) return 'Designer'
  return 'Guest'
}

function roleClass(role: UserRoleType | undefined): string {
  if (role === UserRole.OWNER) return 'border-amber-400/40 bg-amber-300/15 text-amber-200'
  if (role === UserRole.MANAGER) return 'border-sky-400/40 bg-sky-300/15 text-sky-200'
  if (role === UserRole.DESIGNER) return 'border-teal-400/40 bg-teal-300/15 text-teal-200'
  return 'border-slate-500/40 bg-slate-300/10 text-slate-300'
}

export default function Topbar({ title, description, user, onLogout }: TopbarProps) {
  return (
    <header className="border-b border-slate-800/90 bg-slate-950/80 px-4 py-4 backdrop-blur md:px-6">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] uppercase text-slate-400">
            <Sparkles className="size-3.5 text-teal-300" />
            Sprint 3 shell
          </p>
          <h1 className="mt-1 truncate text-xl font-semibold text-slate-100">{title}</h1>
          {description ? <p className="mt-1 truncate text-sm text-slate-400">{description}</p> : null}
        </div>

        <div className="flex items-center gap-2.5">
          <Badge className={roleClass(user?.role)} variant="outline">
            {roleLabel(user?.role)}
          </Badge>
          <span className="hidden text-sm text-slate-300 sm:inline">{user?.full_name ?? 'Guest'}</span>
          <Button
            disabled={!onLogout}
            onClick={() => {
              if (onLogout) {
                void onLogout()
              }
            }}
            size="sm"
            variant="outline"
          >
            <LogOut className="size-4" />
            Logout
          </Button>
        </div>
      </div>
    </header>
  )
}
