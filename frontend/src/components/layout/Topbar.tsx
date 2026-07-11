import { LogOut, Layout } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { getInitials, getAvatarColor } from '@/utils/avatar'
import { cn } from '@/lib/utils'
import type { User, UserRoleType } from '@/types/user'
import { UserRole } from '@/types/user'
import type { ReactNode } from 'react'

type TopbarProps = {
  title: string
  description?: string
  user: User | null
  onLogout?: () => void | Promise<void>
  actions?: ReactNode
}

function roleLabel(role: UserRoleType | undefined): string {
  if (role === UserRole.OWNER) return 'Owner'
  if (role === UserRole.MANAGER) return 'Manager'
  if (role === UserRole.DESIGNER) return 'Designer'
  return 'Guest'
}

function roleClass(role: UserRoleType | undefined): string {
  if (role === UserRole.OWNER) return 'border-teal-500/20 bg-teal-500/5 text-teal-400'
  if (role === UserRole.MANAGER) return 'border-zinc-700 bg-zinc-800 text-zinc-300'
  if (role === UserRole.DESIGNER) return 'border-zinc-700 bg-zinc-800 text-zinc-300'
  return 'border-zinc-800 bg-zinc-900 text-zinc-400'
}

export default function Topbar({ title, description, user, onLogout, actions }: TopbarProps) {
  const initials = getInitials(user?.full_name ?? 'Guest');
  const avatarColor = getAvatarColor(user?.full_name ?? '');

  return (
    <header className="border-b border-zinc-800 bg-zinc-950/50 px-4 py-6 backdrop-blur-md md:px-10">
      <div className="flex items-center justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
             <Layout className="size-3.5 text-zinc-400" />
             <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">OrderHub Console</span>
          </div>
          <h1 className="truncate text-2xl font-bold text-zinc-50 tracking-tight">{title}</h1>
          {description ? <p className="mt-1 truncate text-xs text-zinc-400 font-medium">{description}</p> : null}
        </div>

        <div className="flex items-center gap-6">
          {actions && <div className="hidden items-center gap-3 lg:flex">{actions}</div>}

          <div className="flex items-center gap-4 pl-6 border-l border-zinc-800">
            <div className="flex flex-col items-end mr-1">
              <span className="text-sm font-bold text-zinc-200">{user?.full_name ?? 'Guest'}</span>
              <Badge className={cn("mt-1 text-[9px] h-4 uppercase tracking-wider font-bold px-1.5", roleClass(user?.role))} variant="outline">
                {roleLabel(user?.role)}
              </Badge>
            </div>
            
            <div className={cn("size-10 rounded-xl flex items-center justify-center text-xs font-bold text-white shadow-lg", avatarColor)}>
              {initials}
            </div>

            <Button
              disabled={!onLogout}
              onClick={() => onLogout?.()}
              size="icon"
              variant="ghost"
              className="size-10 rounded-xl hover:bg-red-500/10 hover:text-red-400 text-zinc-400"
            >
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}
