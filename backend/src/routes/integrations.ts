import { Router } from 'express';
import {
  getAllIntegrations,
  getIntegrationByPlatform,
  upsertIntegration,
  syncIntegration,
  deleteIntegration
} from '../controllers/integrationsController';
import { authenticateToken } from '../middleware/auth';

const router = Router();

// Всі маршрути захищені
router.use(authenticateToken);

router.get('/', getAllIntegrations);
router.get('/:platform', getIntegrationByPlatform);
router.post('/', upsertIntegration);
router.post('/:platform/sync', syncIntegration);
router.delete('/:platform', deleteIntegration);

export default router;