import type { OrderDetail } from '@/types/order';

interface DetailItemsProps {
  order: OrderDetail;
}

export function DetailItems({ order }: DetailItemsProps) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden">
      <div className="px-3.5 py-2.5 border-b border-zinc-800/50 bg-zinc-950/20">
        <h3 className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest">
          Product Inventory
        </h3>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-zinc-800/30 bg-zinc-900/40">
              <th className="px-3.5 py-2 text-[8px] font-black text-zinc-600 uppercase tracking-widest">Item Details</th>
              <th className="px-3.5 py-2 text-[8px] font-black text-zinc-600 uppercase tracking-widest text-right">Qty</th>
              <th className="px-3.5 py-2 text-[8px] font-black text-zinc-600 uppercase tracking-widest text-right">Unit Price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/20">
            {order.items?.map((item) => (
              <tr key={item.id} className="group hover:bg-white/[0.01] transition-colors">
                <td className="px-3.5 py-2.5">
                  <div className="flex flex-col gap-0">
                    <span className="text-[11px] font-bold text-zinc-200 group-hover:text-teal-400 transition-colors leading-tight">
                      {item.title}
                    </span>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="text-[8px] font-mono text-zinc-600 uppercase tracking-tight">
                        SKU: {item.sku || 'N/A'}
                      </span>
                      {item.variations && (
                        <>
                          <span className="text-zinc-800">·</span>
                          <span className="text-[8px] text-zinc-500 italic">
                            {item.variations}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </td>
                <td className="px-3.5 py-2.5 text-right align-top">
                  <span className="text-[11px] font-bold text-zinc-500">
                    ×{item.quantity}
                  </span>
                </td>
                <td className="px-3.5 py-2.5 text-right align-top">
                  <span className="text-[11px] font-mono text-zinc-500">
                    {item.unit_price.toFixed(2)} <span className="text-[8px] opacity-40">{item.currency}</span>
                  </span>
                </td>
              </tr>
            ))}
            <tr className="bg-zinc-950/30 border-t border-zinc-800/50">
              <td colSpan={2} className="px-3.5 py-2 text-right">
                <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">Subtotal</span>
              </td>
              <td className="px-3.5 py-2 text-right">
                <span className="text-[11px] font-black text-zinc-200">
                  {order.total_price.toFixed(2)} <span className="text-[8px] opacity-50">{order.currency}</span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div className="px-4 py-2 bg-zinc-950/50 border-t border-zinc-800/30 flex justify-end">
        <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
          Total Items: <span className="text-zinc-400 ml-1">{order.items?.reduce((acc, item) => acc + item.quantity, 0)}</span>
        </p>
      </div>
    </div>
  );
}
