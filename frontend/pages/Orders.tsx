
import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import Header from '../components/Header';
import Badge from '../components/Badge';
import { getOrders } from '../services/mockApi';
import { Order, OrderSource, OrderStatus } from '../types';

const Orders: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    search: '',
    source: 'All',
    status: 'All',
    startDate: '',
    endDate: '',
  });

  useEffect(() => {
    getOrders().then(data => {
      setOrders(data);
      setLoading(false);
    });
  }, []);

  const handleFilterChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFilters({ ...filters, [e.target.name]: e.target.value });
  };

  const filteredOrders = useMemo(() => {
    return orders.filter(order => {
      const searchLower = filters.search.toLowerCase();
      const matchesSearch =
        order.id.toLowerCase().includes(searchLower) ||
        order.customer.name.toLowerCase().includes(searchLower) ||
        order.customer.email.toLowerCase().includes(searchLower);

      const matchesSource = filters.source === 'All' || order.source === filters.source;
      const matchesStatus = filters.status === 'All' || order.status === filters.status;
      
      const orderDate = new Date(order.date);
      const startDate = filters.startDate ? new Date(filters.startDate) : null;
      const endDate = filters.endDate ? new Date(filters.endDate) : null;

      if(startDate) startDate.setHours(0,0,0,0);
      if(endDate) endDate.setHours(23,59,59,999);

      const matchesDate = 
        (!startDate || orderDate >= startDate) && 
        (!endDate || orderDate <= endDate);

      return matchesSearch && matchesSource && matchesStatus && matchesDate;
    });
  }, [orders, filters]);

  if (loading) return <div>Loading orders...</div>;

  return (
    <>
      <Header title="Orders" />

      <div className="mb-6 p-4 bg-card rounded-lg shadow-md">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <input
            type="text"
            name="search"
            placeholder="Search by ID, name, email..."
            value={filters.search}
            onChange={handleFilterChange}
            className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md focus:outline-none focus:ring-primary"
          />
          <select name="source" value={filters.source} onChange={handleFilterChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md focus:outline-none focus:ring-primary">
            <option value="All">All Sources</option>
            {Object.values(OrderSource).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select name="status" value={filters.status} onChange={handleFilterChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md focus:outline-none focus:ring-primary">
            <option value="All">All Statuses</option>
            {Object.values(OrderStatus).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <input type="date" name="startDate" value={filters.startDate} onChange={handleFilterChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md focus:outline-none focus:ring-primary" />
          <input type="date" name="endDate" value={filters.endDate} onChange={handleFilterChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md focus:outline-none focus:ring-primary" />
        </div>
      </div>
      
      <div className="overflow-x-auto bg-card rounded-lg shadow-md">
        <table className="w-full text-sm text-left text-gray-400">
          <thead className="text-xs text-gray-400 uppercase bg-gray-700">
            <tr>
              <th scope="col" className="px-6 py-3">Order ID</th>
              <th scope="col" className="px-6 py-3">Date</th>
              <th scope="col" className="px-6 py-3">Source</th>
              <th scope="col" className="px-6 py-3">Customer</th>
              <th scope="col" className="px-6 py-3">Total</th>
              <th scope="col" className="px-6 py-3">Status</th>
              <th scope="col" className="px-6 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredOrders.map(order => (
              <tr key={order.id} className="border-b bg-gray-800 border-gray-700 hover:bg-gray-600">
                <td className="px-6 py-4 font-medium text-white whitespace-nowrap">{order.id}</td>
                <td className="px-6 py-4">{new Date(order.date).toLocaleDateString()}</td>
                <td className="px-6 py-4"><Badge type={order.source} /></td>
                <td className="px-6 py-4">{order.customer.name}</td>
                <td className="px-6 py-4">${order.total.toFixed(2)}</td>
                <td className="px-6 py-4"><Badge type={order.status} /></td>
                <td className="px-6 py-4">
                  <Link to={`/orders/${order.id}`} className="font-medium text-primary hover:underline">View</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
};

export default Orders;
