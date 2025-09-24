
import { Order, Product, OrderStatus, OrderSource, Shop } from '../types';

let mockProducts: Product[] = [
  { id: 'prod-001', sku: 'TS-BLK-L', name: 'Black T-Shirt (L)', cost: 5.50, price: 19.99 },
  { id: 'prod-002', sku: 'MUG-WHT-11', name: 'White Coffee Mug (11oz)', cost: 3.25, price: 12.99 },
  { id: 'prod-003', sku: 'PST-ART-1824', name: 'Art Poster (18x24)', cost: 8.00, price: 25.00 },
  { id: 'prod-004', sku: 'HOOD-GRY-M', name: 'Gray Hoodie (M)', cost: 12.75, price: 39.99 },
  { id: 'prod-005', sku: 'CAP-NVY-OS', name: 'Navy Blue Cap', cost: 4.00, price: 15.99 },
];

let mockOrders: Order[] = [
  {
    id: 'ORD-001',
    date: '2023-10-26T10:00:00Z',
    source: OrderSource.Shopify,
    customer: { name: 'John Doe', email: 'john.doe@example.com', address: '123 Main St, Anytown, USA' },
    items: [
      { id: 'item-1', productId: 'prod-001', title: 'Black T-Shirt (L)', quantity: 1, price: 19.99, cost: 5.50 },
      { id: 'item-2', productId: 'prod-002', title: 'White Coffee Mug (11oz)', quantity: 2, price: 12.99, cost: 3.25 },
    ],
    total: 45.97,
    status: OrderStatus.New,
    fees: 2.30,
  },
  {
    id: 'ORD-002',
    date: '2023-10-25T14:30:00Z',
    source: OrderSource.Etsy,
    customer: { name: 'Jane Smith', email: 'jane.smith@example.com', address: '456 Oak Ave, Somewhere, USA' },
    items: [
      { id: 'item-3', productId: 'prod-003', title: 'Art Poster (18x24)', quantity: 1, price: 25.00, cost: 8.00 },
    ],
    total: 25.00,
    status: OrderStatus.InProgress,
    fees: 1.75,
  },
  {
    id: 'ORD-003',
    date: '2023-10-25T11:00:00Z',
    source: OrderSource.Manual,
    customer: { name: 'Local Market', email: 'market@example.com', address: 'N/A' },
    items: [
      { id: 'item-4', productId: 'prod-004', title: 'Gray Hoodie (M)', quantity: 5, price: 39.99, cost: 12.75 },
    ],
    total: 199.95,
    status: OrderStatus.Shipped,
    fees: 0,
  },
  {
    id: 'ORD-004',
    date: '2023-10-24T09:00:00Z',
    source: OrderSource.Shopify,
    customer: { name: 'Peter Jones', email: 'peter.jones@example.com', address: '789 Pine Rd, Othertown, USA' },
    items: [
      { id: 'item-5', productId: 'prod-005', title: 'Navy Blue Cap', quantity: 2, price: 15.99, cost: 4.00 },
    ],
    total: 31.98,
    status: OrderStatus.Manufactured,
    fees: 1.60,
  },
  {
    id: 'ORD-005',
    date: '2023-10-23T18:00:00Z',
    source: OrderSource.Etsy,
    customer: { name: 'Mary Garcia', email: 'mary.garcia@example.com', address: '321 Elm St, Anotherville, USA' },
    items: [
      { id: 'item-6', productId: 'prod-001', title: 'Black T-Shirt (L)', quantity: 1, price: 19.99, cost: 5.50 },
      { id: 'item-7', productId: 'prod-004', title: 'Gray Hoodie (M)', quantity: 1, price: 39.99, cost: 12.75 },
    ],
    total: 59.98,
    status: OrderStatus.Shipped,
    fees: 4.20,
  },
  {
    id: 'ORD-006',
    date: '2023-10-22T12:00:00Z',
    source: OrderSource.Shopify,
    customer: { name: 'Chris Lee', email: 'chris.lee@example.com', address: '159 Maple Ave, Yourtown, USA' },
    items: [
      { id: 'item-8', productId: 'prod-002', title: 'White Coffee Mug (11oz)', quantity: 4, price: 12.99, cost: 3.25 },
    ],
    total: 51.96,
    status: OrderStatus.Shipped,
    fees: 2.60,
  },
  {
    id: 'ORD-007',
    date: '2023-10-21T15:45:00Z',
    source: OrderSource.Manual,
    customer: { name: 'Pop-up Event', email: 'events@example.com', address: 'N/A' },
    items: [
      { id: 'item-9', productId: 'prod-005', title: 'Navy Blue Cap', quantity: 10, price: 15.99, cost: 4.00 },
      { id: 'item-10', productId: 'prod-001', title: 'Black T-Shirt (L)', quantity: 10, price: 19.99, cost: 5.50 },
    ],
    total: 359.80,
    status: OrderStatus.Shipped,
    fees: 0,
  },
  {
    id: 'ORD-008',
    date: '2023-10-20T10:20:00Z',
    source: OrderSource.Etsy,
    customer: { name: 'Patricia Williams', email: 'pat.w@example.com', address: '753 Birch Ln, Thistown, USA' },
    items: [
      { id: 'item-11', productId: 'prod-003', title: 'Art Poster (18x24)', quantity: 2, price: 25.00, cost: 8.00 },
    ],
    total: 50.00,
    status: OrderStatus.InProgress,
    fees: 3.50,
  },
  {
    id: 'ORD-009',
    date: '2023-10-19T20:00:00Z',
    source: OrderSource.Shopify,
    customer: { name: 'Robert Brown', email: 'rob.brown@example.com', address: '951 Cedar Blvd, Thatplace, USA' },
    items: [
      { id: 'item-12', productId: 'prod-004', title: 'Gray Hoodie (M)', quantity: 1, price: 39.99, cost: 12.75 },
    ],
    total: 39.99,
    status: OrderStatus.New,
    fees: 2.00,
  },
  {
    id: 'ORD-010',
    date: '2023-10-18T13:10:00Z',
    source: OrderSource.Etsy,
    customer: { name: 'Linda Miller', email: 'linda.m@example.com', address: '852 Spruce Dr, Anotherplace, USA' },
    items: [
      { id: 'item-13', productId: 'prod-001', title: 'Black T-Shirt (L)', quantity: 3, price: 19.99, cost: 5.50 },
    ],
    total: 59.97,
    status: OrderStatus.Manufactured,
    fees: 4.19,
  },
];

const shops: Shop[] = [
    { id: 'shop-1', name: OrderSource.Shopify },
    { id: 'shop-2', name: OrderSource.Etsy }
];

const delay = <T,>(data: T, ms = 500): Promise<T> => new Promise(resolve => setTimeout(() => resolve(data), ms));

export const getOrders = () => delay([...mockOrders]);
export const getOrderById = (id: string) => delay(mockOrders.find(o => o.id === id));
export const getProducts = () => delay([...mockProducts]);
export const getShops = () => delay([...shops]);

export const updateOrderStatus = (id: string, status: OrderStatus) => {
  mockOrders = mockOrders.map(o => o.id === id ? { ...o, status } : o);
  return delay(mockOrders.find(o => o.id === id));
};

export const updateOrderItemCost = (orderId: string, itemId: string, cost: number) => {
  mockOrders = mockOrders.map(o => {
    if (o.id === orderId) {
      return {
        ...o,
        items: o.items.map(item => item.id === itemId ? { ...item, cost } : item),
      };
    }
    return o;
  });
  return delay(mockOrders.find(o => o.id === orderId));
};

export const saveProduct = (product: Product) => {
  const index = mockProducts.findIndex(p => p.id === product.id);
  if (index > -1) {
    mockProducts[index] = product;
  } else {
    mockProducts.push(product);
  }
  return delay(product);
};

export const addOrder = (order: Omit<Order, 'id'>) => {
    const newOrder: Order = {
        ...order,
        id: `ORD-${String(mockOrders.length + 1).padStart(3, '0')}`,
    };
    mockOrders.unshift(newOrder);
    return delay(newOrder);
}
