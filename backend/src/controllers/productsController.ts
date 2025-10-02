import { Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { z } from 'zod';

const prisma = new PrismaClient();

// Validation schemas
const createProductSchema = z.object({
  sku: z.string().min(1),
  name: z.string().min(1),
  cost: z.number().min(0),
  price: z.number().min(0)
});

const updateProductSchema = z.object({
  sku: z.string().min(1).optional(),
  name: z.string().min(1).optional(),
  cost: z.number().min(0).optional(),
  price: z.number().min(0).optional()
});

// Отримати всі продукти
export const getAllProducts = async (req: Request, res: Response) => {
  try {
    const products = await prisma.product.findMany({
      orderBy: { createdAt: 'desc' }
    });

    res.json({ products });
  } catch (error) {
    throw error;
  }
};

// Отримати продукт за ID
export const getProductById = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;

    const product = await prisma.product.findUnique({
      where: { id }
    });

    if (!product) {
      return res.status(404).json({ error: 'Product not found' });
    }

    res.json({ product });
  } catch (error) {
    throw error;
  }
};

// Створити продукт
export const createProduct = async (req: Request, res: Response) => {
  try {
    const data = createProductSchema.parse(req.body);

    const product = await prisma.product.create({
      data
    });

    res.status(201).json({
      message: 'Product created successfully',
      product
    });
  } catch (error) {
    throw error;
  }
};

// Оновити продукт
export const updateProduct = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const data = updateProductSchema.parse(req.body);

    const product = await prisma.product.update({
      where: { id },
      data
    });

    res.json({
      message: 'Product updated successfully',
      product
    });
  } catch (error) {
    throw error;
  }
};

// Видалити продукт
export const deleteProduct = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;

    await prisma.product.delete({
      where: { id }
    });

    res.json({ message: 'Product deleted successfully' });
  } catch (error) {
    throw error;
  }
};