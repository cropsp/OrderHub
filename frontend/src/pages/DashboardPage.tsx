import { useMemo } from 'react';
import { format } from 'date-fns';
import { AlertTriangle } from 'lucide-react';
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
      <ShellPage title="Dashboard" description="Overview of your business performance.">
        <div className="flex h-[400px] items-center justify-center rounded-xl border border-red-500/20 bg-red-500/5 text-red-400">
          Error loading dashboard data. Please try again later.
        </div>
      </ShellPage>
    );
  }

  return (
    <ShellPage
      description="Real-time overview of your order pipeline and financial performance."
      title="Dashboard Overview"
      actions={
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Filter by Shop:</span>
          <Select value={selectedShopId || 'all'} onValueChange={(val) => setSelectedShopId(val === 'all' ? undefined : val)}>
            <SelectTrigger className="w-[200px] border-slate-800 bg-slate-900/50 backdrop-blur-md text-slate-100">
              <SelectValue placeholder="All Shops" />
            </SelectTrigger>
            <SelectContent className="border-slate-800 bg-slate-900 text-slate-100">
              <SelectItem value="all" className="focus:bg-slate-800 focus:text-slate-100 text-slate-200">All Shops</SelectItem>
              {shops?.map((shop) => (
                <SelectItem key={shop.id} value={shop.id} className="focus:bg-slate-800 focus:text-slate-100 text-slate-200">
                  {shop.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      }
    >
      <div className="space-y-8 animate-fade-in">
        {isLoading || !data ? (
          <>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-32 w-full bg-slate-900/60" />
              ))}
            </div>
            <div className="grid gap-6 lg:grid-cols-6">
              <Skeleton className="col-span-4 h-[400px] bg-slate-900/60" />
              <Skeleton className="col-span-2 h-[400px] bg-slate-900/60" />
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              <Skeleton className="h-[320px] bg-slate-900/60" />
              <Skeleton className="h-[320px] bg-slate-900/60" />
            </div>
          </>
        ) : (
          <>
            {/* 1. Stat Cards */}
            <StatCards data={data} />

            {/* 2. Charts Row */}
            <div className="grid gap-6 lg:grid-cols-6">
              {/* Revenue Trends */}
              <div className="lg:col-span-4">
                <RevenueChart data={data.daily_revenue_trend} />
              </div>

              {/* Shop Distribution */}
              <div className="lg:col-span-2">
                <ShopDistributionChart data={data.orders_by_shop} />
              </div>
            </div>
            
            <div className="grid gap-6 lg:grid-cols-2">
              <section className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-800 rounded-xl p-6">
                <div className="mb-6 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-500">
                      Attention List
                    </h3>
                  </div>
                  <Link className="text-[10px] font-bold uppercase tracking-wider text-teal-400 hover:text-teal-300 transition-colors" to="/orders">
                    Manage queue →
                  </Link>
                </div>

                {isAttentionLoading ? (
                  <div className="space-y-3">
                    {[1, 2, 3, 4].map((item) => (
                      <Skeleton key={item} className="h-14 w-full bg-zinc-800/50 rounded-lg" />
                    ))}
                  </div>
                ) : attentionOrders.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 opacity-50">
                    <p className="text-sm text-zinc-500 font-medium">No urgent orders right now.</p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    {attentionOrders.map((order) => {
                      const theme = getShopTheme(order.shop_name ?? '');
                      return (
                        <div
                          key={order.id}
                          className="group relative flex items-center justify-between rounded-lg px-4 py-3 hover:bg-zinc-800/60 cursor-pointer transition-colors"
                          onClick={() => {/* handle navigation if needed */}}
                        >
                          <div className={cn("absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-8 rounded-full", theme.dot)} />
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                               <span className="text-zinc-500 text-xs font-mono">#{order.external_id}</span>
                               <p className="truncate text-sm font-medium text-zinc-100 line-clamp-1" title={order.title}>
                                 {order.title}
                               </p>
                            </div>
                            <p className="text-xs text-zinc-500 mt-0.5">
                              {order.shop_name} <span className="mx-1">·</span> Waiting since {format(new Date(order.ordered_at), 'MMM dd, HH:mm')}
                            </p>
                          </div>
                          <StatusBadge status={order.status} size="sm" className="ml-4" />
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              <section className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-800 rounded-xl p-6">
                <div className="mb-6 flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wide text-zinc-500">
                    Recent Activity
                  </h3>
                </div>

                {isRecentLoading ? (
                  <div className="space-y-3">
                    {[1, 2, 3, 4].map((item) => (
                      <Skeleton key={item} className="h-14 w-full bg-zinc-800/50 rounded-lg" />
                    ))}
                  </div>
                ) : (recentOrders?.items?.length ?? 0) === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 opacity-50">
                    <p className="text-sm text-zinc-500 font-medium">No recent orders available.</p>
                  </div>
                ) : (
                  <div className="flex flex-col">
                    {(recentOrders?.items ?? []).map((order) => {
                      const theme = getShopTheme(order.shop_name ?? '');
                      return (
                        <div
                          key={order.id}
                          className="flex items-center justify-between py-3 border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/40 px-2 rounded-lg transition-colors"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                               <Link to={`/orders?id=${order.id}`} className="text-zinc-500 text-xs font-mono hover:text-teal-400 transition-colors">
                                 #{order.external_id}
                               </Link>
                               <p className="truncate text-sm font-medium text-zinc-200 line-clamp-1">
                                 {order.title}
                               </p>
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                               <div className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider", theme.bg, theme.text)}>
                                  {order.shop_name}
                               </div>
                               <span className="text-zinc-500 text-[10px] uppercase font-medium">
                                 {format(new Date(order.ordered_at), 'MMM dd, HH:mm')}
                               </span>
                            </div>
                          </div>
                          <StatusBadge status={order.status} size="sm" className="ml-4" />
                        </div>
                      );
                    })}
                    
                    <Link 
                      className="mt-4 flex items-center justify-center py-2 text-xs font-bold uppercase tracking-wider text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50 rounded-lg transition-all" 
                      to="/orders"
                    >
                      View all orders →
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
