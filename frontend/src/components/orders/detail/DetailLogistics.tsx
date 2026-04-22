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
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden flex flex-col shadow-sm">
      <div className="p-4">
        <h3 className="text-sm font-semibold text-zinc-100 mb-4 px-1">
          Shipping & Logistics
        </h3>
        
        <div className="space-y-4 px-1">
          <div className="flex items-start gap-3">
            <div className="text-sm text-zinc-400 leading-normal space-y-1">
              <p className="font-semibold text-zinc-200">{order.shipping_name || 'No recipient'}</p>
              <p>{order.shipping_street_1}</p>
              {order.shipping_street_2 && <p>{order.shipping_street_2}</p>}
              <p className="text-zinc-500">{order.shipping_city}, {order.shipping_state} {order.shipping_zip}</p>
              <p className="font-bold text-zinc-600 uppercase tracking-widest mt-2 text-[11px]">{order.shipping_country}</p>
            </div>
          </div>
          
          {order.shipping_phone && (
            <div className="flex items-center gap-2 text-[11px] text-zinc-500 font-medium pt-2 border-t border-zinc-800/30">
              <Phone className="size-3.5 text-zinc-700" />
              <span>{order.shipping_phone}</span>
            </div>
          )}

          {order.ttn_number && (
            <div className="mt-2 p-2.5 rounded-lg bg-teal-500/5 border border-teal-500/10 hover:bg-teal-500/10 transition-colors cursor-pointer group">
              <div className="flex items-center justify-between mb-0.5">
                <p className="text-[11px] font-semibold text-teal-500/70">Tracking (TTN)</p>
                <ClipboardList className="size-3 text-teal-500/40" />
              </div>
              <p className="font-mono text-sm text-teal-100 font-bold">{order.ttn_number}</p>
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
