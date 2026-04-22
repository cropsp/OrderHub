import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { ChevronDown } from 'lucide-react';
import { ORDER_STATUS } from '@/lib/order-status';
import { cn } from '@/lib/utils';

type StatusTabsProps = {
  activeCategoryId: string;
  onCategoryChange: (id: string) => void;
  className?: string;
  counts?: Record<string, number>;
};

export default function StatusTabs({ 
  activeCategoryId, 
  onCategoryChange, 
  className,
  counts = {}
}: StatusTabsProps) {
  
  const renderTab = (id: string, label: string) => {
    const isActive = activeCategoryId === id;
    const count = counts[id] ?? 0;
    
    return (
      <button
        key={id}
        onClick={() => onCategoryChange(id)}
        className={cn(
          "px-4 py-2 text-xs font-bold uppercase tracking-wider transition-all relative border-b-2",
          isActive
            ? "border-teal-400 text-zinc-100"
            : "border-transparent text-zinc-400 hover:text-zinc-200"
        )}
      >
        {label} {count > 0 && `(${count})`}
      </button>
    );
  };

  const renderDropdownTab = (label: string, items: { id: string; label: string }[]) => {
    const isActive = items.some(item => item.id === activeCategoryId);
    const activeItem = items.find(item => item.id === activeCategoryId);
    
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className={cn(
              "px-4 py-2 text-xs font-bold uppercase tracking-wider transition-all relative border-b-2 flex items-center gap-1",
              isActive
                ? "border-teal-400 text-zinc-100"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            )}
          >
            {isActive ? activeItem?.label : label}
            <ChevronDown className="size-3 opacity-50" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="bg-zinc-900 border-zinc-800 text-zinc-300">
          {items.map(item => (
            <DropdownMenuItem 
              key={item.id}
              onClick={() => onCategoryChange(item.id)}
              className="text-[10px] font-bold uppercase tracking-widest focus:bg-zinc-800 focus:text-zinc-100"
            >
              {item.label} {counts[item.id] > 0 && `(${counts[item.id]})`}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  return (
    <div className={cn("flex items-center border-b border-zinc-800/60 overflow-x-auto", className)}>
      {renderTab('all', 'All')}
      {renderTab(ORDER_STATUS.NEW, 'New')}
      {renderTab(ORDER_STATUS.WAITING_INFO, 'Waiting Info')}
      {renderTab(ORDER_STATUS.INFO_RECEIVED, 'Info Received')}
      
      {renderDropdownTab('Design', [
        { id: ORDER_STATUS.DESIGN_PENDING, label: 'Design Pending' },
        { id: ORDER_STATUS.DESIGN_READY, label: 'Design Ready' },
      ])}
      
      {renderDropdownTab('Production', [
        { id: ORDER_STATUS.IN_PRODUCTION, label: 'In Production' },
        { id: ORDER_STATUS.SHIPPED, label: 'Shipped' },
      ])}
      
      {renderTab(ORDER_STATUS.COMPLETED, 'Completed')}
      {renderTab(ORDER_STATUS.CANCELLED, 'Cancelled')}
    </div>
  );
}
