import { format } from 'date-fns';
import { 
  Check, 
  Loader2, 
  ChevronDown 
} from 'lucide-react';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { getShopTheme } from '@/utils/shopTheme';
import { cn } from '@/lib/utils';
import { ORDER_STATUS } from '@/lib/order-status';
import type { OrderDetail } from '@/types/order';

interface DetailHeaderProps {
  order: OrderDetail;
  saveStatus: 'idle' | 'saving' | 'saved' | 'error';
  dataUpdatedAt: number;
  onStatusChange: (status: string) => void;
  onClose: () => void;
}

export function DetailHeader({ order, saveStatus, dataUpdatedAt, onStatusChange, onClose }: DetailHeaderProps) {
  const shopTheme = getShopTheme(order.shop_name ?? '');

  return (
    <header className="px-10 py-8 flex flex-col gap-6 border-b border-zinc-800 bg-zinc-950/50 backdrop-blur-md shrink-0">
      <div className="flex items-center justify-between w-full">
        <button 
          onClick={onClose}
          className="text-sm text-zinc-400 hover:text-zinc-100 flex items-center gap-1.5 transition-colors"
        >
          <span>←</span> Back to Orders
        </button>

        <div className="flex items-center gap-4">
          <div className={cn(
            "flex items-center gap-1.5 transition-opacity duration-300",
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

      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <h2 className="text-2xl font-bold text-zinc-50 tracking-tight leading-tight max-w-2xl">
            {order.title}
          </h2>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <div className={cn("inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider", shopTheme.bg, shopTheme.text)}>
              {order.shop_name}
            </div>
            <span className="font-mono">#{order.external_id}</span>
            <span>·</span>
            <span>{format(new Date(order.ordered_at), 'MMM dd, HH:mm')}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <StatusBadge status={order.status} size="md" className="h-9 px-4 rounded-lg" />
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="h-9 border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 font-bold uppercase text-[10px] tracking-widest gap-2">
                Change Status <ChevronDown className="size-3 opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="bg-zinc-900 border-zinc-800 text-zinc-300 w-48">
              {Object.entries(ORDER_STATUS).map(([key, value]) => (
                <DropdownMenuItem 
                  key={value} 
                  onClick={() => onStatusChange(value)}
                  className="text-[10px] font-bold uppercase tracking-widest focus:bg-zinc-800 focus:text-zinc-100"
                >
                  {key.replace('_', ' ')}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
