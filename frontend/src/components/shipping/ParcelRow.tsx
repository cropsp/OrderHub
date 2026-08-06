import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/lib/utils'
import { formatDateTime, formatDays } from '@/lib/format'
import type { TrackedParcel } from '@/types/westernbid'

import { AttentionChips } from './AttentionChips'
import { ParcelRowDetail } from './ParcelRowDetail'

/**
 * One parcel in the monitor (WB-TRACK-2).
 *
 * Untracked rows are the reason this is a row component rather than a table
 * cell map: they have no Nova Poshta number, no city and no status, so the
 * columns a NovaPost row fills are exactly the ones they cannot. Instead they
 * show their carrier, whatever number WesternBid did report, and WB's own
 * status — which for the single `Parcel canceled` parcel is the only thing that
 * explains why it never moved.
 */

const EM_DASH = '—'

function OrderCell({ parcel }: { parcel: TrackedParcel }) {
  if (parcel.order_id && parcel.order_number) {
    return (
      <Link
        to={`/orders/${parcel.order_id}`}
        className="text-sm text-zinc-300 underline-offset-2 hover:text-zinc-100 hover:underline"
      >
        {parcel.order_number}
      </Link>
    )
  }
  // Most parcels have no link: `wb_parcel.order_id` is populated only when a
  // label was fetched through OrderHub, and parcel↔order matching is WB-2. Say
  // "not linked", never something that reads as "the order is missing".
  return (
    <span
      className="text-sm text-zinc-600"
      title="Created outside OrderHub — parcel-to-order matching lands in WB-2"
    >
      Not linked
    </span>
  )
}

function CarrierNumbers({ parcel }: { parcel: TrackedParcel }) {
  if (parcel.tracking_numbers.length === 0) {
    return <span className="text-sm text-zinc-600">No carrier number</span>
  }
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {parcel.tracking_numbers.map((n) => (
        <span key={n.TrackingNumber} className="font-mono text-xs text-zinc-300">
          <span className="text-zinc-500">{n.Identifier ?? EM_DASH} </span>
          {n.TrackingNumber}
        </span>
      ))}
    </span>
  )
}

export function ParcelRow({ parcel }: { parcel: TrackedParcel }) {
  const [expanded, setExpanded] = useState(false)
  const Chevron = expanded ? ChevronDown : ChevronRight
  const untracked = parcel.state === 'untracked'

  return (
    <div className="border-b border-zinc-800/60 last:border-b-0">
      <div className="flex items-start gap-3 px-4 py-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={`Toggle history for ${
            parcel.tracking_number ?? parcel.recipient_name ?? 'parcel'
          }`}
          className="mt-0.5 shrink-0 text-zinc-500 hover:text-zinc-300"
        >
          <Chevron className="h-4 w-4" aria-hidden />
        </button>

        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {untracked ? (
              <>
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs font-medium text-zinc-300">
                  {parcel.carrier ?? 'Unknown carrier'}
                </span>
                <CarrierNumbers parcel={parcel} />
              </>
            ) : (
              <span className="font-mono text-sm text-zinc-200">
                {parcel.tracking_number ?? EM_DASH}
              </span>
            )}
            <AttentionChips parcel={parcel} />
          </div>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-zinc-400">
            <span className="text-zinc-300">
              {parcel.recipient_name ?? EM_DASH}
            </span>
            {parcel.recipient_country_code && (
              <span className="text-zinc-500">{parcel.recipient_country_code}</span>
            )}
            {parcel.city_recipient && (
              <span className="text-zinc-500">{parcel.city_recipient}</span>
            )}
            <OrderCell parcel={parcel} />
          </div>

          {/* Nova Poshta's own wording, verbatim — the classification above
              carries the meaning, this names the place. */}
          {parcel.status_text && (
            <p className="truncate text-sm text-zinc-500">{parcel.status_text}</p>
          )}

          {untracked && parcel.wb_status && (
            <p className="text-xs text-zinc-500">
              <span className="text-zinc-600">WesternBid: </span>
              {parcel.wb_status}
            </p>
          )}
        </div>

        <div
          className={cn(
            'hidden shrink-0 text-right text-xs tabular-nums text-zinc-500 sm:block',
          )}
        >
          {parcel.state === 'delivered' ? (
            <span>Delivered {formatDateTime(parcel.delivered_at)}</span>
          ) : parcel.days_since_movement != null ? (
            <span>Scanned {formatDays(parcel.days_since_movement)} ago</span>
          ) : null}
        </div>
      </div>

      {expanded && <ParcelRowDetail parcel={parcel} />}
    </div>
  )
}
