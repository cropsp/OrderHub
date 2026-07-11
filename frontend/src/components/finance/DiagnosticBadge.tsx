import { Link } from 'react-router-dom';
import { AlertTriangle, Info } from 'lucide-react';

import type { DiagnosticInfo } from '@/types/finance';

interface DiagnosticBadgeProps {
  shopId: string;
  diagnostic: DiagnosticInfo;
}

export default function DiagnosticBadge({ shopId, diagnostic }: DiagnosticBadgeProps) {
  const showWarning = diagnostic.orders_missing_cost > 0;
  const showComputedInfo = diagnostic.orders_with_computed_cost > 0;

  if (!showWarning && !showComputedInfo) return null;

  return (
    <div className="mt-1 flex flex-col gap-1">
      {showWarning && (
        <Link
          to={`/shops/${shopId}/orders`}
          className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-[10px] font-medium text-amber-400 hover:bg-amber-500/10 transition-colors"
          title="Click to view shop orders and backfill production cost"
        >
          <AlertTriangle className="size-3" />
          <span>
            {diagnostic.orders_missing_cost} of {diagnostic.total_orders_in_period} orders
            without cost — Net Profit may be inflated
          </span>
        </Link>
      )}
      {showComputedInfo && (
        <div
          className="inline-flex items-center gap-1.5 px-2 py-1 text-[10px] text-zinc-400"
          data-testid="diagnostic-computed-info"
        >
          <Info className="size-3" />
          <span>
            {diagnostic.orders_with_computed_cost} of {diagnostic.total_orders_in_period}{' '}
            orders use BOM-computed cost
          </span>
        </div>
      )}
    </div>
  );
}
