import { useState, useMemo, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Phone, ClipboardList, Edit2, Check, Loader2, Search, MapPin, X, RefreshCw, AlertTriangle, Info, Package } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import type { OrderDetail } from '@/types/order';
import { useSearchCities, useGetWarehouses, useGetParcelEstimate } from '@/hooks/useShipping';
import { useShops } from '@/hooks/useShops';
import { usePackaging } from '@/hooks/usePackaging';
import { cn } from '@/lib/utils';
import { countryName } from '@/lib/countries';
import { useToastStore } from '@/components/ui/Toast';
import { AddressValidation } from './AddressValidation';
import { WbLabelButton } from './WbLabelButton';

interface DetailLogisticsProps {
  order: OrderDetail;
  canManageShipping: boolean;
  isPending: boolean;
  onGenerateTTN: (params: { 
    weight: number; 
    volume: number;
    length?: number;
    width?: number;
    height?: number;
    parcel_override?: boolean;
  }) => void;
  onRemoveTTN?: () => void;
  onUpdate?: (payload: any) => Promise<void>;
}

export function DetailLogistics({ order, canManageShipping, isPending, onGenerateTTN, onRemoveTTN, onUpdate }: DetailLogisticsProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [cityQuery, setCityQuery] = useState(order.shipping_city || '');
  const [warehouseQuery, setWarehouseQuery] = useState('');
  const [isWarehouseOpen, setIsWarehouseOpen] = useState(false);
  const [weight, setWeight] = useState(order.shop?.np_default_weight_kg || 0.5);
  const [volume, setVolume] = useState(order.shop?.np_default_volume_m3 || 0.004);
  const [length, setLength] = useState<number>(0);
  const [width, setWidth] = useState<number>(0);
  const [height, setHeight] = useState<number>(0);
  const [isManual, setIsManual] = useState(order.parcel_override);
  const [packagingId, setPackagingId] = useState<string | null>(order.packaging_id ?? null);
  const [isUpdatingPackaging, setIsUpdatingPackaging] = useState(false);

  const { data: packagingList = [] } = usePackaging();
  const selectedBox = useMemo(() => {
    if (!packagingId) return null;
    return packagingList.find(b => b.id === packagingId) ?? (order.packaging ?? null);
  }, [packagingId, packagingList, order.packaging]);
  const ttnExists = !!order.ttn_number;
  const isPackagingOverridden = !!selectedBox && (
    Number(length) !== selectedBox.inner_length_mm ||
    Number(width) !== selectedBox.inner_width_mm ||
    Number(height) !== selectedBox.inner_height_mm
  );

  const handlePackagingChange = async (newId: string | null) => {
    setPackagingId(newId);
    if (newId) {
      const box = packagingList.find(b => b.id === newId);
      if (box) {
        setLength(box.inner_length_mm);
        setWidth(box.inner_width_mm);
        setHeight(box.inner_height_mm);
        setIsManual(true);
      }
    }
    if (!onUpdate) return;
    setIsUpdatingPackaging(true);
    try {
      await onUpdate({ packaging_id: newId });
    } finally {
      setIsUpdatingPackaging(false);
    }
  };

  const handleResetPackagingDefaults = () => {
    if (!selectedBox) return;
    setLength(selectedBox.inner_length_mm);
    setWidth(selectedBox.inner_width_mm);
    setHeight(selectedBox.inner_height_mm);
  };

  const { data: estimate, isFetching: isEstimating } = useGetParcelEstimate(order.id, !order.ttn_number && order.shipping_country === 'UA');

  const { data: shops } = useShops();
  const orderShop = shops?.find(s => s.id === order.shop_id);
  const showNpConfigBanner = !!orderShop?.has_np_token && !orderShop.is_np_ready;

  const containerRef = useRef<HTMLDivElement>(null);

  // Pre-fill from estimate if not overridden — derive state during render
  // rather than in an effect so opening the panel doesn't trigger a second render.
  const [parcelSyncKey, setParcelSyncKey] = useState({ estimate, isManual, shop: order.shop });
  if (
    parcelSyncKey.estimate !== estimate ||
    parcelSyncKey.isManual !== isManual ||
    parcelSyncKey.shop !== order.shop
  ) {
    setParcelSyncKey({ estimate, isManual, shop: order.shop });
    if (estimate && !isManual) {
      setWeight(estimate.chargeable_weight_g / 1000.0);
      setLength(estimate.parcel_length_mm);
      setWidth(estimate.parcel_width_mm);
      setHeight(estimate.parcel_height_mm);
      // Volume is derived in backend from L/W/H now, but we can set it for UI compatibility
      setVolume(estimate.total_volume_cm3 / 1000000.0);
    } else if (!estimate && !order.parcel_override && order.shop) {
      // Fallback to defaults if no items or estimate failed
      setWeight(order.shop.np_default_weight_kg);
      setVolume(order.shop.np_default_volume_m3);
    }
  }

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsWarehouseOpen(false);
        // Also hide city dropdown if it's open (it's driven by cityQuery !== formData.shipping_city)
        // To properly "close" city dropdown without clearing query, we might need an isCityOpen state.
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  
  const [formData, setFormData] = useState({
    shipping_name: order.shipping_name || '',
    shipping_phone: order.shipping_phone || '',
    shipping_street_1: order.shipping_street_1 || '',
    shipping_city: order.shipping_city || '',
    shipping_city_ref: order.shipping_city_ref || '',
    shipping_warehouse_ref: order.shipping_warehouse_ref || '',
    shipping_country: order.shipping_country || 'UA',
  });

  // NP city/warehouse lookups are OWNER/MANAGER-only (skip for designers → no 403)
  // and Nova Poshta is Ukraine-only, so only fire while editing a UA order — otherwise
  // a non-UA order (e.g. a US city) 400s on the NP directory API on every open.
  const { data: cities, isLoading: isCitiesLoading } = useSearchCities(
    cityQuery,
    canManageShipping && isEditing && formData.shipping_country === 'UA'
  );

  const { data: warehouses, isLoading: isWarehousesLoading } = useGetWarehouses(formData.shipping_city_ref, "", canManageShipping);

  const filteredWarehouses = useMemo(() => {
    if (!warehouses) return [];
    if (!warehouseQuery) return warehouses.slice(0, 50);
    const q = warehouseQuery.toLowerCase();
    return warehouses
      .filter((w: any) => w.Description.toLowerCase().includes(q))
      .slice(0, 50);
  }, [warehouses, warehouseQuery]);

  const handleSave = async () => {
    if (!onUpdate) return;
    setIsSaving(true);
    
    // Auto-format phone for Ukraine
    let phone = formData.shipping_phone.replace(/\D/g, '');
    if (formData.shipping_country === 'UA') {
      if (phone.length === 9) phone = '380' + phone;
      else if (phone.length === 10) phone = '38' + phone;
      else if (phone.length === 11 && phone.startsWith('8')) phone = '3' + phone;
    }

    try {
      await onUpdate({ ...formData, shipping_phone: phone });
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCitySelect = (city: any) => {
    setFormData(p => ({ 
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
    setFormData(p => ({ 
      ...p, 
      shipping_street_1: warehouse.Description, 
      shipping_warehouse_ref: warehouse.Ref 
    }));
    setIsWarehouseOpen(false);
    setWarehouseQuery(warehouse.Description);
  };

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden flex flex-col shadow-sm">
      <div className="p-4">
        <div className="flex items-center justify-between mb-4 px-1">
          <h3 className="text-sm font-semibold text-zinc-100">
            Shipping & Logistics
          </h3>
          {canManageShipping && !isEditing && (
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-6 w-6 text-zinc-400 hover:text-zinc-200"
              onClick={() => {
                setIsEditing(true);
                setWarehouseQuery(formData.shipping_street_1);
              }}
            >
              <Edit2 size={12} />
            </Button>
          )}
        </div>
        
        <div className="space-y-4 px-1">
          {isEditing ? (
            <div className="space-y-4">
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 font-medium px-1 uppercase tracking-wider">Recipient Name</label>
                  <Input 
                    className="h-8 text-[11px] bg-zinc-950 border-zinc-800 focus:border-teal-500/50 focus:ring-teal-500/20"
                    placeholder="Full Name"
                    value={formData.shipping_name}
                    onChange={e => setFormData(p => ({ ...p, shipping_name: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 font-medium px-1 uppercase tracking-wider">Recipient Phone</label>
                  <Input 
                    className="h-8 text-[11px] bg-zinc-950 border-zinc-800 focus:border-teal-500/50 focus:ring-teal-500/20"
                    placeholder="+380XXXXXXXXX"
                    value={formData.shipping_phone}
                    onChange={e => setFormData(p => ({ ...p, shipping_phone: e.target.value }))}
                  />
                </div>
              </div>

              {formData.shipping_country === 'UA' ? (
                <div ref={containerRef} className="space-y-3 p-3 rounded-lg bg-zinc-950/40 border border-zinc-800/50">
                  <div className="space-y-1">
                    <label className="text-[10px] text-zinc-400 font-medium px-1 uppercase tracking-wider">City Search</label>
                    <div className="relative">
                      <Input 
                        className="h-8 text-[11px] bg-zinc-900 border-zinc-800 pl-8 focus:ring-teal-500/20"
                        placeholder="Type city name..."
                        value={cityQuery}
                        onChange={e => {
                          setCityQuery(e.target.value);
                          // Clear references if user manually types after selection
                          if (formData.shipping_city_ref) {
                            setFormData(p => ({ 
                              ...p, 
                              shipping_city: '', 
                              shipping_city_ref: '',
                              shipping_warehouse_ref: '',
                              shipping_street_1: '' 
                            }));
                          }
                        }}
                      />
                      <Search className="absolute left-2.5 top-2.5 size-3 text-zinc-600" />
                      {isCitiesLoading && <Loader2 className="absolute right-2.5 top-2.5 size-3 animate-spin text-teal-500" />}
                    </div>
                    {cities && cities.length > 0 && cityQuery !== formData.shipping_city && (
                      <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl z-[100] absolute w-full left-0">
                        {cities.map((city: any) => (
                          <div 
                            key={city.Ref}
                            className="px-3 py-2 text-[11px] text-zinc-300 hover:bg-zinc-800 cursor-pointer border-b border-zinc-800/50 last:border-0"
                            onClick={() => handleCitySelect(city)}
                          >
                            {city.Description}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {formData.shipping_city_ref && (
                    <div className="space-y-1 relative">
                      <label className="text-[10px] text-zinc-400 font-medium px-1 uppercase tracking-wider">Warehouse / Branch</label>
                      <div className="relative">
                        <Input 
                          className="h-8 text-[11px] bg-zinc-900 border-zinc-800 focus:ring-teal-500/20 pr-8"
                          placeholder="Search branch..."
                          value={warehouseQuery}
                          onFocus={() => setIsWarehouseOpen(true)}
                          onBlur={() => {
                            // Delay to allow clicking items
                            setTimeout(() => setIsWarehouseOpen(false), 200);
                          }}
                          onChange={e => {
                            setWarehouseQuery(e.target.value);
                            setIsWarehouseOpen(true);
                          }}
                        />
                        {warehouseQuery && (
                          <button 
                            className="absolute right-2.5 top-2.5 text-zinc-400 hover:text-zinc-300"
                            onClick={() => {
                              setWarehouseQuery('');
                              setFormData(p => ({ ...p, shipping_warehouse_ref: '', shipping_street_1: '' }));
                            }}
                          >
                            <X size={12} />
                          </button>
                        )}
                      </div>
                      
                      {isWarehouseOpen && (
                        <div className="absolute top-full left-0 w-full mt-1 bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl z-[100] overflow-hidden">
                          <ScrollArea className="h-48">
                            {isWarehousesLoading ? (
                              <div className="p-4 flex justify-center"><Loader2 className="size-4 animate-spin text-teal-500" /></div>
                            ) : filteredWarehouses.length > 0 ? (
                              filteredWarehouses.map((wh: any) => (
                                <div 
                                  key={wh.Ref}
                                  className={cn(
                                    "px-3 py-2 text-[10px] text-zinc-300 hover:bg-zinc-800 cursor-pointer border-b border-zinc-800/50 last:border-0",
                                    formData.shipping_warehouse_ref === wh.Ref && "bg-teal-500/10 text-teal-400"
                                  )}
                                  onClick={() => handleWarehouseSelect(wh)}
                                >
                                  {wh.Description}
                                </div>
                              ))
                            ) : (
                              <div className="p-4 text-[10px] text-zinc-400 text-center">No branches found</div>
                            )}
                          </ScrollArea>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <Input 
                    className="h-8 text-[11px] bg-zinc-950 border-zinc-800"
                    placeholder="Street Address"
                    value={formData.shipping_street_1}
                    onChange={e => setFormData(p => ({ ...p, shipping_street_1: e.target.value }))}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <Input 
                      className="h-8 text-[11px] bg-zinc-950 border-zinc-800"
                      placeholder="City"
                      value={formData.shipping_city}
                      onChange={e => setFormData(p => ({ ...p, shipping_city: e.target.value }))}
                    />
                    <Input 
                      className="h-8 text-[11px] bg-zinc-950 border-zinc-800 uppercase"
                      placeholder="Country Code (e.g. US)"
                      maxLength={2}
                      value={formData.shipping_country}
                      onChange={e => setFormData(p => ({ ...p, shipping_country: e.target.value.replace(/[^A-Za-z]/g, '').toUpperCase() }))}
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2 pt-2">
                <Button 
                  size="sm" 
                  className="h-8 bg-teal-600 hover:bg-teal-500 text-white text-[10px] font-bold uppercase tracking-wider gap-1.5 px-4 shadow-lg shadow-teal-900/20 transition-all"
                  onClick={handleSave}
                  disabled={isSaving}
                >
                  {isSaving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                  Save Changes
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-8 text-zinc-400 hover:text-zinc-300 text-[10px] uppercase font-semibold"
                  onClick={() => {
                    setIsEditing(false);
                    setIsWarehouseOpen(false);
                  }}
                  disabled={isSaving}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-3">
              <div className="text-sm text-zinc-400 leading-normal space-y-1 w-full">
                <p className="font-semibold text-zinc-200">{order.shipping_name || 'No recipient'}</p>
                <div className="flex items-center gap-1.5 text-zinc-400">
                  <MapPin size={12} className="text-zinc-600 shrink-0" />
                  <p className="line-clamp-2 text-[12px]">{order.shipping_street_1 || 'No address provided'}</p>
                </div>
                <p className="text-zinc-400 text-[11px] ml-4.5">{order.shipping_city}{order.shipping_state ? `, ${order.shipping_state}` : ''} {order.shipping_zip}</p>
                <div className="flex items-center gap-2 mt-3">
                   <span
                     className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[9px] font-bold border border-zinc-700/50 whitespace-nowrap"
                     title={order.shipping_country || undefined}
                   >
                    {countryName(order.shipping_country, '??')}
                   </span>
                   {order.shipping_warehouse_ref && (
                     <span className="px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-500 text-[9px] font-bold uppercase tracking-widest border border-teal-500/20">
                       NP Verified
                     </span>
                   )}
                </div>
                <AddressValidation order={order} canManageShipping={canManageShipping} onApply={onUpdate} />
              </div>
            </div>
          )}
          
          {!isEditing && (
            <div className="flex items-center gap-2 text-[11px] font-medium pt-3 border-t border-zinc-800/30">
              <Phone className="size-3.5 text-zinc-700" />
              {order.shipping_phone ? (
                <span className="text-zinc-400">{order.shipping_phone}</span>
              ) : (
                <span className="text-amber-500/70 italic flex items-center gap-1">
                  Missing phone number
                </span>
              )}
            </div>
          )}

          {!isEditing && ttnExists && (order.packaging ?? selectedBox) && (
            <div className="flex items-center gap-1.5 text-[10px] text-zinc-400 pt-2 border-t border-zinc-800/30">
              <Package size={11} className="text-zinc-600" />
              <span className="text-zinc-400">Packaged in:</span>
              <span className="font-semibold text-zinc-300">
                {(order.packaging ?? selectedBox)!.name}
              </span>
              <span className="text-zinc-600">
                ({(order.packaging ?? selectedBox)!.inner_length_mm}×{(order.packaging ?? selectedBox)!.inner_width_mm}×{(order.packaging ?? selectedBox)!.inner_height_mm} mm)
              </span>
            </div>
          )}

          {!isEditing && order.ttn_number && (
            <div className="space-y-2">
              <div
                className="mt-2 p-3 rounded-xl bg-teal-500/5 border border-teal-500/10 hover:bg-teal-500/10 transition-all cursor-pointer group active:scale-[0.98] relative"
                onClick={() => {
                  navigator.clipboard.writeText(order.ttn_number!);
                  useToastStore.getState().addToast('TTN copied to clipboard', 'success');
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <p className="text-[10px] font-bold text-teal-500/60 uppercase tracking-widest">Tracking (TTN)</p>
                  <div className="flex items-center gap-2">
                    <ClipboardList className="size-3.5 text-teal-500/40 group-hover:text-teal-500 transition-colors" />
                    {canManageShipping && onRemoveTTN && (
                      <button 
                        className="p-1 rounded-md hover:bg-red-500/10 text-zinc-400 hover:text-red-500 transition-all z-20"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm('Are you sure you want to delete this TTN?')) {
                            onRemoveTTN();
                          }
                        }}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                </div>
                <p className="font-mono text-base text-teal-100 font-black tracking-tight">{order.ttn_number}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {!isEditing && !order.ttn_number && order.shipping_country === 'UA' && canManageShipping && (
        <div className="p-3 border-t border-zinc-800/50 bg-zinc-950/20 space-y-3">
          <div className="space-y-1">
            <label className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider px-1 flex items-center gap-1">
              <Package size={10} /> Packaging
            </label>
            {packagingList.length === 0 ? (
              <div className="text-[10px] text-zinc-400 italic px-2 py-1.5 rounded bg-zinc-900/50 border border-zinc-800">
                No packaging configured —{' '}
                <Link
                  to="/inventory/packaging"
                  className="text-teal-400 hover:underline"
                >
                  add boxes in Inventory → Packaging
                </Link>
              </div>
            ) : (
              <select
                value={packagingId ?? ''}
                onChange={e => handlePackagingChange(e.target.value || null)}
                disabled={isUpdatingPackaging}
                className="w-full h-8 text-[11px] bg-zinc-900 border border-zinc-800 rounded px-2 text-zinc-100 focus:outline-none focus:ring-1 focus:ring-teal-500/40 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <option value="">— None —</option>
                {packagingList.map(box => (
                  <option key={box.id} value={box.id}>
                    {box.name} ({box.inner_length_mm}×{box.inner_width_mm}×{box.inner_height_mm} mm)
                  </option>
                ))}
              </select>
            )}
          </div>
          {showNpConfigBanner && (
            <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/10">
              <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-200/80 leading-snug">
                Nova Poshta sender warehouse not configured for this shop. Set it in Shops → Logistics (NP) before creating a TTN.
              </p>
            </div>
          )}
          {/* Estimation Context */}
          {estimate && (
            <div className="space-y-2">
              <div className="flex items-center justify-between px-1">
                <div className="flex items-center gap-2">
                  <Badge 
                    variant="outline" 
                    className={cn(
                      "text-[9px] font-bold uppercase tracking-widest py-0 h-5 border-zinc-700/50",
                      isManual ? "bg-amber-500/10 text-amber-500 border-amber-500/20" : "bg-teal-500/10 text-teal-500 border-teal-500/20"
                    )}
                  >
                    {isManual ? 'Manual Override' : 'Auto-Calculated'}
                  </Badge>
                  {!isManual && estimate.selected_packaging && (
                    <span className="text-[9px] text-zinc-400 font-medium flex items-center gap-1">
                      <ClipboardList size={10} />
                      {estimate.selected_packaging.name} ({estimate.packaging_type})
                    </span>
                  )}
                </div>
                
                {isManual && (
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="h-5 px-1.5 text-[9px] text-teal-500 hover:text-teal-400 hover:bg-teal-500/10 gap-1 font-bold"
                    onClick={() => setIsManual(false)}
                  >
                    <RefreshCw size={10} className={cn(isEstimating && "animate-spin")} />
                    Reset
                  </Button>
                )}
              </div>

              {/* Warnings */}
              {estimate.warnings.length > 0 && (
                <div className="space-y-1">
                  {estimate.warnings.map((w, idx) => (
                    <div key={idx} className="flex items-start gap-1.5 p-1.5 rounded bg-amber-500/5 border border-amber-500/10">
                      <AlertTriangle size={10} className="text-amber-500 shrink-0 mt-0.5" />
                      <p className="text-[9px] text-amber-200/70 leading-tight">{w}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <div className="flex items-center justify-between px-1">
                <label className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider">Weight (kg)</label>
                {estimate && (
                  <div className="group relative">
                    <Info size={10} className="text-zinc-700" />
                    <div className="absolute bottom-full right-0 mb-2 w-48 p-2 rounded-lg bg-zinc-900 border border-zinc-800 shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-[100]">
                      <div className="space-y-1 text-[10px]">
                        <div className="flex justify-between">
                          <span className="text-zinc-400">Actual:</span>
                          <span className="text-zinc-300">{(estimate.total_weight_g / 1000).toFixed(3)} kg</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-400">Volumetric:</span>
                          <span className="text-zinc-300">{(estimate.volumetric_weight_g / 1000).toFixed(3)} kg</span>
                        </div>
                        <div className="border-t border-zinc-800 my-1" />
                        <div className="flex justify-between font-bold">
                          <span className="text-teal-500">Chargeable:</span>
                          <span className="text-teal-400">{(estimate.chargeable_weight_g / 1000).toFixed(3)} kg</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <Input 
                type="number"
                step="0.001"
                className="h-8 text-[11px] bg-zinc-900 border-zinc-800"
                value={weight}
                onChange={e => {
                  setWeight(parseFloat(e.target.value) || 0);
                  setIsManual(true);
                }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider px-1">Volume (m³)</label>
              <Input 
                type="number"
                step="0.0001"
                className="h-8 text-[11px] bg-zinc-900 border-zinc-800"
                value={volume}
                onChange={e => {
                  setVolume(parseFloat(e.target.value) || 0);
                  setIsManual(true);
                }}
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider px-1">Length (mm)</label>
              <Input 
                type="number"
                className="h-8 text-[11px] bg-zinc-900 border-zinc-800"
                value={length}
                onChange={e => {
                  setLength(parseInt(e.target.value) || 0);
                  setIsManual(true);
                }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider px-1">Width (mm)</label>
              <Input 
                type="number"
                className="h-8 text-[11px] bg-zinc-900 border-zinc-800"
                value={width}
                onChange={e => {
                  setWidth(parseInt(e.target.value) || 0);
                  setIsManual(true);
                }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider px-1">Height (mm)</label>
              <Input
                type="number"
                className="h-8 text-[11px] bg-zinc-900 border-zinc-800"
                value={height}
                onChange={e => {
                  setHeight(parseInt(e.target.value) || 0);
                  setIsManual(true);
                }}
              />
            </div>
          </div>

          {selectedBox && isPackagingOverridden && (
            <div className="flex items-center justify-between gap-2 px-1">
              <span className="text-[9px] font-bold text-amber-500 uppercase tracking-widest flex items-center gap-1">
                <AlertTriangle size={10} /> Selected packaging dimensions overridden
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-5 px-1.5 text-[9px] text-teal-500 hover:text-teal-400 hover:bg-teal-500/10 gap-1 font-bold"
                onClick={handleResetPackagingDefaults}
              >
                <RefreshCw size={10} /> Reset to defaults
              </Button>
            </div>
          )}

          <Button
            className={cn(
              "w-full h-9 rounded-lg font-black text-[10px] uppercase tracking-widest transition-all gap-2 shadow-lg",
              order.shipping_warehouse_ref 
                ? "bg-teal-600 hover:bg-teal-500 text-white shadow-teal-900/20" 
                : "bg-zinc-800 text-zinc-400 cursor-not-allowed opacity-50"
            )}
            disabled={isPending || isEstimating || !order.shipping_warehouse_ref}
            onClick={() => onGenerateTTN({ 
              weight, 
              volume, 
              length, 
              width, 
              height,
              parcel_override: isManual
            })}
          >
            {isPending ? <Loader2 size={14} className="animate-spin" /> : null}
            {isPending ? 'Processing...' : 'Generate NP Label'}
          </Button>
          {!order.shipping_warehouse_ref && (
            <p className="text-[9px] text-zinc-600 text-center mt-1 font-medium">Select a department to enable label generation</p>
          )}
        </div>
      )}

      {/* WB-3: WesternBid thermal label for international (non-UA) shipments. */}
      {!isEditing && canManageShipping && order.shipping_country !== 'UA' && (
        <WbLabelButton order={order} />
      )}
    </div>
  );
}
