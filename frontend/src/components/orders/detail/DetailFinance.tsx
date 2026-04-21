import { DollarSign } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import { BentoCard } from './BentoCard';
import type { OrderDetail } from '@/types/order';

interface DetailFinanceProps {
  order: OrderDetail;
}

export function DetailFinance({ order }: DetailFinanceProps) {
  return (
    <BentoCard title="Financial Intelligence" icon={DollarSign} className="bg-amber-500/[0.03] border-amber-500/10">
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500 font-medium">Total Revenue</span>
          <span className="text-lg font-bold text-slate-100">{order.total_price} {order.currency}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500 font-medium">Platform Fees</span>
          <span className="text-base font-bold text-red-400">-{order.platform_fee || 0} {order.currency}</span>
        </div>
        <Separator className="bg-white/[0.03]" />
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs font-bold text-teal-500/80 uppercase tracking-widest">Est. Profit</span>
          <span className="text-2xl font-heading font-black text-teal-400">
            {(order.total_price - (order.platform_fee || 0)).toFixed(2)} <span className="text-xs font-bold font-sans text-slate-500 ml-1">{order.currency}</span>
          </span>
        </div>
      </div>
    </BentoCard>
  );
}
