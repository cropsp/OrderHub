import { 
  User, 
  Globe,
  Loader2,
  PackagePlus,
  AlertCircle,
  Plus
} from 'lucide-react';
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

import { useOrderForm } from './useOrderForm';
import { OrderItemsEditor } from './OrderItemsEditor';

type NewOrderDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export default function NewOrderDialog({ open, onOpenChange }: NewOrderDialogProps) {
  const { data: shops } = useShops();
  const {
    orderData,
    setOrderData,
    items,
    addItem,
    removeItem,
    updateItem,
    totalPrice,
    error,
    isSubmitting,
    handleSubmit
  } = useOrderForm(() => onOpenChange(false));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl border-zinc-800 bg-zinc-950 p-0 overflow-hidden rounded-3xl shadow-[0_0_50px_-12px_rgba(0,0,0,0.5)]">
        <form onSubmit={handleSubmit} className="flex flex-col max-h-[85vh]">
          <DialogHeader className="p-8 pb-4 bg-zinc-900/20">
            <div className="flex items-center gap-3 mb-2">
               <div className="size-10 rounded-2xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400">
                  <PackagePlus className="size-6" />
               </div>
               <div>
                  <DialogTitle className="text-2xl font-bold text-zinc-50 tracking-tight">Create Manual Order</DialogTitle>
                  <DialogDescription className="text-zinc-400">Entry point for local marketplaces and custom sales.</DialogDescription>
               </div>
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto p-8 pt-2 space-y-8">
            {/* Section 1: Origin & Identity */}
            <section className="space-y-4">
              <div className="flex items-center gap-2 text-teal-500">
                 <Globe className="size-4" />
                 <h3 className="text-xs font-bold uppercase tracking-widest">Origin & Identity</h3>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase text-zinc-500 px-1">Target Shop</p>
                  <Select
                    value={orderData.shop_id}
                    onValueChange={(val) => setOrderData(p => ({ ...p, shop_id: val }))}
                  >
                    <SelectTrigger className="border-zinc-800 bg-zinc-900/50 rounded-xl">
                      <SelectValue placeholder="Select destination store" />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-950 border-zinc-800 text-zinc-100">
                      {shops?.map(shop => (
                        <SelectItem key={shop.id} value={shop.id}>{shop.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase text-zinc-500 px-1">Order # (External ID)</p>
                  <Input 
                    className="border-zinc-800 bg-zinc-900/50 rounded-xl text-zinc-100"
                    placeholder="e.g. WH-2024-001"
                    value={orderData.external_id}
                    onChange={e => setOrderData(p => ({ ...p, external_id: e.target.value }))}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="sm:col-span-2 space-y-2">
                  <p className="text-[10px] font-bold uppercase text-zinc-500 px-1">Brief Description / Title</p>
                  <Input 
                    className="border-zinc-800 bg-zinc-900/50 rounded-xl text-zinc-100"
                    placeholder="Custom leather wallet order"
                    value={orderData.title}
                    onChange={e => setOrderData(p => ({ ...p, title: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase text-zinc-500 px-1">Currency</p>
                  <Select
                    value={orderData.currency}
                    onValueChange={(val) => setOrderData(p => ({ ...p, currency: val }))}
                  >
                    <SelectTrigger className="border-zinc-800 bg-zinc-900/50 rounded-xl text-zinc-100">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-950 border-zinc-800 text-zinc-100">
                      <SelectItem value="USD">🇺🇸 USD</SelectItem>
                      <SelectItem value="UAH">🇺🇦 UAH</SelectItem>
                      <SelectItem value="EUR">🇪🇺 EUR</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            {/* Section 2: Customer Information */}
            <section className="space-y-4">
              <div className="flex items-center gap-2 text-indigo-400">
                 <User className="size-4" />
                 <h3 className="text-xs font-bold uppercase tracking-widest">Customer Information</h3>
              </div>
              <Card className="border-zinc-800/60 bg-zinc-900/20 rounded-2xl overflow-hidden shadow-inner">
                <CardContent className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <p className="text-[10px] font-bold uppercase text-zinc-500 px-1">Contact Email</p>
                    <Input 
                      className="border-zinc-800 bg-zinc-900/50 rounded-xl text-zinc-100"
                      placeholder="customer@example.com"
                      value={orderData.email}
                      onChange={e => setOrderData(p => ({ ...p, email: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <p className="text-[10px] font-bold uppercase text-zinc-500 px-1">Full Name</p>
                    <Input 
                      className="border-zinc-800 bg-zinc-900/50 rounded-xl text-zinc-100"
                      placeholder="Serhii Kovalenko"
                      value={orderData.full_name}
                      onChange={e => setOrderData(p => ({ ...p, full_name: e.target.value }))}
                    />
                  </div>
                </CardContent>
              </Card>
            </section>

            {/* Section 3: Order Composition (Items) */}
            <OrderItemsEditor 
              items={items}
              currency={orderData.currency}
              onAddItem={addItem}
              onRemoveItem={removeItem}
              onUpdateItem={updateItem}
            />
          </div>

          {error && (
            <div className="px-8 py-3 bg-red-500/10 border-y border-red-500/20 flex items-center gap-2 text-xs text-red-400">
               <AlertCircle className="size-4" />
               {error}
            </div>
          )}

          <DialogFooter className="p-8 bg-zinc-900/40 border-t border-zinc-800/60 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="text-center sm:text-left">
               <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Order Revenue</p>
               <div className="flex items-baseline justify-center sm:justify-start gap-1.5">
                  <span className="text-3xl font-black text-zinc-50 tracking-tighter">{totalPrice.toFixed(2)}</span>
                  <span className="text-sm font-bold text-teal-500 uppercase">{orderData.currency}</span>
               </div>
            </div>
            <div className="flex gap-3 w-full sm:w-auto">
              <Button
                type="button"
                variant="ghost"
                className="flex-1 sm:flex-none text-zinc-400 hover:text-zinc-100 rounded-xl"
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
