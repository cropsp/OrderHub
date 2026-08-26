import { useState } from 'react'
import { ChevronDown, ChevronRight, ClipboardList, MessageCircleQuestion } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  caseTypeLabel,
  formatOverdueDays,
  isOverdue,
  overdueDays,
} from '@/types/orderCase'
import type { OpenCaseRow, OpenCasesResponse } from '@/types/orderCase'

/**
 * Open order cases on the dashboard (CASE-1).
 *
 * Same shape as `ParcelAlertsCard` beside it — presentational, the page owns the
 * query, collapse is per-visit, an empty state is a quiet line rather than
 * nothing, and it ignores the period selector because it is an attention queue.
 *
 * What it deliberately does NOT copy is that card's access stance. Parcel alerts
 * are global; cases belong to orders, which belong to shops, so `/cases/open`
 * filters by the caller's shop grants server-side. Nothing here re-derives that.
 *
 * The two groups arrive already split and already ordered — "overdue" has one
 * definition and it lives in `order_case_service`, not in this file.
 */

type OrderCasesCardProps = {
  cases: OpenCasesResponse | undefined
  isLoading: boolean
}

function orderLabel(row: OpenCaseRow): string {
  return row.order_number || row.order_external_id || '—'
}

/**
 * The deadline cell. An overdue row leads with the figure in the parcel-alerts
 * block's vocabulary — `Прострочено 12.5 дн.` — and keeps the absolute date
 * after it, because "how late" is what you triage on and "when" is what you
 * quote to a customer.
 */
function dueLabel(row: OpenCaseRow): string {
  if (!row.due_at) return 'без дедлайну'
  const late = overdueDays(row.due_at)
  const absolute = `до ${formatDateTime(row.due_at)}`
  return late === null
    ? absolute
    : `Прострочено ${formatOverdueDays(late)} дн. · ${absolute}`
}

function CaseRow({ row }: { row: OpenCaseRow }) {
  const navigate = useNavigate()
  const late = isOverdue(row.due_at)

  return (
    <div
      data-testid="order-case-row"
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/orders/${row.order_id}`)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          navigate(`/orders/${row.order_id}`)
        }
      }}
      className={cn(
        'flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-2 border-b border-zinc-800/60 px-4 py-3 last:border-b-0',
        'transition-colors hover:bg-zinc-900/40',
        late && 'bg-red-950/10',
      )}
    >
      <span
        className={cn('size-1.5 shrink-0 rounded-full', late ? 'bg-red-500' : 'bg-zinc-600')}
        aria-hidden
      />

      <span className="shrink-0 font-mono text-xs text-zinc-300">{orderLabel(row)}</span>

      <span className="shrink-0 rounded border border-zinc-700 bg-zinc-800/60 px-1.5 py-0.5 text-[11px] text-zinc-300">
        {caseTypeLabel(row.case_type)}
      </span>

      <span
        className={cn(
          'min-w-0 truncate text-sm',
          late ? 'font-semibold text-red-300' : 'text-zinc-200',
        )}
      >
        {row.title}
      </span>

      {row.next_action && (
        <span className="truncate text-xs text-zinc-500">→ {row.next_action}</span>
      )}

      {row.customer_name && (
        <span className="truncate text-xs text-zinc-600">{row.customer_name}</span>
      )}

      <span
        data-testid="order-case-due"
        className={cn(
          'ml-auto shrink-0 text-xs tabular-nums',
          late ? 'text-red-400' : 'text-zinc-500',
        )}
      >
        {dueLabel(row)}
      </span>

      {row.owner_name && (
        <span className="shrink-0 text-xs text-zinc-600">{row.owner_name}</span>
      )}
    </div>
  )
}

function Group({ title, rows }: { title: string; rows: OpenCaseRow[] }) {
  if (rows.length === 0) return null
  return (
    <div>
      <p className="px-4 pb-1 pt-3 text-[10px] font-black uppercase tracking-widest text-zinc-500">
        {title}
      </p>
      {rows.map((row) => (
        <CaseRow key={row.id} row={row} />
      ))}
    </div>
  )
}

export default function OrderCasesCard({ cases, isLoading }: OrderCasesCardProps) {
  const [open, setOpen] = useState(true)

  if (isLoading) {
    return <Skeleton className="h-16 w-full rounded-3xl bg-zinc-900/60" />
  }

  const inProgress = cases?.in_progress ?? []
  const waiting = cases?.waiting ?? []
  const total = inProgress.length + waiting.length

  // A quiet line rather than an empty box — the same discipline the parcel
  // alerts block uses, so "nothing open" and "the block is broken" don't look
  // the same.
  if (total === 0) {
    return (
      <div
        data-testid="order-cases-card"
        className="flex items-center gap-2 px-2 text-xs text-zinc-600"
      >
        <ClipboardList className="h-3.5 w-3.5" aria-hidden />
        <span>Питання по замовленнях: немає відкритих</span>
      </div>
    )
  }

  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <section
      data-testid="order-cases-card"
      className="rounded-3xl border border-zinc-800 bg-zinc-900/30 backdrop-blur-sm"
    >
      <div className="flex items-center gap-3 px-6 py-4">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex flex-1 items-center gap-3 text-left"
        >
          <Chevron className="h-4 w-4 shrink-0 text-zinc-500" aria-hidden />
          <div className="flex size-8 shrink-0 items-center justify-center rounded-xl border border-teal-500/20 bg-teal-500/10">
            <MessageCircleQuestion className="h-4 w-4 text-teal-400" />
          </div>
          <p className="text-[11px] font-black uppercase tracking-[0.2em] text-teal-400">
            Питання по замовленнях
          </p>
          <span
            data-testid="order-cases-count"
            className="rounded-full bg-teal-950/60 px-2 py-0.5 text-xs font-semibold tabular-nums text-teal-300"
          >
            {total}
          </span>
        </button>
      </div>

      {open && (
        <div className="border-t border-zinc-800/60">
          <Group title="В роботі" rows={inProgress} />
          <Group title="Чекаємо" rows={waiting} />
          <p className="px-4 py-2 text-[11px] text-zinc-600">
            Вирішені питання лишаються в картці замовлення
          </p>
        </div>
      )}
    </section>
  )
}
