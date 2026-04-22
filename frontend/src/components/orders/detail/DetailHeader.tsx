import { format } from 'date-fns';
import { Tag, Calendar, Hash } from 'lucide-react';
import type { OrderDetail } from '@/types/order';

interface DetailHeaderProps {
  order: OrderDetail;
}

export function DetailHeader({ order }: DetailHeaderProps) {
  return (
    <header className="px-6 py-4 border-b border-zinc-900 bg-zinc-950/20">
      <div className="max-w-5xl mx-auto px-6">
        <div className="flex flex-col gap-2">
          <h1 className="text-xl font-bold text-white tracking-tight leading-none">
            {order.title || 'Untitled Order'}
          </h1>
          
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-teal-500/10 border border-teal-500/20 shadow-sm">
              <Tag size={10} className="text-teal-400" />
              <span className="text-[9px] font-black text-teal-400 uppercase tracking-[0.1em]">
                {order.shop_name}
              </span>
            </div>
            
            <div className="flex items-center gap-1.5 text-zinc-600">
              <Hash size={12} className="text-zinc-800" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                ID: {order.external_id}
              </span>
            </div>
            
            <div className="flex items-center gap-1.5 text-zinc-600">
              <Calendar size={12} className="text-zinc-800" />
              <span className="text-[10px] font-medium text-zinc-500">
                {format(new Date(order.ordered_at), 'MMM dd, yyyy - HH:mm')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
