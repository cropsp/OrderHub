import { AlertTriangle, CircleOff, Clock, PauseCircle } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { formatDays } from '@/lib/format'
import type { TrackedParcel } from '@/types/westernbid'

/**
 * Why a parcel is in the attention group (WB-TRACK-2).
 *
 * Every chip is a straight read of a field the server already decided —
 * `state`, `is_overdue`, `is_stalled` — and the only arithmetic here is
 * rounding a server-supplied day count for display. There is deliberately no
 * threshold comparison in this file: "stuck" is defined once, in
 * `wb_tracking_service.classify_parcels`, and a second definition living in a
 * component is exactly how the page and the MCP tool would come to disagree.
 *
 * The chips carry the meaning in English; Nova Poshta's own Ukrainian status
 * text is rendered verbatim beside them and never mapped (WB-1's rule — two of
 * the codes we see, 115 and 121, are on no published NP list at all).
 */

export function AttentionChips({ parcel }: { parcel: TrackedParcel }) {
  const chips = []

  if (parcel.state === 'problem') {
    chips.push(
      <Badge
        key="problem"
        variant="destructive"
        className="gap-1 border-red-900/60 bg-red-950/50 text-red-300"
      >
        <AlertTriangle aria-hidden />
        Problem
      </Badge>,
    )
  }

  if (parcel.state === 'no_data') {
    chips.push(
      <Badge
        key="no_data"
        variant="outline"
        className="gap-1 border-amber-900/60 bg-amber-950/40 text-amber-300"
      >
        <CircleOff aria-hidden />
        No NP data
      </Badge>,
    )
  }

  if (parcel.is_overdue) {
    chips.push(
      <Badge
        key="overdue"
        variant="outline"
        className="gap-1 border-orange-900/60 bg-orange-950/40 text-orange-300"
      >
        <Clock aria-hidden />
        {formatDays(parcel.days_overdue)} overdue
      </Badge>,
    )
  }

  if (parcel.is_stalled) {
    chips.push(
      <Badge
        key="stalled"
        variant="outline"
        className="gap-1 border-zinc-700 bg-zinc-800/60 text-zinc-300"
      >
        <PauseCircle aria-hidden />
        No scan for {formatDays(parcel.days_since_movement)}
      </Badge>,
    )
  }

  if (chips.length === 0) return null

  return <div className="flex flex-wrap items-center gap-1.5">{chips}</div>
}
