import { useDashboard } from '@/hooks/useDashboard';
import ShellPage from './ShellPage';
import StatCards from '@/components/dashboard/StatCards';
import RevenueChart from '@/components/dashboard/RevenueChart';
import ShopDistributionChart from '@/components/dashboard/ShopChart';
import { Skeleton } from '@/components/ui/skeleton';

export default function DashboardPage() {
  const { data, isLoading, error } = useDashboard();

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
            
            {/* 3. Placeholder for Attention List / Recent Activity */}
            <div className="rounded-xl border border-slate-800/60 bg-slate-900/20 p-8 text-center">
              <p className="text-sm text-slate-500 font-medium">
                Detailed "Attention Needed" list and "Recent Activity" feed are coming in the next update.
              </p>
            </div>
          </>
        )}
      </div>
    </ShellPage>
  );
}
