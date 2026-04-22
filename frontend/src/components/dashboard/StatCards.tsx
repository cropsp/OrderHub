import { 
  Layers, 
  AlertTriangle, 
  CheckCircle,
  DollarSign
} from 'lucide-react';
import { MetricCard } from './MetricCard';
import type { DashboardResponse } from '@/types/dashboard';

type StatCardsProps = {
  data: DashboardResponse;
};

export default function StatCards({ data }: StatCardsProps) {
  const { stats, revenue_by_currency } = data;
  
  // Show all currencies in profit card
  const profitDisplay = revenue_by_currency.length > 0 
    ? revenue_by_currency.map(r => `${r.net_profit.toLocaleString()} ${r.currency}`).join(' / ')
    : '0 USD';

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <MetricCard 
        label="Net Profit"
        value={profitDisplay}
        icon={DollarSign}
        accentColor="text-emerald-400"
        trend={{ value: 12, label: "vs last week" }}
      />
      <MetricCard 
        label="Active Orders"
        value={stats.total_orders}
        icon={Layers}
        accentColor="text-blue-400"
        trend={{ value: 5, label: "vs last week" }}
      />
      <MetricCard 
        label="Attention Needed"
        value={stats.attention_needed_count}
        icon={AlertTriangle}
        accentColor="text-amber-400"
        trend={{ value: -2, label: "vs last week" }}
      />
      <MetricCard 
        label="Success Rate"
        value="98.5%"
        icon={CheckCircle}
        accentColor="text-teal-400"
        trend={{ value: 0, label: "vs last week" }}
      />
    </div>
  );
}
