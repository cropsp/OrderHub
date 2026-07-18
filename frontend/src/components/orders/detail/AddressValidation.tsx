import { useState } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Loader2, Check, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AddressBadge } from '@/components/ui/AddressBadge';
import { useToastStore } from '@/components/ui/Toast';
import { useValidateAddress } from '@/hooks/useOrders';
import { useAuth } from '@/hooks/useAuth';
import { UserRole } from '@/types/user';
import { partitionDiff } from '@/lib/addressDiff';
import type { OrderDetail } from '@/types/order';
import type { AddressFieldDiff, AddressVerdict } from '@/types/addressValidation';

interface AddressValidationProps {
  order: OrderDetail;
  canManageShipping: boolean;
  /** DetailLogistics' order-update path — the same one manual edits use. Apply reuses
   *  it so audit-history + partial-update semantics are inherited, not reinvented. */
  onApply?: (payload: Record<string, unknown>) => Promise<void>;
}

// Google diff field -> order shipping_* column. `country` is intentionally absent:
// Apply never rewrites the country (ADDR-VAL-2 rule 3 / OQ-4).
const FIELD_TO_COLUMN: Record<string, string> = {
  street_1: 'shipping_street_1',
  street_2: 'shipping_street_2',
  city: 'shipping_city',
  state: 'shipping_state',
  zip: 'shipping_zip',
};

const FIELD_LABEL: Record<string, string> = {
  street_1: 'Street', street_2: 'Street 2', city: 'City', state: 'State', zip: 'ZIP', country: 'Country',
};

export function AddressValidation({ order, canManageShipping, onApply }: AddressValidationProps) {
  const [verdict, setVerdict] = useState<AddressVerdict | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const validate = useValidateAddress();
  const { user } = useAuth();
  const isOwner = user?.role === UserRole.OWNER;
  const addToast = useToastStore((s) => s.addToast);

  // UA never goes to Google — Nova Poshta owns that flow. Render nothing.
  if ((order.shipping_country || '').toUpperCase() === 'UA') return null;

  const status = verdict?.status ?? order.address_validation_status ?? null;
  const validatedAt = verdict?.validated_at ?? order.address_validation_at ?? null;
  // Require a street, matching the "No address provided" display (DetailLogistics keys
  // purely on shipping_street_1). City + country alone is too sparse for Google to
  // validate — it comes back 400 INVALID_ARGUMENT — so don't let users reach it.
  const hasAddress = Boolean(order.shipping_street_1);

  const runCheck = async () => {
    try {
      const result = await validate.mutateAsync(order.id);
      setVerdict(result);
    } catch {
      addToast('Address check failed. Please try again.', 'error');
    }
  };

  // Apply only the fields Google actually changed (from the diff), so unchanged fields —
  // including street_2 and the untouched country — are never disturbed.
  const applicable = (verdict?.diff ?? []).filter((d) => d.field in FIELD_TO_COLUMN);

  const applySuggestion = async () => {
    if (!onApply || applicable.length === 0) return;
    const summary = applicable
      .map((d) => `• ${FIELD_LABEL[d.field] ?? d.field}: "${d.original ?? ''}" → "${d.suggested ?? ''}"`)
      .join('\n');
    if (!window.confirm(`Apply Google's suggested address?\n\n${summary}`)) return;

    const payload: Record<string, unknown> = {};
    for (const d of applicable) payload[FIELD_TO_COLUMN[d.field]] = d.suggested;

    setIsApplying(true);
    try {
      await onApply(payload);
      addToast('Address updated. Re-check to confirm.', 'success');
      setVerdict(null); // close the diff; the refreshed order carries the persisted badge
    } finally {
      setIsApplying(false);
    }
  };

  const { actionable, cosmetic } = partitionDiff(verdict?.diff ?? []);
  const isChecking = validate.isPending;

  return (
    <div className="pt-3 mt-1 border-t border-zinc-800/30 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-1 shrink-0">
            <MapPin size={11} className="text-zinc-600" /> Address
          </span>
          {status && <AddressBadge status={status} validatedAt={validatedAt} />}
        </div>
        {canManageShipping && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[10px] font-semibold uppercase tracking-wider text-teal-400 hover:text-teal-300 hover:bg-teal-500/10 gap-1 shrink-0"
            disabled={isChecking || !hasAddress}
            onClick={runCheck}
          >
            {isChecking ? <Loader2 size={11} className="animate-spin" /> : null}
            {status ? 'Re-check' : 'Check address'}
          </Button>
        )}
      </div>

      {canManageShipping && !hasAddress && (
        <p className="text-[10px] text-zinc-600 italic">Add a street address to check this address.</p>
      )}

      {status === 'unavailable' && isOwner && (
        <p className="text-[10px] text-zinc-500">
          No Google API key configured —{' '}
          <Link to="/settings" className="text-teal-400 hover:underline">set one in Settings → Address Validation</Link>.
        </p>
      )}

      {/* A real, actionable difference: surface prominently with Apply. */}
      {actionable.length > 0 && (
        <div className="space-y-2 rounded-lg bg-zinc-950/40 border border-zinc-800/60 p-2.5">
          <p className="text-[10px] font-semibold text-amber-400/90 uppercase tracking-wider">Suggested changes</p>
          <div className="space-y-1">
            {actionable.map((d) => <DiffRow key={d.field} entry={d} />)}
          </div>
          {canManageShipping && onApply && (
            <Button
              size="sm"
              className="h-7 bg-teal-600 hover:bg-teal-500 text-white text-[10px] font-bold uppercase tracking-wider gap-1.5 px-3"
              disabled={isApplying}
              onClick={applySuggestion}
            >
              {isApplying ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
              Apply suggestion
            </Button>
          )}
        </div>
      )}

      {/* Cosmetic-only result: de-emphasised, never nags. Apply-to-canonicalise stays available. */}
      {actionable.length === 0 && cosmetic.length > 0 && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] text-zinc-600 italic">Minor formatting differences only (zip+4 / abbreviations).</p>
          {canManageShipping && onApply && (
            <button
              className="text-[10px] text-zinc-500 hover:text-teal-400 underline shrink-0 disabled:opacity-50"
              disabled={isApplying}
              onClick={applySuggestion}
            >
              Apply formatting
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function DiffRow({ entry }: { entry: AddressFieldDiff }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] leading-tight">
      <span className="text-zinc-600 uppercase text-[9px] font-bold w-12 shrink-0">
        {FIELD_LABEL[entry.field] ?? entry.field}
      </span>
      <span className="text-zinc-500 line-through truncate">{entry.original || '—'}</span>
      <ArrowRight size={10} className="text-zinc-600 shrink-0" />
      <span className="text-zinc-200 font-medium truncate">{entry.suggested || '—'}</span>
    </div>
  );
}
