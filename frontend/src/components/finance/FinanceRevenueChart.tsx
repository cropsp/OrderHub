import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { DollarSign } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { TimeSeriesPoint } from '@/types/finance';

interface FinanceRevenueChartProps {
  data: TimeSeriesPoint[];
  granularity: 'day' | 'month';
}

interface CombinedPoint {
  date: string;
  revenue: number;
  net_profit: number;
}

function pickPrimaryCurrency(points: TimeSeriesPoint[]): string | null {
  if (points.length === 0) return null;
  const totals = new Map<string, number>();
  for (const p of points) {
    totals.set(p.currency, (totals.get(p.currency) ?? 0) + p.revenue);
  }
  let best: string | null = null;
  let bestVal = -Infinity;
  for (const [cur, val] of totals.entries()) {
    if (val > bestVal) {
      bestVal = val;
      best = cur;
    }
  }
  return best;
}

function formatTick(value: string, granularity: 'day' | 'month'): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return granularity === 'month'
    ? d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function FinanceRevenueChart({ data, granularity }: FinanceRevenueChartProps) {
  const primary = useMemo(() => pickPrimaryCurrency(data), [data]);
  const otherCurrencies = useMemo(() => {
    const set = new Set(data.map((p) => p.currency));
    if (primary) set.delete(primary);
    return Array.from(set);
  }, [data, primary]);

  const chartData = useMemo<CombinedPoint[]>(() => {
    if (!primary) return [];
    return data
      .filter((p) => p.currency === primary)
      .map((p) => ({ date: p.date, revenue: p.revenue, net_profit: p.net_profit }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [data, primary]);

  const hasData = chartData.length > 0;

  return (
    <Card className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-800 rounded-xl overflow-hidden">
      <CardHeader className="pb-2 flex flex-row items-baseline justify-between">
        <CardTitle className="text-xs font-bold uppercase tracking-wide text-zinc-400">
          Revenue & Net Profit
        </CardTitle>
        {primary && (
          <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-600">
            {primary}
          </span>
        )}
      </CardHeader>
      <CardContent>
        <div className="h-[280px] w-full mt-4">
          {hasData ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="financeRevenue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="40%" stopColor="var(--color-teal-400)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--color-teal-400)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="financeNetProfit" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="40%" stopColor="var(--color-blue-400)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--color-blue-400)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="var(--color-zinc-800)"
                />
                <XAxis
                  dataKey="date"
                  stroke="var(--color-zinc-500)"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={30}
                  tickFormatter={(v) => formatTick(v, granularity)}
                />
                <YAxis
                  stroke="var(--color-zinc-500)"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  cursor={{ stroke: 'var(--color-zinc-700)', strokeWidth: 1 }}
                  content={({ active, payload, label }) => {
                    if (!active || !payload || payload.length === 0) return null;
                    const revVal = payload.find((p) => p.dataKey === 'revenue')?.value;
                    const npVal = payload.find((p) => p.dataKey === 'net_profit')?.value;
                    return (
                      <div className="bg-zinc-900/90 backdrop-blur-md border border-white/10 rounded-lg p-3 shadow-xl">
                        <p className="text-[10px] text-zinc-400 uppercase font-bold mb-2">
                          {formatTick(String(label), granularity)}
                        </p>
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <div className="size-1.5 rounded-full bg-teal-400" />
                            <p className="text-xs font-bold text-zinc-100">
                              Revenue: {Number(revVal ?? 0).toFixed(2)} {primary}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="size-1.5 rounded-full bg-blue-400" />
                            <p className="text-xs font-bold text-zinc-100">
                              Net Profit: {Number(npVal ?? 0).toFixed(2)} {primary}
                            </p>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="revenue"
                  stroke="var(--color-teal-400)"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#financeRevenue)"
                  dot={{ r: 3, fill: 'var(--color-teal-400)', strokeWidth: 0 }}
                  activeDot={{
                    r: 5,
                    fill: 'var(--color-teal-400)',
                    stroke: 'white',
                    strokeWidth: 2,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="net_profit"
                  stroke="var(--color-blue-400)"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#financeNetProfit)"
                  dot={{ r: 3, fill: 'var(--color-blue-400)', strokeWidth: 0 }}
                  activeDot={{
                    r: 5,
                    fill: 'var(--color-blue-400)',
                    stroke: 'white',
                    strokeWidth: 2,
                  }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center space-y-2 opacity-50">
              <DollarSign className="size-8 text-zinc-700" />
              <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                No revenue data
              </p>
            </div>
          )}
        </div>
        {otherCurrencies.length > 0 && (
          <p className="mt-2 text-[10px] text-zinc-400 italic">
            Showing {primary} only — {otherCurrencies.join(', ')} shown in KPI cards.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
