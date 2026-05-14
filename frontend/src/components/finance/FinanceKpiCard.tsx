import { cn } from '@/lib/utils';
import type { CurrencyAmount, KpiCard, OrderCountCard } from '@/types/finance';

type Accent = 'positive' | 'negative' | 'neutral';

interface FinanceKpiCardProps {
  title: string;
  value: KpiCard | OrderCountCard;
  formatter: (current: number | CurrencyAmount[]) => string;
  accent?: Accent;
  /** Optional slot below the comparison line — used for the diagnostic badge under Net Profit. */
  footer?: React.ReactNode;
}

function isKpiCard(value: KpiCard | OrderCountCard): value is KpiCard {
  return Array.isArray((value as KpiCard).current);
}

export default function FinanceKpiCard({
  title,
  value,
  formatter,
  accent = 'neutral',
  footer,
}: FinanceKpiCardProps) {
  const main = isKpiCard(value) ? formatter(value.current) : formatter(value.current);
  const pct = value.change_percent;

  const accentColor =
    accent === 'positive'
      ? 'text-emerald-400'
      : accent === 'negative'
      ? 'text-red-400'
      : 'text-zinc-400';

  return (
    <div className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-800 rounded-xl p-5 flex flex-col gap-3 transition-all hover:-translate-y-px hover:shadow-lg hover:shadow-black/20">
      <span className={cn('text-xs font-bold uppercase tracking-wide', accentColor)}>
        {title}
      </span>

      <div className="text-2xl font-bold text-zinc-100 tracking-tight whitespace-pre-line">
        {main}
      </div>

      {pct === null ? (
        <div className="text-xs text-zinc-600 font-medium">— no prior period data</div>
      ) : (
        <div
          className={cn(
            'flex items-center gap-1.5 text-xs font-medium',
            pct > 0 && 'text-emerald-400',
            pct < 0 && 'text-red-400',
            pct === 0 && 'text-zinc-500',
          )}
        >
          <span>
            {pct > 0 && '↑'}
            {pct < 0 && '↓'}
            {pct === 0 && '→'}
          </span>
          <span>{Math.abs(pct).toFixed(1)}%</span>
          <span className="text-zinc-500 font-normal">vs previous period</span>
        </div>
      )}

      {footer}
    </div>
  );
}
