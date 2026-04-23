import { useState } from 'react';

import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle,
  DialogDescription
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrder, useUpdateOrder, useUpdateOrderStatus } from '@/hooks/useOrders';
import { useAuth } from '@/hooks/useAuth';
import { useToastStore } from '@/components/ui/Toast';
import { UserRole } from '@/types/user';
import { useCreateTTN, useDeleteTTN } from '@/hooks/useShipping';

import AttachmentManager from './AttachmentManager';
import { DetailHeader } from './detail/DetailHeader';
import { DetailCustomizationInfo, DetailInternalNotes } from './detail/DetailNotes';
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
  const { data: order, isLoading } = useOrder(orderId);
  const { user } = useAuth();
  const updateOrder = useUpdateOrder();
  const updateStatus = useUpdateOrderStatus();
  const { addToast } = useToastStore();
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const isOwner = user?.role === UserRole.OWNER;
  const isManager = user?.role === UserRole.MANAGER;
  const canManageShipping = isOwner || isManager;
  const createTTN = useCreateTTN();
  const deleteTTN = useDeleteTTN();

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

  const handleGenerateTTN = (params: { 
    weight: number; 
    volume: number; 
    length?: number; 
    width?: number; 
    height?: number;
    parcel_override?: boolean;
  }) => {
    if (!order) return;
    createTTN.mutate({ 
      orderId: order.id, 
      data: {
        ...params,
        description: `Order #${order.external_id}: ${order.title.substring(0, 50)}`
      } 
    });
  };

  const handleDeleteTTN = () => {
    if (!order) return;
    deleteTTN.mutate(order.id);
  };

  const isOpen = Boolean(orderId);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[95vw] sm:w-[90vw] sm:max-w-none max-w-7xl h-[90vh] border-zinc-800 bg-zinc-950 p-0 shadow-[0_0_50px_-12px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col rounded-3xl">
        <DialogHeader className="sr-only">
          <DialogTitle>Order Management Console</DialogTitle>
          <DialogDescription>Full view of order {orderId}</DialogDescription>
        </DialogHeader>

        {!order || isLoading ? (
          <div className="p-12 space-y-8 h-full bg-zinc-950">
            <Skeleton className="h-12 w-1/3 bg-zinc-900 rounded-xl" />
            <div className="grid grid-cols-12 gap-8 h-full">
              <Skeleton className="col-span-8 h-[600px] bg-zinc-900 rounded-3xl" />
              <Skeleton className="col-span-4 h-[600px] bg-zinc-900 rounded-3xl" />
            </div>
          </div>
        ) : (
          <div className="flex flex-col h-full overflow-hidden bg-zinc-950">
            {/* 1. COMPACT HEADER */}
            <DetailHeader 
              order={order} 
              saveStatus={saveStatus} 
              onStatusChange={async (newStatus) => {
                if (!order) return;
                console.log(`[StatusChange] Attempting transition for order ${order.id} to ${newStatus}`);
                setSaveStatus('saving');
                try {
                  await updateStatus.mutateAsync({ orderId: order.id, status: newStatus });
                  console.log(`[StatusChange] Successfully updated order ${order.id}`);
                  setSaveStatus('saved');
                  setTimeout(() => setSaveStatus('idle'), 2000);
                } catch (err) {
                  console.error('[StatusChange] Failed to update status:', err);
                  setSaveStatus('error');
                  addToast('Failed to update order status', 'error');
                  setTimeout(() => setSaveStatus('idle'), 3000);
                }
              }}
              onClose={onClose}
            />

            {/* 2. SCROLLABLE BODY GRID */}
            <div className="flex-1 overflow-y-auto bg-zinc-950">
              <div className="max-w-[1600px] mx-auto grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-6 p-6 items-start">
                
                {/* LEFT COLUMN: Primary Content */}
                <div className="space-y-6 min-w-0">
                  {/* 1. PRODUCT INVENTORY */}
                  <DetailItems order={order} />

                  {/* 2. CUSTOMIZATION INFO */}
                  <DetailCustomizationInfo 
                    order={order} 
                    onUpdate={handleUpdate} 
                  />

                  {/* 3. PRODUCTION ASSETS */}
                  <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-5">
                    <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-4 px-1">
                      Production Assets
                    </h3>
                    <AttachmentManager orderId={order.id} />
                  </div>

                  {/* 4. INTERNAL NOTES */}
                  <DetailInternalNotes 
                    order={order} 
                    onUpdate={handleUpdate} 
                  />
                </div>

                {/* RIGHT COLUMN: Sticky Sidebar */}
                <aside className="sticky top-6 flex flex-col gap-4 max-h-[calc(100vh-8rem)] overflow-y-auto overflow-x-hidden pr-2 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
                  <DetailCustomer order={order} />
                  <DetailLogistics 
                    order={order} 
                    canManageShipping={canManageShipping}
                    isPending={createTTN.isPending || deleteTTN.isPending}
                    onGenerateTTN={handleGenerateTTN}
                    onRemoveTTN={handleDeleteTTN}
                  />
                  {isOwner && <DetailFinance order={order} />}
                  <DetailTimeline order={order} />
                </aside>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
