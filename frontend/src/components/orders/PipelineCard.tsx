import { format } from 'date-fns';
import { Store, User, Clock } from 'lucide-react';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ORDER_STATUS } from '@/lib/order-status';
import type { OrderListItem } from '@/types/order';
import { useUpdateOrderStatus } from '@/hooks/useOrders';

type PipelineCardProps = {
  order: OrderListItem;
  onClick: () => void;
};

export default function PipelineCard({ order, onClick }: PipelineCardProps) {
  const { mutate: updateStatus, isPending } = useUpdateOrderStatus();

  const handleStatusChange = (newStatus: string) => {
    updateStatus({ orderId: order.id, status: newStatus });
  };

  return (
    <Card 
      className="group border-slate-800/80 bg-slate-900/60 transition-all hover:border-teal-500/30 hover:bg-slate-900/90 shadow-sm shadow-black/20 cursor-pointer"
      onClick={onClick}
    >
      <CardHeader className="space-y-1.5 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[10px] font-bold tracking-wider text-teal-400">
            #{order.external_id}
          </span>
          <div className="flex items-center gap-1 text-[10px] text-slate-500">
            <Clock className="size-3" />
            {format(new Date(order.ordered_at), 'MMM dd')}
          </div>
        </div>
        <h4 className="line-clamp-2 text-sm font-medium leading-tight text-slate-200">
          {order.title}
        </h4>
      </CardHeader>
      
      <CardContent className="space-y-2 p-3 pt-0">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Store className="size-3.5 shrink-0 text-slate-500" />
          <span className="truncate">{order.shop_name}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-medium">
          <User className="size-3.5 shrink-0 text-slate-500" />
          <span className="truncate">{order.customer_name}</span>
        </div>
      </CardContent>

      <CardFooter className="border-t border-slate-800/40 p-2 bg-slate-950/20">
        <Select 
          defaultValue={order.status} 
          onValueChange={handleStatusChange}
          disabled={isPending}
        >
          <SelectTrigger className="h-7 w-full border-transparent bg-transparent px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200 focus:ring-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-950 border-slate-800 text-slate-200">
            {Object.entries(ORDER_STATUS).map(([key, value]) => (
              <SelectItem key={value} value={value} className="text-[10px] uppercase font-bold tracking-widest focus:bg-teal-500/20 focus:text-teal-100">
                {key.replace('_', ' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardFooter>
    </Card>
  );
}
