import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import type { OrderDetail } from '@/types/order';

interface DetailTimelineProps {
  order: OrderDetail;
}

export function DetailTimeline({ order }: DetailTimelineProps) {
  const history = order.status_history || [];

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-zinc-100 mb-4 px-1">
        Timeline
      </h3>
      
      <div className="relative pl-3 space-y-6 before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[1px] before:bg-zinc-800">
        {history.length > 0 ? (
          history.map((entry, idx) => (
            <div key={entry.id || idx} className="relative flex flex-col gap-1.5">
              <div className={cn(
                "absolute -left-[3px] top-1.5 size-1.5 rounded-full ring-4 ring-zinc-900 shadow-sm",
                idx === 0 ? "bg-teal-500 shadow-teal-500/20" : "bg-zinc-700"
              )} />
              
              <div className="flex flex-col pl-4">
                <div className="flex items-center justify-between">
                  <span className={cn(
                    "text-sm font-semibold",
                    idx === 0 ? "text-zinc-100" : "text-zinc-400"
                  )}>
                    {entry.to_status.replace(/_/g, ' ')}
                  </span>
                  <span className="text-[11px] font-medium text-zinc-500">
                    {format(new Date(entry.changed_at), 'MMM dd, HH:mm')}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {entry.changed_by_name || 'System'}
                </p>
              </div>
              
              {entry.comment && (
                <div className="mt-1 ml-4 p-3 rounded bg-zinc-950/40 border border-zinc-800/50">
                  <p className="text-sm text-zinc-400 leading-relaxed italic">
                    "{entry.comment}"
                  </p>
                </div>
              )}
            </div>
          ))
        ) : (
          <p className="text-sm text-zinc-500 italic px-4 text-center">No history recorded</p>
        )}
      </div>
    </div>
  );
}
