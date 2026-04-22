import { useParams, Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import OrderDetailView from '@/components/orders/OrderDetailView';

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();

  if (!id) return null;

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      {/* Navigation Bar */}
      <nav className="border-b border-zinc-900 bg-zinc-950/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-6 py-3">
          <Link 
            to="/orders" 
            className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500 hover:text-teal-400 transition-colors group"
          >
            <ArrowLeft size={12} className="group-hover:-translate-x-1 transition-transform" />
            Back to Orders
          </Link>
        </div>
      </nav>

      {/* Page Content */}
      <main className="flex-1 overflow-y-auto">
        <OrderDetailView orderId={id} />
      </main>
    </div>
  );
}
