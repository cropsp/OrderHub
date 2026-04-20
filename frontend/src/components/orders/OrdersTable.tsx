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
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { ORDER_STATUS } from '@/lib/order-status';
import type { OrderListItem } from '@/types/order';
import { useUpdateOrderStatus } from '@/hooks/useOrders';

type OrdersTableProps = {
  orders: OrderListItem[];
  isLoading?: boolean;
  onSelectOrder: (id: string) => void;
};

export default function OrdersTable({ orders, isLoading, onSelectOrder }: OrdersTableProps) {
  const { mutate: updateStatus, isPending } = useUpdateOrderStatus();

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-slate-800/50 bg-slate-900/20">
        <p className="text-sm text-slate-400 animate-pulse">Loading orders...</p>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center rounded-lg border border-dashed border-slate-800 bg-slate-900/10">
        <p className="text-sm font-medium text-slate-300">No orders found</p>
        <p className="text-xs text-slate-500">Try selecting a different status or filter.</p>
      </div>
    );
  }

  const handleStatusChange = (orderId: string, newStatus: string) => {
    updateStatus({ orderId, status: newStatus });
  };

  return (
    <div className="rounded-md border border-slate-800/60 bg-slate-900/40 backdrop-blur-sm overflow-hidden">
      <Table>
        <TableHeader className="bg-slate-950/40">
          <TableRow className="border-slate-800 hover:bg-transparent">
            <TableHead className="w-[120px] text-[11px] font-bold uppercase tracking-wider text-slate-400">Order ID</TableHead>
            <TableHead className="w-[150px] text-[11px] font-bold uppercase tracking-wider text-slate-400">Shop</TableHead>
            <TableHead className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Title / Item</TableHead>
            <TableHead className="w-[180px] text-[11px] font-bold uppercase tracking-wider text-slate-400">Customer</TableHead>
            <TableHead className="w-[100px] text-[11px] font-bold uppercase tracking-wider text-slate-400">Total</TableHead>
            <TableHead className="w-[140px] text-[11px] font-bold uppercase tracking-wider text-slate-400">Date</TableHead>
            <TableHead className="w-[180px] text-[11px] font-bold uppercase tracking-wider text-slate-400 text-right">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {orders.map((order) => (
            <TableRow 
              key={order.id} 
              className="border-slate-800/60 hover:bg-slate-800/30 transition-colors cursor-pointer"
              onClick={() => onSelectOrder(order.id)}
            >
              <TableCell className="font-mono text-xs font-medium text-teal-400">
                #{order.external_id}
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="border-slate-700 bg-slate-800/50 text-slate-300 font-normal">
                  {order.shop_name}
                </Badge>
              </TableCell>
              <TableCell className="max-w-[250px] truncate">
                <span className="text-sm font-medium text-slate-200">{order.title}</span>
              </TableCell>
              <TableCell>
                <div className="flex flex-col">
                  <span className="text-sm text-slate-200">{order.customer_name}</span>
                  {order.shipping_country && (
                    <span className="text-[10px] text-slate-500 uppercase tracking-tight">{order.shipping_country}</span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <span className="text-sm font-semibold text-slate-200">
                  {order.total_price} <span className="text-[10px] font-normal text-slate-500">{order.currency}</span>
                </span>
              </TableCell>
              <TableCell>
                <span className="text-xs text-slate-400">
                  {format(new Date(order.ordered_at), 'MMM dd, HH:mm')}
                </span>
              </TableCell>
              <TableCell className="text-right">
                <Select 
                  defaultValue={order.status} 
                  onValueChange={(val) => handleStatusChange(order.id, val)}
                  disabled={isPending}
                >
                  <SelectTrigger className="h-8 w-[160px] ml-auto border-slate-700 bg-slate-900/50 text-xs text-slate-300 focus:ring-teal-500/20">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-950 border-slate-800 text-slate-200">
                    {Object.entries(ORDER_STATUS).map(([key, value]) => (
                      <SelectItem key={value} value={value} className="text-xs focus:bg-teal-500/20 focus:text-teal-100">
                        {key.replace('_', ' ')}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
