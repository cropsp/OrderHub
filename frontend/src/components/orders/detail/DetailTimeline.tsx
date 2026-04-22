import { format } from 'date-fns';
import { History, CheckCircle2, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { BentoCard } from './BentoCard';
import type { OrderDetail } from '@/types/order';

interface DetailTimelineProps {
  order: OrderDetail;
}

export function DetailTimeline({ order }: DetailTimelineProps) {
  return (
    <BentoCard title="Timeline" icon={History}>
      <div className="relative pl-6 space-y-10 before:absolute before:inset-0 before:left-0 before:h-full before:w-px before:bg-white/[0.05]">
        {order.status_history.map((entry, idx) => (
          <div key={entry.id} className="relative group">
            <div className={cn(
              "absolute -left-[27px] top-1 size-3 rounded-full border border-zinc-950 ring-[6px] ring-zinc-950/50",
              idx === 0 ? "bg-teal-500 shadow-[0_0_10px_rgba(20,184,166,0.5)]" : "bg-zinc-700"
            )} />
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <p className="text-[10px] font-bold text-zinc-200 uppercase tracking-tighter">
                  {entry.to_status.replace('_', ' ')}
                </p>
                <span className="text-[9px] text-zinc-600 font-medium uppercase tracking-[0.1em]">
                  {format(new Date(entry.changed_at), 'MMM dd, HH:mm')}
                </span>
              </div>
              <div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                {idx === 0 ? <CheckCircle2 className="size-2.5 text-teal-500" /> : <Clock className="size-2.5 text-zinc-600" />}
                <p className="text-[9px] text-zinc-500 font-bold uppercase tracking-widest">
                  {entry.changed_by_name || 'System Auto'}
                </p>
              </div>
              {entry.comment && (
                <div className="mt-3 text-[11px] p-4 rounded-2xl bg-white/[0.015] border border-white/[0.03] text-zinc-400 leading-relaxed group-hover:text-zinc-200 transition-colors">
                  {entry.comment}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </BentoCard>
  );
}
