import { formatMoney } from '@/lib/format';
import type { OrderDetail } from '@/types/order';

interface DetailFinanceProps {
  order: OrderDetail;
}

// MAT-4 variance thresholds for the computed-vs-manual cost diff badge.
// 5% triggers display; 10% colours amber.
const VARIANCE_BADGE_THRESHOLD = 0.05;
const VARIANCE_AMBER_THRESHOLD = 0.10;

export function DetailFinance({ order }: DetailFinanceProps) {
  const orderTotal = order.total_price || 0;
  // Single canonical subtotal — sum of line items, matching DetailItems.
  const itemsSubtotal = (order.items ?? []).reduce(
    (acc, it) => acc + it.quantity * it.unit_price,
    0,
  );
  // OD-2: the order total is only authoritative when it's a positive number.
  // A null/0 total (common on manual/NP orders that never captured a paid
  // amount) is "not set" — deriving shipping = total − items from it invents a
  // negative "Shipping / other" and presents 0.00 as fact. Guard against both.
  const totalKnown = order.total_price != null && order.total_price > 0;

  // ORDER-SHIPPING-1: the channel now tells us what the customer paid for
  // shipping, and how much of the total was discount and tax. When those are
  // stored we render facts. `captured` is true if ANY of the three arrived —
  // they are written as a set by the Shopify mappers and the backfill, so a
  // partial set means a payload was short, not that the order had no shipping.
  const captured =
    order.shipping_revenue != null ||
    order.discount_total != null ||
    order.tax_total != null;

  // The pre-ORDER-SHIPPING-1 residual, kept ONLY as the fallback for orders no
  // channel reports these figures for (Etsy, manual, and Shopify orders not yet
  // backfilled). It silently absorbs discount and tax, so it is labelled as
  // derived wherever it renders and never sits under a "Shipping" heading.
  // Only meaningful when the total is known and not below the items subtotal
  // (a negative derived shipping cost is never rendered as fact).
  const shippingOther = orderTotal - itemsSubtotal;
  const showShipping = totalKnown && shippingOther > 0;
  const showNoFee = totalKnown && shippingOther === 0;
  // Distinguishes the two ways the residual can be unusable. Both used to share
  // one tooltip that claimed the total was missing — which was a lie whenever
  // the total was present and the line items simply exceeded it.
  const derivedUnavailableReason = !totalKnown
    ? 'Order total not set — shipping cannot be derived'
    : 'Line items exceed the order total — no shipping can be derived';

  const manualCost = order.production_cost;
  const computedCost = order.computed_production_cost;

  // SHOP-FEE-1: the transaction fee the channel/gateway takes off this order.
  // Null when the shop has no rate configured, or when the caller may not see
  // costs (censor_order_financials nulls it) — in both cases it contributes 0,
  // which is what this card showed before fees were ever populated.
  const platformFee = order.platform_fee ?? 0;

  // Net profit / margin are only honest when we actually know a cost AND an
  // authoritative total (otherwise profit off a 0 total reads as a real loss).
  // computed (BOM-driven) takes precedence over the manual figure.
  // The fee is subtracted here to match the finance page's definition
  // (revenue − COGS − fees − …); leaving it out made this card disagree with
  // the P&L on every order carrying a fee.
  const effectiveCost = computedCost ?? manualCost ?? null;
  const netProfit =
    totalKnown && effectiveCost != null ? orderTotal - effectiveCost - platformFee : null;
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
          <span className="text-[11px] font-medium text-zinc-400">Items subtotal</span>
          <span className="text-sm font-medium text-zinc-300">
            {formatMoney(itemsSubtotal)} <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
          </span>
        </div>

        {/* ORDER-SHIPPING-1 — captured: one row per stored fact, so the rows add
            up to the order total. A null row is omitted entirely rather than
            printed as 0.00 (same rule as Platform fee below). Discount and Tax
            additionally hide at exactly 0, where they carry no information and
            the arithmetic is unchanged; Shipping renders at 0.00 because free
            shipping is a fact worth seeing. */}
        {captured ? (
          <>
            {order.discount_total != null && order.discount_total !== 0 && (
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-zinc-400">Discount</span>
                <span className="text-sm font-medium text-zinc-300" data-testid="discount-row">
                  −{formatMoney(order.discount_total)}{' '}
                  <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
                </span>
              </div>
            )}

            {order.shipping_revenue != null && (
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-zinc-400">Shipping</span>
                <span className="text-sm font-medium text-zinc-300" data-testid="shipping-row">
                  {formatMoney(order.shipping_revenue)}{' '}
                  <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
                </span>
              </div>
            )}

            {order.tax_total != null && order.tax_total !== 0 && (
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-zinc-400">Tax</span>
                <span className="text-sm font-medium text-zinc-300" data-testid="tax-row">
                  {formatMoney(order.tax_total)}{' '}
                  <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
                </span>
              </div>
            )}
          </>
        ) : (
          /* No channel figures for this order. Fall back to the residual, but
             say so: the label and the footnote are what stop an inference being
             read as a captured fact. */
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-zinc-400">
              Shipping / other (derived)
            </span>
            {showNoFee ? (
              <span className="text-sm text-zinc-400 italic">No fee</span>
            ) : showShipping ? (
              <span className="text-sm font-medium text-zinc-300" data-testid="derived-shipping-row">
                {formatMoney(shippingOther)} <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
              </span>
            ) : (
              <span className="text-sm text-zinc-600" title={derivedUnavailableReason}>
                —
              </span>
            )}
          </div>
        )}

        {!captured && showShipping && (
          <p className="text-[10px] italic text-zinc-600 -mt-1" data-testid="derived-note">
            ⓘ Derived as total − items, so it also absorbs any discount or tax.
            This order predates shipping capture, or its channel reports no
            shipping figure.
          </p>
        )}

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold text-zinc-400">Order total</span>
          {totalKnown ? (
            <span className="text-sm font-semibold text-zinc-200">
              {formatMoney(orderTotal)} <span className="text-[10px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
            </span>
          ) : (
            <span className="text-sm font-semibold text-zinc-600" title="Order total not set">
              —
            </span>
          )}
        </div>

        {!totalKnown && (
          <p className="text-[10px] italic text-zinc-600 -mt-1">
            ⓘ Order total not set for this order.
          </p>
        )}

        {manualCost != null && (
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-zinc-400">
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

        {order.platform_fee != null && (
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-zinc-400">
              Platform fee
            </span>
            <span className="text-sm font-medium text-zinc-300">
              −{formatMoney(order.platform_fee)}{' '}
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

        {/* FX-CONVERSION: materials are priced in UAH, so a USD order's computed
            cost is a converted figure. Show the rate that produced it — otherwise
            the operator sees a USD number with no way to check it. Frozen at
            ship: changing the rate later never moves this order. */}
        {computedCost != null && order.cogs_fx_rate != null && (
          <p className="text-[10px] italic text-zinc-600" data-testid="fx-provenance">
            ⓘ Converted from{' '}
            {order.cogs_basis_amount != null && order.cogs_basis_currency
              ? `${formatMoney(order.cogs_basis_amount)} ${order.cogs_basis_currency}`
              : 'material cost'}{' '}
            at {order.cogs_fx_rate} UAH per $1, fixed when this order shipped.
          </p>
        )}

        <div className="h-px bg-zinc-800/30 my-4" />

        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold text-zinc-400">Net Profit</span>
          <div className="flex items-center gap-2">
            {netProfit != null ? (
              <>
                <span className="text-base text-emerald-500 font-semibold">
                  {formatMoney(netProfit)}
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
