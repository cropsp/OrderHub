import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Loader2, 
  ChevronLeft, 
  Plus, 
  Globe, 
  User, 
  ShoppingCart,
  AlertCircle,
  Search,
  X
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
import { ScrollArea } from '@/components/ui/scroll-area';
import { useShops } from '@/hooks/useShops';
import { useOrderForm } from './useOrderForm';
import { OrderItemsEditor } from './OrderItemsEditor';
import { useSearchCities, useGetWarehouses } from '@/hooks/useShipping';
import { cn } from '@/lib/utils';

import { customersApi } from '@/api/customers';

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

  const [cityQuery, setCityQuery] = useState('');
  const [warehouseQuery, setWarehouseQuery] = useState('');
  const [isWarehouseOpen, setIsWarehouseOpen] = useState(false);
  const [isSearchingCustomer, setIsSearchingCustomer] = useState(false);

  const { data: cities, isLoading: isCitiesLoading } = useSearchCities(cityQuery);
  const { data: warehouses, isLoading: isWarehousesLoading } = useGetWarehouses(orderData.shipping_city_ref);

  const handleEmailBlur = async () => {
    if (!orderData.email || !orderData.email.includes('@')) return;
    
    setIsSearchingCustomer(true);
    try {
      const customer = await customersApi.getByEmail(orderData.email);
      if (customer) {
        setOrderData(p => ({
          ...p,
          full_name: customer.full_name,
          shipping_name: p.shipping_name || customer.full_name,
          shipping_phone: customer.phone || p.shipping_phone,
          shipping_city: customer.shipping_city || p.shipping_city,
          shipping_city_ref: customer.shipping_city_ref || p.shipping_city_ref,
          shipping_warehouse_ref: customer.shipping_warehouse_ref || p.shipping_warehouse_ref,
          shipping_country: customer.country || p.shipping_country,
        }));
        if (customer.shipping_city) setCityQuery(customer.shipping_city);
      }
    } catch (err) {
      // Not found is fine
    } finally {
      setIsSearchingCustomer(false);
    }
  };

  const filteredWarehouses = useMemo(() => {
    if (!warehouses) return [];
    if (!warehouseQuery) return warehouses.slice(0, 50);
    const q = warehouseQuery.toLowerCase();
    return warehouses
      .filter((w: any) => w.Description.toLowerCase().includes(q))
      .slice(0, 50);
  }, [warehouses, warehouseQuery]);

  const handleCitySelect = (city: any) => {
    setOrderData(p => ({ 
      ...p, 
      shipping_city: city.Description, 
      shipping_city_ref: city.Ref,
      shipping_street_1: '', 
      shipping_warehouse_ref: '' 
    }));
    setCityQuery(city.Description);
    setWarehouseQuery('');
  };

  const handleWarehouseSelect = (warehouse: any) => {
    setOrderData(p => ({ 
      ...p, 
      shipping_street_1: warehouse.Description, 
      shipping_warehouse_ref: warehouse.Ref 
    }));
    setIsWarehouseOpen(false);
    setWarehouseQuery(warehouse.Description);
  };

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
                  <div className="relative">
                    <Input 
                      className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                      placeholder="customer@example.com"
                      value={orderData.email}
                      onChange={e => setOrderData(p => ({ ...p, email: e.target.value }))}
                      onBlur={handleEmailBlur}
                    />
                    {isSearchingCustomer && <Loader2 className="absolute right-3 top-2.5 size-4 animate-spin text-teal-500" />}
                  </div>
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

            {/* SHIPPING ADDRESS */}
            <Card className="bg-zinc-900/80 border-zinc-800 shadow-sm rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-zinc-800/50 bg-zinc-900/20 flex items-center gap-2">
                <Globe className="size-4 text-zinc-500" />
                <h3 className="text-sm font-semibold text-zinc-100">Shipping Address</h3>
              </div>
              <CardContent className="p-6 space-y-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="text-[11px] font-medium text-zinc-500 px-1">Recipient Name</label>
                    <Input 
                      className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                      placeholder="Same as customer if empty"
                      value={orderData.shipping_name}
                      onChange={e => setOrderData(p => ({ ...p, shipping_name: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[11px] font-medium text-zinc-500 px-1">Recipient Phone</label>
                    <Input 
                      className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                      placeholder="+380..."
                      value={orderData.shipping_phone}
                      onChange={e => setOrderData(p => ({ ...p, shipping_phone: e.target.value }))}
                    />
                  </div>
                </div>

                {orderData.shipping_country === 'UA' ? (
                  <div className="space-y-4 p-4 rounded-xl bg-zinc-950 border border-zinc-800">
                    <div className="space-y-2">
                      <label className="text-[11px] font-medium text-zinc-500 px-1 uppercase tracking-wider">Nova Poshta City</label>
                      <div className="relative">
                        <Input 
                          className="border-zinc-800 bg-zinc-900 pl-9 focus:ring-teal-500/20"
                          placeholder="Search city..."
                          value={cityQuery}
                          onChange={e => setCityQuery(e.target.value)}
                        />
                        <Search className="absolute left-3 top-2.5 size-4 text-zinc-600" />
                        {isCitiesLoading && <Loader2 className="absolute right-3 top-2.5 size-4 animate-spin text-teal-500" />}
                      </div>
                      {cities && cities.length > 0 && cityQuery !== orderData.shipping_city && (
                        <div className="mt-1 max-h-48 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl z-50">
                          {cities.map((city: any) => (
                            <div 
                              key={city.Ref}
                              className="px-4 py-3 text-sm text-zinc-300 hover:bg-zinc-800 cursor-pointer border-b border-zinc-800/50 last:border-0"
                              onClick={() => handleCitySelect(city)}
                            >
                              {city.Description}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {orderData.shipping_city_ref && (
                      <div className="space-y-2 relative">
                        <label className="text-[11px] font-medium text-zinc-500 px-1 uppercase tracking-wider">Warehouse / Branch</label>
                        <div className="relative">
                          <Input 
                            className="border-zinc-800 bg-zinc-900 pl-9 focus:ring-teal-500/20 pr-10"
                            placeholder="Select branch..."
                            value={warehouseQuery}
                            onFocus={() => setIsWarehouseOpen(true)}
                            onBlur={() => setTimeout(() => setIsWarehouseOpen(false), 200)}
                            onChange={e => {
                              setWarehouseQuery(e.target.value);
                              setIsWarehouseOpen(true);
                            }}
                          />
                          <Search className="absolute left-3 top-2.5 size-4 text-zinc-600" />
                          {warehouseQuery && (
                            <button 
                              className="absolute right-3 top-2.5 text-zinc-500 hover:text-zinc-300"
                              onClick={() => {
                                setWarehouseQuery('');
                                setOrderData(p => ({ ...p, shipping_warehouse_ref: '', shipping_street_1: '' }));
                              }}
                            >
                              <X size={16} />
                            </button>
                          )}
                        </div>
                        
                        {isWarehouseOpen && (
                          <div className="absolute top-full left-0 w-full mt-1 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl z-50 overflow-hidden">
                            <ScrollArea className="h-60">
                              {isWarehousesLoading ? (
                                <div className="p-4 flex justify-center"><Loader2 className="size-5 animate-spin text-teal-500" /></div>
                              ) : filteredWarehouses.length > 0 ? (
                                filteredWarehouses.map((wh: any) => (
                                  <div 
                                    key={wh.Ref}
                                    className={cn(
                                      "px-4 py-3 text-sm text-zinc-300 hover:bg-zinc-800 cursor-pointer border-b border-zinc-800/50 last:border-0",
                                      orderData.shipping_warehouse_ref === wh.Ref && "bg-teal-500/10 text-teal-400"
                                    )}
                                    onClick={() => handleWarehouseSelect(wh)}
                                  >
                                    {wh.Description}
                                  </div>
                                ))
                              ) : (
                                <div className="p-4 text-sm text-zinc-500 text-center">No branches found</div>
                              )}
                            </ScrollArea>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                      <div className="sm:col-span-2 space-y-2">
                        <label className="text-[11px] font-medium text-zinc-500 px-1">Street Address</label>
                        <Input 
                          className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                          placeholder="Main St. 123"
                          value={orderData.shipping_street_1}
                          onChange={e => setOrderData(p => ({ ...p, shipping_street_1: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[11px] font-medium text-zinc-500 px-1">City</label>
                        <Input 
                          className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                          placeholder="Kyiv"
                          value={orderData.shipping_city}
                          onChange={e => setOrderData(p => ({ ...p, shipping_city: e.target.value }))}
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                      <div className="space-y-2">
                        <label className="text-[11px] font-medium text-zinc-500 px-1">State / Province</label>
                        <Input 
                          className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                          placeholder="Kyiv Oblast"
                          value={orderData.shipping_state}
                          onChange={e => setOrderData(p => ({ ...p, shipping_state: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[11px] font-medium text-zinc-500 px-1">ZIP / Postal Code</label>
                        <Input 
                          className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20"
                          placeholder="01001"
                          value={orderData.shipping_zip}
                          onChange={e => setOrderData(p => ({ ...p, shipping_zip: e.target.value }))}
                        />
                      </div>
                    </div>
                  </>
                )}
                
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                  <div className="space-y-2">
                    <label className="text-[11px] font-medium text-zinc-500 px-1">Country (ISO 2)</label>
                    <Input 
                      className="border-zinc-800 bg-zinc-950 rounded-xl text-zinc-100 focus:ring-teal-500/20 uppercase"
                      placeholder="UA"
                      maxLength={2}
                      value={orderData.shipping_country}
                      onChange={e => setOrderData(p => ({ ...p, shipping_country: e.target.value.toUpperCase() }))}
                    />
                  </div>
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
