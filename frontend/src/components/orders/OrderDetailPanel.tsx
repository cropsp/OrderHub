import { format } from 'date-fns';
import { 
  Package, 
  History, 
  User, 
  MapPin, 
  Phone, 
  Mail, 
  DollarSign,
  UploadCloud,
  Info,
  CheckCircle2,
  Clock,
  ClipboardList
} from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import { debounce } from 'lodash-es';

import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle,
  DialogDescription
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { useOrder, useUpdateOrder } from '@/hooks/useOrders';
import { useAuth } from '@/hooks/useAuth';
import { UserRole } from '@/types/user';
import { getCategoryByStatus, type OrderStatusValue } from '@/lib/order-status';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select';
import { ORDER_STATUS } from '@/lib/order-status';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useCreateTTN } from '@/hooks/useShipping';
import { Card, CardContent } from '@/components/ui/card';
import AttachmentManager from './AttachmentManager';

type OrderDetailPanelProps = {
  orderId: string | null;
  onClose: () => void;
};

function BentoCard({ children, className, title, icon: Icon }: { children: React.ReactNode, className?: string, title?: string, icon?: any }) {
  return (
    <div className={cn(
      "rounded-2xl border border-slate-800/60 bg-slate-900/30 backdrop-blur-xl p-6 shadow-sm hover:border-slate-700/80 transition-all group",
      className
    )}>
      {title && (
        <div className="flex items-center gap-2 mb-4">
          {Icon && <Icon className="size-4 text-slate-500 group-hover:text-teal-500 transition-colors" />}
          <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">{title}</h3>
        </div>
      )}
      {children}
    </div>
  );
}

export default function OrderDetailPanel({ orderId, onClose }: OrderDetailPanelProps) {
  const { data, isLoading } = useOrder(orderId);
  const order = data as any as import('@/types/order').OrderDetail | undefined;
  const { user } = useAuth();
  const updateOrder = useUpdateOrder();
  const [internalNote, setInternalNote] = useState('');
  const [customInfo, setCustomInfo] = useState('');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const isOwner = user?.role === UserRole.OWNER;
  const isManager = user?.role === UserRole.MANAGER;
  const canManageShipping = isOwner || isManager;
  const createTTN = useCreateTTN();

  // Initialize local state when data arrives
  useEffect(() => {
    if (order) {
      setInternalNote(order.internal_note || '');
      setCustomInfo(order.custom_info || '');
    }
  }, [order?.id]);

  // Debounced auto-save
  const debouncedSave = useCallback(
    debounce(async (id: string, payload: any) => {
      setSaveStatus('saving');
      try {
        await updateOrder.mutateAsync({ orderId: id, payload });
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 2000);
      } catch {
        setSaveStatus('error');
      }
    }, 1000),
    []
  );

  const handleNoteChange = (val: string) => {
    setInternalNote(val);
    if (order) debouncedSave(order.id, { internal_note: val });
  };

  const handleCustomInfoChange = (val: string) => {
    setCustomInfo(val);
    if (order) debouncedSave(order.id, { custom_info: val });
  };

  const handleStatusChange = async (newStatus: string) => {
    if (order) {
      setSaveStatus('saving');
      try {
        await updateOrder.mutateAsync({ orderId: order.id, payload: { status: newStatus } });
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 2000);
      } catch {
        setSaveStatus('error');
      }
    }
  };

  const isOpen = Boolean(orderId);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[95vw] sm:w-[90vw] sm:max-w-none max-w-7xl h-[90vh] border-slate-800 bg-slate-950 p-0 shadow-[0_0_50px_-12px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col rounded-3xl">
        <DialogHeader className="sr-only">
          <DialogTitle>Order Management Console</DialogTitle>
          <DialogDescription>Full view of order {orderId}</DialogDescription>
        </DialogHeader>

        {!order || isLoading ? (
          <div className="p-12 space-y-8 h-full bg-slate-950">
            <Skeleton className="h-12 w-1/3 bg-slate-900 rounded-xl" />
            <div className="grid grid-cols-12 gap-8 h-full">
              <Skeleton className="col-span-8 h-[600px] bg-slate-900 rounded-3xl" />
              <Skeleton className="col-span-4 h-[600px] bg-slate-900 rounded-3xl" />
            </div>
          </div>
        ) : (
          <div className="flex flex-col h-full overflow-hidden">
            {/* Real Premium Header */}
            <header className="px-10 py-8 flex items-center justify-between border-b border-white/[0.03] bg-gradient-to-b from-white/[0.02] to-transparent shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <Select 
                    defaultValue={order.status} 
                    onValueChange={handleStatusChange}
                  >
                    <SelectTrigger className={cn(
                      "h-7 px-3 text-[10px] font-bold uppercase tracking-widest rounded-full border-none ring-offset-slate-950 focus:ring-teal-500/20",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'teal' && "bg-teal-500/10 text-teal-400",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'sky' && "bg-sky-500/10 text-sky-400",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'indigo' && "bg-indigo-500/10 text-indigo-400",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'amber' && "bg-amber-500/10 text-amber-400",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'orange' && "bg-orange-500/10 text-orange-400",
                    )}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-950 border-slate-800 text-slate-200">
                      {Object.entries(ORDER_STATUS).map(([key, value]) => (
                        <SelectItem key={value} value={value} className="text-[10px] uppercase tracking-widest focus:bg-teal-500/20 focus:text-teal-100">
                          {key.replace('_', ' ')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <span className="text-slate-600 font-medium">/</span>
                  <span className="font-mono text-sm font-bold text-teal-400">#{order.external_id}</span>
                </div>
                <h2 className="text-3xl font-heading font-bold text-slate-50 tracking-tight">{order.title}</h2>
              </div>

              <div className="flex items-center gap-4">
                <div className="flex flex-col items-end gap-1 px-4">
                   <div className="flex items-center gap-2">
                     {saveStatus === 'saving' && <Clock className="size-3 text-amber-400 animate-spin" />}
                     {saveStatus === 'saved' && <CheckCircle2 className="size-3 text-teal-400" />}
                     <span className={cn(
                       "text-[10px] font-bold uppercase tracking-widest",
                       saveStatus === 'saving' ? "text-amber-400" : 
                       saveStatus === 'saved' ? "text-teal-400" : "text-slate-500"
                     )}>
                       {saveStatus === 'saving' ? 'Syncing...' : saveStatus === 'saved' ? 'Updates Saved' : 'All Changes Persisted'}
                     </span>
                   </div>
                   <p className="text-[10px] text-slate-600 font-medium">
                     Last refetched at {format(new Date(), 'HH:mm:ss')}
                   </p>
                </div>
                <Separator orientation="vertical" className="h-10 bg-white/[0.05]" />
                <Button onClick={onClose} variant="ghost" className="rounded-full hover:bg-white/[0.03]">
                  Close Console
                </Button>
              </div>
            </header>

            <ScrollArea className="flex-1">
              <main className="px-10 py-10">
                <div className="grid grid-cols-12 gap-10">
                  
                  {/* MAIN CONTENT ZONE (Left) */}
                  <div className="col-span-12 lg:col-span-8 space-y-10">
                    
                    {/* Live Interaction Panels */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                       <BentoCard title="Internal Notes" icon={ClipboardList}>
                          <Textarea 
                            value={internalNote}
                            onChange={(e) => handleNoteChange(e.target.value)}
                            placeholder="Add private team-only notes about this order..."
                            className="bg-transparent border-none p-0 focus-visible:ring-0 resize-none min-h-[140px] text-slate-300 leading-relaxed placeholder:text-slate-600"
                          />
                       </BentoCard>

                       <BentoCard title="Customization Info" icon={Info}>
                          <Textarea 
                             value={customInfo}
                             onChange={(e) => handleCustomInfoChange(e.target.value)}
                             placeholder="Special instructions or custom data for production..."
                             className="bg-transparent border-none p-0 focus-visible:ring-0 resize-none min-h-[140px] text-teal-100 font-medium leading-relaxed placeholder:text-slate-600"
                          />
                       </BentoCard>
                    </div>

                    {/* Production Assets Bento Section */}
                    <BentoCard title="Production Assets" icon={UploadCloud} className="bg-teal-500/[0.02] border-teal-500/10">
                       <AttachmentManager orderId={order.id} />
                    </BentoCard>

                    {/* Order Items Bento Section */}
                    <BentoCard title="Product Inventory" icon={Package} className="p-0 overflow-hidden">
                       <div className="overflow-x-auto">
                         <table className="w-full text-left">
                           <thead>
                             <tr className="border-b border-white/[0.03] bg-white/[0.01]">
                               <th className="px-8 py-5 text-[10px] uppercase font-bold tracking-[0.2em] text-slate-500">Item Details</th>
                               <th className="px-8 py-5 text-[10px] uppercase font-bold tracking-[0.2em] text-slate-500 text-center">Qty</th>
                               <th className="px-8 py-5 text-[10px] uppercase font-bold tracking-[0.2em] text-slate-500 text-right">Unit Price</th>
                             </tr>
                           </thead>
                           <tbody className="divide-y divide-white/[0.03]">
                             {order.items.map((item) => (
                               <tr key={item.id} className="hover:bg-white/[0.01] transition-colors">
                                 <td className="px-8 py-6">
                                   <div className="flex flex-col gap-1">
                                      <p className="text-base font-bold text-slate-200">{item.title}</p>
                                      {item.variations && (
                                        <p className="text-xs text-slate-500 font-medium">{item.variations}</p>
                                      )}
                                      {item.sku && (
                                        <span className="mt-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-teal-500/5 text-teal-500/70 border border-teal-500/10 w-fit">
                                          SKU: {item.sku}
                                        </span>
                                      )}
                                   </div>
                                 </td>
                                 <td className="px-8 py-6 text-center">
                                   <span className="text-lg font-heading font-bold text-slate-400 italic">x{item.quantity}</span>
                                 </td>
                                 <td className="px-8 py-6 text-right">
                                   <p className="text-lg font-bold text-slate-100">{item.unit_price} <span className="text-[10px] text-slate-500 uppercase">{item.currency}</span></p>
                                 </td>
                               </tr>
                             ))}
                           </tbody>
                         </table>
                       </div>
                    </BentoCard>

                    {/* Customer Message Pane */}
                    {order.customer_note && (
                      <div className="relative overflow-hidden rounded-3xl bg-sky-500/5 p-8 border border-sky-500/10 shadow-[inset_0_2px_40px_rgba(14,165,233,0.03)]">
                        <div className="absolute top-0 right-0 p-8 text-sky-500/10">
                          <Mail className="size-24 scale-150 rotate-12" />
                        </div>
                        <div className="relative">
                          <div className="flex items-center gap-2 mb-4">
                            <Mail className="size-4 text-sky-500" />
                            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-500/60">Raw Customer Message</h3>
                          </div>
                          <p className="text-lg text-slate-300 italic font-medium leading-relaxed max-w-2xl">
                            "{order.customer_note}"
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* SIDEBAR ZONE (Right) */}
                  <div className="col-span-12 lg:col-span-4 space-y-8">
                    
                    {/* Customer Profile Bento */}
                    <BentoCard title="Customer Profile" icon={User}>
                       <div className="space-y-6">
                          <div className="flex items-center gap-4">
                             <div className="size-12 rounded-2xl bg-teal-500/10 flex items-center justify-center border border-teal-500/10">
                                <User className="size-6 text-teal-500" />
                             </div>
                             <div>
                                <p className="text-lg font-bold text-slate-100">{order.customer_name}</p>
                                <p className="text-xs text-slate-500 font-medium flex items-center gap-1.5 mt-1">
                                   <Mail className="size-3" />
                                   {order.customer?.email || 'No assigned email'}
                                </p>
                             </div>
                          </div>
                          <Separator className="bg-white/[0.03]" />
                          <div className="flex items-center justify-between text-xs">
                             <span className="text-slate-500 font-medium">Source Shop</span>
                             <span className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 font-bold uppercase tracking-wider text-[9px]">{order.shop_name}</span>
                          </div>
                       </div>
                    </BentoCard>

                    {/* Logistics Bento */}
                    <BentoCard title="Shipping & Logistics" icon={MapPin}>
                       <div className="space-y-6">
                          <div className="flex items-start gap-4">
                             <div className="size-10 rounded-xl bg-sky-500/10 flex items-center justify-center border border-sky-500/10 mt-1 shrink-0">
                                <MapPin className="size-5 text-sky-500" />
                             </div>
                             <div className="text-sm text-slate-300 leading-relaxed space-y-1">
                                <p className="font-bold text-slate-100">{order.shipping_name}</p>
                                <p>{order.shipping_street_1}</p>
                                {order.shipping_street_2 && <p>{order.shipping_street_2}</p>}
                                <p>{order.shipping_city}, {order.shipping_state} {order.shipping_zip}</p>
                                <p className="font-bold text-slate-600 uppercase tracking-[0.3em] mt-2 text-[10px]">{order.shipping_country}</p>
                             </div>
                          </div>
                          
                          {order.shipping_phone && (
                            <div className="flex items-center gap-3 pl-14 text-xs text-slate-400">
                               <Phone className="size-3.5" />
                               <span>{order.shipping_phone}</span>
                            </div>
                          )}

                          <div className="pt-2">
                            {order.ttn_number ? (
                              <div className="p-4 rounded-2xl bg-teal-500/10 border border-teal-500/20 group cursor-pointer hover:bg-teal-500/15 transition-colors">
                                <div className="flex items-center justify-between mb-2">
                                   <p className="text-[10px] font-bold text-teal-500 uppercase tracking-widest">Tracking (TTN)</p>
                                   <ClipboardList className="size-3 text-teal-500/40" />
                                </div>
                                <p className="font-mono text-xl text-slate-100 font-bold tracking-tighter">{order.ttn_number}</p>
                              </div>
                            ) : (
                              order.shipping_country === 'UA' && canManageShipping && (
                                <Button 
                                  className="w-full py-6 rounded-2xl bg-slate-900 border-slate-800 hover:bg-slate-800 text-teal-500 font-bold tracking-tight"
                                  variant="outline"
                                  disabled={createTTN.isPending}
                                  onClick={() => createTTN.mutate({ orderId: order.id, data: {} })}
                                >
                                  {createTTN.isPending ? 'Connecting NP...' : 'Generate Shipping Label (NP)'}
                                </Button>
                              )
                            )}
                          </div>
                       </div>
                    </BentoCard>

                    {/* Financial Overview Bento (Owner Only) */}
                    {isOwner && (
                      <BentoCard title="Financial Intelligence" icon={DollarSign} className="bg-amber-500/[0.03] border-amber-500/10">
                         <div className="space-y-5">
                            <div className="flex items-center justify-between">
                               <span className="text-xs text-slate-500 font-medium">Total Revenue</span>
                               <span className="text-lg font-bold text-slate-100">{order.total_price} {order.currency}</span>
                            </div>
                            <div className="flex items-center justify-between">
                               <span className="text-xs text-slate-500 font-medium">Platform Fees</span>
                               <span className="text-base font-bold text-red-400">-{order.platform_fee || 0} {order.currency}</span>
                            </div>
                            <Separator className="bg-white/[0.03]" />
                            <div className="flex items-center justify-between pt-1">
                               <span className="text-xs font-bold text-teal-500/80 uppercase tracking-widest">Est. Profit</span>
                               <span className="text-2xl font-heading font-black text-teal-400">
                                 {(order.total_price - (order.platform_fee || 0)).toFixed(2)} <span className="text-xs font-bold font-sans text-slate-500 ml-1">{order.currency}</span>
                               </span>
                            </div>
                         </div>
                      </BentoCard>
                    )}

                    {/* Execution History */}
                    <BentoCard title="Timeline" icon={History}>
                       <div className="relative pl-6 space-y-10 before:absolute before:inset-0 before:left-0 before:h-full before:w-px before:bg-white/[0.05]">
                          {order.status_history.map((entry, idx) => (
                             <div key={entry.id} className="relative group">
                                <div className={cn(
                                   "absolute -left-[27px] top-1 size-3 rounded-full border border-slate-950 ring-[6px] ring-slate-950/50",
                                   idx === 0 ? "bg-teal-500 shadow-[0_0_10px_rgba(20,184,166,0.5)]" : "bg-slate-700"
                                )} />
                                <div className="space-y-1">
                                   <div className="flex items-center gap-3">
                                      <p className="text-[10px] font-bold text-slate-200 uppercase tracking-tighter">
                                        {entry.to_status.replace('_', ' ')}
                                      </p>
                                      <span className="text-[9px] text-slate-600 font-medium uppercase tracking-[0.1em]">
                                        {format(new Date(entry.changed_at), 'MMM dd, HH:mm')}
                                      </span>
                                   </div>
                                   <div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                                      {idx === 0 ? <CheckCircle2 className="size-2.5 text-teal-500" /> : <Clock className="size-2.5 text-slate-600" />}
                                      <p className="text-[9px] text-slate-500 font-bold uppercase tracking-widest">
                                        {entry.changed_by_name || 'System Auto'}
                                      </p>
                                   </div>
                                   {entry.comment && (
                                     <div className="mt-3 text-[11px] p-4 rounded-2xl bg-white/[0.015] border border-white/[0.03] text-slate-400 leading-relaxed group-hover:text-slate-200 transition-colors">
                                       {entry.comment}
                                     </div>
                                   )}
                                </div>
                             </div>
                          ))}
                       </div>
                    </BentoCard>
                  </div>
                </div>
              </main>
            </ScrollArea>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
