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
  const orderTotal = order.total_price || 0;
  // Single canonical subtotal — sum of line items, matching DetailItems.
  const itemsSubtotal = (order.items ?? []).reduce(
    (acc, it) => acc + it.quantity * it.unit_price,
    0,
  );
  // Shipping/other = the gap between what the customer paid and the line items.
  const shippingOther = orderTotal - itemsSubtotal;

  const manualCost = order.production_cost;
  const computedCost = order.computed_production_cost;

  // Net profit / margin are only honest when we actually know a cost.
  // computed (BOM-driven) takes precedence over the manual figure.
  const effectiveCost = computedCost ?? manualCost ?? null;
  const netProfit = effectiveCost != null ? orderTotal - effectiveCost : null;
  const marginPercent =
    netProfit != null && orderTotal > 0
      ? Math.round((netProfit / orderTotal) * 100)
      : null;

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
          <span className="text-[11px] font-medium text-zinc-500">Items subtotal</span>
          <span className="text-sm font-medium text-zinc-300">
            {itemsSubtotal.toFixed(2)} <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-zinc-500">Shipping / other</span>
          {shippingOther === 0 ? (
            <span className="text-sm text-zinc-500 italic">No fee</span>
          ) : (
            <span className="text-sm font-medium text-zinc-300">
              {shippingOther.toFixed(2)} <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
            </span>
          )}
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold text-zinc-400">Order total</span>
          <span className="text-sm font-semibold text-zinc-200">
            {orderTotal.toFixed(2)} <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
          </span>
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

        {computedCost != null && (
          <p className="text-[10px] italic text-zinc-600">
            ⓘ FIN-1 uses computed cost when available (BOM-driven).
          </p>
        )}

        <div className="h-px bg-zinc-800/30 my-4" />

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold text-zinc-400">Net Profit</span>
          <div className="flex items-center gap-2">
            {netProfit != null ? (
              <>
                <span className="text-base text-emerald-500 font-semibold">
                  {netProfit.toFixed(2)}
                </span>
                {marginPercent != null && (
                  <span className="text-[10px] font-bold text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                    {marginPercent}%
                  </span>
                )}
              </>
            ) : (
              <span className="text-base text-zinc-600 font-semibold" title="No production cost recorded">
                —
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
