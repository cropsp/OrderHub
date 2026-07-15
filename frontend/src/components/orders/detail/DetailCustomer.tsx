import { Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { countryName } from '@/lib/countries';
import { getInitials, getAvatarColor } from '@/utils/avatar';
import type { OrderDetail } from '@/types/order';

interface DetailCustomerProps {
  order: OrderDetail;
}

export function DetailCustomer({ order }: DetailCustomerProps) {
  const avatarColor = getAvatarColor(order.customer_name || '??');
  const initials = getInitials(order.customer_name || '??');

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-zinc-100 mb-4 px-0.5">
        Customer profile
      </h3>
      
      <div className="flex items-center gap-3 px-0.5 mb-5">
        <div className={cn("size-10 rounded-full flex items-center justify-center text-xs font-bold text-white shadow-lg", avatarColor)}>
          {initials}
        </div>
        <div className="flex flex-col min-w-0">
          <p className="text-sm font-semibold text-zinc-100 truncate leading-none">{order.customer_name}</p>
          <p className="text-[11px] font-medium text-zinc-400 mt-1.5 uppercase tracking-tighter">ID: {order.external_id || 'N/A'}</p>
        </div>
      </div>

      <div className="space-y-4 border-t border-zinc-800/50 pt-4 px-0.5">
        <div className="flex items-center justify-between group">
          <span className="text-[11px] font-medium text-zinc-400">Email</span>
          {order.customer?.email ? (
            <span className="text-sm text-zinc-300 font-medium truncate max-w-[150px] text-right">{order.customer.email}</span>
          ) : (
            <button className="text-[11px] font-bold text-teal-500/60 hover:text-teal-400 flex items-center gap-1 transition-colors">
              <Plus size={12} /> Add Email
            </button>
          )}
        </div>
        
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-zinc-400">Country</span>
          <span className="text-sm text-zinc-300 font-semibold" title={order.shipping_country || undefined}>
            {countryName(order.shipping_country, 'N/A')}
          </span>
        </div>
      </div>

      {order.customer_note && (
        <div className="mt-4 pt-4 border-t border-zinc-800/50">
          <blockquote className="relative pl-3 border-l-2 border-teal-500/30 py-0.5">
            <p className="text-[11px] text-zinc-400 italic leading-snug">
              "{order.customer_note}"
            </p>
          </blockquote>
        </div>
      )}
    </div>
  );
}
