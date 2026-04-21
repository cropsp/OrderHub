import { cn } from '@/lib/utils';

interface BentoCardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  icon?: any;
}

export function BentoCard({ children, className, title, icon: Icon }: BentoCardProps) {
  return (
    <div className={cn(
      "rounded-2xl border border-slate-800/60 bg-slate-900/30 backdrop-blur-xl p-6 shadow-sm hover:border-slate-700/80 transition-all group",
      className
    )}>
      {title && (
        <div className="flex items-center gap-2 mb-4">
          {Icon && <Icon className="size-4 text-slate-500 group-hover:text-teal-500 transition-colors" />}
          <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">{title}</h3>
        </div>
      )}
      {children}
    </div>
  );
}
