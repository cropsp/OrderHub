import { MapPin, Phone, ClipboardList } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { BentoCard } from './BentoCard';
import type { OrderDetail } from '@/types/order';

interface DetailLogisticsProps {
  order: OrderDetail;
  canManageShipping: boolean;
  isPending: boolean;
  onGenerateTTN: () => void;
}

export function DetailLogistics({ order, canManageShipping, isPending, onGenerateTTN }: DetailLogisticsProps) {
  return (
    <BentoCard title="Shipping & Logistics" icon={MapPin}>
      <div className="space-y-6">
        <div className="flex items-start gap-4">
          <div className="size-10 rounded-xl bg-sky-500/10 flex items-center justify-center border border-sky-500/10 mt-1 shrink-0">
            <MapPin className="size-5 text-sky-500" />
          </div>
          <div className="text-sm text-slate-300 leading-relaxed space-y-1">
            <p className="font-bold text-slate-100">{order.shipping_name}</p>
            <p>{order.shipping_street_1}</p>
            {order.shipping_street_2 && <p>{order.shipping_street_2}</p>}
            <p>{order.shipping_city}, {order.shipping_state} {order.shipping_zip}</p>
            <p className="font-bold text-slate-600 uppercase tracking-[0.3em] mt-2 text-[10px]">{order.shipping_country}</p>
          </div>
        </div>
        
        {order.shipping_phone && (
          <div className="flex items-center gap-3 pl-14 text-xs text-slate-400">
            <Phone className="size-3.5" />
            <span>{order.shipping_phone}</span>
          </div>
        )}

        <div className="pt-2">
          {order.ttn_number ? (
            <div className="p-4 rounded-2xl bg-teal-500/10 border border-teal-500/20 group cursor-pointer hover:bg-teal-500/15 transition-colors">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] font-bold text-teal-500 uppercase tracking-widest">Tracking (TTN)</p>
                <ClipboardList className="size-3 text-teal-500/40" />
              </div>
              <p className="font-mono text-xl text-slate-100 font-bold tracking-tighter">{order.ttn_number}</p>
            </div>
          ) : (
            order.shipping_country === 'UA' && canManageShipping && (
              <Button 
                className="w-full py-6 rounded-2xl bg-slate-900 border-slate-800 hover:bg-slate-800 text-teal-500 font-bold tracking-tight"
                variant="outline"
                disabled={isPending}
                onClick={onGenerateTTN}
              >
                {isPending ? 'Connecting NP...' : 'Generate Shipping Label (NP)'}
              </Button>
            )
          )}
        </div>
      </div>
    </BentoCard>
  );
}
