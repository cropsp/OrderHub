import { useState, useMemo, useEffect, useRef } from 'react';
import { Phone, ClipboardList, Edit2, Check, Loader2, Search, MapPin, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { OrderDetail } from '@/types/order';
import { useSearchCities, useGetWarehouses } from '@/hooks/useShipping';
import { cn } from '@/lib/utils';
import { useToastStore } from '@/components/ui/Toast';

interface DetailLogisticsProps {
  order: OrderDetail;
  canManageShipping: boolean;
  isPending: boolean;
  onGenerateTTN: (params: { weight: number; volume: number }) => void;
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
  const containerRef = useRef<HTMLDivElement>(null);

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
  
  const { data: cities, isLoading: isCitiesLoading } = useSearchCities(cityQuery);
  
  const [formData, setFormData] = useState({
    shipping_name: order.shipping_name || '',
    shipping_phone: order.shipping_phone || '',
    shipping_street_1: order.shipping_street_1 || '',
    shipping_city: order.shipping_city || '',
    shipping_city_ref: order.shipping_city_ref || '',
    shipping_warehouse_ref: order.shipping_warehouse_ref || '',
    shipping_country: order.shipping_country || 'UA',
  });

  const { data: warehouses, isLoading: isWarehousesLoading } = useGetWarehouses(formData.shipping_city_ref);

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
              className="h-6 w-6 text-zinc-500 hover:text-zinc-200"
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
                  <label className="text-[10px] text-zinc-500 font-medium px-1 uppercase tracking-wider">Recipient Name</label>
                  <Input 
                    className="h-8 text-[11px] bg-zinc-950 border-zinc-800 focus:border-teal-500/50 focus:ring-teal-500/20"
                    placeholder="Full Name"
                    value={formData.shipping_name}
                    onChange={e => setFormData(p => ({ ...p, shipping_name: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-500 font-medium px-1 uppercase tracking-wider">Recipient Phone</label>
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
                    <label className="text-[10px] text-zinc-500 font-medium px-1 uppercase tracking-wider">City Search</label>
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
                      <label className="text-[10px] text-zinc-500 font-medium px-1 uppercase tracking-wider">Warehouse / Branch</label>
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
                            className="absolute right-2.5 top-2.5 text-zinc-500 hover:text-zinc-300"
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
                              <div className="p-4 text-[10px] text-zinc-500 text-center">No branches found</div>
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
                      onChange={e => setFormData(p => ({ ...p, shipping_country: e.target.value.toUpperCase() }))}
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
                  className="h-8 text-zinc-500 hover:text-zinc-300 text-[10px] uppercase font-semibold"
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
                <p className="text-zinc-500 text-[11px] ml-4.5">{order.shipping_city}{order.shipping_state ? `, ${order.shipping_state}` : ''} {order.shipping_zip}</p>
                <div className="flex items-center gap-2 mt-3">
                   <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 text-[9px] font-bold uppercase tracking-widest border border-zinc-700/50">
                    {order.shipping_country || '??'}
                   </span>
                   {order.shipping_warehouse_ref && (
                     <span className="px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-500 text-[9px] font-bold uppercase tracking-widest border border-teal-500/20">
                       NP Verified
                     </span>
                   )}
                </div>
              </div>
            </div>
          )}
          
          {!isEditing && (
            <div className="flex items-center gap-2 text-[11px] font-medium pt-3 border-t border-zinc-800/30">
              <Phone className="size-3.5 text-zinc-700" />
              {order.shipping_phone ? (
                <span className="text-zinc-500">{order.shipping_phone}</span>
              ) : (
                <span className="text-amber-500/70 italic flex items-center gap-1">
                  Missing phone number
                </span>
              )}
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
                        className="p-1 rounded-md hover:bg-red-500/10 text-zinc-500 hover:text-red-500 transition-all z-20"
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
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-500 font-bold uppercase tracking-wider px-1">Weight (kg)</label>
              <Input 
                type="number"
                step="0.1"
                className="h-8 text-[11px] bg-zinc-900 border-zinc-800"
                value={weight}
                onChange={e => setWeight(parseFloat(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-500 font-bold uppercase tracking-wider px-1">Volume (m³)</label>
              <Input 
                type="number"
                step="0.001"
                className="h-8 text-[11px] bg-zinc-900 border-zinc-800"
                value={volume}
                onChange={e => setVolume(parseFloat(e.target.value) || 0)}
              />
            </div>
          </div>
          
          <Button 
            className={cn(
              "w-full h-9 rounded-lg font-black text-[10px] uppercase tracking-widest transition-all gap-2 shadow-lg",
              order.shipping_warehouse_ref 
                ? "bg-teal-600 hover:bg-teal-500 text-white shadow-teal-900/20" 
                : "bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-50"
            )}
            disabled={isPending || !order.shipping_warehouse_ref}
            onClick={() => onGenerateTTN({ weight, volume })}
          >
            {isPending ? <Loader2 size={14} className="animate-spin" /> : null}
            {isPending ? 'Processing...' : 'Generate NP Label'}
          </Button>
          {!order.shipping_warehouse_ref && (
            <p className="text-[9px] text-zinc-600 text-center mt-1 font-medium">Select a department to enable label generation</p>
          )}
        </div>
      )}
    </div>
  );
}
