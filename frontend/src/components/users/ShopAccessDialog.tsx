import { useMemo, useState } from 'react';
import { Store, ShieldCheck, AlertTriangle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useShops } from '@/hooks/useShops';
import { useUserShopAccess, useSetUserShopAccess } from '@/hooks/useUsers';
import type { User } from '@/types/user';

interface BlockedShop {
  shop_id: string;
  assigned_order_count: number;
}

function extractBlocked(error: unknown): BlockedShop[] | null {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })
      .response;
    if (response?.status === 409) {
      const detail = response.data?.detail as { blocked?: BlockedShop[] } | undefined;
      return detail?.blocked ?? [];
    }
  }
  return null;
}

interface Props {
  user: User | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function ShopAccessDialog({ user, open, onOpenChange }: Props) {
  const isOwnerTarget = user?.role === 'owner';
  const { data: shops, isLoading: shopsLoading } = useShops({ enabled: open });
  const { data: access, isLoading: accessLoading } = useUserShopAccess(open ? user?.id ?? null : null);
  const setAccess = useSetUserShopAccess();

  // `selected` is null until the owner touches a checkbox — until then the server
  // grants (access) are the source of truth. This avoids syncing async data into
  // state via an effect.
  const [selected, setSelected] = useState<Set<string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingUnassign, setPendingUnassign] = useState<BlockedShop[] | null>(null);
  const [seenUserId, setSeenUserId] = useState<string | null>(null);

  // Reset editable state when the target user changes or the dialog closes —
  // adjusting state during render, React's recommended alternative to an effect.
  if (open && user && user.id !== seenUserId) {
    setSeenUserId(user.id);
    setSelected(null);
    setError(null);
    setPendingUnassign(null);
  } else if (!open && seenUserId !== null) {
    setSeenUserId(null);
  }

  const effectiveSelected = useMemo(
    () => selected ?? new Set(access?.shop_ids ?? []),
    [selected, access],
  );

  const totalBlocked = useMemo(
    () => (pendingUnassign ?? []).reduce((sum, b) => sum + b.assigned_order_count, 0),
    [pendingUnassign],
  );

  const toggle = (shopId: string) => {
    if (isOwnerTarget) return;
    const base = selected ?? new Set(access?.shop_ids ?? []);
    const next = new Set(base);
    if (next.has(shopId)) next.delete(shopId);
    else next.add(shopId);
    setSelected(next);
  };

  const submit = async (unassignOrders: boolean) => {
    if (!user) return;
    setError(null);
    try {
      await setAccess.mutateAsync({
        id: user.id,
        shop_ids: Array.from(effectiveSelected),
        unassign_orders: unassignOrders,
      });
      onOpenChange(false);
    } catch (err) {
      const blocked = extractBlocked(err);
      if (blocked) {
        setPendingUnassign(blocked);
      } else {
        setError('Failed to update shop access.');
      }
    }
  };

  const loading = shopsLoading || accessLoading;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-zinc-800 bg-zinc-950 text-zinc-100 rounded-2xl overflow-hidden">
        <DialogHeader className="p-1 px-1">
          <DialogTitle className="text-xl font-bold tracking-tight">Shop Access</DialogTitle>
          <DialogDescription className="text-xs text-zinc-400 font-medium">
            {isOwnerTarget
              ? `${user?.full_name} is an owner — unrestricted access to every shop.`
              : `Choose which shops ${user?.full_name} can see.`}
          </DialogDescription>
        </DialogHeader>

        {isOwnerTarget ? (
          <div className="flex items-center gap-3 rounded-xl border border-teal-500/20 bg-teal-500/5 p-4 text-teal-300">
            <ShieldCheck className="size-5" />
            <p className="text-[11px] font-medium">Owners always have full access. Nothing to configure.</p>
          </div>
        ) : pendingUnassign ? (
          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <AlertTriangle className="size-5 shrink-0 text-amber-400" />
              <p className="text-[12px] text-amber-200/90 leading-relaxed">
                {user?.full_name} still has <span className="font-bold">{totalBlocked}</span> assigned
                order{totalBlocked === 1 ? '' : 's'} in {pendingUnassign.length} shop
                {pendingUnassign.length === 1 ? '' : 's'} you are revoking. Removing access will
                unassign those orders.
              </p>
            </div>
          </div>
        ) : loading ? (
          <div className="py-8 text-center text-[11px] text-zinc-500">Loading shops…</div>
        ) : (
          <div className="max-h-72 space-y-1.5 overflow-y-auto py-1">
            {(shops ?? []).map((shop) => {
              const checked = effectiveSelected.has(shop.id);
              return (
                <label
                  key={shop.id}
                  className="flex cursor-pointer items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3 transition-colors hover:bg-zinc-900"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-teal-500"
                    checked={checked}
                    onChange={() => toggle(shop.id)}
                  />
                  <Store className="size-4 text-zinc-500" />
                  <span className="text-sm font-medium text-zinc-200">{shop.name}</span>
                </label>
              );
            })}
            {(shops ?? []).length === 0 && (
              <p className="py-6 text-center text-[11px] text-zinc-500">No shops available.</p>
            )}
          </div>
        )}

        {error && (
          <p className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-[11px] font-medium text-red-400 text-center">
            {error}
          </p>
        )}

        <DialogFooter className="flex flex-row gap-3 pt-2">
          <Button
            type="button"
            variant="ghost"
            className="flex-1 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11"
            onClick={() => onOpenChange(false)}
          >
            {isOwnerTarget ? 'Close' : 'Cancel'}
          </Button>
          {!isOwnerTarget && pendingUnassign && (
            <Button
              type="button"
              className="flex-1 bg-amber-600 text-white hover:bg-amber-500 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11"
              disabled={setAccess.isPending}
              onClick={() => submit(true)}
            >
              {setAccess.isPending ? 'Unassigning…' : 'Unassign & Revoke'}
            </Button>
          )}
          {!isOwnerTarget && !pendingUnassign && (
            <Button
              type="button"
              className="flex-1 bg-teal-600 text-white hover:bg-teal-500 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11"
              disabled={setAccess.isPending || loading}
              onClick={() => submit(false)}
            >
              {setAccess.isPending ? 'Saving…' : 'Save Access'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
