
import React, { useEffect, useState, useMemo } from 'react';
import Header from '../components/Header';
import Card from '../components/Card';
import { getOrders } from '../services/mockApi';
import { Order, OrderStatus } from '../types';
import { OrdersIcon } from '../components/icons/OrdersIcon';
import { ReportsIcon } from '../components/icons/ReportsIcon';
import { ProductsIcon } from '../components/icons/ProductsIcon';

const Dashboard: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getOrders().then(data => {
      setOrders(data);
      setLoading(false);
    });
  }, []);

  const stats = useMemo(() => {
    const newOrders = orders.filter(o => o.status === OrderStatus.New).length;
    const totalRevenue = orders.reduce((sum, o) => sum + o.total, 0);
    const totalCost = orders.reduce((sum, o) => {
        const orderCost = o.items.reduce((itemSum, item) => itemSum + (item.cost || 0) * item.quantity, 0);
        return sum + orderCost;
    }, 0);
    const totalFees = orders.reduce((sum, o) => sum + o.fees, 0);
    const profit = totalRevenue - totalCost - totalFees;
    return { newOrders, totalRevenue, profit };
  }, [orders]);
  
  if (loading) return <div>Loading dashboard...</div>;

  return (
    <>
      <Header title="Dashboard" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Card title="New Orders" value={stats.newOrders.toString()} icon={<OrdersIcon />} />
        <Card title="Total Revenue" value={`$${stats.totalRevenue.toFixed(2)}`} icon={<ReportsIcon />} />
        <Card title="Profit" value={`$${stats.profit.toFixed(2)}`} icon={<ProductsIcon />} />
      </div>

      <div className="mt-8 bg-card p-6 rounded-lg shadow-md">
        <h2 className="text-xl font-semibold text-text-primary mb-4">Recent Orders</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left text-gray-400">
            <thead className="text-xs text-gray-400 uppercase bg-gray-700">
              <tr>
                <th scope="col" className="px-6 py-3">Order ID</th>
                <th scope="col" className="px-6 py-3">Customer</th>
                <th scope="col" className="px-6 py-3">Total</th>
                <th scope="col" className="px-6 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.slice(0, 5).map(order => (
                <tr key={order.id} className="border-b bg-gray-800 border-gray-700 hover:bg-gray-600">
                  <td className="px-6 py-4 font-medium text-white whitespace-nowrap">{order.id}</td>
                  <td className="px-6 py-4">{order.customer.name}</td>
                  <td className="px-6 py-4">${order.total.toFixed(2)}</td>
                  <td className="px-6 py-4">{order.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
};

export default Dashboard;
