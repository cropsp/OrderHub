import { Request } from 'express';

export interface AuthRequest extends Request {
  userId?: string;
}

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

export interface CreateProductDto {
  sku: string;
  name: string;
  cost: number;
  price: number;
}

export interface UpdateProductDto {
  sku?: string;
  name?: string;
  cost?: number;
  price?: number;
}

export interface CreateOrderDto {
  source: OrderSource;
  customerName: string;
  customerEmail: string;
  customerAddress: string;
  items: OrderItemDto[];
  fees?: number;
}

export interface OrderItemDto {
  productId: string;
  title: string;
  quantity: number;
  price: number;
  cost?: number;
}

export interface UpdateOrderStatusDto {
  status: OrderStatus;
}

export interface UpdateOrderItemCostDto {
  itemId: string;
  cost: number;
}

export interface LoginDto {
  email: string;
  password: string;
}

export interface RegisterDto {
  email: string;
  password: string;
  name: string;
}

export interface IntegrationDto {
  platform: string;
  apiKey: string;
  apiSecret: string;
}
