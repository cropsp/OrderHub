import { LayoutGrid, List } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type ViewToggleProps = {
  view: 'table' | 'board';
  onViewChange: (view: 'table' | 'board') => void;
  className?: string;
};

export default function ViewToggle({ view, onViewChange, className }: ViewToggleProps) {
  return (
    <div className={cn("flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950/50 p-1", className)}>
      <Button
        className={cn(
          "h-8 gap-2 px-3 text-xs font-medium transition-all",
          view === 'table' 
            ? "bg-teal-500/10 text-teal-300 hover:bg-teal-500/20" 
            : "bg-transparent text-zinc-400 hover:text-zinc-300"
        )}
        onClick={() => onViewChange('table')}
        size="sm"
        variant="ghost"
      >
        <List className="size-3.5" />
        Table
      </Button>
      <Button
        className={cn(
          "h-8 gap-2 px-3 text-xs font-medium transition-all",
          view === 'board' 
            ? "bg-teal-500/10 text-teal-300 hover:bg-teal-500/20" 
            : "bg-transparent text-zinc-400 hover:text-zinc-300"
        )}
        onClick={() => onViewChange('board')}
        size="sm"
        variant="ghost"
      >
        <LayoutGrid className="size-3.5" />
        Board
      </Button>
    </div>
  );
}
