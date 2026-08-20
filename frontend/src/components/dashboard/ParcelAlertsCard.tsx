import { useState } from 'react'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  CircleOff,
  Clock,
  Package,
  PackageSearch,
  TrendingUp,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ParcelAlert } from '@/types/westernbid'

/**
 * Parcel alerts on the dashboard (WB-ALERTS-1).
 *
 * `/westernbid` classifies parcels correctly and nobody opened it for two
 * weeks. This is the same findings, pushed to the page people actually land on.
 *
 * Presentational on purpose — the page owns the query, like every other card in
 * this directory. Nothing here decides what deserves an alert: the kinds, the
 * thresholds and the Ukrainian reason text are all produced server-side during
 * the tracking poll, and this component only renders them. A second definition
 * of "needs attention" living in a component is exactly what
 * `wb_tracking_service` exists to prevent.
 */

type ParcelAlertsCardProps = {
  alerts: ParcelAlert[]
  /** When the alert set was last reconciled; null = the poll has never run. */
  syncedAt: string | null
  isLoading: boolean
  /** The alert whose dismiss is in flight, so only its button spins. */
  dismissingId: string | null
  onDismiss: (alertId: string) => void
}

type KindStyle = {
  label: string
  icon: LucideIcon
  badge: string
  dot: string
}

/**
 * Kind → how it reads. Colours reuse the `/westernbid` attention vocabulary
 * (`AttentionChips`) so the two surfaces agree at a glance.
 *
 * An unknown kind falls back rather than crashing: the server owns this
 * vocabulary and may grow it before the frontend ships.
 */
const KIND_STYLES: Record<string, KindStyle> = {
  delivery_problem: {
    label: 'Проблема',
    icon: AlertTriangle,
    badge: 'border-red-900/60 bg-red-950/50 text-red-300',
    dot: 'bg-red-500',
  },
  no_data_stuck: {
    label: 'Без даних',
    icon: CircleOff,
    badge: 'border-amber-900/60 bg-amber-950/40 text-amber-300',
    dot: 'bg-amber-500',
  },
  overdue_long: {
    label: 'Прострочено',
    icon: Clock,
    badge: 'border-orange-900/60 bg-orange-950/40 text-orange-300',
    dot: 'bg-orange-500',
  },
  untracked_aging: {
    label: 'Не відстежується',
    icon: PackageSearch,
    badge: 'border-zinc-700 bg-zinc-800/60 text-zinc-300',
    dot: 'bg-zinc-500',
  },
}

const FALLBACK_STYLE: KindStyle = {
  label: 'Потребує уваги',
  icon: AlertTriangle,
  badge: 'border-zinc-700 bg-zinc-800/60 text-zinc-300',
  dot: 'bg-zinc-500',
}

/**
 * What an operator can act on. The Nova Poshta number when there is one;
 * otherwise every carrier number WesternBid reported.
 *
 * The fallback is the whole point of showing `tracking_numbers` at all:
 * `untracked_aging` alerts have no NP number by definition, and WB-TRACK-2
 * already shipped one version of this screen that told people to "check by
 * hand" while displaying nothing to check with.
 */
function actionableNumbers(alert: ParcelAlert): string[] {
  if (alert.tracking_number) return [alert.tracking_number]
  return alert.tracking_numbers.map((n) => n.TrackingNumber).filter(Boolean)
}

function AlertRow({
  alert,
  isDismissing,
  onDismiss,
}: {
  alert: ParcelAlert
  isDismissing: boolean
  onDismiss: (alertId: string) => void
}) {
  const style = KIND_STYLES[alert.kind] ?? FALLBACK_STYLE
  const Icon = style.icon
  const numbers = actionableNumbers(alert)

  return (
    <div
      data-testid="parcel-alert-row"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-zinc-800/60 px-4 py-3 last:border-b-0"
    >
      <span className={cn('size-1.5 shrink-0 rounded-full', style.dot)} aria-hidden />

      <Badge variant="outline" className={cn('gap-1 shrink-0', style.badge)}>
        <Icon className="h-3 w-3" aria-hidden />
        {style.label}
      </Badge>

      <span className="font-mono text-xs text-zinc-300">
        {numbers.length > 0 ? numbers.join(' · ') : '—'}
      </span>

      <span className="text-sm text-zinc-400">{alert.detail}</span>

      {alert.recipient_name && (
        <span className="truncate text-xs text-zinc-600">
          {alert.recipient_name}
        </span>
      )}

      <span className="ml-auto shrink-0 text-xs tabular-nums text-zinc-500">
        {alert.age_days.toFixed(1)} дн. тому
      </span>

      <Button
        variant="outline"
        size="sm"
        disabled={isDismissing}
        onClick={() => onDismiss(alert.id)}
      >
        Опрацьовано
      </Button>
    </div>
  )
}

export default function ParcelAlertsCard({
  alerts,
  syncedAt,
  isLoading,
  dismissingId,
  onDismiss,
}: ParcelAlertsCardProps) {
  // Open by default when there is something to see. Collapse state is
  // per-visit, like every other collapsible in the app.
  const [open, setOpen] = useState(true)

  if (isLoading) {
    return <Skeleton className="h-16 w-full rounded-3xl bg-zinc-900/60" />
  }

  // A quiet line rather than nothing at all. On a surface built to replace one
  // nobody trusted enough to visit, "all clear" and "the generator is broken"
  // must not look identical — the sync timestamp is what tells them apart.
  if (alerts.length === 0) {
    return (
      <div
        data-testid="parcel-alerts-card"
        className="flex items-center gap-2 px-2 text-xs text-zinc-600"
      >
        <Package className="h-3.5 w-3.5" aria-hidden />
        <span>Посилки: все гаразд</span>
        <span className="text-zinc-700">·</span>
        <span>
          {syncedAt
            ? `синхронізовано ${formatDateTime(syncedAt)}`
            : 'опитування ще не виконувалось'}
        </span>
      </div>
    )
  }

  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <section
      data-testid="parcel-alerts-card"
      className="rounded-3xl border border-orange-900/50 bg-orange-950/10 backdrop-blur-sm"
    >
      <div className="flex items-center gap-3 px-6 py-4">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex flex-1 items-center gap-3 text-left"
        >
          <Chevron className="h-4 w-4 shrink-0 text-orange-400/70" aria-hidden />
          <div className="flex size-8 shrink-0 items-center justify-center rounded-xl border border-orange-500/20 bg-orange-500/10">
            <AlertTriangle className="h-4 w-4 text-orange-500" />
          </div>
          <p className="text-[11px] font-black uppercase tracking-[0.2em] text-orange-400">
            Посилки — потребують уваги
          </p>
          <span className="rounded-full bg-orange-950/60 px-2 py-0.5 text-xs font-semibold tabular-nums text-orange-300">
            {alerts.length}
          </span>
        </button>

        <Link
          to="/westernbid"
          className="flex shrink-0 items-center gap-1 text-[10px] font-black uppercase tracking-widest text-teal-400 transition-colors hover:text-teal-300"
        >
          Усі посилки <TrendingUp size={12} />
        </Link>
      </div>

      {open && (
        <div className="border-t border-orange-900/40">
          {alerts.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              isDismissing={dismissingId === alert.id}
              onDismiss={onDismiss}
            />
          ))}
          <p className="px-4 py-2 text-[11px] text-zinc-600">
            Сповіщення зникає само, коли проблема вирішилась
            {syncedAt ? ` · синхронізовано ${formatDateTime(syncedAt)}` : ''}
          </p>
        </div>
      )}
    </section>
  )
}
