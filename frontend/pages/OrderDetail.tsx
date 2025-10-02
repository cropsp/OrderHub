
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import Badge from '../components/Badge';
import { getOrderById, updateOrderStatus, updateOrderItemCost } from '../services/mockApi';
import { Order, OrderStatus, OrderItem } from '../types';

const OrderDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchOrder = useCallback(() => {
    if (id) {
      getOrderById(id).then(data => {
        if (data) {
          setOrder(data);
        } else {
          // Handle order not found
          navigate('/404');
        }
        setLoading(false);
      });
    }
  }, [id, navigate]);
  
  useEffect(() => {
    fetchOrder();
  }, [fetchOrder]);
  
  const handleStatusChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (order) {
      const newStatus = e.target.value as OrderStatus;
      const updatedOrder = await updateOrderStatus(order.id, newStatus);
      if(updatedOrder) setOrder(updatedOrder);
    }
  };
  
  const handleCostChange = (itemId: string, newCost: string) => {
    if (order) {
        const costValue = parseFloat(newCost);
        if(!isNaN(costValue)){
            const updatedItems = order.items.map(item =>
                item.id === itemId ? { ...item, cost: costValue } : item
            );
            setOrder({...order, items: updatedItems});
        }
    }
  };

  const handleCostBlur = async (item: OrderItem) => {
    if (order && item.cost !== undefined) {
        await updateOrderItemCost(order.id, item.id, item.cost);
    }
  }

  if (loading) return <div>Loading order details...</div>;
  if (!order) return <div>Order not found.</div>;

  const orderCost = order.items.reduce((sum, item) => sum + (item.cost || 0) * item.quantity, 0);
  const profit = order.total - orderCost - order.fees;

  return (
    <>
      <Header title={`Order Details: ${order.id}`} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
            <div className="bg-card p-6 rounded-lg shadow-md mb-6">
                <h2 className="text-xl font-semibold mb-4">Order Items</h2>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left text-gray-400">
                        <thead className="text-xs uppercase bg-gray-700">
                            <tr>
                                <th className="px-4 py-2">Product</th>
                                <th className="px-4 py-2">Quantity</th>
                                <th className="px-4 py-2">Price</th>
                                <th className="px-4 py-2">Cost</th>
                                <th className="px-4 py-2">Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            {order.items.map(item => (
                                <tr key={item.id} className="border-b bg-gray-800 border-gray-700">
                                    <td className="px-4 py-2">{item.title}</td>
                                    <td className="px-4 py-2">{item.quantity}</td>
                                    <td className="px-4 py-2">${item.price.toFixed(2)}</td>
                                    <td className="px-4 py-2">
                                        <input 
                                            type="number"
                                            value={item.cost === undefined ? '' : item.cost}
                                            onChange={(e) => handleCostChange(item.id, e.target.value)}
                                            onBlur={() => handleCostBlur(item)}
                                            className="w-20 bg-gray-700 border border-border rounded px-2 py-1"
                                            placeholder="N/A"
                                        />
                                    </td>
                                    <td className="px-4 py-2">${(item.quantity * item.price).toFixed(2)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <div className="md:col-span-1 space-y-6">
            <div className="bg-card p-6 rounded-lg shadow-md">
                <h2 className="text-xl font-semibold mb-4">Order Summary</h2>
                <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span>Subtotal:</span> <span>${order.total.toFixed(2)}</span></div>
                    <div className="flex justify-between"><span>Fees:</span> <span className="text-red-400">-${order.fees.toFixed(2)}</span></div>
                    <div className="flex justify-between"><span>Total Cost:</span> <span className="text-red-400">-${orderCost.toFixed(2)}</span></div>
                    <hr className="border-border my-2"/>
                    <div className="flex justify-between font-bold text-base"><span>Profit:</span> <span>${profit.toFixed(2)}</span></div>
                </div>

                <div className="mt-4">
                    <label className="block text-sm font-medium mb-2">Status</label>
                    <select value={order.status} onChange={handleStatusChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md focus:outline-none focus:ring-primary">
                        {Object.values(OrderStatus).map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>
                <div className="mt-4"><Badge type={order.source}/></div>

            </div>

            <div className="bg-card p-6 rounded-lg shadow-md">
                <h2 className="text-xl font-semibold mb-4">Customer Info</h2>
                <p className="font-bold">{order.customer.name}</p>
                <p>{order.customer.email}</p>
                <p>{order.customer.address}</p>
            </div>
        </div>
      </div>
    </>
  );
};

export default OrderDetail;
