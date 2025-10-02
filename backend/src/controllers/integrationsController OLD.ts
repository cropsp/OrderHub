import { Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { z } from 'zod';

const prisma = new PrismaClient();

// Validation schemas
const integrationSchema = z.object({
  platform: z.string().min(1),
  apiKey: z.string().min(1),
  apiSecret: z.string().min(1),
  isActive: z.boolean().default(true)
});

// Отримати всі інтеграції
export const getAllIntegrations = async (req: Request, res: Response) => {
  try {
    const integrations = await prisma.integration.findMany({
      select: {
        id: true,
        platform: true,
        apiKey: true, // В продакшні краще не повертати повні ключі
        isActive: true,
        lastSync: true,
        createdAt: true,
        updatedAt: true
      }
    });

    // Маскуємо API ключі для безпеки
    const maskedIntegrations = integrations.map(int => ({
      ...int,
      apiKey: int.apiKey.substring(0, 4) + '••••••••••••',
      apiSecret: '••••••••••••••••'
    }));

    res.json({ integrations: maskedIntegrations });
  } catch (error) {
    throw error;
  }
};

// Отримати інтеграцію за платформою
export const getIntegrationByPlatform = async (req: Request, res: Response) => {
  try {
    const { platform } = req.params;

    const integration = await prisma.integration.findUnique({
      where: { platform }
    });

    if (!integration) {
      return res.status(404).json({ error: 'Integration not found' });
    }

    if (!integration.isActive) {
      return res.status(400).json({ error: 'Integration is not active' });
    }

    // TODO: Тут буде логіка синхронізації з Shopify/Etsy API
    // Зараз просто оновлюємо lastSync
    await prisma.integration.update({
      where: { platform },
      data: { lastSync: new Date() }
    });

    res.json({
      message: `${platform} sync completed successfully`,
      lastSync: new Date()
    });
  } catch (error) {
    throw error;
  }
};

// Видалити інтеграцію
export const deleteIntegration = async (req: Request, res: Response) => {
  try {
    const { platform } = req.params;

    await prisma.integration.delete({
      where: { platform }
    });

    res.json({ message: 'Integration deleted successfully' });
  } catch (error) {
    throw error;
  }
};
    });

    if (!integration) {
      return res.status(404).json({ error: 'Integration not found' });
    }

    // Маскуємо API ключі
    res.json({
      integration: {
        ...integration,
        apiKey: integration.apiKey.substring(0, 4) + '••••••••••••',
        apiSecret: '••••••••••••••••'
      }
    });
  } catch (error) {
    throw error;
  }
};

// Створити або оновити інтеграцію
export const upsertIntegration = async (req: Request, res: Response) => {
  try {
    const data = integrationSchema.parse(req.body);

    const integration = await prisma.integration.upsert({
      where: { platform: data.platform },
      update: {
        apiKey: data.apiKey,
        apiSecret: data.apiSecret,
        isActive: data.isActive
      },
      create: data
    });

    res.json({
      message: 'Integration saved successfully',
      integration: {
        ...integration,
        apiKey: integration.apiKey.substring(0, 4) + '••••••••••••',
        apiSecret: '••••••••••••••••'
      }
    });
  } catch (error) {
    throw error;
  }
};

// Синхронізувати замовлення з платформи
export const syncIntegration = async (req: Request, res: Response) => {
  try {
    const { platform } = req.params;

    const integration = await prisma.integration.findUnique({
      where: { platform }