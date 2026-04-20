import { 
  PieChart, 
  Pie, 
  Cell, 
  ResponsiveContainer, 
  Legend, 
  Tooltip 
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { ShopOrderCount } from '@/types/dashboard';

type ShopChartProps = {
  data: ShopOrderCount[];
};

const COLORS = ['#2dd4bf', '#0ea5e9', '#6366f1', '#a855f7', '#ec4899'];

export default function ShopDistributionChart({ data }: ShopChartProps) {
  return (
    <Card className="col-span-4 lg:col-span-2 border-slate-800/60 bg-slate-900/40 backdrop-blur-sm shadow-md">
      <CardHeader>
        <CardTitle className="text-sm font-bold uppercase tracking-widest text-slate-400">Order Distribution</CardTitle>
        <CardDescription className="text-xs text-slate-500">Volume breakdown by shop</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[300px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={80}
                paddingAngle={5}
                dataKey="order_count"
                nameKey="shop_name"
              >
                {data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#0f172a', 
                  border: '1px solid #1e293b',
                  borderRadius: '8px',
                  fontSize: '12px',
                  color: '#f8fafc'
                }}
              />
              <Legend 
                verticalAlign="bottom" 
                align="center"
                iconType="circle"
                wrapperStyle={{ fontSize: '10px', color: '#94a3b8' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
