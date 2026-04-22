import { useState } from 'react';
import { 
  UploadCloud,
} from 'lucide-react';

import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle,
  DialogDescription
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrder, useUpdateOrder } from '@/hooks/useOrders';
import { useAuth } from '@/hooks/useAuth';
import { useToastStore } from '@/components/ui/Toast';
import { UserRole } from '@/types/user';
import { useCreateTTN } from '@/hooks/useShipping';

import AttachmentManager from './AttachmentManager';
import { BentoCard } from './detail/BentoCard';
import { DetailHeader } from './detail/DetailHeader';
import { DetailNotes } from './detail/DetailNotes';
import { DetailItems } from './detail/DetailItems';
import { DetailCustomer } from './detail/DetailCustomer';
import { DetailLogistics } from './detail/DetailLogistics';
import { DetailFinance } from './detail/DetailFinance';
import { DetailTimeline } from './detail/DetailTimeline';

type OrderDetailPanelProps = {
  orderId: string | null;
  onClose: () => void;
};

export default function OrderDetailPanel({ orderId, onClose }: OrderDetailPanelProps) {
  const { data: order, isLoading, dataUpdatedAt } = useOrder(orderId);
  const { user } = useAuth();
  const updateOrder = useUpdateOrder();
  const { addToast } = useToastStore();
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const isOwner = user?.role === UserRole.OWNER;
  const isManager = user?.role === UserRole.MANAGER;
  const canManageShipping = isOwner || isManager;
  const createTTN = useCreateTTN();

  const handleUpdate = async (payload: any) => {
    if (!order) return;
    setSaveStatus('saving');
    try {
      await updateOrder.mutateAsync({ orderId: order.id, payload });
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
      addToast('Failed to save changes. Please try again.', 'error');
    }
  };

  const handleGenerateTTN = () => {
    if (!order) return;
    createTTN.mutate({ 
      orderId: order.id, 
      data: {
        weight: 0.5, 
        description: `Order #${order.external_id}: ${order.title.substring(0, 50)}`
      } 
    });
  };

  const isOpen = Boolean(orderId);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[95vw] sm:w-[90vw] sm:max-w-none max-w-7xl h-[90vh] border-slate-800 bg-slate-950 p-0 shadow-[0_0_50px_-12px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col rounded-3xl">
        <DialogHeader className="sr-only">
          <DialogTitle>Order Management Console</DialogTitle>
          <DialogDescription>Full view of order {orderId}</DialogDescription>
        </DialogHeader>

        {!order || isLoading ? (
          <div className="p-12 space-y-8 h-full bg-slate-950">
            <Skeleton className="h-12 w-1/3 bg-slate-900 rounded-xl" />
            <div className="grid grid-cols-12 gap-8 h-full">
              <Skeleton className="col-span-8 h-[600px] bg-slate-900 rounded-3xl" />
              <Skeleton className="col-span-4 h-[600px] bg-slate-900 rounded-3xl" />
            </div>
          </div>
        ) : (
          <div className="flex flex-col h-full overflow-hidden">
            <DetailHeader 
              order={order} 
              saveStatus={saveStatus} 
              dataUpdatedAt={dataUpdatedAt || 0}
              onStatusChange={(status) => handleUpdate({ status })}
              onClose={onClose}
            />

            <ScrollArea className="flex-1">
              <main className="px-10 py-10">
                <div className="grid grid-cols-12 gap-10">
                  
                  {/* MAIN CONTENT ZONE (Left) */}
                  <div className="col-span-12 lg:col-span-8 space-y-10">
                    <DetailNotes order={order} onUpdate={handleUpdate} />

                    <BentoCard title="Production Assets" icon={UploadCloud} className="bg-teal-500/[0.02] border-teal-500/10">
                       <AttachmentManager orderId={order.id} />
                    </BentoCard>

                    <DetailItems order={order} />
                  </div>

                  {/* SIDEBAR ZONE (Right) */}
                  <div className="col-span-12 lg:col-span-4 space-y-8">
                    <DetailCustomer order={order} />

                    <DetailLogistics 
                      order={order} 
                      canManageShipping={canManageShipping}
                      isPending={createTTN.isPending}
                      onGenerateTTN={handleGenerateTTN}
                    />

                    {isOwner && <DetailFinance order={order} />}

                    <DetailTimeline order={order} />
                  </div>
                </div>
              </main>
            </ScrollArea>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
