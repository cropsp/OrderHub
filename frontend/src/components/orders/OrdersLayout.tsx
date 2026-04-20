import { useState } from 'react';
import { useOrders } from '@/hooks/useOrders';
import { STATUS_CATEGORIES } from '@/lib/order-status';
import StatusTabs from './StatusTabs';
import ViewToggle from './ViewToggle';
import OrdersTable from './OrdersTable';
import PipelineBoard from './PipelineBoard';

export default function OrdersLayout() {
  // 1. View State (Table or Board)
  const [view, setView] = useState<'table' | 'board'>('table');
  
  // 2. Active Tab State (Logical Category)
  const [activeCategoryId, setActiveCategoryId] = useState(STATUS_CATEGORIES[0].id);
  
  // 3. Find current category metadata
  const currentCategory = STATUS_CATEGORIES.find(c => c.id === activeCategoryId) || STATUS_CATEGORIES[0];
  
  // 4. Fetch data using React Query hook
  // We filter by all statuses included in the logical category
  const { data, isLoading } = useOrders({ 
    status: currentCategory.statuses[0] as any // Backend API currently only accepts one status per request, we'll need to adapt for multiple later
  });

  const orders = data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <StatusTabs 
          activeCategoryId={activeCategoryId} 
          onCategoryChange={setActiveCategoryId} 
        />
        <ViewToggle view={view} onViewChange={setView} />
      </div>

      <div className="min-h-[500px]">
        {view === 'table' ? (
          <OrdersTable 
            isLoading={isLoading} 
            orders={orders} 
          />
        ) : (
          <PipelineBoard 
            columnStatuses={currentCategory.statuses} 
            isLoading={isLoading} 
            orders={orders} 
          />
        )}
      </div>
    </div>
  );
}
