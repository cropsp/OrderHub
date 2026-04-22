import { useState } from 'react';
import { Plus, Search, Filter } from 'lucide-react';
import { useOrders } from '@/hooks/useOrders';
import { useShops } from '@/hooks/useShops';
import { ORDER_STATUS } from '@/lib/order-status';
import StatusTabs from './StatusTabs';
import ViewToggle from './ViewToggle';
import OrdersTable from './OrdersTable';
import PipelineBoard from './PipelineBoard';
import OrderDetailPanel from './OrderDetailPanel';
import NewOrderDialog from './NewOrderDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select';
import { getShopTheme } from '@/utils/shopTheme';
import { cn } from '@/lib/utils';
import type { OrderListFilters } from '@/types/order';

type OrdersLayoutProps = {
  isArchive?: boolean;
  fixedShopId?: string;
};

export default function OrdersLayout({ isArchive = false, fixedShopId }: OrdersLayoutProps) {
  // 1. View State
  const [view, setView] = useState<'table' | 'board'>('table');
  
  // 2. Filters State
  const [activeCategoryId, setActiveCategoryId] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedShopId, setSelectedShopId] = useState<string | undefined>(fixedShopId);

  const { data: shops } = useShops();
  
  // 3. Selection & Modal State
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [isNewOrderOpen, setIsNewOrderOpen] = useState(false);
  
  // 4. Fetch data
  const filters: OrderListFilters = {
    status: activeCategoryId === 'all' ? undefined : (activeCategoryId as any),
    shop_id: selectedShopId,
    search: search || undefined,
  };

  const { data, isLoading } = useOrders(filters);
  const orders = data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <StatusTabs 
          activeCategoryId={activeCategoryId} 
          onCategoryChange={setActiveCategoryId}
          className="w-full"
        />
        
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex flex-1 items-center gap-3 max-w-2xl">
            <div className="relative flex-1 group">
              <Search className="absolute left-3 top-1/2 -tranzinc-y-1/2 size-4 text-zinc-500 group-focus-within:text-teal-400 transition-colors" />
              <Input 
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by Order ID, Customer or Product..." 
                className="pl-10 bg-zinc-900 border-zinc-800 focus-visible:border-teal-500/50 focus-visible:ring-teal-500/10 h-10 rounded-xl"
              />
            </div>
            
            {!fixedShopId && (
              <Select value={selectedShopId || 'all'} onValueChange={(val) => setSelectedShopId(val === 'all' ? undefined : val)}>
                <SelectTrigger className="w-[180px] h-10 rounded-xl border-zinc-800 bg-zinc-900 text-zinc-300 gap-2">
                  <Filter className="size-3.5 text-zinc-500" />
                  <SelectValue placeholder="All Shops" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800 text-zinc-300">
                  <SelectItem value="all">All Shops</SelectItem>
                  {shops?.map((shop) => {
                    const theme = getShopTheme(shop.name);
                    return (
                      <SelectItem key={shop.id} value={shop.id} className="focus:bg-zinc-800 focus:text-zinc-100">
                        <div className="flex items-center gap-2">
                          <div className={cn("size-2 rounded-full", theme.dot)} />
                          {shop.name}
                        </div>
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {!isArchive && (
              <Button 
                onClick={() => setIsNewOrderOpen(true)}
                className="bg-teal-500 hover:bg-teal-400 text-zinc-950 font-bold h-10 px-6 rounded-xl shadow-lg shadow-teal-500/20 border-none"
              >
                <Plus className="mr-2 size-4" /> New Order
              </Button>
            )}
            <div className="h-10 w-px bg-zinc-800 mx-1 hidden sm:block" />
            <ViewToggle view={view} onViewChange={setView} />
          </div>
        </div>
      </div>

      <div className="min-h-[500px]">
        {view === 'table' ? (
          <OrdersTable 
            isLoading={isLoading} 
            orders={orders} 
            onSelectOrder={setSelectedOrderId}
          />
        ) : (
          <PipelineBoard 
            columnStatuses={activeCategoryId === 'all' ? [
              ORDER_STATUS.NEW, 
              ORDER_STATUS.WAITING_INFO, 
              ORDER_STATUS.INFO_RECEIVED,
              ORDER_STATUS.DESIGN_PENDING,
              ORDER_STATUS.DESIGN_READY,
              ORDER_STATUS.IN_PRODUCTION,
              ORDER_STATUS.SHIPPED
            ] : [activeCategoryId as any]} 
            isLoading={isLoading} 
            orders={orders} 
            onSelectOrder={setSelectedOrderId}
          />
        )}
      </div>

      <OrderDetailPanel 
        orderId={selectedOrderId} 
        onClose={() => setSelectedOrderId(null)} 
      />

      <NewOrderDialog 
        open={isNewOrderOpen} 
        onOpenChange={setIsNewOrderOpen} 
      />
    </div>
  );
}
