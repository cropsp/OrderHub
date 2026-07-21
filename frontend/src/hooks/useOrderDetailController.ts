import { useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import {
  useAddOrderItem,
  useDeleteOrderItem,
  useOrder,
  useUpdateOrder,
  useUpdateOrderItem,
  useUpdateOrderStatus,
} from '@/hooks/useOrders';
import { useCreateTTN, useDeleteTTN } from '@/hooks/useShipping';
import { useToastStore } from '@/components/ui/Toast';
import type { OrderDetail } from '@/types/order';
import { UserRole, Capability } from '@/types/user';

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
  const addItem = useAddOrderItem();
  const updateItem = useUpdateOrderItem();
  const deleteItem = useDeleteOrderItem();
  const createTTN = useCreateTTN();
  const deleteTTN = useDeleteTTN();
  const { addToast } = useToastStore();

  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  const isOwner = user?.role === UserRole.OWNER;
  const isManager = user?.role === UserRole.MANAGER;
  const canManageShipping = isOwner || isManager;
  // USER-ACCESS-2: per-order costs (DetailFinance) are gated by view_costs, not
  // by owner-ship. Owner always qualifies; others need the explicit capability.
  const canViewCosts =
    isOwner || Boolean(user?.capabilities?.includes(Capability.VIEW_COSTS));

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

  const handleAddItem = async (payload: {
    title: string;
    quantity: number;
    unit_price: number;
    product_variant_id?: string;
  }) => {
    if (!order) return;
    try {
      await addItem.mutateAsync({ orderId: order.id, ...payload });
    } catch (err) {
      addToast('Failed to add item', 'error');
      throw err;
    }
  };

  const handleUpdateItem = async (
    itemId: string,
    payload: {
      title?: string;
      quantity?: number;
      unit_price?: number;
      product_variant_id?: string;
    },
  ) => {
    if (!order) return;
    try {
      await updateItem.mutateAsync({ orderId: order.id, itemId, ...payload });
    } catch (err) {
      addToast('Failed to update item', 'error');
      throw err;
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    if (!order) return;
    try {
      await deleteItem.mutateAsync({ orderId: order.id, itemId });
    } catch (err) {
      addToast('Failed to delete item', 'error');
      throw err;
    }
  };

  return {
    order,
    isLoading,
    user,
    isOwner,
    isManager,
    canManageShipping,
    canViewCosts,
    saveStatus,
    handleUpdate,
    handleStatusChange,
    handleGenerateTTN,
    handleDeleteTTN,
    handleAddItem,
    handleUpdateItem,
    handleDeleteItem,
    isTTNPending: createTTN.isPending || deleteTTN.isPending,
  };
}
