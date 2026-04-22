import { Plus, Trash2, ShoppingCart } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type Item = {
  title: string;
  quantity: number;
  unit_price: number;
};

type OrderItemsEditorProps = {
  items: Item[];
  currency: string;
  onAddItem: () => void;
  onRemoveItem: (idx: number) => void;
  onUpdateItem: (idx: number, field: string, value: any) => void;
};

export function OrderItemsEditor({ 
  items, 
  currency, 
  onAddItem, 
  onRemoveItem, 
  onUpdateItem 
}: OrderItemsEditorProps) {
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-amber-500">
           <ShoppingCart className="size-4" />
           <h3 className="text-xs font-bold uppercase tracking-widest">Order Composition</h3>
        </div>
        <Button 
          type="button" 
          variant="ghost" 
          size="sm" 
          onClick={onAddItem}
          className="h-8 text-teal-400 hover:text-teal-300 hover:bg-teal-500/10 rounded-lg text-xs"
        >
          <Plus className="mr-1.5 size-3.5" /> Add Item
        </Button>
      </div>

      <div className="space-y-3">
        {items.map((item, idx) => (
          <div key={idx} className="group relative flex flex-wrap sm:flex-nowrap items-end gap-3 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="flex-1 min-w-[200px] space-y-2">
               <p className="text-[10px] font-bold uppercase text-slate-600 px-1">Product Title</p>
               <Input 
                className="h-9 border-slate-800 bg-slate-900/40 rounded-lg text-slate-100"
                placeholder="Item name..."
                value={item.title}
                onChange={e => onUpdateItem(idx, 'title', e.target.value)}
              />
            </div>
            <div className="w-20 space-y-2">
               <p className="text-[10px] font-bold uppercase text-slate-600 px-1 text-center">Qty</p>
               <Input 
                type="number"
                className="h-9 border-slate-800 bg-slate-900/40 rounded-lg text-center text-slate-100"
                value={item.quantity}
                onChange={e => onUpdateItem(idx, 'quantity', parseInt(e.target.value) || 1)}
              />
            </div>
            <div className="w-32 space-y-2">
               <p className="text-[10px] font-bold uppercase text-slate-600 px-1 text-right">Price</p>
               <div className="relative">
                  <Input 
                    type="number"
                    step="0.01"
                    className="h-9 border-slate-800 bg-slate-900/40 rounded-lg text-right pr-10 text-slate-100"
                    value={item.unit_price}
                    onChange={e => onUpdateItem(idx, 'unit_price', parseFloat(e.target.value) || 0)}
                  />
                  <span className="absolute right-2.5 top-2.5 text-[10px] font-bold text-slate-600 uppercase">{currency}</span>
               </div>
            </div>
            <Button 
              type="button"
              variant="ghost" 
              size="icon" 
              className="size-9 text-slate-600 hover:text-red-400 rounded-lg"
              onClick={() => onRemoveItem(idx)}
              disabled={items.length === 1}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
