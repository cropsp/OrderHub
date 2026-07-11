import { Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { PartnerPayment, PartnerSettlement } from '@/api/partnerPayouts'

interface PartnerPaymentsTableProps {
  items: PartnerPayment[]
  settlementsById: Record<string, PartnerSettlement>
  onDelete: (payment: PartnerPayment) => void
}

function fmt(amount: string, currency: string): string {
  return `${Number(amount).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`
}

export default function PartnerPaymentsTable({
  items,
  settlementsById,
  onDelete,
}: PartnerPaymentsTableProps) {
  if (items.length === 0) {
    return (
      <p className="text-xs text-zinc-400">No payments recorded yet.</p>
    )
  }
  return (
    <div className="overflow-x-auto rounded-2xl border border-zinc-800">
      <table className="w-full text-sm">
        <thead className="bg-zinc-900/60 text-[10px] uppercase tracking-widest text-zinc-400">
          <tr>
            <th className="px-3 py-2 text-left">Paid at</th>
            <th className="px-3 py-2 text-left">Partner</th>
            <th className="px-3 py-2 text-right">Amount</th>
            <th className="px-3 py-2 text-left">Linked to</th>
            <th className="px-3 py-2 text-left">Notes</th>
            <th className="px-3 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => {
            const linked = p.settlement_id
              ? settlementsById[p.settlement_id]
              : null
            return (
              <tr
                key={p.id}
                className="border-t border-zinc-800/60 text-zinc-200"
              >
                <td className="px-3 py-2 text-xs text-zinc-400">
                  {p.paid_at}
                </td>
                <td className="px-3 py-2">{p.partner_name}</td>
                <td className="px-3 py-2 text-right font-semibold">
                  {fmt(p.amount, p.currency)}
                </td>
                <td className="px-3 py-2 text-xs text-zinc-400">
                  {linked
                    ? `${linked.period_start} — ${linked.period_end} (${fmt(
                        linked.computed_amount,
                        linked.base_currency,
                      )})`
                    : p.settlement_id
                    ? '(unlinked)'
                    : '(none)'}
                </td>
                <td className="px-3 py-2 text-xs text-zinc-400">
                  {p.notes || ''}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs text-red-400 hover:text-red-300"
                    onClick={() => onDelete(p)}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
