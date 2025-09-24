
export enum OrderStatus {
  New = 'New',
  InProgress = 'In Progress',
  Manufactured = 'Manufactured',
  Shipped = 'Shipped',
}

export enum OrderSource {
  Shopify = 'Shopify',
  Etsy = 'Etsy',
  Manual = 'Manual',
}

export interface OrderItem {
  id: string;
  productId: string;
  title: string;
  quantity: number;
  price: number;
  cost?: number;
}

export interface Customer {
  name: string;
  email: string;
  address: string;
}

export interface Order {
  id: string;
  date: string;
  source: OrderSource;
  customer: Customer;
  items: OrderItem[];
  total: number;
  status: OrderStatus;
  fees: number;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  cost: number;
  price: number;
}

export interface Shop {
  id: string;
  name: OrderSource;
}
