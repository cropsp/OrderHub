import ShellPage from './ShellPage';
import OrdersLayout from '@/components/orders/OrdersLayout';

export default function ArchivePage() {
  return (
    <ShellPage 
      title="Archive" 
      description="View and browse completed or cancelled historical orders."
    >
      <OrdersLayout isArchive={true} />
    </ShellPage>
  );
}
