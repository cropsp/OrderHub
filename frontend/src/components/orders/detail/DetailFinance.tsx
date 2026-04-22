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
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-4 px-1">
        Financial Intelligence
      </h3>
      
      <div className="space-y-2 px-1">
        <div className="flex items-center justify-between">
          <span className="text-zinc-600 font-bold uppercase tracking-widest text-[9px]">Revenue</span>
          <span className="text-xs font-mono font-bold text-zinc-300">
            {revenue.toFixed(2)} <span className="text-[9px] opacity-40 uppercase">{order.currency}</span>
          </span>
        </div>
        
        <div className="flex items-center justify-between">
          <span className="text-zinc-600 font-bold uppercase tracking-widest text-[9px]">Platform Fees</span>
          <span className="text-[10px] text-zinc-500 font-mono italic">No fee</span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-zinc-600 font-bold uppercase tracking-widest text-[9px]">Production Cost</span>
          <span className="text-[10px] text-zinc-500 font-mono italic">Not set</span>
        </div>

        <div className="h-px bg-zinc-800/50 my-3" />

        <div className="flex items-center justify-between">
          <span className="text-teal-500/70 font-black uppercase tracking-[0.15em] text-[9px]">Net Profit</span>
          <div className="flex items-center gap-2">
            <span className="text-emerald-500 font-mono font-black text-sm">
              {netProfit.toFixed(2)}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500 text-[9px] font-black tracking-widest">
              {marginPercent}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
