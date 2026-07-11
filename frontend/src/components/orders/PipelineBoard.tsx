import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ORDER_STATUS, type OrderStatusValue } from '@/lib/order-status';
import type { OrderListItem } from '@/types/order';
import PipelineCard from './PipelineCard';

type PipelineBoardProps = {
  orders: OrderListItem[];
  columnStatuses: OrderStatusValue[];
  isLoading?: boolean;
};

export default function PipelineBoard({ orders, columnStatuses, isLoading }: PipelineBoardProps) {
  if (isLoading) {
    return (
      <div className="flex h-[500px] items-center justify-center rounded-lg border border-zinc-800/50 bg-zinc-900/20">
        <p className="text-sm text-zinc-400 animate-pulse">Loading board...</p>
      </div>
    );
  }

  // Get human readable label for a status value
  const getStatusLabel = (val: string) => {
    return Object.entries(ORDER_STATUS).find(([_, v]) => v === val)?.[0].replace('_', ' ') ?? val;
  };

  return (
    <ScrollArea className="w-full whitespace-nowrap rounded-xl border border-zinc-800 bg-zinc-900/40 backdrop-blur-sm">
      <div className="flex w-max min-h-[600px] p-6 gap-6">
        {columnStatuses.map((status) => {
          const columnOrders = orders.filter((o) => o.status === status);
          
          return (
            <div key={status} className="flex h-full w-[300px] flex-col shrink-0">
              <div className="mb-4 flex items-center justify-between px-1">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.1em] text-zinc-400">
                  {getStatusLabel(status)}
                  <span className="ml-2 text-[10px] tabular-nums text-zinc-600 bg-zinc-800/50 px-1.5 py-0.5 rounded-full">
                    {columnOrders.length}
                  </span>
                </h3>
              </div>
              
              <div className="flex flex-col gap-3">
                {columnOrders.length === 0 ? (
                  <div className="flex aspect-[4/1] items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-zinc-950/20">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-700">Empty</p>
                  </div>
                ) : (
                  columnOrders.map((order) => (
                    <PipelineCard key={order.id} order={order} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
      <ScrollBar orientation="horizontal" className="bg-zinc-950/50" />
    </ScrollArea>
  );
}
