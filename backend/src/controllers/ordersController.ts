import { Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { z } from 'zod';
import { OrderStatus, OrderSource } from '../types';

const prisma = new PrismaClient();

// Validation schemas
const orderItemSchema = z.object({
  productId: z.string(),
  title: z.string(),
  quantity: z.number().int().positive(),
  price: z.number().min(0),
  cost: z.number().min(0).optional()
});

const createOrderSchema = z.object({
  source: z.enum([OrderSource.Shopify, OrderSource.Etsy, OrderSource.Manual]),
  customerName: z.string().min(1),
  customerEmail: z.string().email(),
  customerAddress: z.string(),
  items: z.array(orderItemSchema).min(1),
  fees: z.number().min(0).default(0)
});

const updateOrderStatusSchema = z.object({
  status: z.enum([OrderStatus.New, OrderStatus.InProgress, OrderStatus.Manufactured, OrderStatus.Shipped])
});

// Отримати всі замовлення з фільтрами
export const getAllOrders = async (req: Request, res: Response) => {
  try {
    const { source, status, startDate, endDate, search } = req.query;

    const where: any = {};

    if (source && source !== 'All') {
      where.source = source;
    }

    if (status && status !== 'All') {
      where.status = status;
    }

    if (startDate || endDate) {
      where.date = {};
      if (startDate) {
        where.date.gte = new Date(startDate as string);
      }
      if (endDate) {
        const end = new Date(endDate as string);
        end.setHours(23, 59, 59, 999);
        where.date.lte = end;
      }
    }

    if (search) {
      where.OR = [
        { orderNumber: { contains: search as string } },
        { customerName: { contains: search as string } },
        { customerEmail: { contains: search as string } }
      ];
    }

    const orders = await prisma.order.findMany({
      where,
      include: {
        items: {
          include: {
            product: true
          }
        }
      },
      orderBy: { date: 'desc' }
    });

    res.json({ orders });
  } catch (error) {
    throw error;
  }
};

// Отримати замовлення за ID
export const getOrderById = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;

    const order = await prisma.order.findUnique({
      where: { id },
      include: {
        items: {
          include: {
            product: true
          }
        }
      }
    });

    if (!order) {
      return res.status(404).json({ error: 'Order not found' });
    }

    res.json({ order });
  } catch (error) {
    throw error;
  }
};

// Створити замовлення
export const createOrder = async (req: Request, res: Response) => {
  try {
    const data = createOrderSchema.parse(req.body);

    // Розрахунок загальної суми
    const total = data.items.reduce((sum, item) => sum + item.price * item.quantity, 0);

    // Генерація номера замовлення
    const orderCount = await prisma.order.count();
    const orderNumber = `ORD-${String(orderCount + 1).padStart(3, '0')}`;

    const order = await prisma.order.create({
      data: {
        orderNumber,
        source: data.source,
        customerName: data.customerName,
        customerEmail: data.customerEmail,
        customerAddress: data.customerAddress,
        total,
        fees: data.fees,
        status: OrderStatus.New,
        items: {
          create: data.items.map(item => ({
            productId: item.productId,
            title: item.title,
            quantity: item.quantity,
            price: item.price,
            cost: item.cost
          }))
        }
      },
      include: {
        items: true
      }
    });

    res.status(201).json({
      message: 'Order created successfully',
      order
    });
  } catch (error) {
    throw error;
  }
};

// Оновити статус замовлення
export const updateOrderStatus = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const { status } = updateOrderStatusSchema.parse(req.body);

    const order = await prisma.order.update({
      where: { id },
      data: { status },
      include: {
        items: true
      }
    });

    res.json({
      message: 'Order status updated successfully',
      order
    });
  } catch (error) {
    throw error;
  }
};

// Оновити вартість товару в замовленні
export const updateOrderItemCost = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const { itemId, cost } = req.body;

    if (typeof cost !== 'number' || cost < 0) {
      return res.status(400).json({ error: 'Invalid cost value' });
    }

    await prisma.orderItem.update({
      where: { id: itemId },
      data: { cost }
    });

    const order = await prisma.order.findUnique({
      where: { id },
      include: {
        items: true
      }
    });

    res.json({
      message: 'Item cost updated successfully',
      order
    });
  } catch (error) {
    throw error;
  }
};

// Видалити замовлення
export const deleteOrder = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;

    await prisma.order.delete({
      where: { id }
    });

    res.json({ message: 'Order deleted successfully' });
  } catch (error) {
    throw error;
  }
};