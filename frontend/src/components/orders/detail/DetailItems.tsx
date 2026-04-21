import { Package } from 'lucide-react';
import { BentoCard } from './BentoCard';
import type { OrderDetail } from '@/types/order';

interface DetailItemsProps {
  order: OrderDetail;
}

export function DetailItems({ order }: DetailItemsProps) {
  return (
    <BentoCard title="Product Inventory" icon={Package} className="p-0 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-white/[0.03] bg-white/[0.01]">
              <th className="px-8 py-5 text-[10px] uppercase font-bold tracking-[0.2em] text-slate-500">Item Details</th>
              <th className="px-8 py-5 text-[10px] uppercase font-bold tracking-[0.2em] text-slate-500 text-center">Qty</th>
              <th className="px-8 py-5 text-[10px] uppercase font-bold tracking-[0.2em] text-slate-500 text-right">Unit Price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.03]">
            {order.items.map((item) => (
              <tr key={item.id} className="hover:bg-white/[0.01] transition-colors">
                <td className="px-8 py-6">
                  <div className="flex flex-col gap-1">
                    <p className="text-base font-bold text-slate-200">{item.title}</p>
                    {item.variations && (
                      <p className="text-xs text-slate-500 font-medium">{item.variations}</p>
                    )}
                    {item.sku && (
                      <span className="mt-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-teal-500/5 text-teal-500/70 border border-teal-500/10 w-fit">
                        SKU: {item.sku}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-8 py-6 text-center">
                  <span className="text-lg font-heading font-bold text-slate-400 italic">x{item.quantity}</span>
                </td>
                <td className="px-8 py-6 text-right">
                  <p className="text-lg font-bold text-slate-100">{item.unit_price} <span className="text-[10px] text-slate-500 uppercase">{item.currency}</span></p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BentoCard>
  );
}
