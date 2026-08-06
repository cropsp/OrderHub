import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * One group of the exception-first monitor (WB-TRACK-2).
 *
 * The count comes from the endpoint's full-set `counts`, NOT from the number of
 * rows rendered — a collapsed group must show a truthful number for rows it has
 * not fetched, and the delivered group is fetched lazily and paged.
 *
 * `defaultOpen` is the whole layout argument in one prop: attention and
 * untracked open, in-transit and delivered closed. The manager wants the two
 * parcels that need action, not the eighty that do not.
 */
type TrackingGroupProps = {
  title: string
  count: number
  /** Short clause under the title — what this group means, why it is here. */
  hint?: string
  defaultOpen?: boolean
  /** Fires the first time the group opens, so a group can load lazily. */
  onFirstOpen?: () => void
  tone?: 'attention' | 'neutral'
  children: ReactNode
}

export function TrackingGroup({
  title,
  count,
  hint,
  defaultOpen = false,
  onFirstOpen,
  tone = 'neutral',
  children,
}: TrackingGroupProps) {
  const [open, setOpen] = useState(defaultOpen)
  const [hasOpened, setHasOpened] = useState(defaultOpen)

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && !hasOpened) {
      setHasOpened(true)
      onFirstOpen?.()
    }
  }

  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <section
      className={cn(
        'rounded-xl border bg-zinc-900/40 backdrop-blur-sm',
        tone === 'attention'
          ? 'border-orange-900/50 bg-orange-950/10'
          : 'border-zinc-800/60',
      )}
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <Chevron className="h-4 w-4 shrink-0 text-zinc-500" aria-hidden />
        <span
          className={cn(
            'text-sm font-semibold',
            tone === 'attention' ? 'text-orange-200' : 'text-zinc-200',
          )}
        >
          {title}
        </span>
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums',
            tone === 'attention'
              ? 'bg-orange-950/60 text-orange-300'
              : 'bg-zinc-800 text-zinc-300',
          )}
        >
          {count}
        </span>
        {hint && (
          <span className="truncate text-xs text-zinc-500">{hint}</span>
        )}
      </button>

      {open && <div className="border-t border-zinc-800/60">{children}</div>}
    </section>
  )
}
