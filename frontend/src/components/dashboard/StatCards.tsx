import { 
  ShoppingBag, 
  AlertCircle, 
  CheckCircle2,
  DollarSign
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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

  const cards = [
    {
      title: 'Net Profit',
      value: profitDisplay,
      description: 'Estimated profit (Shipped + Completed)',
      icon: DollarSign,
      color: 'text-teal-400',
    },
    {
      title: 'Active Orders',
      value: stats.total_orders.toString(),
      description: 'Total orders in pipeline',
      icon: ShoppingBag,
      color: 'text-sky-400',
    },
    {
      title: 'Attention Needed',
      value: stats.attention_needed_count.toString(),
      description: 'New, Waiting or Info Received',
      icon: AlertCircle,
      color: 'text-amber-400',
    },
    {
      title: 'Success Rate',
      value: '98.5%', // Mock for now
      description: 'Satisfaction score',
      icon: CheckCircle2,
      color: 'text-indigo-400',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title} className="border-slate-800/60 bg-slate-900/40 backdrop-blur-sm shadow-sm transition-all hover:bg-slate-900/60">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-slate-500">
              {card.title}
            </CardTitle>
            <card.icon className={`size-4 ${card.color}`} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-slate-100">{card.value}</div>
            <p className="mt-1 text-[10px] text-slate-500">
              {card.description}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
