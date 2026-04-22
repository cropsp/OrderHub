import type { OrderDetail } from '@/types/order';

interface DetailFinanceProps {
  order: OrderDetail;
}

export function DetailFinance({ order }: DetailFinanceProps) {
  // Margin calculation helper
  const revenue = order.total_price || 0;
  // Fallback to total price if net_profit isn't directly available or calculate it
  const netProfit = order.total_price; // Simplification for now, adjust based on real data
  const marginPercent = revenue > 0 ? Math.round((netProfit / revenue) * 100) : 0;

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
