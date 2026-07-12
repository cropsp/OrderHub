import { useState } from 'react';
import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import { statusLabel } from '@/lib/order-status';
import type { OrderDetail } from '@/types/order';

interface DetailTimelineProps {
  order: OrderDetail;
}

const COLLAPSED_COUNT = 5;

// Friendly names for the raw field keys logged in "Fields updated: key: old -> new" comments.
const FIELD_LABELS: Record<string, string> = {
  packaging_id: 'Packaging',
  shipping_name: 'Recipient',
  shipping_phone: 'Phone',
  shipping_country: 'Country',
  shipping_city: 'City',
  shipping_street_1: 'Address',
  shipping_street_2: 'Address',
  shipping_zip: 'Postal code',
  shipping_warehouse_ref: 'Nova Poshta branch',
  shipping_city_ref: 'Nova Poshta city',
  tracking_number: 'Tracking number',
  production_cost: 'Production cost',
  shipping_np_cost: 'Shipping cost',
  platform_fee: 'Platform fee',
  total_price: 'Order total',
  notes: 'Notes',
};

/**
 * Turn a raw audit comment into readable text.
 * "Fields updated: packaging_id: None -> 96c4… , shipping_country: UK -> UA"
 *   → "Updated Packaging, Country"  (raw ids/values dropped — the detail panels show current values)
 * Non-field comments (TTN created/deleted, human notes) are already readable → returned as-is.
 */
function humanizeComment(comment: string): string {
  const FIELDS_PREFIX = 'Fields updated: ';
  if (!comment.startsWith(FIELDS_PREFIX)) return comment;

  const body = comment.slice(FIELDS_PREFIX.length);
  const labels: string[] = [];
  // Match each "key:" that starts a change (line start or after ", "); keep only recognised keys.
  const re = /(?:^|,\s*)([a-z_]+):\s/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    const label = FIELD_LABELS[m[1]];
    if (label && !labels.includes(label)) labels.push(label);
  }
  // Nothing recognised → keep the original text rather than hide information.
  return labels.length > 0 ? `Updated ${labels.join(', ')}` : comment;
}

export function DetailTimeline({ order }: DetailTimelineProps) {
  const [showAll, setShowAll] = useState(false);

  // Backend serves status_history oldest-first; show newest-first so the current state reads on top.
  const events = [...(order.status_history || [])].reverse();
  const visible = showAll ? events : events.slice(0, COLLAPSED_COUNT);

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-zinc-100 mb-4 px-1">
        Timeline
      </h3>

      <div className="relative pl-3 space-y-6 before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[1px] before:bg-zinc-800">
        {events.length > 0 ? (
          visible.map((entry, idx) => {
            const isCurrent = idx === 0;
            // Rows where the status didn't change are field-edit / audit rows, not transitions.
            const isFieldUpdate = entry.from_status === entry.to_status;
            const headline = isFieldUpdate
              ? humanizeComment(entry.comment || 'Details updated')
              : statusLabel(entry.to_status);
            // For real transitions, surface any human/TTN note; field-updates already fold it into headline.
            const note = !isFieldUpdate && entry.comment ? humanizeComment(entry.comment) : null;

            return (
              <div key={entry.id || idx} className="relative flex flex-col gap-1.5">
                <div className={cn(
                  "absolute -left-[3px] top-1.5 size-1.5 rounded-full ring-4 ring-zinc-900 shadow-sm",
                  isCurrent ? "bg-teal-500 shadow-teal-500/20" : isFieldUpdate ? "bg-zinc-800" : "bg-zinc-700"
                )} />

                <div className="flex flex-col pl-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className={cn(
                      "text-sm min-w-0 truncate",
                      isCurrent ? "font-semibold text-zinc-100" : isFieldUpdate ? "font-normal text-zinc-400" : "font-semibold text-zinc-300"
                    )}>
                      {headline}
                    </span>
                    <span className="text-[11px] font-medium text-zinc-400 shrink-0">
                      {formatDateTime(entry.changed_at)}
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    {entry.changed_by_name || 'System'}
                  </p>
                </div>

                {note && (
                  <div className="mt-1 ml-4 p-3 rounded bg-zinc-950/40 border border-zinc-800/50">
                    <p className="text-sm text-zinc-400 leading-relaxed">
                      {note}
                    </p>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <p className="text-sm text-zinc-400 italic px-4 text-center">No history recorded</p>
        )}
      </div>

      {events.length > COLLAPSED_COUNT && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-5 ml-4 text-[11px] font-semibold uppercase tracking-wide text-teal-400 hover:text-teal-300 transition-colors"
        >
          {showAll ? 'Show less' : `Show all (${events.length})`}
        </button>
      )}
    </div>
  );
}
