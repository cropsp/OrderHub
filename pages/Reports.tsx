
import React, { useState, useEffect, useMemo } from 'react';
import Header from '../components/Header';
import Card from '../components/Card';
import { getOrders, getShops } from '../services/mockApi';
import { Order, OrderSource, Shop } from '../types';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
// FIX: ProductsIcon was incorrectly imported from ReportsIcon.tsx. It is now imported from its own file.
import { ReportsIcon } from '../components/icons/ReportsIcon';
import { ProductsIcon } from '../components/icons/ProductsIcon';

const Reports: React.FC = () => {
    const [orders, setOrders] = useState<Order[]>([]);
    const [shops, setShops] = useState<Shop[]>([]);
    const [loading, setLoading] = useState(true);
    const [filters, setFilters] = useState({
        shop: 'All',
        startDate: '',
        endDate: '',
    });

    useEffect(() => {
        Promise.all([getOrders(), getShops()]).then(([orderData, shopData]) => {
            setOrders(orderData);
            setShops(shopData);
            setLoading(false);
        });
    }, []);

    const handleFilterChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        setFilters({ ...filters, [e.target.name]: e.target.value });
    };
    
    const filteredData = useMemo(() => {
        const filteredOrders = orders.filter(order => {
            const matchesShop = filters.shop === 'All' || order.source === filters.shop;
            
            const orderDate = new Date(order.date);
            const startDate = filters.startDate ? new Date(filters.startDate) : null;
            const endDate = filters.endDate ? new Date(filters.endDate) : null;
            
            if(startDate) startDate.setHours(0,0,0,0);
            if(endDate) endDate.setHours(23,59,59,999);
    
            const matchesDate = 
              (!startDate || orderDate >= startDate) && 
              (!endDate || orderDate <= endDate);
    
            return matchesShop && matchesDate;
        });
        
        const totals = filteredOrders.reduce((acc, order) => {
            const cost = order.items.reduce((sum, item) => sum + (item.cost || 0) * item.quantity, 0);
            acc.revenue += order.total;
            acc.cost += cost;
            acc.fees += order.fees;
            acc.profit += order.total - cost - order.fees;
            return acc;
        }, { revenue: 0, cost: 0, fees: 0, profit: 0 });

        const chartData = filteredOrders
            .sort((a,b) => new Date(a.date).getTime() - new Date(b.date).getTime())
            .reduce<Record<string, { date: string; revenue: number; profit: number }>>((acc, order) => {
                const date = new Date(order.date).toLocaleDateString('en-CA'); // YYYY-MM-DD
                if (!acc[date]) {
                    acc[date] = { date, revenue: 0, profit: 0 };
                }
                const cost = order.items.reduce((sum, item) => sum + (item.cost || 0) * item.quantity, 0);
                acc[date].revenue += order.total;
                acc[date].profit += order.total - cost - order.fees;
                return acc;
            }, {});

        return { totals, chartData: Object.values(chartData) };
    }, [orders, filters]);

    if (loading) return <div>Loading reports...</div>;

    return (
        <>
            <Header title="Reports" />
            <div className="mb-6 p-4 bg-card rounded-lg shadow-md">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <select name="shop" value={filters.shop} onChange={handleFilterChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md">
                        <option value="All">All Shops</option>
                        {shops.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
                         <option value={OrderSource.Manual}>{OrderSource.Manual}</option>
                    </select>
                    <input type="date" name="startDate" value={filters.startDate} onChange={handleFilterChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md" />
                    <input type="date" name="endDate" value={filters.endDate} onChange={handleFilterChange} className="w-full px-3 py-2 text-text-primary bg-gray-700 border border-border rounded-md" />
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
                <Card title="Total Revenue" value={`$${filteredData.totals.revenue.toFixed(2)}`} icon={<ReportsIcon/>} />
                <Card title="Total Cost" value={`$${filteredData.totals.cost.toFixed(2)}`} icon={<ReportsIcon/>} />
                <Card title="Total Fees" value={`$${filteredData.totals.fees.toFixed(2)}`} icon={<ReportsIcon/>} />
                <Card title="Total Profit" value={`$${filteredData.totals.profit.toFixed(2)}`} icon={<ProductsIcon/>} />
            </div>

            <div className="bg-card p-6 rounded-lg shadow-md h-96">
                <h3 className="text-xl font-semibold mb-4">Revenue & Profit Over Time</h3>
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={filteredData.chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#4b5563" />
                        <XAxis dataKey="date" stroke="#d1d5db" />
                        <YAxis stroke="#d1d5db" />
                        <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #4b5563' }}/>
                        <Legend wrapperStyle={{ color: '#d1d5db' }}/>
                        <Line type="monotone" dataKey="revenue" stroke="#4f46e5" activeDot={{ r: 8 }} />
                        <Line type="monotone" dataKey="profit" stroke="#10b981" />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </>
    );
};

export default Reports;