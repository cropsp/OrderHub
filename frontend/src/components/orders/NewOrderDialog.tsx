import { useState } from 'react';
import { 
  Plus, 
  Trash2, 
  User, 
  ShoppingCart, 
  Globe,
  Loader2,
  PackagePlus,
  AlertCircle
} from 'lucide-react';
import { useCreateOrder } from '@/hooks/useOrders';
import { useShops } from '@/hooks/useShops';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';

type NewOrderDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const INITIAL_ITEM = { title: '', quantity: 1, unit_price: 0 };

export default function NewOrderDialog({ open, onOpenChange }: NewOrderDialogProps) {
  const { data: shops } = useShops();
  const createOrder = useCreateOrder();
  
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const [orderData, setOrderData] = useState({
    shop_id: '',
    external_id: '',
    title: '',
    currency: 'USD',
    email: '',
    full_name: '',
  });

  const [items, setItems] = useState([INITIAL_ITEM]);

  const addItem = () => setItems([...items, { ...INITIAL_ITEM }]);
  const removeItem = (index: number) => setItems(items.filter((_, i) => i !== index));
  const updateItem = (index: number, field: string, value: any) => {
    const newItems = [...items];
    (newItems[index] as any)[field] = value;
    setItems(newItems);
  };

  const totalPrice = items.reduce((sum, item) => sum + (item.quantity * item.unit_price), 0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orderData.shop_id) return setError('Please select a shop.');
    if (!orderData.email) return setError('Customer email is required.');
    if (items.length === 0 || !items[0].title) return setError('At least one item is required.');

    setIsSubmitting(true);
    setError(null);

    try {
      await createOrder.mutateAsync({
        ...orderData,
        ordered_at: new Date().toISOString(),
        total_price: totalPrice,
        items: items.map(it => ({
          ...it,
          currency: orderData.currency
        }))
      });
      onOpenChange(false);
      // Reset form
      setOrderData({
        shop_id: '',
        external_id: '',
        title: '',
        currency: 'USD',
        email: '',
        full_name: '',
      });
      setItems([{ ...INITIAL_ITEM }]);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create order');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl border-slate-800 bg-slate-950 p-0 overflow-hidden rounded-3xl shadow-[0_0_50px_-12px_rgba(0,0,0,0.5)]">
        <form onSubmit={handleSubmit} className="flex flex-col max-h-[85vh]">
          <DialogHeader className="p-8 pb-4 bg-slate-900/20">
            <div className="flex items-center gap-3 mb-2">
               <div className="size-10 rounded-2xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400">
                  <PackagePlus className="size-6" />
               </div>
               <div>
                  <DialogTitle className="text-2xl font-bold text-slate-50 tracking-tight">Create Manual Order</DialogTitle>
                  <DialogDescription className="text-slate-400">Entry point for local marketplaces and custom sales.</DialogDescription>
               </div>
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto p-8 pt-2 space-y-8">
            {/* Section 1: Core Info */}
            <section className="space-y-4">
              <div className="flex items-center gap-2 text-teal-500">
                 <Globe className="size-4" />
                 <h3 className="text-xs font-bold uppercase tracking-widest">Origin & Identity</h3>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase text-slate-500 px-1">Target Shop</p>
                  <Select
                    value={orderData.shop_id}
                    onValueChange={(val) => setOrderData(p => ({ ...p, shop_id: val }))}
                  >
                    <SelectTrigger className="border-slate-800 bg-slate-900/50 rounded-xl">
                      <SelectValue placeholder="Select destination store" />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-950 border-slate-800 text-slate-100">
                      {shops?.map(shop => (
                        <SelectItem key={shop.id} value={shop.id}>{shop.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase text-slate-500 px-1">Order # (External ID)</p>
                  <Input 
                    className="border-slate-800 bg-slate-900/50 rounded-xl text-slate-100"
                    placeholder="e.g. WH-2024-001"
                    value={orderData.external_id}
                    onChange={e => setOrderData(p => ({ ...p, external_id: e.target.value }))}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="sm:col-span-2 space-y-2">
                  <p className="text-[10px] font-bold uppercase text-slate-500 px-1">Brief Description / Title</p>
                  <Input 
                    className="border-slate-800 bg-slate-900/50 rounded-xl text-slate-100"
                    placeholder="Custom leather wallet order"
                    value={orderData.title}
                    onChange={e => setOrderData(p => ({ ...p, title: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase text-slate-500 px-1">Currency</p>
                  <Select
                    value={orderData.currency}
                    onValueChange={(val) => setOrderData(p => ({ ...p, currency: val }))}
                  >
                    <SelectTrigger className="border-slate-800 bg-slate-900/50 rounded-xl text-slate-100">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-950 border-slate-800 text-slate-100">
                      <SelectItem value="USD">🇺🇸 USD</SelectItem>
                      <SelectItem value="UAH">🇺🇦 UAH</SelectItem>
                      <SelectItem value="EUR">🇪🇺 EUR</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            {/* Section 2: Customer */}
            <section className="space-y-4">
              <div className="flex items-center gap-2 text-indigo-400">
                 <User className="size-4" />
                 <h3 className="text-xs font-bold uppercase tracking-widest">Customer Information</h3>
              </div>
              <Card className="border-slate-800/60 bg-slate-900/20 rounded-2xl overflow-hidden shadow-inner">
                <CardContent className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <p className="text-[10px] font-bold uppercase text-slate-500 px-1">Contact Email</p>
                    <Input 
                      className="border-slate-800 bg-slate-900/50 rounded-xl text-slate-100"
                      placeholder="customer@example.com"
                      value={orderData.email}
                      onChange={e => setOrderData(p => ({ ...p, email: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <p className="text-[10px] font-bold uppercase text-slate-500 px-1">Full Name</p>
                    <Input 
                      className="border-slate-800 bg-slate-900/50 rounded-xl text-slate-100"
                      placeholder="Serhii Kovalenko"
                      value={orderData.full_name}
                      onChange={e => setOrderData(p => ({ ...p, full_name: e.target.value }))}
                    />
                  </div>
                </CardContent>
              </Card>
            </section>

            {/* Section 3: Items */}
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
                  onClick={addItem}
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
                        onChange={e => updateItem(idx, 'title', e.target.value)}
                      />
                    </div>
                    <div className="w-20 space-y-2">
                       <p className="text-[10px] font-bold uppercase text-slate-600 px-1 text-center">Qty</p>
                       <Input 
                        type="number"
                        className="h-9 border-slate-800 bg-slate-900/40 rounded-lg text-center text-slate-100"
                        value={item.quantity}
                        onChange={e => updateItem(idx, 'quantity', parseInt(e.target.value) || 1)}
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
                            onChange={e => updateItem(idx, 'unit_price', parseFloat(e.target.value) || 0)}
                          />
                          <span className="absolute right-2.5 top-2.5 text-[10px] font-bold text-slate-600 uppercase">{orderData.currency}</span>
                       </div>
                    </div>
                    <Button 
                      type="button"
                      variant="ghost" 
                      size="icon" 
                      className="size-9 text-slate-600 hover:text-red-400 rounded-lg"
                      onClick={() => removeItem(idx)}
                      disabled={items.length === 1}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {error && (
            <div className="px-8 py-3 bg-red-500/10 border-y border-red-500/20 flex items-center gap-2 text-xs text-red-400">
               <AlertCircle className="size-4" />
               {error}
            </div>
          )}

          <DialogFooter className="p-8 bg-slate-900/40 border-t border-slate-800/60 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="text-center sm:text-left">
               <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Order Revenue</p>
               <div className="flex items-baseline justify-center sm:justify-start gap-1.5">
                  <span className="text-3xl font-black text-slate-50 tracking-tighter">{totalPrice.toFixed(2)}</span>
                  <span className="text-sm font-bold text-teal-500 uppercase">{orderData.currency}</span>
               </div>
            </div>
            <div className="flex gap-3 w-full sm:w-auto">
              <Button
                type="button"
                variant="ghost"
                className="flex-1 sm:flex-none text-slate-400 hover:text-slate-100 rounded-xl"
                onClick={() => onOpenChange(false)}
              >
                Discard
              </Button>
              <Button
                type="submit"
                className="flex-1 sm:flex-none bg-teal-600 text-white hover:bg-teal-500 shadow-xl rounded-xl px-6"
                disabled={isSubmitting}
              >
                {isSubmitting ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Plus className="mr-2 size-4" />}
                {isSubmitting ? 'Creating...' : 'Create Order'}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
