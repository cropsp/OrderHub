import { useState } from 'react';
import { useOrders } from '@/hooks/useOrders';
import { STATUS_CATEGORIES, ARCHIVE_CATEGORIES } from '@/lib/order-status';
import StatusTabs from './StatusTabs';
import ViewToggle from './ViewToggle';
import OrdersTable from './OrdersTable';
import PipelineBoard from './PipelineBoard';
import OrderDetailPanel from './OrderDetailPanel';
import type { OrderListFilters } from '@/types/order';

type OrdersLayoutProps = {
  isArchive?: boolean;
  fixedShopId?: string;
};

export default function OrdersLayout({ isArchive = false, fixedShopId }: OrdersLayoutProps) {
  const categories = isArchive ? ARCHIVE_CATEGORIES : STATUS_CATEGORIES;
  
  // 1. View State (Table or Board)
  const [view, setView] = useState<'table' | 'board'>('table');
  
  // 2. Active Tab State (Logical Category)
  const [activeCategoryId, setActiveCategoryId] = useState(categories[0].id);

  // 3. Selection State (for Drawer/Panel)
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  
  // 4. Find current category metadata
  const currentCategory = categories.find(c => c.id === activeCategoryId) || categories[0];
  
  // 5. Fetch data
  const filters: OrderListFilters = {
    status: currentCategory.statuses[0],
    ...(fixedShopId ? { shop_id: fixedShopId } : {}),
  };

  const { data, isLoading } = useOrders(filters);

  const orders = data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <StatusTabs 
          activeCategoryId={activeCategoryId} 
          onCategoryChange={setActiveCategoryId}
          categories={categories}
        />
        <ViewToggle view={view} onViewChange={setView} />
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
            columnStatuses={currentCategory.statuses} 
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
    </div>
  );
}
