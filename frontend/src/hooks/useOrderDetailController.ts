import { useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import { useOrder, useUpdateOrder, useUpdateOrderStatus } from '@/hooks/useOrders';
import { useCreateTTN, useDeleteTTN } from '@/hooks/useShipping';
import { useToastStore } from '@/components/ui/Toast';
import type { OrderDetail } from '@/types/order';
import { UserRole } from '@/types/user';

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface GenerateTTNParams {
  weight: number;
  volume: number;
  length?: number;
  width?: number;
  height?: number;
  parcel_override?: boolean;
}

// Shared controller for OrderDetailPanel (dialog) and OrderDetailView (full page).
// Both containers duplicated data-loading, role derivation, and mutation handlers —
// consolidating here prevents the two from drifting on every TTN or status change.
export function useOrderDetailController(orderId: string | null) {
  const { data: order, isLoading } = useOrder(orderId);
  const { user } = useAuth();
  const updateOrder = useUpdateOrder();
  const updateStatus = useUpdateOrderStatus();
  const createTTN = useCreateTTN();
  const deleteTTN = useDeleteTTN();
  const { addToast } = useToastStore();

  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  const isOwner = user?.role === UserRole.OWNER;
  const isManager = user?.role === UserRole.MANAGER;
  const canManageShipping = isOwner || isManager;

  const handleUpdate = async (payload: Partial<OrderDetail>) => {
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

  const handleStatusChange = async (newStatus: string) => {
    if (!order) return;
    setSaveStatus('saving');
    try {
      await updateStatus.mutateAsync({ orderId: order.id, status: newStatus });
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
      addToast('Failed to update order status', 'error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    }
  };

  const handleGenerateTTN = (params: GenerateTTNParams) => {
    if (!order) return;
    createTTN.mutate({
      orderId: order.id,
      data: {
        ...params,
        description: `Order #${order.external_id}: ${order.title.substring(0, 50)}`,
      },
    });
  };

  const handleDeleteTTN = () => {
    if (!order) return;
    deleteTTN.mutate(order.id);
  };

  return {
    order,
    isLoading,
    user,
    isOwner,
    isManager,
    canManageShipping,
    saveStatus,
    handleUpdate,
    handleStatusChange,
    handleGenerateTTN,
    handleDeleteTTN,
    isTTNPending: createTTN.isPending || deleteTTN.isPending,
  };
}
