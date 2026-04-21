import { User, Mail } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import { BentoCard } from './BentoCard';
import type { OrderDetail } from '@/types/order';

interface DetailCustomerProps {
  order: OrderDetail;
}

export function DetailCustomer({ order }: DetailCustomerProps) {
  return (
    <div className="space-y-8">
      <BentoCard title="Customer Profile" icon={User}>
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <div className="size-12 rounded-2xl bg-teal-500/10 flex items-center justify-center border border-teal-500/10">
              <User className="size-6 text-teal-500" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-100">{order.customer_name}</p>
              <p className="text-xs text-slate-500 font-medium flex items-center gap-1.5 mt-1">
                <Mail className="size-3" />
                {order.customer?.email || 'No assigned email'}
              </p>
            </div>
          </div>
          <Separator className="bg-white/[0.03]" />
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500 font-medium">Source Shop</span>
            <span className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 font-bold uppercase tracking-wider text-[9px]">{order.shop_name}</span>
          </div>
        </div>
      </BentoCard>

      {order.customer_note && (
        <div className="relative overflow-hidden rounded-3xl bg-sky-500/5 p-8 border border-sky-500/10 shadow-[inset_0_2px_40px_rgba(14,165,233,0.03)]">
          <div className="absolute top-0 right-0 p-8 text-sky-500/10">
            <Mail className="size-24 scale-150 rotate-12" />
          </div>
          <div className="relative">
            <div className="flex items-center gap-2 mb-4">
              <Mail className="size-4 text-sky-500" />
              <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-500/60">Raw Customer Message</h3>
            </div>
            <p className="text-lg text-slate-300 italic font-medium leading-relaxed max-w-2xl">
              "{order.customer_note}"
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
