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
              <section className="rounded-xl border border-amber-500/25 bg-gradient-to-br from-amber-500/10 via-red-500/5 to-slate-950/40 p-6 shadow-[0_0_0_1px_rgba(245,158,11,0.08)]">
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-amber-200">
                      Attention List
                    </h3>
                  </div>
                  <Link className="text-xs font-medium text-amber-300 hover:text-amber-200" to="/orders">
                    Manage queue
                  </Link>
                </div>

                {isAttentionLoading ? (
                  <div className="space-y-2">
                    {[1, 2, 3, 4].map((item) => (
                      <Skeleton key={item} className="h-12 w-full bg-slate-900/60" />
                    ))}
                  </div>
                ) : attentionOrders.length === 0 ? (
                  <p className="text-sm text-amber-200/80">No urgent orders right now.</p>
                ) : (
                  <div className="space-y-2">
                    {attentionOrders.map((order) => (
                      <div
                        key={order.id}
                        className="flex items-center justify-between rounded-lg border border-amber-500/20 bg-slate-950/50 px-4 py-3"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-slate-100">
                            #{order.external_id} · {order.title}
                          </p>
                          <p className="text-xs text-amber-100/80">
                            {order.shop_name ?? 'Unknown shop'} · Waiting since{' '}
                            {format(new Date(order.ordered_at), 'MMM dd, HH:mm')}
                          </p>
                        </div>
                        <span className="ml-4 shrink-0 rounded-md border border-amber-500/30 bg-amber-500/15 px-2 py-1 text-[11px] uppercase tracking-wide text-amber-200">
                          {order.status.replace('_', ' ')}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="rounded-xl border border-slate-800/60 bg-slate-900/30 p-6">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                    Recent Activity
                  </h3>
                  <Link className="text-xs font-medium text-teal-400 hover:text-teal-300" to="/orders">
                    View all orders
                  </Link>
                </div>

                {isRecentLoading ? (
                  <div className="space-y-2">
                    {[1, 2, 3, 4].map((item) => (
                      <Skeleton key={item} className="h-12 w-full bg-slate-900/60" />
                    ))}
                  </div>
                ) : (recentOrders?.items?.length ?? 0) === 0 ? (
                  <p className="text-sm text-slate-500">No recent orders available.</p>
                ) : (
                  <div className="space-y-2">
                    {(recentOrders?.items ?? []).map((order) => (
                      <div
                        key={order.id}
                        className="flex items-center justify-between rounded-lg border border-slate-800/70 bg-slate-950/30 px-4 py-3"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-slate-200">
                            #{order.external_id} · {order.title}
                          </p>
                          <p className="text-xs text-slate-500">
                            {order.shop_name ?? 'Unknown shop'} · {format(new Date(order.ordered_at), 'MMM dd, HH:mm')}
                          </p>
                        </div>
                        <span className="ml-4 shrink-0 rounded-md border border-slate-700 bg-slate-800/50 px-2 py-1 text-[11px] uppercase tracking-wide text-slate-300">
                          {order.status.replace('_', ' ')}
                        </span>
                      </div>
                    ))}
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
