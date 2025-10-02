import { Router } from 'express';
import { register, login, getProfile } from '../controllers/authController';
import { authenticateToken } from '../middleware/auth';

const router = Router();

// Публічні маршрути
router.post('/register', register);
router.post('/login', login);

// Захищені маршрути
router.get('/profile', authenticateToken, getProfile);

export default router;