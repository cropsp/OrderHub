import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: string | number
  icon: LucideIcon
  trend?: {
    value: number
    label: string
  }
  accentColor?: string
  className?: string
}

export function MetricCard({
  label,
  value,
  icon: Icon,
  trend,
  accentColor = "text-zinc-400",
  className
}: MetricCardProps) {
  const isPositive = trend && trend.value > 0
  const isNegative = trend && trend.value < 0
  const isNeutral = trend && trend.value === 0

  return (
    <div className={cn(
      "bg-zinc-900/80 backdrop-blur-sm border border-zinc-800 rounded-xl p-5 flex flex-col gap-3 transition-all hover:-tranzinc-y-px hover:shadow-lg hover:shadow-black/20",
      className
    )}>
      <div className="flex items-center gap-2">
        <Icon className={cn("size-4", accentColor)} />
        <span className="text-zinc-500 text-xs font-bold uppercase tracking-wide">{label}</span>
      </div>
      
      <div className="text-3xl font-bold text-zinc-100 tracking-tight">
        {value}
      </div>

      {trend && (
        <div className={cn(
          "flex items-center gap-1.5 text-xs font-medium",
          isPositive && "text-green-400",
          isNegative && "text-red-400",
          isNeutral && "text-zinc-500"
        )}>
          <span>
            {isPositive && "↑"}
            {isNegative && "↓"}
            {isNeutral && "→"}
          </span>
          <span>{Math.abs(trend.value)}%</span>
          <span className="text-zinc-500 font-normal">{trend.label}</span>
        </div>
      )}
    </div>
  )
}
