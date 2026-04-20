import ShellPage from './ShellPage';
import OrdersLayout from '@/components/orders/OrdersLayout';

export default function OrdersPage() {
  return (
    <ShellPage 
      title="Orders" 
      description="Manage your order pipeline, production flow, and status updates."
    >
      <OrdersLayout />
    </ShellPage>
  );
}
