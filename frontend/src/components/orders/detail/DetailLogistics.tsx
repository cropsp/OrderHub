import { MapPin, Phone, ClipboardList } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { OrderDetail } from '@/types/order';

interface DetailLogisticsProps {
  order: OrderDetail;
  canManageShipping: boolean;
  isPending: boolean;
  onGenerateTTN: () => void;
}

export function DetailLogistics({ order, canManageShipping, isPending, onGenerateTTN }: DetailLogisticsProps) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden flex flex-col">
      <div className="p-3.5">
        <h3 className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-3.5 px-0.5">
          Shipping & Logistics
        </h3>
        
        <div className="space-y-2.5 px-0.5">
          <div className="flex items-start gap-3">
            <div className="text-[10px] text-zinc-400 leading-tight space-y-0">
              <p className="font-bold text-zinc-200">{order.shipping_name || 'No recipient'}</p>
              <p>{order.shipping_street_1}</p>
              {order.shipping_street_2 && <p>{order.shipping_street_2}</p>}
              <p>{order.shipping_city}, {order.shipping_state} {order.shipping_zip}</p>
              <p className="font-black text-zinc-600 uppercase tracking-widest mt-1 text-[8px]">{order.shipping_country}</p>
            </div>
          </div>
          
          {order.shipping_phone && (
            <div className="flex items-center gap-1.5 text-[9px] text-zinc-500 font-bold uppercase tracking-widest pt-1">
              <Phone className="size-2.5 text-zinc-700" />
              <span>{order.shipping_phone}</span>
            </div>
          )}

          {order.ttn_number && (
            <div className="mt-2 p-2.5 rounded-lg bg-teal-500/5 border border-teal-500/10 hover:bg-teal-500/10 transition-colors cursor-pointer group">
              <div className="flex items-center justify-between mb-0.5">
                <p className="text-[8px] font-black text-teal-500/70 uppercase tracking-widest">Tracking (TTN)</p>
                <ClipboardList className="size-2.5 text-teal-500/40" />
              </div>
              <p className="font-mono text-xs text-zinc-100 font-bold tracking-tight">{order.ttn_number}</p>
            </div>
          )}
        </div>
      </div>

      {!order.ttn_number && order.shipping_country === 'UA' && canManageShipping && (
        <div className="p-2 border-t border-zinc-800/50 bg-zinc-950/20">
          <Button 
            className="w-full h-8 rounded-lg bg-zinc-800 border border-zinc-800 hover:bg-zinc-800/80 hover:border-zinc-700 text-teal-400 font-bold text-[9px] uppercase tracking-widest transition-all"
            variant="ghost"
            disabled={isPending}
            onClick={onGenerateTTN}
          >
            {isPending ? 'Connecting...' : 'Generate NP Label'}
          </Button>
        </div>
      )}
    </div>
  );
}
