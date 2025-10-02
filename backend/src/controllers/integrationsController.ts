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

// Створення інтерфейсу для розширеного об'єкта запиту (якщо використовується middleware)
interface AuthRequest extends Request {
  userId?: string;
}

// Функція для централізованої обробки помилок (рекомендовано, щоб сервер не падав)
const handleControllerError = (error: unknown, res: Response) => {
  if (error instanceof z.ZodError) {
    return res.status(400).json({ error: 'Validation failed', details: error.issues });
  }
  console.error("Controller Error:", error);
  return res.status(500).json({ error: 'Internal Server Error' });
};


// Отримати всі інтеграції
export const getAllIntegrations = async (req: Request, res: Response) => {
  try {
    const integrations = await prisma.integration.findMany({
      select: {
        id: true,
        platform: true,
        apiKey: true, 
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
    handleControllerError(error, res); // Використовуємо обробник
  }
};

// Отримати інтеграцію за платформою (для синхронізації)
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
    handleControllerError(error, res); // Використовуємо обробник
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
    handleControllerError(error, res); // Використовуємо обробник
  }
};

// =================================================================
// ВИПРАВЛЕННЯ: ЗАЙВИЙ БЛОК КОДУ ВИДАЛЕНО! (Рядки 117-133 у вашому старому файлі)
// =================================================================

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
    handleControllerError(error, res);
  }
};

// Синхронізувати замовлення з платформи
export const syncIntegration = async (req: Request, res: Response) => {
  try {
    const { platform } = req.params;

    const integration = await prisma.integration.findUnique({
      where: { platform }
    }); // <--- ПРОПУЩЕНА ДУЖКА БУЛА ТУТ

    if (!integration) {
        return res.status(404).json({ error: 'Integration not found' });
    }

    // TODO: Додайте тут логіку синхронізації

    res.json({
        message: `${platform} sync initiated successfully`,
        status: 'pending'
    });

  } catch (error) {
    handleControllerError(error, res);
  }
};