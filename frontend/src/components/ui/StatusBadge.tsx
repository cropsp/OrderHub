import { cn } from "@/lib/utils"

export type OrderStatus =
  | 'new' | 'waiting_info' | 'info_received' | 'design_pending'
  | 'design_ready' | 'in_production' | 'shipped' | 'completed' | 'cancelled'

interface StatusBadgeProps {
  status: OrderStatus | string
  size?: 'sm' | 'md'
  className?: string
}

const statusConfig: Record<string, { label: string; classes: string; dot: string }> = {
  new: { 
    label: 'New', 
    classes: 'bg-blue-500/10 text-blue-400 border-l-2 border-blue-500',
    dot: 'bg-blue-500'
  },
  waiting_info: { 
    label: 'Waiting Info', 
    classes: 'bg-amber-500/10 text-amber-400 border-l-2 border-amber-500',
    dot: 'bg-amber-500'
  },
  info_received: { 
    label: 'Info Received', 
    classes: 'bg-violet-500/10 text-violet-400 border-l-2 border-violet-500',
    dot: 'bg-violet-500'
  },
  design_pending: { 
    label: 'Design Pending', 
    classes: 'bg-pink-500/10 text-pink-400 border-l-2 border-pink-500',
    dot: 'bg-pink-500'
  },
  design_ready: { 
    label: 'Design Ready', 
    classes: 'bg-cyan-500/10 text-cyan-400 border-l-2 border-cyan-500',
    dot: 'bg-cyan-500'
  },
  in_production: { 
    label: 'In Production', 
    classes: 'bg-orange-500/10 text-orange-400 border-l-2 border-orange-500',
    dot: 'bg-orange-500'
  },
  shipped: { 
    label: 'Shipped', 
    classes: 'bg-emerald-500/10 text-emerald-400 border-l-2 border-emerald-500',
    dot: 'bg-emerald-500'
  },
  completed: { 
    label: 'Completed', 
    classes: 'bg-green-500/10 text-green-400 border-l-2 border-green-500',
    dot: 'bg-green-500'
  },
  cancelled: { 
    label: 'Cancelled', 
    classes: 'bg-zinc-500/10 text-zinc-400 border-l-2 border-zinc-500',
    dot: 'bg-zinc-500'
  }
}

export function StatusBadge({ status, size = 'md', className }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.new
  
  return (
    <div className={cn(
      "inline-flex items-center gap-1.5 font-medium uppercase tracking-wide transition-colors",
      size === 'sm' ? "text-[10px] px-2 py-0.5" : "text-xs px-2.5 py-1",
      config.classes,
      className
    )}>
      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", config.dot)} />
      {config.label}
    </div>
  )
}
