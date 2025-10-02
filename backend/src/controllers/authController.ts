import { Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';
import jwt, { Secret, SignOptions } from 'jsonwebtoken'; // Додали імпорт SignOptions
import { z } from 'zod';

const prisma = new PrismaClient();

// ВИПРАВЛЕННЯ 1: Явно вказуємо тип 'Secret'
const JWT_SECRET: Secret = process.env.JWT_SECRET || 'your-super-secret-jwt-key-change-this-in-production';
// const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '7d';  Старий рядок
const JWT_EXPIRES_IN = (process.env.JWT_EXPIRES_IN || '7d') as jwt.SignOptions['expiresIn'];

// Validation schemas
const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6)
});

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
  name: z.string().min(2)
});

// Створення інтерфейсу для розширеного об'єкта запиту
interface AuthRequest extends Request {
  userId?: string;
}

// Функція для централізованої обробки помилок
const handleControllerError = (error: unknown, res: Response) => {
  if (error instanceof z.ZodError) {
    return res.status(400).json({ error: 'Validation failed', details: error.issues });
  }
  console.error("Controller Error:", error);
  return res.status(500).json({ error: 'Internal Server Error' });
};


export const register = async (req: Request, res: Response) => {
  try {
    const { email, password, name } = registerSchema.parse(req.body);

    const existingUser = await prisma.user.findUnique({
      where: { email }
    });

    if (existingUser) {
      return res.status(409).json({ error: 'User already exists' });
    }

    const hashedPassword = await bcrypt.hash(password, 10);

    const user = await prisma.user.create({
      data: {
        email,
        password: hashedPassword,
        name
      },
      select: {
        id: true,
        email: true,
        name: true,
        createdAt: true
      }
    });

    // ВИПРАВЛЕННЯ 2: Явно типізуємо опції для jwt.sign()
    const signOptions: SignOptions = {
        expiresIn: JWT_EXPIRES_IN
    };

    const token = jwt.sign({ userId: user.id }, JWT_SECRET, signOptions);

    res.status(201).json({
      message: 'User registered successfully',
      user,
      token
    });
  } catch (error) {
    handleControllerError(error, res);
  }
};

export const login = async (req: Request, res: Response) => {
  try {
    const { email, password } = loginSchema.parse(req.body);

    const user = await prisma.user.findUnique({
      where: { email }
    });

    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const isValidPassword = await bcrypt.compare(password, user.password);

    if (!isValidPassword) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // ВИПРАВЛЕННЯ 3: Явно типізуємо опції для jwt.sign()
    const signOptions: SignOptions = {
        expiresIn: JWT_EXPIRES_IN
    };
    
    const token = jwt.sign({ userId: user.id }, JWT_SECRET, signOptions);

    res.json({
      message: 'Login successful',
      user: {
        id: user.id,
        email: user.email,
        name: user.name
      },
      token
    });
  } catch (error) {
    handleControllerError(error, res);
  }
};

export const getProfile = async (req: AuthRequest, res: Response) => {
  try {
    const userId = req.userId;

    if (!userId) {
      return res.status(401).json({ error: 'Unauthorized: Missing user ID' });
    }

    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: {
        id: true,
        email: true,
        name: true,
        createdAt: true
      }
    });

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    res.json({ user });
  } catch (error) {
    handleControllerError(error, res);
  }
};