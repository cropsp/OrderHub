import { useMemo } from 'react';
import { format } from 'date-fns';
import { AlertTriangle, Clock, PackagePlus, Receipt, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useOrders } from '@/hooks/useOrders';
import { useDashboard } from '@/hooks/useDashboard';
import ShellPage from './ShellPage';
import StatCards from '@/components/dashboard/StatCards';
import RevenueChart from '@/components/dashboard/RevenueChart';
import ShopDistributionChart from '@/components/dashboard/ShopChart';
import { Skeleton } from '@/components/ui/skeleton';
import { useShops } from '@/hooks/useShops';
import { useState } from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { getShopTheme } from '@/utils/shopTheme';
import { cn } from '@/lib/utils';

export default function DashboardPage() {
  const [selectedShopId, setSelectedShopId] = useState<string | undefined>(undefined);
  const { data: shops } = useShops();
  const { data, isLoading, error } = useDashboard(selectedShopId);
  const { data: recentOrders, isLoading: isRecentLoading } = useOrders({ 
    page: 1, 
    limit: 10,
    shop_id: selectedShopId 
  });
  const { data: attentionNew, isLoading: isNewAttentionLoading } = useOrders({
    page: 1,
    limit: 10,
    status: 'new',
    shop_id: selectedShopId
  });
  const { data: attentionWaitingInfo, isLoading: isWaitingAttentionLoading } = useOrders({
    page: 1,
    limit: 10,
    status: 'waiting_info',
    shop_id: selectedShopId
  });
  const { data: attentionInfoReceived, isLoading: isInfoAttentionLoading } = useOrders({
    page: 1,
    limit: 10,
    status: 'info_received',
    shop_id: selectedShopId
  });

  const isAttentionLoading = isNewAttentionLoading || isWaitingAttentionLoading || isInfoAttentionLoading;
  const attentionOrders = useMemo(() => {
    const merged = [
      ...(attentionNew?.items ?? []),
      ...(attentionWaitingInfo?.items ?? []),
      ...(attentionInfoReceived?.items ?? []),
    ];

    const unique = new Map<string, (typeof merged)[number]>();
    for (const order of merged) {
      if (!unique.has(order.id)) {
        unique.set(order.id, order);
      }
    }

    return Array.from(unique.values())
      .sort((a, b) => new Date(a.ordered_at).getTime() - new Date(b.ordered_at).getTime())
      .slice(0, 8);
  }, [attentionInfoReceived?.items, attentionNew?.items, attentionWaitingInfo?.items]);

  if (error) {
    return (
      <ShellPage title="Executive Dashboard" description="System telemetry and business intelligence overview.">
        <div className="flex h-[400px] flex-col items-center justify-center rounded-3xl border border-red-500/10 bg-red-500/5 text-red-400 gap-4">
          <AlertTriangle className="size-12 opacity-50" />
          <p className="font-bold uppercase tracking-widest text-xs">Intelligence Link Severed</p>
          <p className="text-sm text-red-400/60 max-w-xs text-center">Failed to establish connection with the dashboard stream. Please verify your session.</p>
        </div>
      </ShellPage>
    );
  }

  return (
    <ShellPage
      description="Real-time strategic overview of your production pipeline and financial throughput."
      title="Executive Overview"
      actions={
        <div className="flex items-center gap-4">
          <div className="h-8 w-px bg-zinc-800/60 mx-2 hidden md:block" />
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Active Context:</span>
            <Select value={selectedShopId || 'all'} onValueChange={(val) => setSelectedShopId(val === 'all' ? undefined : val)}>
              <SelectTrigger className="w-[180px] h-10 border-zinc-800 bg-zinc-950 text-zinc-100 rounded-xl focus:ring-teal-500/20">
                <SelectValue placeholder="Unified View" />
              </SelectTrigger>
              <SelectContent className="border-zinc-800 bg-zinc-950 text-zinc-100 rounded-xl">
                <SelectItem value="all" className="focus:bg-zinc-900 focus:text-teal-400 text-zinc-400 font-bold uppercase text-[10px] tracking-widest">Global Operations</SelectItem>
                {shops?.map((shop) => (
                  <SelectItem key={shop.id} value={shop.id} className="focus:bg-zinc-900 focus:text-teal-400">
                    <div className="flex items-center gap-2">
                       <div className="size-1.5 rounded-full" style={{ backgroundColor: shop.color }} />
                       <span className="text-sm font-semibold">{shop.name}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      }
    >
      <div className="space-y-10 animate-in fade-in duration-700">
        {isLoading || !data ? (
          <>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-32 w-full bg-zinc-900/60 rounded-3xl" />
              ))}
            </div>
            <div className="grid gap-8 lg:grid-cols-6">
              <Skeleton className="lg:col-span-4 h-[450px] bg-zinc-900/60 rounded-3xl" />
              <Skeleton className="lg:col-span-2 h-[450px] bg-zinc-900/60 rounded-3xl" />
            </div>
          </>
        ) : (
          <>
            {/* 1. Stat Cards */}
            <StatCards data={data} />

            {/* PKG-2: low-stock packaging widget — hidden when count is 0. */}
            {data.low_stock_packaging_count > 0 && (
              <Link
                to="/packaging"
                className="flex items-center justify-between bg-amber-500/10 border border-amber-500/20 rounded-3xl px-6 py-4 hover:bg-amber-500/[0.13] transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="size-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                    <PackagePlus className="h-4 w-4 text-amber-500" />
                  </div>
                  <div>
                    <p className="text-[11px] font-black uppercase tracking-[0.2em] text-amber-400">
                      Low-stock packaging
                    </p>
                    <p className="text-xs text-zinc-400 mt-1">
                      {data.low_stock_packaging_count}{' '}
                      {data.low_stock_packaging_count === 1 ? 'box is' : 'boxes are'} at or below threshold — time to restock.
                    </p>
                  </div>
                </div>
                <span className="text-[10px] font-black uppercase tracking-widest text-amber-400 group-hover:text-amber-300 flex items-center gap-1">
                  Open inventory <TrendingUp size={12} />
                </span>
              </Link>
            )}

            {/* MAT-5: workshop overhead not tagged to any shop — hidden when 0. */}
            {data.unallocated_overhead.length > 0 && (
              <Link
                to="/inventory/overhead-materials"
                data-testid="unallocated-overhead-card"
                className="flex items-center justify-between bg-sky-500/10 border border-sky-500/20 rounded-3xl px-6 py-4 hover:bg-sky-500/[0.13] transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="size-8 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center">
                    <Receipt className="h-4 w-4 text-sky-400" />
                  </div>
                  <div>
                    <p className="text-[11px] font-black uppercase tracking-[0.2em] text-sky-400">
                      Workshop overhead (unallocated)
                    </p>
                    <p className="text-xs text-zinc-400 mt-1">
                      {data.unallocated_overhead
                        .map(
                          (a) =>
                            `${a.amount.toLocaleString('en-US', {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })} ${a.currency}`,
                        )
                        .join(' · ')}{' '}
                      — workshop-wide spend not tied to any shop.
                    </p>
                  </div>
                </div>
                <span className="text-[10px] font-black uppercase tracking-widest text-sky-400 group-hover:text-sky-300 flex items-center gap-1">
                  Open overhead <TrendingUp size={12} />
                </span>
              </Link>
            )}

            {/* 2. Charts Row */}
            <div className="grid gap-8 lg:grid-cols-6">
              {/* Revenue Trends */}
              <div className="lg:col-span-4 transition-all duration-500 hover:translate-y-[-2px]">
                <RevenueChart data={data.daily_revenue_trend} />
              </div>

              {/* Shop Distribution */}
              <div className="lg:col-span-2 transition-all duration-500 hover:translate-y-[-2px]">
                <ShopDistributionChart data={data.orders_by_shop} />
              </div>
            </div>
            
            <div className="grid gap-8 lg:grid-cols-2">
              <section className="bg-zinc-900/20 backdrop-blur-md border border-zinc-800/60 rounded-3xl p-8 shadow-2xl relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-br from-amber-500/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                <div className="mb-8 flex items-center justify-between relative z-10">
                  <div className="flex items-center gap-3">
                    <div className="size-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                       <AlertTriangle className="h-4 w-4 text-amber-500" />
                    </div>
                    <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-zinc-500">
                      Priority triage
                    </h3>
                  </div>
                  <Link className="text-[10px] font-black uppercase tracking-widest text-teal-400 hover:text-teal-300 transition-all flex items-center gap-2 group/link" to="/orders">
                    System Queue <TrendingUp size={12} className="group-hover/link:translate-x-0.5 group-hover/link:-translate-y-0.5 transition-transform" />
                  </Link>
                </div>

                {isAttentionLoading ? (
                  <div className="space-y-4">
                    {[1, 2, 3, 4].map((item) => (
                      <Skeleton key={item} className="h-16 w-full bg-zinc-900/60 rounded-2xl" />
                    ))}
                  </div>
                ) : attentionOrders.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <div className="size-16 rounded-full bg-zinc-950 border border-zinc-800 flex items-center justify-center mb-4 opacity-20">
                       <Clock className="size-8" />
                    </div>
                    <p className="text-sm text-zinc-600 font-bold uppercase tracking-widest">All pipelines clear</p>
                  </div>
                ) : (
                  <div className="space-y-2 relative z-10">
                    {attentionOrders.map((order) => {
                      const theme = getShopTheme(order.shop_name ?? '');
                      return (
                        <Link
                          key={order.id}
                          to={`/orders?id=${order.id}`}
                          className="group/item relative flex items-center justify-between rounded-2xl px-5 py-4 hover:bg-zinc-950 border border-transparent hover:border-zinc-800 transition-all duration-300 shadow-sm hover:shadow-xl"
                        >
                          <div className={cn("absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 rounded-r-full transition-all group-hover/item:h-10", theme.dot)} />
                          <div className="min-w-0">
                            <div className="flex items-center gap-3">
                               <span className="text-zinc-600 text-[10px] font-black font-mono uppercase tracking-tighter">#{order.external_id}</span>
                               <p className="truncate text-sm font-bold text-zinc-100 tracking-tight line-clamp-1 group-hover/item:text-teal-400 transition-colors" title={order.title}>
                                 {order.title}
                               </p>
                            </div>
                            <div className="flex items-center gap-2 mt-1.5">
                               <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">{order.shop_name}</p>
                               <span className="text-zinc-800 font-black">•</span>
                               <p className="text-[10px] font-bold text-zinc-600">
                                 Stalled {format(new Date(order.ordered_at), 'MMM dd, HH:mm')}
                               </p>
                            </div>
                          </div>
                          <StatusBadge status={order.status} size="sm" className="ml-4 shadow-inner" />
                        </Link>
                      );
                    })}
                  </div>
                )}
              </section>

              <section className="bg-zinc-900/20 backdrop-blur-md border border-zinc-800/60 rounded-3xl p-8 shadow-2xl relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-br from-teal-500/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                <div className="mb-8 flex items-center justify-between relative z-10">
                   <div className="flex items-center gap-3">
                    <div className="size-8 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center">
                       <TrendingUp className="h-4 w-4 text-teal-500" />
                    </div>
                    <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-zinc-500">
                      Telemetry feed
                    </h3>
                  </div>
                </div>

                {isRecentLoading ? (
                  <div className="space-y-4">
                    {[1, 2, 3, 4].map((item) => (
                      <Skeleton key={item} className="h-16 w-full bg-zinc-900/60 rounded-2xl" />
                    ))}
                  </div>
                ) : (recentOrders?.items?.length ?? 0) === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center opacity-20">
                    <p className="text-sm font-bold uppercase tracking-widest">No recent throughput</p>
                  </div>
                ) : (
                  <div className="flex flex-col relative z-10">
                    <div className="space-y-1">
                      {(recentOrders?.items ?? []).map((order) => {
                        const theme = getShopTheme(order.shop_name ?? '');
                        return (
                          <Link
                            key={order.id}
                            to={`/orders?id=${order.id}`}
                            className="flex items-center justify-between py-4 px-4 rounded-2xl border border-transparent hover:border-zinc-800 hover:bg-zinc-950 transition-all duration-300 group/recent shadow-sm hover:shadow-xl"
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-3">
                                 <span className="text-zinc-600 text-[10px] font-black font-mono uppercase tracking-tighter group-hover/recent:text-teal-400 transition-colors">
                                   #{order.external_id}
                                 </span>
                                 <p className="truncate text-sm font-bold text-zinc-200 tracking-tight line-clamp-1">
                                   {order.title}
                                 </p>
                              </div>
                              <div className="flex items-center gap-3 mt-1.5">
                                 <div className={cn("px-2 py-0.5 rounded-lg text-[9px] font-black uppercase tracking-widest shadow-inner", theme.bg, theme.text)}>
                                    {order.shop_name}
                                 </div>
                                 <span className="text-zinc-600 text-[10px] font-bold">
                                   {format(new Date(order.ordered_at), 'MMM dd, HH:mm')}
                                 </span>
                              </div>
                            </div>
                            <StatusBadge status={order.status} size="sm" className="ml-4 shadow-inner" />
                          </Link>
                        );
                      })}
                    </div>
                    
                    <Link 
                      className="mt-6 flex items-center justify-center py-4 bg-zinc-950/50 hover:bg-zinc-950 border border-zinc-800/40 rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500 hover:text-zinc-100 transition-all shadow-sm hover:shadow-xl" 
                      to="/orders"
                    >
                      Access historical logs
                    </Link>
                  </div>
                )}
              </section>
            </div>
          </>
        )}
      </div>
    </ShellPage>
  );
}
