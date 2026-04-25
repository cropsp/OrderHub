import { useState } from 'react';
import { useCreateOrder } from '@/hooks/useOrders';

const INITIAL_ITEM = { title: '', quantity: 1, unit_price: 0 };

export function useOrderForm(onSuccess: () => void) {
  const createOrder = useCreateOrder();
  const [error, setError] = useState<string | null>(null);
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
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orderData.shop_id) return setError('Please select a shop.');
    if (!orderData.email) return setError('Customer email is required.');
    if (items.length === 0 || !items[0].title) return setError('At least one item is required.');

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
    isSubmitting,
    handleSubmit,
    resetForm
  };
}
