import type { ReactNode } from 'react'

import { formatDateTime, formatDays } from '@/lib/format'
import { useParcelEvents } from '@/hooks/useWesternBid'
import { Skeleton } from '@/components/ui/skeleton'
import type { TrackedParcel } from '@/types/westernbid'

/**
 * The expanded body of a parcel row (WB-TRACK-2, rule 4).
 *
 * Three blocks, in the order they answer questions:
 *
 *  1. Nova Poshta's transition log — the only thing that answers "how long has
 *     this actually been sitting". `wb_tracking_event` records one row per
 *     observed CHANGE, so a parcel polled daily without moving has exactly one
 *     row; that is the signal, not a gap, and the copy says so.
 *  2. Current NP detail — the dates the chips summarise.
 *  3. WesternBid's own leg — `Status` / `PaymentStatus`, demoted here from the
 *     old page's headline. They describe only WB's leg to the Lviv warehouse
 *     ("Parcel created" on a parcel that has been moving for a week), so they
 *     are labelled as such rather than presented as delivery status.
 *
 * History is fetched here, per parcel, only once a row is opened — never
 * inlined on the list payload.
 */

const EM_DASH = '—'

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="text-sm text-zinc-300">{value || EM_DASH}</dd>
    </div>
  )
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
        {title}
      </h4>
      {children}
    </div>
  )
}

function History({ parcel }: { parcel: TrackedParcel }) {
  const { data: events, isLoading } = useParcelEvents(parcel.tracking_number, true)

  if (!parcel.tracking_number) {
    return (
      <p className="text-sm text-zinc-500">
        No Nova Poshta number, so there is nothing to track — check this parcel
        with {parcel.carrier ?? 'the carrier'} directly.
      </p>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-64 bg-zinc-800" />
        <Skeleton className="h-4 w-48 bg-zinc-800" />
      </div>
    )
  }

  if (!events || events.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        No transitions recorded yet — this parcel has not changed status since
        tracking began.
      </p>
    )
  }

  return (
    <ol className="space-y-2">
      {events.map((event, i) => (
        <li key={`${event.observed_at}-${i}`} className="flex gap-3 text-sm">
          <span className="w-32 shrink-0 tabular-nums text-zinc-500">
            {formatDateTime(event.np_tracking_update_date ?? event.observed_at)}
          </span>
          {/* Nova Poshta's own Ukrainian wording, verbatim. */}
          <span className="text-zinc-300">{event.status_text || EM_DASH}</span>
          {event.status_code && (
            <span className="shrink-0 text-xs text-zinc-600">
              code {event.status_code}
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}

export function ParcelRowDetail({ parcel }: { parcel: TrackedParcel }) {
  return (
    <div className="grid gap-6 border-t border-zinc-800/60 bg-zinc-950/40 px-4 py-4 md:grid-cols-2">
      <Block title="Nova Poshta history">
        <History parcel={parcel} />
        {parcel.state === 'no_data' && (
          <p className="text-sm text-amber-300/80">
            Nova Poshta stopped returning data on{' '}
            {formatDateTime(parcel.no_data_since)}.
            {parcel.status_text
              ? ` Last status seen: ${parcel.status_text}`
              : ' No status was ever recorded for this number.'}
          </p>
        )}
      </Block>

      <div className="space-y-6">
        <Block title="Delivery detail">
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Destination" value={parcel.city_recipient} />
            <Field label="Status code" value={parcel.status_code} />
            <Field
              label="Scheduled"
              value={
                parcel.scheduled_delivery_at
                  ? formatDateTime(parcel.scheduled_delivery_at)
                  : null
              }
            />
            <Field
              label="Last scan"
              value={
                parcel.last_movement_at
                  ? `${formatDateTime(parcel.last_movement_at)} (${formatDays(
                      parcel.days_since_movement,
                    )} ago)`
                  : null
              }
            />
            {parcel.delivered_at && (
              <Field
                label="Delivered"
                value={formatDateTime(parcel.delivered_at)}
              />
            )}
          </dl>
        </Block>

        <Block title="WesternBid leg">
          <dl className="grid grid-cols-2 gap-3">
            <Field label="WB status" value={parcel.wb_status} />
            <Field label="Payment" value={parcel.payment_status} />
          </dl>
          <p className="text-xs text-zinc-600">
            WesternBid reports only its own leg to the Lviv warehouse — it does
            not know whether the parcel was delivered.
          </p>
        </Block>

        {parcel.tracking_numbers.length > 0 && (
          <Block title="Carrier numbers">
            <ul className="space-y-1">
              {parcel.tracking_numbers.map((n) => (
                <li key={n.TrackingNumber} className="text-sm text-zinc-300">
                  <span className="text-zinc-500">{n.Identifier ?? EM_DASH}</span>{' '}
                  <span className="font-mono text-xs">{n.TrackingNumber}</span>
                </li>
              ))}
            </ul>
          </Block>
        )}
      </div>
    </div>
  )
}
