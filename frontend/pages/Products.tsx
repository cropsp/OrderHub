
import React, { useState, useEffect } from 'react';
import Header from '../components/Header';
import { getProducts, saveProduct } from '../services/mockApi';
import { Product } from '../types';
import { PlusIcon } from '../components/icons/PlusIcon';

const ProductModal: React.FC<{ product: Product | null; onClose: () => void; onSave: (product: Product) => void; }> = ({ product, onClose, onSave }) => {
  const [formData, setFormData] = useState<Product>(product || { id: '', sku: '', name: '', cost: 0, price: 0 });

  useEffect(() => {
    setFormData(product || { id: `prod-${Date.now()}`, sku: '', name: '', cost: 0, price: 0 });
  }, [product]);
  
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: name === 'cost' || name === 'price' ? parseFloat(value) : value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(formData);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center z-50">
      <div className="bg-card p-6 rounded-lg shadow-xl w-full max-w-md">
        <h2 className="text-2xl font-bold mb-4">{product ? 'Edit Product' : 'Add Product'}</h2>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <input type="text" name="name" value={formData.name} onChange={handleChange} placeholder="Product Name" required className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md"/>
            <input type="text" name="sku" value={formData.sku} onChange={handleChange} placeholder="SKU" required className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md"/>
            <div className="flex gap-4">
                <input type="number" name="cost" value={formData.cost} onChange={handleChange} placeholder="Cost" step="0.01" required className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md"/>
                <input type="number" name="price" value={formData.price} onChange={handleChange} placeholder="Price" step="0.01" required className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md"/>
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-4">
            <button type="button" onClick={onClose} className="px-4 py-2 bg-gray-600 rounded-md hover:bg-gray-500">Cancel</button>
            <button type="submit" className="px-4 py-2 bg-primary rounded-md hover:bg-indigo-500">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
};

const Products: React.FC = () => {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

  const fetchProducts = () => {
    getProducts().then(data => {
      setProducts(data);
      setLoading(false);
    });
  };

  useEffect(() => {
    fetchProducts();
  }, []);

  const handleOpenModal = (product: Product | null) => {
    setSelectedProduct(product);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setSelectedProduct(null);
    setIsModalOpen(false);
  };

  const handleSaveProduct = async (product: Product) => {
    await saveProduct(product);
    fetchProducts();
    handleCloseModal();
  };

  if (loading) return <div>Loading products...</div>;

  return (
    <>
      <div className="flex justify-between items-center">
        <Header title="Products" />
        <button onClick={() => handleOpenModal(null)} className="flex items-center px-4 py-2 bg-primary text-white rounded-md hover:bg-indigo-500">
            <PlusIcon />
            <span className="ml-2">Add Product</span>
        </button>
      </div>
      
      <div className="overflow-x-auto bg-card rounded-lg shadow-md">
        <table className="w-full text-sm text-left text-gray-400">
          <thead className="text-xs text-gray-400 uppercase bg-gray-700">
            <tr>
              <th scope="col" className="px-6 py-3">SKU</th>
              <th scope="col" className="px-6 py-3">Name</th>
              <th scope="col" className="px-6 py-3">Cost</th>
              <th scope="col" className="px-6 py-3">Price</th>
              <th scope="col" className="px-6 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {products.map(product => (
              <tr key={product.id} className="border-b bg-gray-800 border-gray-700 hover:bg-gray-600">
                <td className="px-6 py-4 font-medium text-white whitespace-nowrap">{product.sku}</td>
                <td className="px-6 py-4">{product.name}</td>
                <td className="px-6 py-4">${product.cost.toFixed(2)}</td>
                <td className="px-6 py-4">${product.price.toFixed(2)}</td>
                <td className="px-6 py-4">
                  <button onClick={() => handleOpenModal(product)} className="font-medium text-primary hover:underline">Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {isModalOpen && <ProductModal product={selectedProduct} onClose={handleCloseModal} onSave={handleSaveProduct} />}
    </>
  );
};

export default Products;
