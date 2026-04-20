import { useState } from 'react';
import { useOrders } from '@/hooks/useOrders';
import { STATUS_CATEGORIES } from '@/lib/order-status';
import StatusTabs from './StatusTabs';
import ViewToggle from './ViewToggle';
import OrdersTable from './OrdersTable';
import PipelineBoard from './PipelineBoard';
import OrderDetailPanel from './OrderDetailPanel';

export default function OrdersLayout() {
  // 1. View State (Table or Board)
  const [view, setView] = useState<'table' | 'board'>('table');
  
  // 2. Active Tab State (Logical Category)
  const [activeCategoryId, setActiveCategoryId] = useState(STATUS_CATEGORIES[0].id);

  // 3. Selection State (for Drawer/Panel)
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  
  // 4. Find current category metadata
  const currentCategory = STATUS_CATEGORIES.find(c => c.id === activeCategoryId) || STATUS_CATEGORIES[0];
  
  // 5. Fetch data
  const { data, isLoading } = useOrders({ 
    status: currentCategory.statuses[0] as any 
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
