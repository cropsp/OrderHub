import { 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  AreaChart,
  Area
} from 'recharts';
import { DollarSign } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { DailyRevenue } from '@/types/dashboard';

type RevenueChartProps = {
  data: DailyRevenue[];
};

export default function RevenueChart({ data }: RevenueChartProps) {
  return (
    <Card className="col-span-4 bg-zinc-900/80 backdrop-blur-sm border border-zinc-800 rounded-xl overflow-hidden">
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-bold uppercase tracking-wide text-zinc-500">Revenue Trend</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[240px] w-full mt-4">
          <ResponsiveContainer width="100%" height="100%">
            {data && data.length > 0 ? (
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="40%" stopColor="var(--color-teal-400)" stopOpacity={0.4}/>
                    <stop offset="100%" stopColor="var(--color-teal-400)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-zinc-800)" />
                <XAxis 
                  dataKey="date" 
                  stroke="var(--color-zinc-500)" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false}
                  minTickGap={30}
                  tickFormatter={(str) => {
                    const date = new Date(str);
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  }}
                />
                <YAxis 
                  stroke="var(--color-zinc-500)" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false}
                  ticks={[0, 40, 80, 120, 160]}
                  tickFormatter={(value) => `$${value}`}
                />
                <Tooltip 
                  cursor={{ stroke: 'var(--color-zinc-700)', strokeWidth: 1 }}
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="bg-zinc-900/90 backdrop-blur-md border border-white/10 rounded-lg p-3 shadow-xl">
                          <p className="text-[10px] text-zinc-500 uppercase font-bold mb-1">
                            {new Date(label).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                          </p>
                          <div className="flex items-center gap-2">
                            <div className="size-1.5 rounded-full bg-teal-400" />
                            <p className="text-sm font-bold text-zinc-100">
                              {payload[0].value} USD
                            </p>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area 
                  type="monotone" 
                  dataKey="revenue" 
                  stroke="var(--color-teal-400)" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorRev)" 
                  dot={{ r: 3, fill: 'var(--color-teal-400)', strokeWidth: 0 }}
                  activeDot={{ r: 5, fill: 'var(--color-teal-400)', stroke: 'white', strokeWidth: 2 }}
                />
              </AreaChart>
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center space-y-2 opacity-50">
                <DollarSign className="size-8 text-zinc-700" />
                <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">No revenue data</p>
              </div>
            )}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
