import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { type StatusCategory, STATUS_CATEGORIES } from '@/lib/order-status';
import { cn } from '@/lib/utils';

type StatusTabsProps = {
  activeCategoryId: string;
  onCategoryChange: (id: string) => void;
  categories?: StatusCategory[];
  className?: string;
};

export default function StatusTabs({ 
  activeCategoryId, 
  onCategoryChange, 
  categories = STATUS_CATEGORIES,
  className 
}: StatusTabsProps) {
  return (
    <Tabs 
      className={cn("w-full", className)} 
      onValueChange={onCategoryChange} 
      value={activeCategoryId}
    >
      <TabsList className="bg-slate-950/50 border border-slate-800/60 h-10 p-1">
        {categories.map((category) => (
          <TabsTrigger
            className={cn(
              "px-4 text-xs font-medium uppercase tracking-wider transition-all",
              "data-[state=active]:bg-teal-500/20 data-[state=active]:text-teal-300 data-[state=active]:shadow-none",
              "text-slate-400 hover:text-slate-200"
            )}
            key={category.id}
            value={category.id}
          >
            {category.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
