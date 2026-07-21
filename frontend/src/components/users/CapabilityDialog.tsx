import { useMemo, useState } from 'react';
import { Coins, Wallet, ShieldCheck } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useUserCapabilities, useSetUserCapabilities } from '@/hooks/useUsers';
import { Capability } from '@/types/user';
import type { User } from '@/types/user';

interface Props {
  user: User | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// The capabilities this editor manages, with labels. Mirrors backend
// models.user.Capability (USER-ACCESS-2).
const CAPABILITY_ROWS = [
  {
    key: Capability.VIEW_FINANCE,
    icon: Wallet,
    label: 'View finance',
    hint: 'P&L page, dashboard revenue & net profit, partner payouts.',
  },
  {
    key: Capability.VIEW_COSTS,
    icon: Coins,
    label: 'View costs',
    hint: 'Per-order & product costs, BOM cost, material unit costs, COGS.',
  },
] as const;

export default function CapabilityDialog({ user, open, onOpenChange }: Props) {
  const isOwnerTarget = user?.role === 'owner';
  const { data, isLoading } = useUserCapabilities(open ? user?.id ?? null : null);
  const setCaps = useSetUserCapabilities();

  // `selected` is null until the owner touches a checkbox — until then the
  // server values are the source of truth (mirrors ShopAccessDialog).
  const [selected, setSelected] = useState<Record<string, boolean> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seenUserId, setSeenUserId] = useState<string | null>(null);

  if (open && user && user.id !== seenUserId) {
    setSeenUserId(user.id);
    setSelected(null);
    setError(null);
  } else if (!open && seenUserId !== null) {
    setSeenUserId(null);
  }

  const effective = useMemo<Record<string, boolean>>(
    () => selected ?? data?.capabilities ?? {},
    [selected, data],
  );

  const toggle = (key: string) => {
    if (isOwnerTarget) return;
    const base = selected ?? data?.capabilities ?? {};
    setSelected({ ...base, [key]: !base[key] });
  };

  const submit = async () => {
    if (!user) return;
    setError(null);
    try {
      // Send only the managed capabilities.
      const payload: Record<string, boolean> = {};
      for (const row of CAPABILITY_ROWS) payload[row.key] = Boolean(effective[row.key]);
      await setCaps.mutateAsync({ id: user.id, capabilities: payload });
      onOpenChange(false);
    } catch {
      setError('Failed to update capabilities.');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-zinc-800 bg-zinc-950 text-zinc-100 rounded-2xl overflow-hidden">
        <DialogHeader className="p-1 px-1">
          <DialogTitle className="text-xl font-bold tracking-tight">Money Access</DialogTitle>
          <DialogDescription className="text-xs text-zinc-400 font-medium">
            {isOwnerTarget
              ? `${user?.full_name} is an owner — full financial visibility.`
              : `Choose what financial data ${user?.full_name} can see.`}
          </DialogDescription>
        </DialogHeader>

        {isOwnerTarget ? (
          <div className="flex items-center gap-3 rounded-xl border border-teal-500/20 bg-teal-500/5 p-4 text-teal-300">
            <ShieldCheck className="size-5" />
            <p className="text-[11px] font-medium">Owners always see all money. Nothing to configure.</p>
          </div>
        ) : isLoading ? (
          <div className="py-8 text-center text-[11px] text-zinc-500">Loading…</div>
        ) : (
          <div className="space-y-1.5 py-1">
            {CAPABILITY_ROWS.map((row) => {
              const Icon = row.icon;
              const checked = Boolean(effective[row.key]);
              return (
                <label
                  key={row.key}
                  className="flex cursor-pointer items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3 transition-colors hover:bg-zinc-900"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 size-4 accent-teal-500"
                    checked={checked}
                    onChange={() => toggle(row.key)}
                  />
                  <Icon className="mt-0.5 size-4 shrink-0 text-zinc-500" />
                  <span className="flex flex-col">
                    <span className="text-sm font-medium text-zinc-200">{row.label}</span>
                    <span className="text-[11px] text-zinc-500">{row.hint}</span>
                  </span>
                </label>
              );
            })}
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
          {!isOwnerTarget && (
            <Button
              type="button"
              className="flex-1 bg-teal-600 text-white hover:bg-teal-500 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11"
              disabled={setCaps.isPending || isLoading}
              onClick={submit}
            >
              {setCaps.isPending ? 'Saving…' : 'Save Access'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
