import { format } from 'date-fns';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { MoreHorizontal, Eye, Archive, RefreshCw } from 'lucide-react';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { getShopTheme } from '@/utils/shopTheme';
import { getInitials, getAvatarColor } from '@/utils/avatar';
import { cn } from '@/lib/utils';
import type { OrderListItem } from '@/types/order';

type OrdersTableProps = {
  orders: OrderListItem[];
  isLoading?: boolean;
  onSelectOrder: (id: string) => void;
};

export default function OrdersTable({ orders, isLoading, onSelectOrder }: OrdersTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-14 w-full bg-zinc-800/40 animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-zinc-900/40">
        <p className="text-sm font-medium text-zinc-400">No orders found</p>
        <p className="text-xs text-zinc-600 mt-1">Try adjusting your filters.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
      <Table>
        <TableHeader className="bg-zinc-900 sticky top-0 z-10">
          <TableRow className="border-zinc-800 hover:bg-transparent">
            <TableHead className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 py-4">Order</TableHead>
            <TableHead className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Customer</TableHead>
            <TableHead className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Product</TableHead>
            <TableHead className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Total</TableHead>
            <TableHead className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Date</TableHead>
            <TableHead className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Status</TableHead>
            <TableHead className="w-10"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {orders.map((order) => {
            const shopTheme = getShopTheme(order.shop_name ?? '');
            const avatarColor = getAvatarColor(order.customer_name ?? '');
            const initials = getInitials(order.customer_name ?? '??');

            return (
              <TableRow 
                key={order.id} 
                className="border-zinc-800/60 hover:bg-zinc-800/40 transition-colors cursor-pointer group h-14"
                onClick={() => onSelectOrder(order.id)}
              >
                <TableCell>
                  <div className="flex flex-col gap-1">
                    <span className="font-mono text-xs text-zinc-500">#{order.external_id}</span>
                    <div className={cn("inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider w-fit", shopTheme.bg, shopTheme.text)}>
                      {order.shop_name}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2.5">
                    <div className={cn("size-8 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0", avatarColor)}>
                      {initials}
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="text-sm font-medium text-zinc-100 truncate">{order.customer_name}</span>
                      <span className="text-[10px] text-zinc-500 truncate">@{order.platform_user_id || 'unknown'}</span>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="max-w-[200px]">
                  <p className="text-sm text-zinc-300 truncate" title={order.title}>
                    {order.title}
                  </p>
                </TableCell>
                <TableCell>
                  <div className="flex items-baseline gap-1">
                    <span className="text-sm font-bold text-zinc-100">{order.total_price}</span>
                    <span className="text-[10px] font-medium text-zinc-500 uppercase">{order.currency}</span>
                  </div>
                </TableCell>
                <TableCell>
                  <span className="text-sm text-zinc-400">
                    {format(new Date(order.ordered_at), 'MMM dd')}
                  </span>
                </TableCell>
                <TableCell>
                  <StatusBadge status={order.status} size="sm" />
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="p-2 hover:bg-zinc-800 rounded-lg text-zinc-500 hover:text-zinc-100 transition-colors">
                        <MoreHorizontal className="size-4" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="bg-zinc-900 border-zinc-800 text-zinc-300">
                      <DropdownMenuItem onClick={() => onSelectOrder(order.id)} className="gap-2 focus:bg-zinc-800 focus:text-zinc-100">
                        <Eye className="size-3.5" /> View Details
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2 focus:bg-zinc-800 focus:text-zinc-100">
                        <RefreshCw className="size-3.5" /> Change Status
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2 focus:bg-zinc-800 focus:text-zinc-100 text-red-400 focus:text-red-300">
                        <Archive className="size-3.5" /> Archive
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
