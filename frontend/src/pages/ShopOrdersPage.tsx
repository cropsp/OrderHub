import { useMemo } from 'react';
import { useParams } from 'react-router-dom';

import OrdersLayout from '@/components/orders/OrdersLayout';
import { useShops } from '@/hooks/useShops';

import ShellPage from './ShellPage';

export default function ShopOrdersPage() {
  const { shopId } = useParams<{ shopId: string }>();
  const { data: shops, isLoading } = useShops();

  const shop = useMemo(() => {
    if (!shopId || !shops) return null;
    return shops.find((item) => item.id === shopId) ?? null;
  }, [shopId, shops]);

  if (!shopId) {
    return (
      <ShellPage title="Shop Orders">
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-8 text-center text-red-400">
          Invalid shop route.
        </div>
      </ShellPage>
    );
  }

  if (!isLoading && !shop) {
    return (
      <ShellPage title="Shop Orders" description="Manage orders for a specific store.">
        <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-8 text-center">
          <p className="text-sm font-medium text-zinc-200">Shop not found</p>
          <p className="mt-1 text-xs text-zinc-400">
            This shop might have been deleted or you may not have access to it.
          </p>
        </div>
      </ShellPage>
    );
  }

  return (
    <ShellPage
      title={shop ? `${shop.name} Orders` : 'Shop Orders'}
      description="Order list filtered by selected shop."
    >
      <OrdersLayout fixedShopId={shopId} />
    </ShellPage>
  );
}
