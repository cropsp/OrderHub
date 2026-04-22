import { DollarSign, ArrowUpRight } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import { BentoCard } from './BentoCard';
import type { OrderDetail } from '@/types/order';

interface DetailFinanceProps {
  order: OrderDetail;
}

export function DetailFinance({ order }: DetailFinanceProps) {
  const platformFee = order.platform_fee || 0;
  const productionCost = order.production_cost || 0;
  const netProfit = order.total_price - platformFee - productionCost;

  return (
    <BentoCard title="Financial Intelligence" icon={DollarSign}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-500 font-medium">Total Revenue</span>
          <span className="text-base font-bold text-zinc-100">{order.total_price} <span className="text-[10px] text-zinc-500 font-normal">{order.currency}</span></span>
        </div>
        
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-zinc-500">Platform Fees</span>
            <span className="text-red-400/80">-{platformFee.toFixed(2)}</span>
          </div>
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-zinc-500">Production Cost</span>
            <span className="text-red-400/80">-{productionCost.toFixed(2)}</span>
          </div>
        </div>

        <Separator className="bg-zinc-800/60" />

        <div className="pt-2">
          <div className="flex items-center justify-between mb-1">
             <span className="text-[10px] font-bold text-teal-400 uppercase tracking-widest flex items-center gap-1">
               <ArrowUpRight className="size-3" /> Net Profit
             </span>
             <span className="text-2xl font-bold text-zinc-50 tracking-tight">
               {netProfit.toFixed(2)}
             </span>
          </div>
          <div className="w-full bg-zinc-800 h-1.5 rounded-full overflow-hidden">
             <div 
               className="bg-teal-500 h-full transition-all duration-1000" 
               style={{ width: `${Math.max(0, Math.min(100, (netProfit / order.total_price) * 100))}%` }}
             />
          </div>
          <p className="text-[9px] text-zinc-500 mt-2 text-right uppercase font-bold tracking-tighter">
            {((netProfit / order.total_price) * 100).toFixed(1)}% margin
          </p>
        </div>
      </div>
    </BentoCard>
  );
}
