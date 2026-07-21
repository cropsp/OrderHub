import { useAuth } from './useAuth';
import type { CapabilityType } from '@/types/user';

/**
 * USER-ACCESS-2 — does the current user hold `cap`?
 *
 * OWNER always returns true (superuser; matches the backend short-circuit and
 * keeps money widgets visible even if the /me capabilities array is stale or
 * absent). For everyone else it reads the effective capability list resolved by
 * GET /users/me. UI gating only — the backend independently enforces every
 * money surface, so this never guards against a leak, only avoids rendering
 * empty/denied widgets.
 */
export function useCapability(cap: CapabilityType): boolean {
  const { user } = useAuth();
  if (!user) return false;
  if (user.role === 'owner') return true;
  return Boolean(user.capabilities?.includes(cap));
}
