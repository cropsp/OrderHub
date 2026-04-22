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
      "rounded-2xl border border-zinc-800 bg-zinc-950/50 backdrop-blur-xl p-6 shadow-sm hover:border-zinc-700 transition-all group",
      className
    )}>
      {title && (
        <div className="flex items-center gap-2 mb-4">
          {Icon && <Icon className="size-3.5 text-zinc-600 group-hover:text-zinc-400 transition-colors" />}
          <h3 className="text-[10px] font-bold uppercase tracking-[0.1em] text-zinc-600">{title}</h3>
        </div>
      )}
      {children}
    </div>
  );
}
