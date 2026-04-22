import { Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getInitials, getAvatarColor } from '@/utils/avatar';
import type { OrderDetail } from '@/types/order';

interface DetailCustomerProps {
  order: OrderDetail;
}

export function DetailCustomer({ order }: DetailCustomerProps) {
  const avatarColor = getAvatarColor(order.customer_name || '??');
  const initials = getInitials(order.customer_name || '??');

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-3.5">
      <h3 className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-3.5 px-0.5">
        Customer Profile
      </h3>
      
      <div className="flex items-center gap-2.5 px-0.5 mb-3.5">
        <div className={cn("size-7 rounded-full flex items-center justify-center text-[9px] font-bold text-white shadow-lg", avatarColor)}>
          {initials}
        </div>
        <div className="flex flex-col min-w-0">
          <p className="text-xs font-bold text-zinc-100 truncate leading-none">{order.customer_name}</p>
          <p className="text-[8px] font-mono text-zinc-600 uppercase tracking-tighter mt-0.5">ID: {order.external_id || 'N/A'}</p>
        </div>
      </div>

      <div className="space-y-1.5 border-t border-zinc-800/50 pt-3.5 px-0.5">
        <div className="flex items-center justify-between group">
          <span className="text-[8px] font-bold text-zinc-700 uppercase tracking-widest">Email</span>
          {order.customer?.email ? (
            <span className="text-[11px] text-zinc-400 font-medium truncate max-w-[130px] text-right">{order.customer.email}</span>
          ) : (
            <button className="text-[8px] font-bold text-teal-500/60 hover:text-teal-400 uppercase tracking-widest flex items-center gap-1 transition-colors">
              <Plus size={8} /> Add Email
            </button>
          )}
        </div>
        
        <div className="flex items-center justify-between">
          <span className="text-[8px] font-bold text-zinc-700 uppercase tracking-widest">Country</span>
          <span className="text-[11px] text-zinc-500 font-bold uppercase">{order.shipping_country || 'N/A'}</span>
        </div>
      </div>

      {order.customer_note && (
        <div className="mt-4 pt-4 border-t border-zinc-800/50">
          <blockquote className="relative pl-3 border-l-2 border-teal-500/30 py-0.5">
            <p className="text-[11px] text-zinc-500 italic leading-snug">
              "{order.customer_note}"
            </p>
          </blockquote>
        </div>
      )}
    </div>
  );
}
