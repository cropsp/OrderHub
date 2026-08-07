import { AlertCircle, Info } from 'lucide-react'

import type { BaseQualityPanel as BaseQuality } from '@/api/partnerPayouts'

interface Props {
  quality: BaseQuality
}

/**
 * Data-readiness warnings for the previewed period (PARTNER-CONFIG-1 rule 7).
 *
 * These are WARNINGS, not blocks — the operator may settle anyway. The one
 * exception is `fx_blocker`, which is the reason Create will be refused, shown
 * here so the warnings and the blocker arrive together instead of as a panel
 * plus a separate error toast.
 *
 * The point of the panel is that all three problems overstate a base silently:
 * an order with no cost makes profit look bigger, an unimported Etsy month
 * makes fees look like zero, and a NULL platform_fee does the same on Shopify.
 * None of them are visible in the number itself.
 */
export default function BaseQualityPanel({ quality }: Props) {
  const warnings: string[] = []

  if (quality.orders_missing_cost > 0) {
    warnings.push(
      `${quality.orders_missing_cost} of ${quality.total_orders} orders in this period have no recorded cost. A profit base treats their COGS as zero, which overstates it.`,
    )
  }
  if (quality.orders_missing_platform_fee > 0) {
    warnings.push(
      `${quality.orders_missing_platform_fee} orders have no platform fee. Set the store's fee rate and run the platform-fee backfill, or these count as fee-free.`,
    )
  }
  if (quality.etsy_months_without_statement.length > 0) {
    warnings.push(
      `No Etsy statement imported for ${quality.etsy_months_without_statement
        .map(m => m.slice(0, 7))
        .join(', ')}. Etsy fees are zero until the statement lands.`,
    )
  }
  if (quality.etsy_refunds_unbooked) {
    warnings.push(
      'Etsy refunds are not booked yet, so no refund is deducted from this base.',
    )
  }

  if (!quality.fx_blocker && warnings.length === 0) {
    return (
      <div className="rounded-3xl border border-zinc-800 bg-zinc-900/40 p-4 text-xs text-zinc-500">
        <div className="flex items-center gap-2">
          <Info className="size-3.5" />
          Base quality: nothing to flag for this period.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-2 rounded-3xl border border-zinc-800 bg-zinc-900/40 p-4">
      <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
        Base quality
      </p>

      {quality.fx_blocker && (
        <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          <AlertCircle className="mt-0.5 size-3 shrink-0" />
          <span>{quality.fx_blocker}</span>
        </div>
      )}

      {warnings.map(w => (
        <div
          key={w}
          className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-300"
        >
          <AlertCircle className="mt-0.5 size-3 shrink-0" />
          <span>{w}</span>
        </div>
      ))}
    </div>
  )
}
