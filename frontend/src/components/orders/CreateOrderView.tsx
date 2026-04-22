import { useNavigate } from 'react-router-dom';
import { 
  Loader2, 
  ChevronLeft, 
  Plus, 
  Globe, 
  User, 
  ShoppingCart,
  AlertCircle
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { useShops } from '@/hooks/useShops';
import { useOrderForm } from './useOrderForm';
import { OrderItemsEditor } from './OrderItemsEditor';

export default function CreateOrderView() {
  const navigate = useNavigate();
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
  } = useOrderForm(() => navigate('/orders'));

  return (
    <div className="flex flex-col min-h-full bg-zinc-950 pb-12 font-sans">
      {/* 1. HEADER */}
      <header className="sticky top-0 z-30 w-full bg-zinc-950/80 backdrop-blur-xl border-b border-zinc-800/50 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={() => navigate('/orders')}
              className="h-8 w-8 text-zinc-500 hover:text-zinc-100 transition-colors"
            >
              <ChevronLeft size={20} />
            </Button>
            <div className="flex flex-col">
              <h1 className="text-xl font-bold text-zinc-100 tracking-tight leading-none">
                Create Manual Order
              </h1>
              <p className="text-xs text-zinc-500 mt-1">Manual entry for custom sales and marketplaces</p>
            </div>
          </div>
        </div>
      </header>

      {/* 2. MAIN CONTENT GRID */}
      <main className="flex-1 mt-6">
        <form onSubmit={handleSubmit} className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-8 p-6 pt-0 items-start">
          
          {/* LEFT COLUMN: Form Data */}
          <div className="space-y-6 min-w-0">
            
            {/* ORIGIN & IDENTITY */}
            <Card className="bg-zinc-900/80 border-zinc-800 shadow-sm rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-zinc-800/50 bg-zinc-900/20 flex items-center gap-2">
                <Globe className="size-4 text-zinc-500" />
                <h3 className="text-sm font-semibold text-zinc-100">Origin & Identity</h3>
              </div>
              <CardContent className="p-6 space-y-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="text-[11px] font-medium text-zinc-500 px-1">Target Shop</label>
                    <Select
                      value={orderData.shop_id}
                      onValueChange={(val) => setOrderData(p => ({ ...p, shop_id: val }))}
                    >
                      <SelectTrigger className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20">
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
                    <label className="text-[11px] font-medium text-zinc-500 px-1">Order # (External ID)</label>
                    <Input 
                      className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                      placeholder="e.g. WH-2024-001"
                      value={orderData.external_id}
                      onChange={e => setOrderData(p => ({ ...p, external_id: e.target.value }))}
                    />
                  </div>
                </div>
                
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                  <div className="sm:col-span-2 space-y-2">
                    <label className="text-[11px] font-medium text-zinc-500 px-1">Brief Description / Title</label>
                    <Input 
                      className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                      placeholder="Custom leather wallet order"
                      value={orderData.title}
                      onChange={e => setOrderData(p => ({ ...p, title: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[11px] font-medium text-zinc-500 px-1">Currency</label>
                    <Select
                      value={orderData.currency}
                      onValueChange={(val) => setOrderData(p => ({ ...p, currency: val }))}
                    >
                      <SelectTrigger className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100">
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
              </CardContent>
            </Card>

            {/* CUSTOMER INFORMATION */}
            <Card className="bg-zinc-900/80 border-zinc-800 shadow-sm rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-zinc-800/50 bg-zinc-900/20 flex items-center gap-2">
                <User className="size-4 text-zinc-500" />
                <h3 className="text-sm font-semibold text-zinc-100">Customer Information</h3>
              </div>
              <CardContent className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-[11px] font-medium text-zinc-500 px-1">Contact Email</label>
                  <Input 
                    className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                    placeholder="customer@example.com"
                    value={orderData.email}
                    onChange={e => setOrderData(p => ({ ...p, email: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[11px] font-medium text-zinc-500 px-1">Full Name</label>
                  <Input 
                    className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                    placeholder="Serhii Kovalenko"
                    value={orderData.full_name}
                    onChange={e => setOrderData(p => ({ ...p, full_name: e.target.value }))}
                  />
                </div>
              </CardContent>
            </Card>

            {/* ORDER ITEMS */}
            <div className="bg-zinc-900/80 border border-zinc-800 shadow-sm rounded-xl overflow-hidden">
               <div className="px-5 py-4 border-b border-zinc-800/50 bg-zinc-900/20 flex items-center gap-2">
                  <ShoppingCart className="size-4 text-zinc-500" />
                  <h3 className="text-sm font-semibold text-zinc-100">Order Composition</h3>
               </div>
               <div className="p-6">
                  <OrderItemsEditor 
                    items={items}
                    currency={orderData.currency}
                    onAddItem={addItem}
                    onRemoveItem={removeItem}
                    onUpdateItem={updateItem}
                  />
               </div>
            </div>

            {error && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-sm text-red-400">
                 <AlertCircle className="size-5 shrink-0" />
                 {error}
              </div>
            )}
          </div>

          {/* RIGHT COLUMN: Summary & Actions (Sticky) */}
          <aside className="sticky top-24 space-y-6">
            
            {/* ORDER SUMMARY */}
            <Card className="bg-zinc-900/80 border-zinc-800 shadow-sm rounded-xl overflow-hidden">
               <div className="px-5 py-4 border-b border-zinc-800/50 bg-zinc-900/20">
                  <h3 className="text-sm font-semibold text-zinc-100">Order Summary</h3>
               </div>
               <CardContent className="p-6 space-y-6">
                  <div className="flex flex-col items-center py-4 bg-zinc-950/40 rounded-2xl border border-zinc-800/50">
                    <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-widest mb-1">Total Revenue</p>
                    <div className="flex items-baseline gap-2">
                      <span className="text-4xl font-black text-zinc-100 tracking-tighter">
                        {totalPrice.toFixed(2)}
                      </span>
                      <span className="text-sm font-bold text-teal-500 uppercase">{orderData.currency}</span>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <Button
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full bg-teal-600 hover:bg-teal-500 text-white font-semibold h-11 rounded-xl shadow-lg shadow-teal-900/20 transition-all gap-2"
                    >
                      {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : <Plus size={18} />}
                      {isSubmitting ? 'Creating...' : 'Create Order'}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => navigate('/orders')}
                      className="w-full text-zinc-500 hover:text-zinc-100 hover:bg-zinc-800/50 h-11 rounded-xl transition-all"
                    >
                      Discard changes
                    </Button>
                  </div>
               </CardContent>
            </Card>

            <div className="px-4">
              <p className="text-xs text-zinc-600 leading-relaxed text-center">
                Manual orders are immediately active and visible to all managers. No external platform sync will be performed.
              </p>
            </div>
          </aside>
        </form>
      </main>
    </div>
  );
}
