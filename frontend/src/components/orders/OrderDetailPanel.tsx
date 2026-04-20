import { format } from 'date-fns';
import { 
  Package, 
  History, 
  User, 
  MapPin, 
  Phone, 
  Mail, 
  DollarSign,
} from 'lucide-react';
import { 
  Sheet, 
  SheetContent, 
  SheetHeader, 
  SheetTitle,
  SheetDescription
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrder } from '@/hooks/useOrders';
import { useAuth } from '@/hooks/useAuth';
import { UserRole } from '@/types/user';
import { getCategoryByStatus, type OrderStatusValue } from '@/lib/order-status';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useCreateTTN } from '@/hooks/useShipping';

type OrderDetailPanelProps = {
  orderId: string | null;
  onClose: () => void;
};

function SectionTitle({ icon: Icon, title }: { icon: any, title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="size-4 text-slate-500" />
      <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">{title}</h3>
    </div>
  );
}

export default function OrderDetailPanel({ orderId, onClose }: OrderDetailPanelProps) {
  const { data, isLoading } = useOrder(orderId);
  const order = data as any as import('@/types/order').OrderDetail | undefined;
  const { user } = useAuth();
  const isOwner = user?.role === UserRole.OWNER;
  const isManager = user?.role === UserRole.MANAGER;
  const canManageShipping = isOwner || isManager;
  const createTTN = useCreateTTN();

  const isOpen = Boolean(orderId);

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-xl border-l border-slate-800 bg-slate-950 p-0 shadow-2xl">
        <ScrollArea className="h-full">
          <div className="p-6">
            {!order || isLoading ? (
              <div className="space-y-6">
                <Skeleton className="h-8 w-1/2 bg-slate-900" />
                <Skeleton className="h-32 w-full bg-slate-900" />
                <Skeleton className="h-64 w-full bg-slate-900" />
              </div>
            ) : (
              <div className="space-y-8 animate-fade-in">
                {/* Header */}
                <SheetHeader className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Badge className={cn(
                      "px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'teal' && "bg-teal-500/10 text-teal-400 border-teal-500/20",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'sky' && "bg-sky-500/10 text-sky-400 border-sky-500/20",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'indigo' && "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'amber' && "bg-amber-500/10 text-amber-400 border-amber-500/20",
                      getCategoryByStatus(order.status as OrderStatusValue)?.color === 'orange' && "bg-orange-500/10 text-orange-400 border-orange-500/20",
                    )} variant="outline">
                      {order.status.replace('_', ' ')}
                    </Badge>
                    <span className="text-xs text-slate-500 font-medium">
                      Ordered {format(new Date(order.ordered_at), 'MMM dd, yyyy')}
                    </span>
                  </div>
                  <SheetTitle className="text-2xl font-heading text-slate-100 leading-tight">
                    {order.title}
                  </SheetTitle>
                  <SheetDescription className="flex items-center gap-2 text-slate-400">
                    <span className="font-mono text-xs font-semibold text-teal-400">#{order.external_id}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Package className="size-3" />
                      {order.shop_name}
                    </span>
                  </SheetDescription>
                </SheetHeader>

                <Separator className="bg-slate-900" />

                {/* Customer & Shipping */}
                <section>
                  <SectionTitle icon={User} title="Customer & Shipping" />
                  <div className="grid gap-6 sm:grid-cols-2">
                    <div className="space-y-3">
                      <div className="flex items-start gap-3">
                        <User className="size-4 mt-0.5 text-slate-600" />
                        <div>
                          <p className="text-sm font-medium text-slate-200">{order.customer_name}</p>
                          <p className="text-xs text-slate-500 flex items-center gap-1">
                            <Mail className="size-3" />
                            {order.customer?.email || 'No email'}
                          </p>
                        </div>
                      </div>
                      {order.shipping_phone && (
                        <div className="flex items-center gap-3">
                          <Phone className="size-4 text-slate-600" />
                          <p className="text-xs text-slate-300">{order.shipping_phone}</p>
                        </div>
                      )}
                    </div>
                    <div className="flex items-start gap-3">
                      <MapPin className="size-4 mt-0.5 text-slate-600" />
                      <div className="text-xs space-y-1 text-slate-300">
                        <p className="font-medium text-slate-200">{order.shipping_name}</p>
                        <p>{order.shipping_street_1}</p>
                        {order.shipping_street_2 && <p>{order.shipping_street_2}</p>}
                        <p>{order.shipping_city}, {order.shipping_state} {order.shipping_zip}</p>
                        <p className="font-bold text-slate-500 uppercase tracking-widest mt-1">{order.shipping_country}</p>

                        <div className="pt-2">
                          {order.ttn_number ? (
                            <div className="mt-2 p-2 rounded-md bg-teal-500/10 border border-teal-500/20 inline-block">
                              <p className="text-[10px] font-bold text-teal-500 uppercase">Tracking (TTN)</p>
                              <p className="font-mono text-slate-200 mt-0.5">{order.ttn_number}</p>
                            </div>
                          ) : (
                            order.shipping_country === 'UA' && canManageShipping && (
                              <Button 
                                size="sm" 
                                variant="outline" 
                                className="mt-2 h-7 bg-slate-900 border-slate-700 hover:bg-slate-800 text-xs"
                                disabled={createTTN.isPending}
                                onClick={() => createTTN.mutate({ orderId: order.id, data: {} })}
                              >
                                {createTTN.isPending ? 'Generating...' : 'Create TTN'}
                              </Button>
                            )
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                {/* Order Items */}
                <section>
                  <SectionTitle icon={Package} title="Order Items" />
                  <div className="rounded-lg border border-slate-900 bg-slate-900/20 overflow-hidden">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="bg-slate-900/50 border-b border-slate-900">
                          <th className="p-3 font-semibold text-slate-400">Product</th>
                          <th className="p-3 font-semibold text-slate-400 text-center w-16">Qty</th>
                          <th className="p-3 font-semibold text-slate-400 text-right w-24">Price</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-900">
                        {order.items.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-900/30 transition-colors">
                            <td className="p-3">
                              <p className="font-medium text-slate-200">{item.title}</p>
                              {item.variations && (
                                <p className="mt-1 text-[10px] text-slate-500">{item.variations}</p>
                              )}
                              {item.sku && (
                                <p className="mt-1 font-mono text-[9px] text-slate-600 uppercase">SKU: {item.sku}</p>
                              )}
                            </td>
                            <td className="p-3 text-center text-slate-300 font-medium">x{item.quantity}</td>
                            <td className="p-3 text-right">
                              <p className="font-semibold text-slate-200">{item.unit_price} {item.currency}</p>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                {/* Financial Details (Owner Only) */}
                {isOwner && (
                  <section className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                    <SectionTitle icon={DollarSign} title="Financial Overview" />
                    <div className="grid gap-4 sm:grid-cols-3 text-center">
                      <div className="space-y-1">
                        <p className="text-[10px] uppercase font-bold text-slate-500">Revenue</p>
                        <p className="text-sm font-bold text-slate-100">{order.total_price} {order.currency}</p>
                      </div>
                      <div className="space-y-1">
                        <p className="text-[10px] uppercase font-bold text-slate-500">Platform Fee</p>
                        <p className="text-sm font-bold text-red-400">-{order.platform_fee || 0} {order.currency}</p>
                      </div>
                      <div className="space-y-1">
                        <p className="text-[10px] uppercase font-bold text-slate-500">Net Est.</p>
                        <p className="text-sm font-bold text-teal-400">
                          {(order.total_price - (order.platform_fee || 0)).toFixed(2)} {order.currency}
                        </p>
                      </div>
                    </div>
                  </section>
                )}

                {/* Notes */}
                {(order.customer_note || order.internal_note || order.custom_info) && (
                  <section className="space-y-4">
                    {order.customer_note && (
                      <div className="p-3 rounded-lg bg-sky-500/5 border border-sky-500/10">
                        <p className="text-[10px] uppercase font-bold text-sky-500/60 mb-1">Customer Note</p>
                        <p className="text-xs text-slate-300 italic">"{order.customer_note}"</p>
                      </div>
                    )}
                    {order.custom_info && (
                      <div className="p-3 rounded-lg bg-teal-500/5 border border-teal-500/10">
                        <p className="text-[10px] uppercase font-bold text-teal-500/60 mb-1">Order Customization</p>
                        <p className="text-xs text-slate-200 font-medium whitespace-pre-wrap">{order.custom_info}</p>
                      </div>
                    )}
                  </section>
                )}

                {/* History */}
                <section className="pb-10">
                  <SectionTitle icon={History} title="Timeline & History" />
                  <div className="relative space-y-6 before:absolute before:inset-0 before:ml-2 before:h-full before:w-0.5 before:bg-slate-900">
                    {order.status_history.length === 0 ? (
                      <p className="text-xs text-slate-600 italic ml-6">Initial import from {order.shop_name}</p>
                    ) : (
                      order.status_history.map((entry) => (
                        <div key={entry.id} className="relative ml-6">
                           <div className="absolute -left-7 top-1.5 size-3 rounded-full border-2 border-slate-950 bg-teal-500" />
                           <div className="flex flex-col">
                             <div className="flex items-center gap-2">
                               <p className="text-xs font-bold text-slate-200 uppercase tracking-tighter">
                                 {entry.from_status} → {entry.to_status}
                               </p>
                               <span className="text-[10px] text-slate-600">
                                 {format(new Date(entry.changed_at), 'MMM dd, HH:mm')}
                               </span>
                             </div>
                             <p className="text-[10px] text-slate-400 mt-0.5 italic">
                               By {entry.changed_by_name || 'System'}
                             </p>
                             {entry.comment && (
                               <div className="mt-2 text-xs p-2 rounded bg-slate-900/50 text-slate-300">
                                 {entry.comment}
                               </div>
                             )}
                           </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
