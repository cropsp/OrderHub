import type { PartnerBalance } from '@/api/partnerPayouts'

interface PartnerBalancesSummaryProps {
  balances: PartnerBalance[]
}

function formatAmount(value: string, currency: string): string {
  const n = Number(value)
  return `${n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`
}

function classifyBalance(value: string): {
  label: string
  className: string
} {
  const n = Number(value)
  if (Math.abs(n) < 0.005) {
    return {
      label: 'Settled in full',
      className: 'text-emerald-400',
    }
  }
  if (n > 0) {
    return { label: 'Owed', className: 'text-amber-400' }
  }
  return { label: 'Overpaid', className: 'text-violet-400' }
}

export default function PartnerBalancesSummary({
  balances,
}: PartnerBalancesSummaryProps) {
  if (balances.length === 0) return null

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
        Per-partner balances
      </p>
      <div className="space-y-2">
        {balances.map((b) => {
          const cls = classifyBalance(b.balance_owed)
          return (
            <div
              key={`${b.partner_name}|${b.currency}`}
              className="flex items-center justify-between gap-4 text-sm"
            >
              <div className="font-medium text-zinc-100">{b.partner_name}</div>
              <div className="flex items-center gap-6 text-xs text-zinc-400">
                <span>
                  Settled{' '}
                  <span className="text-zinc-200">
                    {formatAmount(b.total_settled, b.currency)}
                  </span>
                </span>
                <span>
                  Paid{' '}
                  <span className="text-zinc-200">
                    {formatAmount(b.total_paid, b.currency)}
                  </span>
                </span>
                <span className={`font-semibold ${cls.className}`}>
                  {cls.label === 'Settled in full'
                    ? cls.label
                    : `${cls.label} ${formatAmount(
                        Math.abs(Number(b.balance_owed)).toFixed(2),
                        b.currency,
                      )}`}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
