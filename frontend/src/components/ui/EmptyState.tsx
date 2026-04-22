import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({ 
  icon: Icon, 
  title, 
  description, 
  actionLabel, 
  onAction,
  className 
}: EmptyStateProps) {
  return (
    <div className={cn(
      "flex flex-col items-center justify-center py-12 px-4 text-center animate-in fade-in zoom-in-95 duration-500",
      className
    )}>
      <div className="size-16 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-4 shadow-xl shadow-black/20">
        <Icon className="size-8 text-zinc-700" />
      </div>
      <h3 className="text-sm font-bold text-zinc-200 uppercase tracking-widest mb-1">{title}</h3>
      <p className="text-xs text-zinc-500 max-w-[240px] leading-relaxed mb-6">
        {description}
      </p>
      {actionLabel && onAction && (
        <Button 
          onClick={onAction}
          className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-[10px] font-bold uppercase tracking-widest h-9 px-6 rounded-lg"
        >
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
