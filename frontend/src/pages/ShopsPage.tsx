import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  Plus,
  Settings2,
  Trash2,
  AlertCircle,
  RefreshCw,
  Store,
  Package2,
  Truck,
  LineChart,
  Images,
  Percent,
} from 'lucide-react';
import { useCreateShop, useShops, useUpdateShop, useDeleteShop, useSyncShop, useBackfillProductImages, useBackfillPlatformFees } from '@/hooks/useShops';
import { shippingApi } from '@/api/shipping';
import ShellPage from './ShellPage';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { useAuth } from '@/hooks/useAuth';
import type { ShopPlatform } from '@/types/common';
import { cn } from '@/lib/utils';

function getErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const data = (error as any).response?.data;
    
    // Handle FastAPI validation errors (array of objects)
    if (data?.detail && Array.isArray(data.detail)) {
      return data.detail.map((err: any) => `${err.loc.join('.')}: ${err.msg}`).join(', ');
    }
    
    // Handle standard string detail
    // TODO: SEC-07 — backend now returns generic detail; reconsider message extraction.
    if (data?.detail && typeof data.detail === 'string') {
      return data.detail;
    }

    return 'Request failed';
  }

  if (error instanceof Error) return error.message;
  return 'Request failed';
}

const INITIAL_SHOP_STATE = {
  id: '',
  name: '',
  platform: 'etsy' as ShopPlatform,
  color: '#14b8a6',
  shopify_store_url: '',
  shopify_access_token: '',
  shopify_webhook_secret: '',
  np_api_key: '',
  np_sender_name: '',
  np_sender_phone: '',
  np_sender_city_ref: '',
  np_sender_warehouse_ref: '',
  fee_percent: '',
};

export default function ShopsPage() {
  const { user } = useAuth();
  const { data: shops, isLoading, error } = useShops();
  const createShop = useCreateShop();
  const updateShop = useUpdateShop();
  const deleteShop = useDeleteShop();
  const syncShop = useSyncShop();
  const backfillImages = useBackfillProductImages();
  const backfillFees = useBackfillPlatformFees();
  
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingShop, setEditingShop] = useState(INITIAL_SHOP_STATE);
  const [dialogError, setDialogError] = useState<string | null>(null);
  
  // NP Search State
  const [citySearch, setCitySearch] = useState('');
  const [cityResults, setCityResults] = useState([]);
  const [warehouses, setWarehouses] = useState([]);

  const handleSearchCities = async (q: string) => {
    try {
      const results = await shippingApi.searchCities(q);
      setCityResults(results);
    } catch (err) {
      console.error('Failed to search cities', err);
    }
  };

  const handleGetWarehouses = async (cityRef: string) => {
    try {
      const results = await shippingApi.getWarehouses(cityRef);
      setWarehouses(results);
    } catch (err) {
      console.error('Failed to get warehouses', err);
    }
  };
  
  const isOwner = user?.role === 'owner';

  // NP-FIX-3b: Sender phone must be a UA mobile number — backend normalizes
  // to 380XXXXXXXXX on save and 422s on invalid. The frontend regex mirrors
  // the same accepted shapes (380XXXXXXXXX, 0XXXXXXXXX, XXXXXXXXX, with
  // optional + and separators) so the operator gets immediate feedback.
  const senderPhoneDigits = (editingShop.np_sender_phone ?? '').replace(/[^\d+]/g, '');
  const senderPhoneValid =
    senderPhoneDigits === '' || /^(\+?380|0)?\d{9}$/.test(senderPhoneDigits);

  // SHOP-FEE-1: mirrors the backend's Field(ge=0, le=100). Empty is valid — it
  // means "no automatic fee", which is the default for every shop.
  const feePercentRaw = editingShop.fee_percent.trim();
  const feePercentValid =
    feePercentRaw === '' ||
    (Number.isFinite(parseFloat(feePercentRaw)) &&
      parseFloat(feePercentRaw) >= 0 &&
      parseFloat(feePercentRaw) <= 100);

  const handleOpenCreate = () => {
    setEditingShop(INITIAL_SHOP_STATE);
    setDialogError(null);
    setCitySearch('');
    setCityResults([]);
    setWarehouses([]);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (shop: any) => {
    setEditingShop({
      id: shop.id,
      name: shop.name,
      platform: shop.platform,
      color: shop.color || '#14b8a6',
      shopify_store_url: shop.shopify_store_url || '',
      shopify_access_token: '', // Never pre-fill token
      shopify_webhook_secret: '', // Never pre-fill secret
      np_api_key: '', // Never pre-fill key
      np_sender_name: shop.np_sender_name || '',
      np_sender_phone: shop.np_sender_phone || '',
      np_sender_city_ref: shop.np_sender_city_ref || '',
      np_sender_warehouse_ref: shop.np_sender_warehouse_ref || '',
      // Explicit null check, not `|| ''` — a configured rate of 0 is meaningful
      // and must not be hydrated as "unset". Without this hydration, editing any
      // other field would send fee_percent: null and silently wipe the rate.
      fee_percent: shop.fee_percent != null ? String(shop.fee_percent) : '',
    });
    setCitySearch(''); // We don't have city name in Shop model, user will search again or we can improve later
    setCityResults([]);
    setWarehouses([]);
    if (shop.np_sender_city_ref) {
      handleGetWarehouses(shop.np_sender_city_ref);
    }
    setDialogError(null);
    setIsDialogOpen(true);
  };

  const handleSaveShop = async (event: FormEvent) => {
    event.preventDefault();
    setDialogError(null);

    const name = editingShop.name.trim();
    if (!name) {
      setDialogError('Store name is required.');
      return;
    }

    const payload: any = {
      name,
      platform: editingShop.platform,
      color: editingShop.color || '#14b8a6',
      is_active: true,
      np_sender_name: editingShop.np_sender_name || null,
      np_sender_phone: editingShop.np_sender_phone || null,
      np_sender_city_ref: editingShop.np_sender_city_ref || null,
      np_sender_warehouse_ref: editingShop.np_sender_warehouse_ref || null,
    };

    if (editingShop.platform === 'shopify') {
      // SHOP-FEE-1. Empty clears the rate (back to "no auto fee"); anything else
      // must parse, or the shop would silently keep its old rate.
      const feeRaw = editingShop.fee_percent.trim();
      if (feeRaw === '') {
        payload.fee_percent = null;
      } else {
        const fee = parseFloat(feeRaw);
        if (!Number.isFinite(fee) || fee < 0 || fee > 100) {
          setDialogError('Platform fee must be between 0 and 100.');
          return;
        }
        payload.fee_percent = fee;
      }
      if (editingShop.shopify_store_url.trim()) {
        payload.shopify_store_url = editingShop.shopify_store_url.trim();
      }
      if (editingShop.shopify_access_token.trim()) {
        payload.shopify_access_token = editingShop.shopify_access_token.trim();
      }
      if (editingShop.shopify_webhook_secret.trim()) {
        payload.shopify_webhook_secret = editingShop.shopify_webhook_secret.trim();
      }
    }

    if (editingShop.np_api_key.trim()) {
      payload.np_api_key = editingShop.np_api_key.trim();
    }

    try {
      if (editingShop.id) {
        await updateShop.mutateAsync({ id: editingShop.id, payload });
      } else {
        await createShop.mutateAsync(payload);
      }
      setIsDialogOpen(false);
    } catch (err) {
      setDialogError(getErrorMessage(err));
    }
  };

  if (error) {
    return (
      <ShellPage title="Shop Management" description="Error loading shops.">
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-8 text-center text-red-400">
          Failed to load shops. Please check your connection.
        </div>
      </ShellPage>
    );
  }

  return (
    <ShellPage
      title="Shop Management"
      description="Connect and manage your Etsy, Shopify, and local Ukrainian stores."
    >
      <Dialog
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
      >
        <DialogContent className="sm:max-w-3xl border-zinc-800 bg-zinc-950 text-zinc-100">
          <DialogHeader className="mb-4">
            <DialogTitle className="text-2xl font-bold tracking-tight">
              {editingShop.id ? 'Edit Store Settings' : 'Initialize New Store'}
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Configure platform integration and logistics credentials.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveShop} className="space-y-6">
            <Tabs defaultValue="general" className="w-full">
              <TabsList className="grid w-full grid-cols-3 bg-zinc-900/50 p-1 border border-zinc-800">
                <TabsTrigger value="general" className="flex items-center gap-2 data-[state=active]:bg-zinc-800">
                  <Store className="size-3.5" /> General
                </TabsTrigger>
                <TabsTrigger value="platform" className="flex items-center gap-2 data-[state=active]:bg-zinc-800">
                  <Package2 className="size-3.5" /> Platform API
                </TabsTrigger>
                <TabsTrigger value="shipping" className="flex items-center gap-2 data-[state=active]:bg-zinc-800">
                  <Truck className="size-3.5" /> Logistics (NP)
                </TabsTrigger>
              </TabsList>

              <div className="mt-6 min-h-[300px]">
                <TabsContent value="general" className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Store Name</p>
                      <Input
                        className="border-zinc-800 bg-zinc-900/50"
                        placeholder="LeatherCraft Boutique"
                        value={editingShop.name}
                        onChange={(e) => setEditingShop(p => ({ ...p, name: e.target.value }))}
                      />
                    </div>
                    <div className="space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Brand Color</p>
                      <div className="flex gap-2">
                        <Input
                          className="h-10 w-12 border-zinc-800 bg-zinc-900/50 p-1"
                          type="color"
                          value={editingShop.color}
                          onChange={(e) => setEditingShop(p => ({ ...p, color: e.target.value }))}
                        />
                        <Input
                          className="border-zinc-800 bg-zinc-900/50 font-mono text-xs"
                          value={editingShop.color}
                          onChange={(e) => setEditingShop(p => ({ ...p, color: e.target.value }))}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Sales Platform</p>
                    <Select
                      value={editingShop.platform}
                      onValueChange={(v) => setEditingShop(p => ({ ...p, platform: v as ShopPlatform }))}
                    >
                      <SelectTrigger className="w-full border-zinc-800 bg-zinc-900/50">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="border-zinc-800 bg-zinc-950">
                        <SelectItem value="etsy" className="focus:bg-orange-500/10 focus:text-orange-400">ETSY (Manual Sync)</SelectItem>
                        <SelectItem value="shopify" className="focus:bg-green-500/10 focus:text-green-400">SHOPIFY (Auto Sync)</SelectItem>
                        <SelectItem value="manual" className="focus:bg-teal-500/10 focus:text-teal-400">LOCAL / MANUAL ONLY</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </TabsContent>

                <TabsContent value="platform" className="space-y-4">
                  {editingShop.platform === 'shopify' ? (
                    <>
                      <div className="space-y-2">
                        <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Shopify Store URL</p>
                        <Input
                          className="border-zinc-800 bg-zinc-900/50"
                          placeholder="https://your-store.myshopify.com"
                          value={editingShop.shopify_store_url}
                          onChange={(e) => setEditingShop(p => ({ ...p, shopify_store_url: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Access Token (Admin API)</p>
                        <Input
                          className="border-zinc-800 bg-zinc-900/50"
                          type="password"
                          placeholder={editingShop.id ? "Leave empty to keep existing" : "shpat_..."}
                          value={editingShop.shopify_access_token}
                          onChange={(e) => setEditingShop(p => ({ ...p, shopify_access_token: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Webhook Secret</p>
                        <Input
                          className="border-zinc-800 bg-zinc-900/50"
                          type="password"
                          placeholder={editingShop.id ? "Leave empty to keep existing" : "Shopify webhook secret"}
                          value={editingShop.shopify_webhook_secret}
                          onChange={(e) => setEditingShop(p => ({ ...p, shopify_webhook_secret: e.target.value }))}
                        />
                      </div>
                      <Separator className="bg-zinc-800" />
                      <div className="space-y-2">
                        <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Platform Fee (%)</p>
                        <Input
                          className={cn(
                            "border-zinc-800 bg-zinc-900/50",
                            !feePercentValid && "border-red-500/50",
                          )}
                          type="number"
                          step="0.01"
                          min="0"
                          max="100"
                          placeholder="e.g. 8.00 — leave empty for no automatic fee"
                          value={editingShop.fee_percent}
                          onChange={(e) => setEditingShop(p => ({ ...p, fee_percent: e.target.value }))}
                        />
                        {feePercentValid ? (
                          <p className="text-[11px] text-zinc-500">
                            Total effective transaction fee — channel commission, payment
                            gateway and merchant-of-record cut combined. Applied to each
                            order's total when it is imported, and frozen there: changing
                            this rate never re-prices existing orders.
                          </p>
                        ) : (
                          <p className="text-xs text-red-400">
                            Platform fee must be a number between 0 and 100.
                          </p>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center p-8 border border-dashed border-zinc-800 rounded-xl bg-zinc-900/10">
                      <Package2 className="size-12 text-zinc-700 mb-2" />
                      <p className="text-sm text-zinc-400">No API configuration needed for {editingShop.platform.toUpperCase()}.</p>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="shipping" className="space-y-4">
                  <div className="space-y-2">
                    <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Nova Poshta API Key</p>
                    <Input
                      className="border-zinc-800 bg-zinc-900/50"
                      type="password"
                      placeholder={editingShop.id ? "Leave empty to keep existing" : "API secret key"}
                      value={editingShop.np_api_key}
                      onChange={(e) => setEditingShop(p => ({ ...p, np_api_key: e.target.value }))}
                    />
                  </div>
                  <Separator className="bg-zinc-800" />
                  <p className="text-[10px] font-bold text-teal-500 uppercase tracking-widest">Sender Metadata</p>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                       <p className="text-xs font-medium text-zinc-400">Sender Name (Optional override)</p>
                       <Input
                         className="border-zinc-800 bg-zinc-900/50"
                         placeholder="Leave empty to use NP default"
                         value={editingShop.np_sender_name}
                         onChange={(e) => setEditingShop(p => ({ ...p, np_sender_name: e.target.value }))}
                       />
                    </div>
                    <div className="space-y-2">
                       <p className="text-xs font-medium text-zinc-400">Sender Phone (Optional override)</p>
                       <Input
                         className={cn(
                           "border-zinc-800 bg-zinc-900/50",
                           !senderPhoneValid && "border-red-500/50"
                         )}
                         placeholder="380XXXXXXXXX or 0XXXXXXXXX"
                         value={editingShop.np_sender_phone}
                         onChange={(e) => setEditingShop(p => ({ ...p, np_sender_phone: e.target.value }))}
                       />
                       {!senderPhoneValid && (
                         <p className="text-xs text-red-400">
                           Phone must be a Ukrainian mobile number (e.g. 380991234567 or 0991234567).
                         </p>
                       )}
                    </div>
                  </div>

                  <div className="space-y-4 rounded-xl border border-teal-500/10 bg-teal-500/5 p-4">
                    <p className="text-[10px] font-bold text-teal-400 uppercase tracking-widest">Permanent Sender Location</p>
                    <div className="space-y-2 relative">
                       <p className="text-xs font-medium text-zinc-400">Sender City</p>
                       <Input
                         className="border-zinc-800 bg-zinc-900/50"
                         placeholder="Search city (e.g. Київ)"
                         value={citySearch}
                         onChange={(e) => {
                           setCitySearch(e.target.value);
                           if (e.target.value.length >= 2) handleSearchCities(e.target.value);
                         }}
                       />
                       {cityResults.length > 0 && (
                         <div className="absolute z-10 mt-1 max-h-40 w-full overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-1 shadow-2xl">
                           {cityResults.map((city: any) => (
                             <div
                               key={city.Ref}
                               className="cursor-pointer rounded-md px-3 py-2 text-xs hover:bg-zinc-800"
                               onClick={() => {
                                 setEditingShop(p => ({ ...p, np_sender_city_ref: city.Ref }));
                                 setCitySearch(city.Description);
                                 setCityResults([]);
                                 handleGetWarehouses(city.Ref);
                               }}
                             >
                               {city.Description}
                             </div>
                           ))}
                         </div>
                       )}
                    </div>

                    <div className="space-y-2">
                       <p className="text-xs font-medium text-zinc-400">Sender Warehouse (MUST BE A WAREHOUSE TO AVOID COURIER)</p>
                       <Select
                         value={editingShop.np_sender_warehouse_ref}
                         onValueChange={(v) => setEditingShop(p => ({ ...p, np_sender_warehouse_ref: v }))}
                         disabled={!editingShop.np_sender_city_ref}
                       >
                         <SelectTrigger className="border-zinc-800 bg-zinc-900/50">
                           <SelectValue placeholder="Select your shipping warehouse" />
                         </SelectTrigger>
                         <SelectContent className="max-h-60 border-zinc-800 bg-zinc-950">
                           {warehouses.map((w: any) => (
                             <SelectItem key={w.Ref} value={w.Ref} className="text-xs">
                               {w.Description}
                             </SelectItem>
                           ))}
                         </SelectContent>
                       </Select>
                    </div>
                  </div>
                </TabsContent>
              </div>
            </Tabs>

            {dialogError && (
              <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-400">
                <AlertCircle className="size-4" />
                {dialogError}
              </div>
            )}

            <DialogFooter className="bg-zinc-900/20 p-6 -m-6 mt-6 border-t border-zinc-800">
              <Button
                type="button"
                variant="ghost"
                className="text-zinc-400 hover:text-zinc-100"
                onClick={() => setIsDialogOpen(false)}
              >
                Close
              </Button>
              <Button
                type="submit"
                className="bg-teal-600 text-white hover:bg-teal-500 shadow-[0_0_20px_-5px_rgba(20,184,166,0.5)]"
                disabled={createShop.isPending || updateShop.isPending || !senderPhoneValid || !feePercentValid}
              >
                {(createShop.isPending || updateShop.isPending) ? 'Saving...' : 'Save Configuration'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
             <h2 className="text-2xl font-bold text-zinc-50 tracking-tight">Integrated Stores</h2>
             <p className="text-sm text-zinc-400">Manage API connections and brand aesthetics.</p>
          </div>
          {isOwner && (
            <Button
              className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg"
              onClick={handleOpenCreate}
            >
              <Plus className="mr-2 h-4 w-4" /> Initialize Store
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 w-full bg-zinc-900/40 rounded-2xl" />
            ))}
          </div>
        ) : (
          <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
            <CardContent className="p-0">
              <Table className="min-w-[720px]">
                <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                  <TableRow className="border-none hover:bg-transparent">
                    <TableHead className="w-[300px] text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-5">Store Identity</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Platform</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5 text-center">Status</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Connectivity</TableHead>
                    {isOwner && <TableHead className="text-right text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-5">Management</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Array.isArray(shops) && shops.map((shop) => (
                    <TableRow key={shop.id} className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors group">
                      <TableCell className="px-8 py-6">
                        <div className="flex items-center gap-4">
                          <div 
                            className="size-10 rounded-xl flex items-center justify-center border shadow-inner" 
                            style={{ 
                              backgroundColor: `${shop.color}15`, 
                              borderColor: `${shop.color}40`,
                              color: shop.color
                            }} 
                          >
                            <Store className="size-5" />
                          </div>
                           <div className="space-y-1">
                              <p className="text-sm font-bold text-zinc-100 tracking-tight">{shop?.name || 'Unnamed Store'}</p>
                              <p className="text-[10px] text-zinc-400 font-mono">ID: {shop?.id?.slice(0, 8) || 'unknown'}...</p>
                           </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="border-zinc-800 bg-zinc-900/50 text-zinc-400 font-mono text-[10px] tracking-widest py-0.5">
                          {String(shop.platform || '').toUpperCase()}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-teal-500/5 text-teal-400 border border-teal-500/10">
                          <div className="size-1.5 rounded-full bg-teal-500 animate-pulse" />
                          <span className="text-[10px] font-bold uppercase tracking-wider">Online</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          {shop.has_shopify_token && (
                            <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[9px] uppercase tracking-tighter">Shopify Live</Badge>
                          )}
                          {shop.has_shopify_webhook_secret && (
                            <Badge className="bg-purple-500/10 text-purple-400 border-purple-500/20 text-[9px] uppercase tracking-tighter">Webhooks Active</Badge>
                          )}
                          {shop.has_np_token && (
                            <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[9px] uppercase tracking-tighter">NovaPoshta Live</Badge>
                          )}
                          {!shop.has_shopify_token && !shop.has_np_token && (
                            <span className="text-[10px] text-zinc-600 font-medium">No active connections</span>
                          )}
                        </div>
                      </TableCell>
                      {isOwner && (
                        <TableCell className="px-8 py-6 text-right">
                          <div className="flex justify-end items-center gap-1.5">
                            <Link
                              to={`/shops/${shop.id}/finance`}
                              title="Per-shop finance"
                              className="inline-flex h-9 items-center gap-1.5 px-3 rounded-xl text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.05] transition-colors"
                            >
                              <LineChart className="h-4 w-4" />
                              <span className="text-[11px] font-bold uppercase tracking-wider">Finance</span>
                            </Link>
                            <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                            {shop.platform?.toLowerCase() === 'shopify' && (
                              <Button
                                variant="ghost"
                                size="icon"
                                title="Manual Sync"
                                className={cn(
                                  "h-9 w-9 text-teal-500 hover:text-teal-400 hover:bg-teal-500/10 rounded-xl",
                                  syncShop.isPending && "animate-spin"
                                )}
                                disabled={syncShop.isPending}
                                onClick={() => syncShop.mutate(shop.id)}
                              >
                                <RefreshCw className="h-4 w-4" />
                              </Button>
                            )}
                            {shop.platform?.toLowerCase() === 'shopify' && (
                              <Button
                                variant="ghost"
                                size="icon"
                                title="Pull product images from Shopify"
                                className={cn(
                                  "h-9 w-9 text-teal-500 hover:text-teal-400 hover:bg-teal-500/10 rounded-xl",
                                  backfillImages.isPending && "animate-pulse"
                                )}
                                disabled={backfillImages.isPending}
                                onClick={() => backfillImages.mutate(shop.id)}
                              >
                                <Images className="h-4 w-4" />
                              </Button>
                            )}
                            {isOwner && shop.platform?.toLowerCase() === 'shopify' && shop.fee_percent != null && (
                              <Button
                                variant="ghost"
                                size="icon"
                                title={`Backfill platform fees at ${shop.fee_percent}% (dry run first)`}
                                className={cn(
                                  "h-9 w-9 text-teal-500 hover:text-teal-400 hover:bg-teal-500/10 rounded-xl",
                                  backfillFees.isPending && "animate-pulse"
                                )}
                                disabled={backfillFees.isPending}
                                onClick={() => {
                                  // Dry run is the default and the first gate: it
                                  // reports the P&L impact and any settlement
                                  // overlap. Only then is a real write offered.
                                  backfillFees
                                    .mutateAsync({ id: shop.id, dry_run: true })
                                    .then((preview) => {
                                      if (preview.matched === 0) return;
                                      const settlements = preview.overlapping_settlements.length;
                                      const confirmed = window.confirm(
                                        `Price ${preview.matched} order(s) at ${preview.fee_percent}%?\n\n` +
                                          `${preview.affects_pnl_now} are already SHIPPED/COMPLETED, so this changes closed months.\n` +
                                          (settlements
                                            ? `${settlements} partner settlement(s) overlap — those periods become retroactively over-settled.\n`
                                            : '') +
                                          `\nOrders with a fee already set are never touched.`,
                                      );
                                      if (confirmed) {
                                        backfillFees.mutate({ id: shop.id, dry_run: false });
                                      }
                                    })
                                    .catch(() => {
                                      /* surfaced by the hook's onError toast */
                                    });
                                }}
                              >
                                <Percent className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Config"
                              className="h-9 w-9 text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.05] rounded-xl"
                              onClick={() => handleOpenEdit(shop)}
                            >
                              <Settings2 className="h-4 w-4" />
                            </Button>
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              title="Delete"
                              className="h-9 w-9 text-zinc-600 hover:text-red-400 hover:bg-red-500/10 rounded-xl"
                              onClick={() => {
                                if (window.confirm(`Are you sure you want to deactivate ${shop?.name || 'this store'}?`)) {
                                  deleteShop.mutate(shop.id);
                                }
                              }}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                            </div>
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                  {(!shops || (Array.isArray(shops) && shops.length === 0)) && (
                    <TableRow>
                      <TableCell colSpan={5} className="h-32 text-center">
                        <div className="flex flex-col items-center justify-center gap-2">
                           <Store className="size-8 text-zinc-800" />
                           <p className="text-sm text-zinc-400 italic">No stores initialized in this workspace.</p>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        <div className="rounded-2xl border border-amber-500/10 bg-amber-500/[0.02] p-6 shadow-sm">
          <div className="flex gap-4">
            <div className="size-10 rounded-xl bg-amber-500/10 flex items-center justify-center shrink-0">
               <AlertCircle className="h-5 w-5 text-amber-500" />
            </div>
            <div className="space-y-1.5 pt-1">
              <h4 className="text-sm font-bold text-amber-500 uppercase tracking-widest">Security Audit Context</h4>
              <p className="text-xs text-zinc-400 leading-relaxed font-medium">
                Cryptographic tokens and NP secret keys are processed through AES-256 server-side encryption. 
                Managers and Designers can trigger sync actions but are strictly barred from retrieving raw API credentials.
              </p>
            </div>
          </div>
        </div>
      </div>
    </ShellPage>
  );
}
