import { useNavigate } from 'react-router-dom';
import { formatDate, formatMoney } from '@/lib/format';
import { Clock } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { getShopTheme } from '@/utils/shopTheme';
import { getInitials, getAvatarColor } from '@/utils/avatar';
import { orderDisplayName } from '@/lib/orderName';
import { cn } from '@/lib/utils';
import type { OrderListItem } from '@/types/order';

type PipelineCardProps = {
  order: OrderListItem;
};

export default function PipelineCard({ order }: PipelineCardProps) {
  const navigate = useNavigate();
  const shopTheme = getShopTheme(order.shop_name ?? '');
  const name = orderDisplayName(order);
  const avatarColor = getAvatarColor(name);
  const initials = getInitials(name);

  return (
    /* TODO: implement D&D in future sprint */
    <Card 
      className="group bg-zinc-900 border-zinc-800 transition-all hover:border-teal-500/30 hover:bg-zinc-800/80 shadow-sm shadow-black/20 cursor-pointer"
      onClick={() => navigate(`/orders/${order.id}`)}
    >
      <CardHeader className="space-y-2 p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[10px] font-bold tracking-wider text-zinc-400">
            #{order.external_id}
          </span>
          <div className={cn("px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider", shopTheme.bg, shopTheme.text)}>
            {order.shop_name}
          </div>
        </div>
        <h4 className="line-clamp-2 text-sm font-medium leading-tight text-zinc-100">
          {order.title}
        </h4>
      </CardHeader>
      
      <CardContent className="space-y-3 p-4 pt-0">
        <div className="flex items-center gap-2">
          <div className={cn("size-6 rounded-full flex items-center justify-center text-[8px] font-bold text-white shrink-0", avatarColor)}>
            {initials}
          </div>
          <span className="text-xs text-zinc-300 truncate font-medium">{name}</span>
        </div>
        
        <div className="flex items-center justify-between mt-auto pt-2 border-t border-zinc-800/60">
          <div className="flex items-baseline gap-1">
            <span className="text-sm font-bold text-zinc-100">{formatMoney(order.total_price)}</span>
            <span className="text-[10px] font-medium text-zinc-400 uppercase">{order.currency}</span>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-zinc-400">
            <Clock className="size-3" />
            {formatDate(order.ordered_at)}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
