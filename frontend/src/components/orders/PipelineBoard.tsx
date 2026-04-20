import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ORDER_STATUS, type OrderStatusValue } from '@/lib/order-status';
import type { OrderListItem } from '@/types/order';
import PipelineCard from './PipelineCard';

type PipelineBoardProps = {
  orders: OrderListItem[];
  columnStatuses: OrderStatusValue[];
  isLoading?: boolean;
  onSelectOrder: (id: string) => void;
};

export default function PipelineBoard({ orders, columnStatuses, isLoading, onSelectOrder }: PipelineBoardProps) {
  if (isLoading) {
    return (
      <div className="flex h-[500px] items-center justify-center rounded-lg border border-slate-800/50 bg-slate-900/20">
        <p className="text-sm text-slate-400 animate-pulse">Loading board...</p>
      </div>
    );
  }

  // Get human readable label for a status value
  const getStatusLabel = (val: string) => {
    return Object.entries(ORDER_STATUS).find(([_, v]) => v === val)?.[0].replace('_', ' ') ?? val;
  };

  return (
    <ScrollArea className="w-full whitespace-nowrap rounded-md border border-slate-800/60 bg-slate-900/40 backdrop-blur-sm">
      <div className="flex w-max min-h-[600px] p-6 gap-6">
        {columnStatuses.map((status) => {
          const columnOrders = orders.filter((o) => o.status === status);
          
          return (
            <div key={status} className="flex h-full w-[300px] flex-col shrink-0">
              <div className="mb-4 flex items-center justify-between px-1">
                <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">
                  {getStatusLabel(status)}
                  <span className="ml-2 text-[10px] tabular-nums text-slate-600">
                    {columnOrders.length}
                  </span>
                </h3>
              </div>
              
              <div className="flex flex-col gap-3">
                {columnOrders.length === 0 ? (
                  <div className="flex aspect-[4/1] items-center justify-center rounded-lg border border-dashed border-slate-800/50 bg-slate-950/20">
                    <p className="text-[10px] font-medium text-slate-600">Empty</p>
                  </div>
                ) : (
                  columnOrders.map((order) => (
                    <PipelineCard key={order.id} order={order} onClick={() => onSelectOrder(order.id)} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
      <ScrollBar orientation="horizontal" className="bg-slate-950/50" />
    </ScrollArea>
  );
}
