import { useState } from 'react';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { statusLabel, type OrderStatusValue } from '@/lib/order-status';
import { cn } from '@/lib/utils';
import type { OrderListItem } from '@/types/order';
import PipelineCard from './PipelineCard';

type PipelineBoardProps = {
  orders: OrderListItem[];
  columnStatuses: OrderStatusValue[];
  isLoading?: boolean;
};

const CountPill = ({ count }: { count: number }) => (
  <span className="ml-2 text-[10px] tabular-nums text-zinc-600 bg-zinc-800/50 px-1.5 py-0.5 rounded-full">
    {count}
  </span>
);

const EmptyColumn = () => (
  <div className="flex aspect-[4/1] items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-zinc-950/20">
    <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-700">Empty</p>
  </div>
);

export default function PipelineBoard({ orders, columnStatuses, isLoading }: PipelineBoardProps) {
  // Mobile: which status column is shown (chips switch it). Default to the first column.
  const [activeStatus, setActiveStatus] = useState<OrderStatusValue>(columnStatuses[0]);

  if (isLoading) {
    return (
      <div className="flex h-[500px] items-center justify-center rounded-lg border border-zinc-800/50 bg-zinc-900/20">
        <p className="text-sm text-zinc-400 animate-pulse">Loading board...</p>
      </div>
    );
  }

  const ordersFor = (status: OrderStatusValue) => orders.filter((o) => o.status === status);
  // Keep the mobile selection valid if the active category / columns change underneath us.
  const mobileStatus = columnStatuses.includes(activeStatus) ? activeStatus : columnStatuses[0];
  const mobileOrders = ordersFor(mobileStatus);

  return (
    <>
      {/* DESKTOP: horizontal board. Columns keep a usable width and scroll internally so a tall
          column no longer balloons the whole page. */}
      <div className="hidden lg:block">
        <ScrollArea className="w-full whitespace-nowrap rounded-xl border border-zinc-800 bg-zinc-900/40 backdrop-blur-sm">
          <div className="flex w-max min-h-[600px] p-6 gap-6">
            {columnStatuses.map((status) => {
              const columnOrders = ordersFor(status);
              return (
                <div key={status} className="flex h-full w-[300px] min-w-[280px] flex-col shrink-0">
                  <div className="mb-4 flex items-center justify-between px-1">
                    <h3 className="text-[10px] font-bold uppercase tracking-[0.1em] text-zinc-400">
                      {statusLabel(status)}
                      <CountPill count={columnOrders.length} />
                    </h3>
                  </div>

                  <div
                    tabIndex={0}
                    className="flex flex-col gap-3 max-h-[70vh] overflow-y-auto pr-1 rounded-lg focus:outline-none focus-visible:ring-1 focus-visible:ring-teal-500/40 [&>*]:shrink-0"
                  >
                    {columnOrders.length === 0 ? (
                      <EmptyColumn />
                    ) : (
                      columnOrders.map((order) => <PipelineCard key={order.id} order={order} />)
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <ScrollBar orientation="horizontal" className="bg-zinc-950/50" />
        </ScrollArea>
      </div>

      {/* MOBILE: a scrollable row of status chips picks one full-width column, so every status is
          reachable instead of one endless off-screen board. */}
      <div className="lg:hidden rounded-xl border border-zinc-800 bg-zinc-900/40 backdrop-blur-sm p-4">
        <div className="flex items-center gap-2 overflow-x-auto pb-3 -mx-1 px-1">
          {columnStatuses.map((status) => {
            const isActive = status === mobileStatus;
            return (
              <button
                key={status}
                type="button"
                onClick={() => setActiveStatus(status)}
                className={cn(
                  'shrink-0 rounded-md border px-2.5 py-1.5 text-xs font-medium uppercase tracking-wide transition',
                  isActive
                    ? 'border-teal-400/40 bg-teal-400/15 text-teal-100'
                    : 'border-zinc-700 bg-zinc-900/70 text-zinc-300 hover:text-zinc-100'
                )}
              >
                {statusLabel(status)}
                <CountPill count={ordersFor(status).length} />
              </button>
            );
          })}
        </div>

        <div className="flex flex-col gap-3">
          {mobileOrders.length === 0 ? <EmptyColumn /> : mobileOrders.map((order) => <PipelineCard key={order.id} order={order} />)}
        </div>
      </div>
    </>
  );
}
