import { 
  PieChart, 
  Pie, 
  Cell, 
  ResponsiveContainer, 
  Legend, 
  Tooltip,
  Label,
  Sector
} from 'recharts';
import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { ShopOrderCount } from '@/types/dashboard';
import { PackageOpen } from 'lucide-react';

type ShopChartProps = {
  data: ShopOrderCount[];
};

const COLORS = ['#2dd4bf', '#0ea5e9', '#6366f1', '#a855f7', '#ec4899', '#f59e0b', '#10b981'];

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const item = payload[0];
    return (
      <div className="bg-slate-950 border border-slate-800 p-3 rounded-xl shadow-2xl backdrop-blur-md">
        <div className="flex items-center gap-2 mb-1">
          <div className="size-2 rounded-full" style={{ backgroundColor: item.payload.fill }} />
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{item.name}</p>
        </div>
        <div className="flex items-baseline gap-1">
          <p className="text-lg font-black text-slate-100">{item.value}</p>
          <p className="text-[10px] text-slate-500 font-medium lowercase">orders</p>
        </div>
      </div>
    );
  }
  return null;
};

const renderActiveShape = (props: any) => {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
  return (
    <g>
      <Sector
        cx={cx}
        cy={cy}
        innerRadius={innerRadius}
        outerRadius={outerRadius + 4}
        startAngle={startAngle}
        endAngle={endAngle}
        fill={fill}
        className="drop-shadow-[0_0_8px_rgba(45,212,191,0.3)]"
      />
    </g>
  );
};

const AnyPie = Pie as any;

export default function ShopDistributionChart({ data }: ShopChartProps) {
  const [activeIndex, setActiveIndex] = useState(-1);

  const totalOrders = useMemo(() => 
    data.reduce((acc, curr) => acc + curr.order_count, 0), 
    [data]
  );

  const isEmpty = data.length === 0;

  return (
    <Card className="col-span-4 lg:col-span-2 border-slate-800/60 bg-slate-900/40 backdrop-blur-sm shadow-md flex flex-col">
      <CardHeader>
        <CardTitle className="text-sm font-bold uppercase tracking-widest text-slate-400">Order Distribution</CardTitle>
        <CardDescription className="text-xs text-slate-500">Volume breakdown by shop</CardDescription>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col justify-center min-h-[300px]">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center space-y-4 py-10 opacity-40">
             <div className="size-20 rounded-full border-2 border-dashed border-slate-700 flex items-center justify-center">
                <PackageOpen className="size-8 text-slate-600" />
             </div>
             <p className="text-xs font-bold uppercase tracking-widest text-slate-500">No data yet</p>
          </div>
        ) : (
          <div className="h-[300px] min-h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%" minHeight={300}>
              <PieChart>
                <AnyPie
                  data={data}
                  cx="50%"
                  cy="50%"
                  innerRadius={65}
                  outerRadius={85}
                  paddingAngle={5}
                  dataKey="order_count"
                  nameKey="shop_name"
                  stroke="none"
                  activeIndex={activeIndex}
                  activeShape={renderActiveShape}
                  onMouseEnter={(_: any, index: number) => setActiveIndex(index)}
                  onMouseLeave={() => setActiveIndex(-1)}
                  animationBegin={0}
                  animationDuration={1500}
                >
                  {data.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                  <Label 
                    content={({ viewBox }) => {
                      const { cx, cy } = viewBox as any;
                      return (
                        <g>
                          <text x={cx} y={cy - 5} textAnchor="middle" dominantBaseline="middle" className="fill-slate-100 text-3xl font-black font-heading tracking-tighter">
                            {totalOrders}
                          </text>
                          <text x={cx} y={cy + 20} textAnchor="middle" dominantBaseline="middle" className="fill-slate-500 text-[9px] font-bold uppercase tracking-[0.2em]">
                            TOTAL
                          </text>
                        </g>
                      )
                    }}
                  />
                </AnyPie>
                <Tooltip content={<CustomTooltip />} />
                <Legend 
                  verticalAlign="bottom" 
                  align="center"
                  iconType="circle"
                  wrapperStyle={{ 
                    fontSize: '9px', 
                    color: '#94a3b8', 
                    paddingTop: '20px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em'
                  }}
                  formatter={(value) => <span className="text-slate-500 font-bold">{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
