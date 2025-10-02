
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { getProducts, addOrder } from '../services/mockApi';
import { Product, OrderItem, OrderSource, OrderStatus } from '../types';

const NewOrder: React.FC = () => {
    const navigate = useNavigate();
    const [products, setProducts] = useState<Product[]>([]);
    const [customerName, setCustomerName] = useState('');
    const [items, setItems] = useState<Partial<OrderItem & { key: number }>>([{ key: Date.now() }]);
    
    useEffect(() => {
        getProducts().then(setProducts);
    }, []);

    const handleItemChange = (index: number, field: keyof OrderItem, value: any) => {
        const newItems = [...items];
        const currentItem = { ...newItems[index] };
        
        if (field === 'productId') {
            const product = products.find(p => p.id === value);
            currentItem.productId = value;
            currentItem.title = product?.name;
            currentItem.price = product?.price;
            currentItem.cost = product?.cost;
        } else if (field === 'quantity') {
            currentItem.quantity = parseInt(value, 10) || 0;
        }

        newItems[index] = currentItem;
        setItems(newItems);
    };

    const addItem = () => {
        setItems([...items, { key: Date.now() }]);
    };
    
    const removeItem = (index: number) => {
        if(items.length > 1) {
            setItems(items.filter((_, i) => i !== index));
        }
    };

    const total = items.reduce((sum, item) => sum + (item.price || 0) * (item.quantity || 0), 0);
    const cost = items.reduce((sum, item) => sum + (item.cost || 0) * (item.quantity || 0), 0);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const finalItems: OrderItem[] = items.map((item, index) => ({
            id: `manual-item-${Date.now()}-${index}`,
            productId: item.productId!,
            title: item.title!,
            quantity: item.quantity!,
            price: item.price!,
            cost: item.cost,
        }));

        await addOrder({
            date: new Date().toISOString(),
            source: OrderSource.Manual,
            customer: { name: customerName, email: '', address: '' },
            items: finalItems,
            total,
            status: OrderStatus.New,
            fees: 0,
        });

        navigate('/orders');
    };

    return (
        <>
            <Header title="Create Manual Order" />
            <form onSubmit={handleSubmit} className="bg-card p-6 rounded-lg shadow-md space-y-6">
                <div>
                    <label className="block text-sm font-medium mb-1">Customer Name</label>
                    <input
                        type="text"
                        value={customerName}
                        onChange={(e) => setCustomerName(e.target.value)}
                        required
                        className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md"
                    />
                </div>

                <h3 className="text-lg font-semibold border-b border-border pb-2">Order Items</h3>
                {items.map((item, index) => (
                    <div key={item.key} className="flex items-end gap-4 p-4 border border-border rounded-md">
                        <div className="flex-1">
                            <label className="block text-sm font-medium mb-1">Product</label>
                            <select
                                value={item.productId || ''}
                                onChange={(e) => handleItemChange(index, 'productId', e.target.value)}
                                required
                                className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md"
                            >
                                <option value="" disabled>Select a product</option>
                                {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium mb-1">Quantity</label>
                            <input
                                type="number"
                                value={item.quantity || ''}
                                onChange={(e) => handleItemChange(index, 'quantity', e.target.value)}
                                required
                                min="1"
                                className="w-24 px-3 py-2 bg-gray-700 border border-border rounded-md"
                            />
                        </div>
                        <div className="text-sm">Price: ${item.price?.toFixed(2) || '0.00'}</div>
                        <button type="button" onClick={() => removeItem(index)} disabled={items.length <= 1} className="px-3 py-2 bg-red-600 text-white rounded-md hover:bg-red-500 disabled:bg-gray-500">-</button>
                    </div>
                ))}
                
                <button type="button" onClick={addItem} className="px-4 py-2 bg-secondary text-white rounded-md hover:bg-emerald-500">+ Add Item</button>

                <div className="text-right space-y-2 text-lg pt-4 border-t border-border">
                    <p>Total Cost: <span className="font-semibold">${cost.toFixed(2)}</span></p>
                    <p>Order Total: <span className="font-bold">${total.toFixed(2)}</span></p>
                </div>

                <div className="flex justify-end">
                    <button type="submit" className="px-6 py-2 bg-primary text-white rounded-md hover:bg-indigo-500">Create Order</button>
                </div>
            </form>
        </>
    );
};

export default NewOrder;
