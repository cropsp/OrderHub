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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { DailyRevenue } from '@/types/dashboard';

type RevenueChartProps = {
  data: DailyRevenue[];
};

export default function RevenueChart({ data }: RevenueChartProps) {
  return (
    <Card className="col-span-4 border-slate-800/60 bg-slate-900/40 backdrop-blur-sm shadow-md">
      <CardHeader>
        <CardTitle className="text-sm font-bold uppercase tracking-widest text-slate-400">Revenue Trend</CardTitle>
        <CardDescription className="text-xs text-slate-500">Completed order volume over the last 30 days</CardDescription>
      </CardHeader>
      <CardContent className="pl-2">
        <div className="h-[300px] min-h-[300px] w-full mt-4">
          <ResponsiveContainer width="100%" height="100%" minHeight={300} debounce={50}>
            {data && data.length > 0 ? (
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                <XAxis 
                  dataKey="date" 
                  stroke="#64748b" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false}
                  tickFormatter={(str) => {
                    const date = new Date(str);
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  }}
                />
                <YAxis 
                  stroke="#64748b" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false}
                  tickFormatter={(value) => `$${value}`}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#0f172a', 
                    border: '1px solid #1e293b',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }}
                  itemStyle={{ color: '#2dd4bf' }}
                  labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
                />
                <Area 
                  type="monotone" 
                  dataKey="revenue" 
                  stroke="#2dd4bf" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorRev)" 
                />
              </AreaChart>
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center space-y-2 opacity-50">
                <div className="size-12 rounded-full border-2 border-dashed border-slate-800 flex items-center justify-center">
                  <DollarSign className="size-6 text-slate-700" />
                </div>
                <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">No revenue data</p>
                <p className="text-[10px] text-slate-600">No completed or shipped orders in the last 30 days</p>
              </div>
            )}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
