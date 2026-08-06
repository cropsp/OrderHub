import { useState } from 'react'
import { CheckCircle2, RefreshCw, Truck } from 'lucide-react'

import { formatDateTime } from '@/lib/format'
import {
  useDeliveredParcels,
  useRefreshTracking,
  useTrackingOverview,
} from '@/hooks/useWesternBid'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ParcelRow } from '@/components/shipping/ParcelRow'
import { TrackingGroup } from '@/components/shipping/TrackingGroup'
import type { TrackedParcel } from '@/types/westernbid'

import ShellPage from './ShellPage'

/**
 * WB-TRACK-2 — the parcel monitoring page.
 *
 * Exception-first, not a sortable table. The measured prod distribution is 19%
 * overdue and 81% clean, so the page's job is to surface the dozen parcels that
 * need action and keep the seventy that do not out of the way.
 *
 * Delivery status is the headline; WesternBid's own `Status` / `PaymentStatus`
 * are demoted into the row expansion, because they describe only WB's leg to
 * the Lviv warehouse and still read "Parcel created" on a parcel that has been
 * moving for a week. They are kept, not deleted — they are the only explanation
 * for the one `Parcel canceled` parcel, which has no carrier number and so
 * classifies `untracked`.
 *
 * EVERY attention decision is the server's (`state`, `is_overdue`,
 * `is_stalled`, `days_*`). This file groups and orders by those fields and
 * computes no threshold of its own: "stuck" is defined once, in
 * `wb_tracking_service.classify_parcels`, and shared with the MCP tool.
 */

const DELIVERED_PAGE_SIZE = 25
/** Matches the endpoint's own `le=200`; the 60-day window keeps this unreached. */
const DELIVERED_MAX = 200

/** problem and no_data need a human, so they sort above merely-late parcels. */
const STATE_URGENCY: Record<string, number> = { problem: 0, no_data: 1 }

function byUrgency(a: TrackedParcel, b: TrackedParcel): number {
  const rank = (STATE_URGENCY[a.state] ?? 2) - (STATE_URGENCY[b.state] ?? 2)
  if (rank !== 0) return rank
  const overdue = (b.days_overdue ?? 0) - (a.days_overdue ?? 0)
  if (overdue !== 0) return overdue
  return (b.days_since_movement ?? 0) - (a.days_since_movement ?? 0)
}

/** Needs a human now: the server flagged it, in any of the four ways. */
function needsAttention(p: TrackedParcel): boolean {
  return p.state === 'problem' || p.state === 'no_data' || p.is_overdue || p.is_stalled
}

function RowList({ parcels }: { parcels: TrackedParcel[] }) {
  return (
    <div>
      {parcels.map((p) => (
        <ParcelRow key={p.shipment_id} parcel={p} />
      ))}
    </div>
  )
}

export default function WesternBidPage() {
  const { data, isLoading } = useTrackingOverview()
  const refresh = useRefreshTracking()

  const [deliveredOpen, setDeliveredOpen] = useState(false)
  const [deliveredLimit, setDeliveredLimit] = useState(DELIVERED_PAGE_SIZE)
  const deliveredQuery = useDeliveredParcels(deliveredLimit, 0, deliveredOpen)

  const parcels = data?.parcels ?? []
  const counts = data?.counts

  const attention = parcels.filter(needsAttention).sort(byUrgency)
  const untracked = parcels.filter((p) => p.state === 'untracked' && !needsAttention(p))
  const inTransit = parcels.filter((p) => p.state === 'moving' && !needsAttention(p))

  const delivered = deliveredQuery.data?.parcels ?? []
  // From the full-set `counts`, NOT from the rows fetched — this group is lazy
  // and paged, so its own list length would understate it every time.
  const deliveredCount = counts?.delivered ?? 0

  const actions = (
    <div className="flex items-center gap-3">
      <span className="text-xs text-zinc-500">
        {data
          ? data.polled_at
            ? `Last polled ${formatDateTime(data.polled_at)}`
            : 'Never polled'
          : null}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={refresh.isPending}
        onClick={() => refresh.mutate()}
      >
        <RefreshCw
          className={refresh.isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
          aria-hidden
        />
        Refresh now
      </Button>
    </div>
  )

  return (
    <ShellPage
      title="Parcel Delivery"
      description="Nova Poshta delivery status for parcels sent via WesternBid. Polled daily."
      actions={actions}
    >
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full bg-zinc-800/60" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <TrackingGroup
            title="Needs attention"
            count={attention.length}
            hint="overdue, stalled, failed delivery or no tracking data"
            tone="attention"
            defaultOpen
          >
            {attention.length === 0 ? (
              <div className="flex items-center gap-3 px-4 py-6 text-sm text-zinc-400">
                <CheckCircle2 className="h-5 w-5 text-emerald-500/70" aria-hidden />
                Nothing needs attention — every tracked parcel is moving on time.
              </div>
            ) : (
              <RowList parcels={attention} />
            )}
          </TrackingGroup>

          {untracked.length > 0 && (
            <TrackingGroup
              title="Untracked — check by hand"
              count={untracked.length}
              hint="UPS / USPS: Nova Poshta cannot track these"
              defaultOpen
            >
              <RowList parcels={untracked} />
            </TrackingGroup>
          )}

          <TrackingGroup title="In transit" count={inTransit.length}>
            <RowList parcels={inTransit} />
          </TrackingGroup>

          <TrackingGroup
            title="Delivered"
            count={deliveredCount}
            onFirstOpen={() => setDeliveredOpen(true)}
          >
            {deliveredQuery.isLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-10 w-full bg-zinc-800/60" />
                <Skeleton className="h-10 w-full bg-zinc-800/60" />
              </div>
            ) : (
              <>
                <RowList parcels={delivered} />
                {delivered.length < deliveredCount &&
                  deliveredLimit < DELIVERED_MAX && (
                    <div className="border-t border-zinc-800/60 p-3 text-center">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setDeliveredLimit((l) =>
                            Math.min(l + DELIVERED_PAGE_SIZE, DELIVERED_MAX),
                          )
                        }
                      >
                        Show more
                      </Button>
                    </div>
                  )}
              </>
            )}
          </TrackingGroup>

          {counts && counts.total === 0 && (
            <div className="flex flex-col items-center gap-2 py-16 text-zinc-500">
              <Truck className="h-8 w-8 opacity-50" aria-hidden />
              <p className="text-sm">No WesternBid parcels in the tracking window.</p>
            </div>
          )}
        </div>
      )}
    </ShellPage>
  )
}
