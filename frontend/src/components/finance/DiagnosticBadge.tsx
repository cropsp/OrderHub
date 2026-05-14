import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';

import type { DiagnosticInfo } from '@/types/finance';

interface DiagnosticBadgeProps {
  shopId: string;
  diagnostic: DiagnosticInfo;
}

export default function DiagnosticBadge({ shopId, diagnostic }: DiagnosticBadgeProps) {
  if (diagnostic.orders_missing_cost <= 0) return null;

  return (
    <Link
      to={`/shops/${shopId}/orders`}
      className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-[10px] font-medium text-amber-400 hover:bg-amber-500/10 transition-colors"
      title="Click to view shop orders and backfill production cost"
    >
      <AlertTriangle className="size-3" />
      <span>
        {diagnostic.orders_missing_cost} of {diagnostic.total_orders_in_period} orders
        without cost — Net Profit may be inflated
      </span>
    </Link>
  );
}
