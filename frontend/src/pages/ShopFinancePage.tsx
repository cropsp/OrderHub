import { useEffect, useMemo, useState } from 'react';
import { useParams, Link, Navigate } from 'react-router-dom';
import { format } from 'date-fns';
import { AlertTriangle, ArrowRight } from 'lucide-react';

import ShellPage from './ShellPage';
import { useShopFinance } from '@/hooks/useShopFinance';
import FinancePeriodSelector from '@/components/finance/FinancePeriodSelector';
import {
  loadLastPreset,
  rangeForPreset,
  type PeriodRange,
} from '@/components/finance/periodPresets';
import FinanceKpiCard from '@/components/finance/FinanceKpiCard';
import FinanceRevenueChart from '@/components/finance/FinanceRevenueChart';
import DiagnosticBadge from '@/components/finance/DiagnosticBadge';
import { Skeleton } from '@/components/ui/skeleton';
import type { CurrencyAmount } from '@/types/finance';

function formatCurrencyList(amounts: CurrencyAmount[]): string {
  if (!amounts || amounts.length === 0) return '—';
  return amounts
    .map(
      (a) =>
        `${a.amount.toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })} ${a.currency}`,
    )
    .join('\n');
}

function formatCount(value: number | CurrencyAmount[]): string {
  if (Array.isArray(value)) return formatCurrencyList(value);
  return value.toLocaleString('en-US');
}

export default function ShopFinancePage() {
  const { shopId } = useParams<{ shopId: string }>();

  const [range, setRange] = useState<PeriodRange>(() => {
    const preset = loadLastPreset();
    const effective = preset === 'custom' ? 'this_month' : preset;
    return rangeForPreset(effective);
  });

  const startIso = useMemo(() => format(range.start, 'yyyy-MM-dd'), [range.start]);
  const endIso = useMemo(() => format(range.end, 'yyyy-MM-dd'), [range.end]);

  const { data, isLoading, error } = useShopFinance(shopId, startIso, endIso);

  useEffect(() => {
    if (data?.shop_name) {
      document.title = `${data.shop_name} — Finance · OrderHub`;
    }
  }, [data?.shop_name]);

  if (!shopId) {
    return <Navigate replace to="/shops" />;
  }

  const handlePeriodChange = (next: PeriodRange) => {
    setRange(next);
  };

  if (error) {
    return (
      <ShellPage title="Finance" description="Per-shop financial overview.">
        <div className="flex h-[400px] flex-col items-center justify-center rounded-3xl border border-red-500/10 bg-red-500/5 text-red-400 gap-4">
          <AlertTriangle className="size-12 opacity-50" />
          <p className="font-bold uppercase tracking-widest text-xs">
            Failed to load finance data
          </p>
          <p className="text-sm text-red-400/60 max-w-md text-center">
            {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
              'Check your connection and try again.'}
          </p>
        </div>
      </ShellPage>
    );
  }

  return (
    <ShellPage
      title={data?.shop_name ? `${data.shop_name} — Finance` : 'Finance'}
      description="Revenue, costs, fees and net profit for the selected period."
    >
      <div className="space-y-6">
        <FinancePeriodSelector value={range} onChange={handlePeriodChange} />

        {isLoading || !data ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4, 5, 6, 7].map((i) => (
              <Skeleton key={i} className="h-32 w-full bg-zinc-900/40 rounded-xl" />
            ))}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <FinanceKpiCard
                title="Revenue"
                value={data.revenue}
                formatter={formatCount}
              />
              <FinanceKpiCard
                title="COGS"
                value={data.cogs}
                formatter={formatCount}
              />
              <FinanceKpiCard
                title="Fees"
                value={data.fees}
                formatter={formatCount}
              />
              <FinanceKpiCard
                title="Net Profit"
                value={data.net_profit}
                formatter={formatCount}
                footer={
                  <DiagnosticBadge shopId={shopId} diagnostic={data.diagnostic} />
                }
              />
              <FinanceKpiCard
                title="Pipeline Value"
                value={data.pipeline_value}
                formatter={formatCount}
              />
              <FinanceKpiCard
                title="Order Count"
                value={data.order_count}
                formatter={formatCount}
              />
              <FinanceKpiCard
                title="Avg Order Value"
                value={data.aov}
                formatter={formatCount}
              />
            </div>

            <div>
              <Link
                to={`/shops/${shopId}/orders`}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal-400 hover:text-teal-300 transition-colors"
              >
                Переглянути ордери за період
                <ArrowRight className="size-3.5" />
              </Link>
            </div>

            <FinanceRevenueChart
              data={data.time_series}
              granularity={data.granularity}
            />
          </>
        )}
      </div>
    </ShellPage>
  );
}
