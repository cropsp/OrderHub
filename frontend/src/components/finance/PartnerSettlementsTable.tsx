import { Trash2, Plus } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { PartnerSettlement } from '@/api/partnerPayouts'

interface PartnerSettlementsTableProps {
  items: PartnerSettlement[]
  onRecordPayment: (settlement: PartnerSettlement) => void
  onDelete: (settlement: PartnerSettlement) => void
}

const FORMULA_LABELS: Record<PartnerSettlement['formula_type'], string> = {
  revenue_items_minus_fees: 'Items − Fees',
  net_profit_product_only: 'Net Profit (product-only)',
}

function fmt(amount: string, currency: string): string {
  return `${Number(amount).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`
}

function progressBadge(s: PartnerSettlement) {
  const paid = Number(s.paid_amount)
  const due = Number(s.computed_amount)
  if (paid <= 0) {
    return <Badge variant="secondary">Unpaid</Badge>
  }
  if (Math.abs(paid - due) < 0.005) {
    return (
      <Badge className="bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
        Paid in full
      </Badge>
    )
  }
  if (paid > due) {
    return (
      <Badge className="bg-violet-500/15 text-violet-300 border border-violet-500/30">
        Overpaid by {fmt((paid - due).toFixed(2), s.base_currency)}
      </Badge>
    )
  }
  return (
    <Badge className="bg-amber-500/15 text-amber-300 border border-amber-500/30">
      Paid {fmt(paid.toFixed(2), s.base_currency)} /{' '}
      {fmt(due.toFixed(2), s.base_currency)}
    </Badge>
  )
}

export default function PartnerSettlementsTable({
  items,
  onRecordPayment,
  onDelete,
}: PartnerSettlementsTableProps) {
  if (items.length === 0) {
    return (
      <p className="text-xs text-zinc-400">
        No settlements recorded for this shop yet.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto rounded-2xl border border-zinc-800">
      <table className="w-full text-sm">
        <thead className="bg-zinc-900/60 text-[10px] uppercase tracking-widest text-zinc-400">
          <tr>
            <th className="px-3 py-2 text-left">Period</th>
            <th className="px-3 py-2 text-left">Partner</th>
            <th className="px-3 py-2 text-left">Formula</th>
            <th className="px-3 py-2 text-right">%</th>
            <th className="px-3 py-2 text-right">Amount</th>
            <th className="px-3 py-2 text-left">Progress</th>
            <th className="px-3 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr
              key={s.id}
              className="border-t border-zinc-800/60 text-zinc-200"
            >
              <td className="px-3 py-2 text-xs text-zinc-400">
                {s.period_start} — {s.period_end}
              </td>
              <td className="px-3 py-2">{s.partner_name}</td>
              <td className="px-3 py-2 text-xs text-zinc-400">
                {FORMULA_LABELS[s.formula_type]}
              </td>
              <td className="px-3 py-2 text-right">{Number(s.percent)}%</td>
              <td className="px-3 py-2 text-right font-semibold">
                {fmt(s.computed_amount, s.base_currency)}
              </td>
              <td className="px-3 py-2">{progressBadge(s)}</td>
              <td className="px-3 py-2 text-right">
                <div className="flex justify-end gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs text-teal-300 hover:text-teal-200"
                    onClick={() => onRecordPayment(s)}
                  >
                    <Plus className="size-3" />
                    Payment
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs text-red-400 hover:text-red-300"
                    onClick={() => onDelete(s)}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
