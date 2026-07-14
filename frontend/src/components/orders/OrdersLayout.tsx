import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Filter } from 'lucide-react';
import { useOrders } from '@/hooks/useOrders';
import { useShops } from '@/hooks/useShops';
import { ORDER_STATUS } from '@/lib/order-status';
import StatusTabs from './StatusTabs';
import ViewToggle from './ViewToggle';
import OrdersTable from './OrdersTable';
import PipelineBoard from './PipelineBoard';
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

const PAGE_LIMIT = 50;

type OrdersLayoutProps = {
  isArchive?: boolean;
  fixedShopId?: string;
};

export default function OrdersLayout({ isArchive = false, fixedShopId }: OrdersLayoutProps) {
  const navigate = useNavigate();
  // 1. View State
  const [view, setView] = useState<'table' | 'board'>('table');
  
  // 2. Filters State
  const [activeCategoryId, setActiveCategoryId] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedShopId, setSelectedShopId] = useState<string | undefined>(fixedShopId);
  const [page, setPage] = useState(1);

  const { data: shops } = useShops();

  // 4. Fetch data
  const filters: OrderListFilters = {
    status: activeCategoryId === 'all' ? undefined : (activeCategoryId as any),
    shop_id: selectedShopId,
    search: search || undefined,
    page,
    limit: PAGE_LIMIT,
  };

  const { data, isLoading } = useOrders(filters);
  const orders = data?.items ?? [];
  const canPrev = page > 1;
  const canNext = page < (data?.pages ?? 1);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <StatusTabs
          activeCategoryId={activeCategoryId}
          onCategoryChange={(id) => { setActiveCategoryId(id); setPage(1); }}
          className="w-full"
        />
        
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex flex-1 items-center gap-3 max-w-2xl">
            <div className="relative flex-1 group">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-zinc-400 group-focus-within:text-teal-400 transition-colors" />
              <Input
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                placeholder="Search by Order ID, Customer or Product..."
                className="pl-10 bg-zinc-900 border-zinc-800 focus-visible:border-teal-500/50 focus-visible:ring-teal-500/10 h-10 rounded-xl"
              />
            </div>
            
            {!fixedShopId && (
              <Select value={selectedShopId || 'all'} onValueChange={(val) => { setSelectedShopId(val === 'all' ? undefined : val); setPage(1); }}>
                <SelectTrigger className="w-[180px] h-10 rounded-xl border-zinc-800 bg-zinc-900 text-zinc-300 gap-2">
                  <Filter className="size-3.5 text-zinc-400" />
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
                onClick={() => navigate('/orders/new')}
                className="bg-teal-500 hover:bg-teal-400 text-zinc-950 font-bold h-10 px-6 rounded-xl shadow-lg shadow-teal-500/20 border-none transition-all hover:scale-[1.02] active:scale-[0.98]"
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
          <>
            <OrdersTable
              isLoading={isLoading}
              orders={orders}
            />
            {!isLoading && orders.length > 0 && (
              <div className="flex items-center justify-between px-2 pt-4">
                <p className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest">
                  Page {data?.page ?? 1} of {data?.pages ?? 1}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 px-4 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest transition-all"
                    disabled={!canPrev}
                    onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 px-4 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest transition-all"
                    disabled={!canNext}
                    onClick={() => setPage((prev) => prev + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
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
          />
        )}
      </div>
    </div>
  );
}
