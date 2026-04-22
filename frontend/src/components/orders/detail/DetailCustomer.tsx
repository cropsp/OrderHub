import { User, Mail, Globe, ExternalLink } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import { BentoCard } from './BentoCard';
import { getInitials, getAvatarColor } from '@/utils/avatar';
import { cn } from '@/lib/utils';
import type { OrderDetail } from '@/types/order';

interface DetailCustomerProps {
  order: OrderDetail;
}

export function DetailCustomer({ order }: DetailCustomerProps) {
  const avatarColor = getAvatarColor(order.customer_name ?? '');
  const initials = getInitials(order.customer_name ?? '??');

  return (
    <div className="space-y-6">
      <BentoCard title="Customer Profile" icon={User}>
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <div className={cn("size-14 rounded-full flex items-center justify-center text-lg font-bold text-white shadow-lg shadow-black/20 shrink-0", avatarColor)}>
              {initials}
            </div>
            <div className="min-w-0">
              <p className="text-xl font-bold text-zinc-50 truncate">{order.customer_name}</p>
              <div className="flex items-center gap-2 mt-1">
                 <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">@{order.platform_user_id || 'guest'}</span>
                 <a href="#" className="text-zinc-500 hover:text-teal-400 transition-colors">
                   <ExternalLink className="size-3" />
                 </a>
              </div>
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500 font-medium flex items-center gap-2">
                <Mail className="size-3.5" /> Email
              </span>
              <span className="text-zinc-300 font-medium">{order.customer?.email || 'N/A'}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500 font-medium flex items-center gap-2">
                <Globe className="size-3.5" /> Country
              </span>
              <span className="text-zinc-300 font-medium uppercase tracking-wider">{order.shipping_country || 'N/A'}</span>
            </div>
          </div>
        </div>
      </BentoCard>

      {order.customer_note && (
        <div className="relative overflow-hidden rounded-2xl bg-teal-500/5 p-6 border border-teal-500/10">
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-3">
              <Mail className="size-3.5 text-teal-400" />
              <h3 className="text-[10px] font-bold uppercase tracking-wider text-teal-400/60">Customer Message</h3>
            </div>
            <p className="text-sm text-zinc-300 italic leading-relaxed">
              "{order.customer_note}"
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
