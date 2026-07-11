import { useState } from 'react';
import { useCreateOrder } from '@/hooks/useOrders';

const INITIAL_ITEM = { title: '', quantity: 1, unit_price: 0 };

// C-1: field-level validation. Keys are checked in this priority order so the
// view can scroll/focus the first offending field.
export type OrderFieldError = 'shop_id' | 'email' | 'items';
export type OrderFieldErrors = Partial<Record<OrderFieldError, string>>;

export function useOrderForm(onSuccess: () => void) {
  const createOrder = useCreateOrder();
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<OrderFieldErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const [orderData, setOrderData] = useState({
    shop_id: '',
    external_id: '',
    title: '',
    currency: 'USD',
    email: '',
    full_name: '',
    shipping_name: '',
    shipping_phone: '',
    shipping_street_1: '',
    shipping_city: '',
    shipping_city_ref: '',
    shipping_warehouse_ref: '',
    shipping_state: '',
    shipping_zip: '',
    shipping_country: 'UA',
  });

  const [items, setItems] = useState([INITIAL_ITEM]);

  const addItem = () => setItems([...items, { ...INITIAL_ITEM }]);
  const removeItem = (index: number) => setItems(items.filter((_, i) => i !== index));
  const updateItem = (index: number, field: string, value: any) => {
    const newItems = [...items];
    (newItems[index] as any)[field] = value;
    setItems(newItems);
  };

  const totalPrice = items.reduce((sum, item) => sum + (item.quantity * item.unit_price), 0);

  const resetForm = () => {
    setOrderData({
      shop_id: '',
      external_id: '',
      title: '',
      currency: 'USD',
      email: '',
      full_name: '',
      shipping_name: '',
      shipping_phone: '',
      shipping_street_1: '',
      shipping_city: '',
      shipping_city_ref: '',
      shipping_warehouse_ref: '',
      shipping_state: '',
      shipping_zip: '',
      shipping_country: 'UA',
    });
    setItems([{ ...INITIAL_ITEM }]);
    setError(null);
    setFieldErrors({});
  };

  // Clear a single field's error as soon as the user edits that field.
  const clearFieldError = (field: OrderFieldError) => {
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const nextErrors: OrderFieldErrors = {};
    if (!orderData.shop_id) nextErrors.shop_id = 'Please select a shop.';
    if (!orderData.email) nextErrors.email = 'Customer email is required.';
    if (items.length === 0 || !items[0].title)
      nextErrors.items = 'At least one item is required.';

    // Always set a fresh object so the view's effect re-runs (scroll-to-error)
    // even when the same fields fail on a repeated submit.
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError(null);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await createOrder.mutateAsync({
        ...orderData,
        ordered_at: new Date().toISOString(),
        total_price: totalPrice,
        items: items.map(it => ({
          ...it,
          currency: orderData.currency
        }))
      });
      resetForm();
      onSuccess();
    } catch (err: any) {
      // TODO: SEC-07 — backend now returns generic detail; reconsider message extraction.
      setError(err.response?.data?.detail || 'Failed to create order');
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
    orderData,
    setOrderData,
    items,
    addItem,
    removeItem,
    updateItem,
    totalPrice,
    error,
    fieldErrors,
    clearFieldError,
    isSubmitting,
    handleSubmit,
    resetForm
  };
}
