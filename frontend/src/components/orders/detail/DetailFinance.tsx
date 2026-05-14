import type { OrderDetail } from '@/types/order';

interface DetailFinanceProps {
  order: OrderDetail;
}

// MAT-4 variance thresholds for the computed-vs-manual cost diff badge.
// 5% triggers display; 10% colours amber.
const VARIANCE_BADGE_THRESHOLD = 0.05;
const VARIANCE_AMBER_THRESHOLD = 0.10;

function formatMoney(value: number): string {
  return value.toFixed(2);
}

export function DetailFinance({ order }: DetailFinanceProps) {
  // Margin calculation helper
  const revenue = order.total_price || 0;
  // Fallback to total price if net_profit isn't directly available or calculate it
  const netProfit = order.total_price; // Simplification for now, adjust based on real data
  const marginPercent = revenue > 0 ? Math.round((netProfit / revenue) * 100) : 0;

  const manualCost = order.production_cost;
  const computedCost = order.computed_production_cost;

  const variance =
    manualCost != null && computedCost != null && manualCost !== 0
      ? (computedCost - manualCost) / manualCost
      : null;
  const showVarianceBadge =
    variance != null && Math.abs(variance) > VARIANCE_BADGE_THRESHOLD;
  const variancePercent = variance != null ? variance * 100 : 0;
  const variancePrefix = variancePercent > 0 ? '+' : '';
  const varianceAmber =
    variance != null && Math.abs(variance) > VARIANCE_AMBER_THRESHOLD;

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-zinc-100 mb-4 px-1">
        Payment summary
      </h3>

      <div className="space-y-3 px-1">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-zinc-500">Subtotal</span>
          <span className="text-sm font-medium text-zinc-300">
            {revenue.toFixed(2)} <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-zinc-500">Shipping</span>
          <span className="text-sm text-zinc-500 italic">No fee</span>
        </div>

        {manualCost != null && (
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-zinc-500">
              Production cost
            </span>
            <span className="text-sm font-medium text-zinc-300">
              {formatMoney(manualCost)}{' '}
              <span className="text-[10px] text-zinc-600 uppercase ml-0.5">
                {order.currency}
              </span>
            </span>
          </div>
        )}

        {computedCost != null && (
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-zinc-600">
              Computed cost (from BOM)
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-zinc-400">
                {formatMoney(computedCost)}{' '}
                <span className="text-[10px] text-zinc-600 uppercase ml-0.5">
                  {order.currency}
                </span>
              </span>
              {showVarianceBadge && (
                <span
                  className={
                    varianceAmber
                      ? 'text-[10px] font-bold text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded'
                      : 'text-[10px] font-bold text-zinc-400 bg-zinc-500/10 px-1.5 py-0.5 rounded'
                  }
                  data-testid="variance-badge"
                >
                  {variancePrefix}
                  {variancePercent.toFixed(1)}% vs manual
                </span>
              )}
            </div>
          </div>
        )}

        <div className="h-px bg-zinc-800/30 my-4" />

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold text-zinc-400">Net Profit</span>
          <div className="flex items-center gap-2">
            <span className="text-base text-emerald-500 font-semibold">
              {netProfit.toFixed(2)}
            </span>
            <span className="text-[10px] font-bold text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded">
              {marginPercent}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
