import { format } from 'date-fns';
import { 
  Tag, 
  Calendar, 
  Hash, 
  Check, 
  Loader2, 
  ChevronDown,
  X
} from 'lucide-react';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { cn } from '@/lib/utils';
import { ORDER_STATUS } from '@/lib/order-status';
import type { OrderDetail } from '@/types/order';

interface DetailHeaderProps {
  order: OrderDetail;
  saveStatus: 'idle' | 'saving' | 'saved' | 'error';
  onStatusChange: (status: string) => void;
  onClose: () => void;
}

export function DetailHeader({ order, saveStatus, onStatusChange, onClose }: DetailHeaderProps) {
  return (
    <header className="px-6 py-4 border-b border-zinc-900 bg-zinc-950/20 shrink-0">
      <div className="max-w-[1600px] mx-auto flex items-center justify-between gap-6">
        <div className="flex flex-col gap-2 min-w-0">
          <h1 className="text-xl font-bold text-white tracking-tight leading-none truncate">
            {order.title || 'Untitled Order'}
          </h1>
          
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-teal-500/10 border border-teal-500/20 shadow-sm">
              <Tag size={10} className="text-teal-400" />
              <span className="text-[9px] font-black text-teal-400 uppercase tracking-[0.1em]">
                {order.shop_name}
              </span>
            </div>
            
            <div className="flex items-center gap-1.5 text-zinc-600">
              <Hash size={12} className="text-zinc-800" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                ID: {order.external_id}
              </span>
            </div>
            
            <div className="flex items-center gap-1.5 text-zinc-600">
              <Calendar size={12} className="text-zinc-800" />
              <span className="text-[10px] font-medium text-zinc-500">
                {format(new Date(order.ordered_at), 'MMM dd, yyyy - HH:mm')}
              </span>
            </div>

            {/* SAVE STATUS INDICATOR */}
            <div className={cn(
              "flex items-center gap-1.5 transition-opacity duration-300 ml-2",
              saveStatus === 'idle' ? "opacity-0" : "opacity-100"
            )}>
              {saveStatus === 'saving' ? (
                <>
                  <Loader2 className="size-3 text-zinc-500 animate-spin" />
                  <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Saving...</span>
                </>
              ) : saveStatus === 'saved' ? (
                <>
                  <Check className="size-3 text-teal-500" />
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Saved</span>
                </>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <StatusBadge status={order.status} size="md" className="h-9 px-4 rounded-lg" />
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="h-9 border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 font-bold uppercase text-[10px] tracking-widest gap-2">
                Action <ChevronDown className="size-3 opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="bg-zinc-900 border-zinc-800 text-zinc-300 w-48">
              {Object.entries(ORDER_STATUS).map(([key, value]) => (
                <DropdownMenuItem 
                  key={value} 
                  onSelect={() => onStatusChange(value)}
                  className="text-[10px] font-bold uppercase tracking-widest focus:bg-zinc-800 focus:text-zinc-100"
                >
                  {key.replace('_', ' ')}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button 
            variant="ghost" 
            size="icon" 
            onClick={onClose}
            className="size-9 text-zinc-500 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl transition-all"
          >
            <X size={18} />
          </Button>
        </div>
      </div>
    </header>
  );
}
