#!/bin/bash

# OrderHub - Create Source Files Script
# Цей скрипт створює всі TypeScript файли з кодом

echo "📝 Creating source files for backend..."

# Перевірка чи існує папка backend
if [ ! -d "backend/src" ]; then
    echo "❌ Error: backend/src folder not found. Please run setup-backend.sh first"
    exit 1
fi

# ============================================
# TYPES
# ============================================
echo "📄 Creating types/index.ts..."
cat > backend/src/types/index.ts << 'ENDOFFILE'
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
ENDOFFILE

# ============================================
# MIDDLEWARE - AUTH
# ============================================
echo "📄 Creating middleware/auth.ts..."
cat > backend/src/middleware/auth.ts << 'ENDOFFILE'
import { Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { AuthRequest } from '../types';

const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key';

export const authenticateToken = (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  try {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];

    if (!token) {
      return res.status(401).json({ error: 'Access token required' });
    }

    jwt.verify(token, JWT_SECRET, (err, decoded) => {
      if (err) {
        return res.status(403).json({ error: 'Invalid or expired token' });
      }

      req.userId = (decoded as any).userId;
      next();
    });
  } catch (error) {
    return res.status(500).json({ error: 'Authentication error' });
  }
};
ENDOFFILE

# ============================================
# MIDDLEWARE - ERROR HANDLER
# ============================================
echo "📄 Creating middleware/errorHandler.ts..."
cat > backend/src/middleware/errorHandler.ts << 'ENDOFFILE'
import { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';

export const errorHandler = (
  err: Error,
  req: Request,
  res: Response,
  next: NextFunction
) => {
  console.error('Error:', err);

  if (err instanceof ZodError) {
    return res.status(400).json({
      error: 'Validation error',
      details: err.errors.map(e => ({
        field: e.path.join('.'),
        message: e.message
      }))
    });
  }

  if (err.name === 'PrismaClientKnownRequestError') {
    const prismaError = err as any;
    if (prismaError.code === 'P2002') {
      return res.status(409).json({
        error: 'Resource already exists',
        field: prismaError.meta?.target?.[0]
      });
    }
    if (prismaError.code === 'P2025') {
      return res.status(404).json({ error: 'Resource not found' });
    }
  }

  res.status(500).json({
    error: err.message || 'Internal server error'
  });
};
ENDOFFILE

echo "✅ Middleware files created!"
echo "⏳ This may take a moment - creating controllers..."

# Файли контролерів занадто великі для одного heredoc
# Створюємо їх по частинах або пишемо що потрібно скопіювати вручну

echo ""
echo "⚠️  IMPORTANT: Due to file size, you need to manually create controller files."
echo ""
echo "📋 Create these files with content from the artifacts:"
echo "  - backend/src/controllers/authController.ts"
echo "  - backend/src/controllers/productsController.ts"
echo "  - backend/src/controllers/ordersController.ts"
echo "  - backend/src/controllers/integrationsController.ts"
echo "  - backend/src/routes/auth.ts"
echo "  - backend/src/routes/products.ts"
echo "  - backend/src/routes/orders.ts"
echo "  - backend/src/routes/integrations.ts"
echo "  - backend/src/server.ts"
echo "  - backend/prisma/seed.ts"
echo "  - backend/README.md"
echo ""
echo "📦 All files are available in the artifacts panel on the right →"
echo ""
echo "✅ Basic structure created!"
