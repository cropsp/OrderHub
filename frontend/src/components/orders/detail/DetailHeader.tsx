import { format } from 'date-fns';
import { Clock, CheckCircle2 } from 'lucide-react';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { ORDER_STATUS, getCategoryByStatus, type OrderStatusValue } from '@/lib/order-status';
import type { OrderDetail } from '@/types/order';

interface DetailHeaderProps {
  order: OrderDetail;
  saveStatus: 'idle' | 'saving' | 'saved' | 'error';
  dataUpdatedAt: number;
  onStatusChange: (status: string) => void;
  onClose: () => void;
}

export function DetailHeader({ order, saveStatus, dataUpdatedAt, onStatusChange, onClose }: DetailHeaderProps) {
  return (
    <header className="px-10 py-8 flex items-center justify-between border-b border-white/[0.03] bg-gradient-to-b from-white/[0.02] to-transparent shrink-0">
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <Select 
            defaultValue={order.status} 
            onValueChange={onStatusChange}
          >
            <SelectTrigger className={cn(
              "h-7 px-3 text-[10px] font-bold uppercase tracking-widest rounded-full border-none ring-offset-slate-950 focus:ring-teal-500/20",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'teal' && "bg-teal-500/10 text-teal-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'sky' && "bg-sky-500/10 text-sky-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'indigo' && "bg-indigo-500/10 text-indigo-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'amber' && "bg-amber-500/10 text-amber-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'orange' && "bg-orange-500/10 text-orange-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'violet' && "bg-violet-500/10 text-violet-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'blue' && "bg-blue-500/10 text-blue-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'emerald' && "bg-emerald-500/10 text-emerald-400",
              getCategoryByStatus(order.status as OrderStatusValue)?.color === 'slate' && "bg-slate-500/10 text-slate-400",
            )}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-950 border-slate-800 text-slate-200">
              {Object.entries(ORDER_STATUS).map(([key, value]) => (
                <SelectItem key={value} value={value} className="text-[10px] uppercase tracking-widest focus:bg-teal-500/20 focus:text-teal-100">
                  {key.replace('_', ' ')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-slate-600 font-medium">/</span>
          <span className="font-mono text-sm font-bold text-teal-400">#{order.external_id}</span>
        </div>
        <h2 className="text-3xl font-heading font-bold text-slate-50 tracking-tight">{order.title}</h2>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex flex-col items-end gap-1 px-4">
           <div className="flex items-center gap-2">
             {saveStatus === 'saving' && <Clock className="size-3 text-amber-400 animate-spin" />}
             {saveStatus === 'saved' && <CheckCircle2 className="size-3 text-teal-400" />}
             <span className={cn(
               "text-[10px] font-bold uppercase tracking-widest",
               saveStatus === 'saving' ? "text-amber-400" : 
               saveStatus === 'saved' ? "text-teal-400" : "text-slate-500"
             )}>
               {saveStatus === 'saving' ? 'Syncing...' : saveStatus === 'saved' ? 'Updates Saved' : 'All Changes Persisted'}
             </span>
           </div>
           <p className="text-[10px] text-slate-600 font-medium">
             Last refetched at {format(dataUpdatedAt, 'HH:mm:ss')}
           </p>
        </div>
        <Separator orientation="vertical" className="h-10 bg-white/[0.05]" />
        <Button onClick={onClose} variant="ghost" className="rounded-full hover:bg-white/[0.03]">
          Close Console
        </Button>
      </div>
    </header>
  );
}
