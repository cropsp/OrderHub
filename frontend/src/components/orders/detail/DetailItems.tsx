import type { OrderDetail } from '@/types/order';

interface DetailItemsProps {
  order: OrderDetail;
}

export function DetailItems({ order }: DetailItemsProps) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-zinc-800/50 bg-zinc-900/20">
        <h3 className="text-sm font-semibold text-zinc-100">
          Product inventory
        </h3>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-zinc-800/30 bg-zinc-900/40">
              <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500">Item details</th>
              <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 text-right">Qty</th>
              <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 text-right">Unit price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/20">
            {order.items?.map((item) => (
              <tr key={item.id} className="group hover:bg-white/[0.01] transition-colors">
                <td className="px-4 py-4">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm font-semibold text-zinc-200 group-hover:text-teal-400 transition-colors leading-tight">
                      {item.title}
                    </span>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[11px] font-mono text-zinc-500 uppercase tracking-tight">
                        SKU: {item.sku || 'N/A'}
                      </span>
                      {item.variations && (
                        <>
                          <span className="text-zinc-800">·</span>
                          <span className="text-[11px] text-zinc-500 italic">
                            {item.variations}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-4 text-right align-top">
                  <span className="text-sm font-medium text-zinc-400">
                    ×{item.quantity}
                  </span>
                </td>
                <td className="px-4 py-4 text-right align-top">
                  <span className="text-sm font-medium text-zinc-300">
                    {item.unit_price.toFixed(2)} <span className="text-[11px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
                  </span>
                </td>
              </tr>
            ))}
            <tr className="bg-zinc-950/30 border-t border-zinc-800/50">
              <td colSpan={2} className="px-4 py-3.5 text-right">
                <span className="text-sm font-medium text-zinc-500">Subtotal</span>
              </td>
              <td className="px-4 py-3.5 text-right">
                <span className="text-sm font-bold text-zinc-100">
                  {order.total_price.toFixed(2)} <span className="text-[11px] text-zinc-500 uppercase ml-0.5">{order.currency}</span>
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
