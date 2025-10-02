import { Router } from 'express';
import {
  getAllOrders,
  getOrderById,
  createOrder,
  updateOrderStatus,
  updateOrderItemCost,
  deleteOrder
} from '../controllers/ordersController';
import { authenticateToken } from '../middleware/auth';

const router = Router();

// Всі маршрути захищені
router.use(authenticateToken);

router.get('/', getAllOrders);
router.get('/:id', getOrderById);
router.post('/', createOrder);
router.patch('/:id/status', updateOrderStatus);
router.patch('/:id/item-cost', updateOrderItemCost);
router.delete('/:id', deleteOrder);

export default router;