import { cn } from '@/lib/utils';
import type { AddressValidationStatus } from '@/types/addressValidation';

/**
 * ADDR-VAL-2 (OQ-2) — address-validation status pill. Mirrors StatusBadge's
 * pill+dot idiom but with an address-status config; StatusBadge itself is hard-keyed
 * to order statuses (unknown keys fall back to "New"), so it can't be reused directly.
 * `ua` is intentionally absent — the whole block is hidden for UA orders.
 */
const config: Record<
  Exclude<AddressValidationStatus, 'ua'>,
  { label: string; classes: string; dot: string }
> = {
  verified: {
    label: 'Verified',
    classes: 'bg-green-500/10 text-green-400 border-l-2 border-green-500',
    dot: 'bg-green-500',
  },
  needs_attention: {
    label: 'Needs attention',
    classes: 'bg-amber-500/10 text-amber-400 border-l-2 border-amber-500',
    dot: 'bg-amber-500',
  },
  couldnt_verify: {
    label: "Couldn't verify",
    classes: 'bg-zinc-500/10 text-zinc-400 border-l-2 border-zinc-500',
    dot: 'bg-zinc-500',
  },
  unsupported: {
    label: 'Not supported here',
    classes: 'bg-zinc-500/10 text-zinc-500 border-l-2 border-zinc-600',
    dot: 'bg-zinc-600',
  },
  unavailable: {
    label: 'Validation unavailable',
    classes: 'bg-zinc-500/10 text-zinc-500 border-l-2 border-zinc-600',
    dot: 'bg-zinc-600',
  },
};

interface AddressBadgeProps {
  status: AddressValidationStatus;
  /** ISO timestamp of the check; shown as a title tooltip when present. */
  validatedAt?: string | null;
  className?: string;
}

export function AddressBadge({ status, validatedAt, className }: AddressBadgeProps) {
  if (status === 'ua') return null;
  const c = config[status];
  if (!c) return null;

  return (
    <div
      title={validatedAt ? `Checked ${new Date(validatedAt).toLocaleString()}` : undefined}
      className={cn(
        'inline-flex items-center gap-1.5 font-medium uppercase tracking-wide text-[10px] px-2 py-0.5 transition-colors',
        c.classes,
        className,
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', c.dot)} />
      {c.label}
    </div>
  );
}
