import { useState } from 'react';
import { Printer, Loader2, X, AlertTriangle, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { attachmentsApi } from '@/api/attachments';
import { useWbLabelCandidates, useWbLabelFetch } from '@/hooks/useShipping';
import { useToastStore } from '@/components/ui/Toast';
import { getApiErrorMessage } from '@/types/api';
import { countryName } from '@/lib/countries';
import type { OrderDetail } from '@/types/order';
import type { WbLabelCandidate } from '@/api/shipping';

interface WbLabelButtonProps {
  order: OrderDetail;
}

/** WB-3 — fetch + print the correct WesternBid thermal label from the order card.
 * WB exposes no order key, so the manager confirms the parcel from a name-matched
 * candidate list; the pick is cached so later prints skip the picker. */
export function WbLabelButton({ order }: WbLabelButtonProps) {
  const addToast = useToastStore(s => s.addToast);
  const candidatesMutation = useWbLabelCandidates();
  const fetchMutation = useWbLabelFetch();

  const [candidates, setCandidates] = useState<WbLabelCandidate[] | null>(null);
  const [broadened, setBroadened] = useState(false);
  const busy = candidatesMutation.isPending || fetchMutation.isPending;

  // Blob → hidden-iframe print (reuses the AttachmentManager blob precedent).
  const printAttachment = async (attachmentId: string) => {
    const blob = await attachmentsApi.download(attachmentId);
    const url = window.URL.createObjectURL(blob);
    const iframe = document.createElement('iframe');
    iframe.style.position = 'fixed';
    iframe.style.right = '0';
    iframe.style.bottom = '0';
    iframe.style.width = '0';
    iframe.style.height = '0';
    iframe.style.border = '0';
    iframe.src = url;
    iframe.onload = () => {
      try {
        iframe.contentWindow?.focus();
        iframe.contentWindow?.print();
      } catch {
        /* the print dialog may be blocked; the blob is still cached server-side */
      }
      // Give the dialog time to open before revoking the object URL.
      window.setTimeout(() => {
        window.URL.revokeObjectURL(url);
        iframe.remove();
      }, 60_000);
    };
    document.body.appendChild(iframe);
  };

  const confirmParcel = async (shipmentId: string) => {
    try {
      const res = await fetchMutation.mutateAsync({ orderId: order.id, shipmentId });
      if (res.status === 'unsupported') {
        addToast(res.message ?? 'This carrier has no API thermal label.', 'info');
        setCandidates(null);
        return;
      }
      if (res.attachment_id) {
        setCandidates(null);
        await printAttachment(res.attachment_id);
      }
    } catch (error) {
      addToast(getApiErrorMessage(error, 'Failed to fetch the WesternBid label'), 'error');
    }
  };

  const start = async (broaden = false) => {
    setBroadened(broaden);
    try {
      const res = await candidatesMutation.mutateAsync({ orderId: order.id, broaden });
      if (res.status === 'cached' && res.attachment_id) {
        await printAttachment(res.attachment_id);
        return;
      }
      if (res.status === 'linked' && res.candidates[0]) {
        // Already matched in a prior session but not yet cached — fetch straight away.
        await confirmParcel(res.candidates[0].shipment_id);
        return;
      }
      setCandidates(res.candidates);
      if (res.status === 'empty' && !broaden) {
        // fall through to the empty-state UI (offers a broadened retry)
      }
    } catch (error) {
      addToast(getApiErrorMessage(error, 'Failed to search WesternBid'), 'error');
    }
  };

  return (
    <div className="p-3 border-t border-zinc-800/50 bg-zinc-950/20 space-y-2">
      {candidates === null ? (
        <Button
          className="w-full h-9 rounded-lg font-black text-[10px] uppercase tracking-widest gap-2 bg-teal-600 hover:bg-teal-500 text-white shadow-lg shadow-teal-900/20"
          disabled={busy}
          onClick={() => start(false)}
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Printer size={14} />}
          {busy ? 'Working…' : 'Print WB Label'}
        </Button>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <p className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider">
              {candidates.length > 0 ? 'Select the matching parcel' : 'No parcel found'}
            </p>
            <button
              className="p-0.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              onClick={() => setCandidates(null)}
              aria-label="Cancel"
            >
              <X size={14} />
            </button>
          </div>

          {candidates.map(c => (
            <button
              key={c.shipment_id}
              disabled={busy}
              onClick={() => confirmParcel(c.shipment_id)}
              className="w-full text-left p-2.5 rounded-lg bg-zinc-900/60 border border-zinc-800 hover:border-teal-500/40 hover:bg-teal-500/5 transition-all disabled:opacity-50 group"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-zinc-200 truncate">
                  {c.recipient_name ?? '—'}
                </span>
                <Check size={13} className="text-teal-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </div>
              <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[9px] text-zinc-500">
                <span>{c.shipping_type ?? '—'}</span>
                <span>·</span>
                <span>{countryName(c.recipient_country_code)}</span>
                {c.recipient_postal_code && <><span>·</span><span>{c.recipient_postal_code}</span></>}
                {c.created_date && (
                  <>
                    <span>·</span>
                    <span>{new Date(c.created_date).toLocaleDateString()}</span>
                  </>
                )}
              </div>
            </button>
          ))}

          {candidates.length === 0 && (
            <div className="space-y-2">
              <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/10">
                <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
                <p className="text-[10px] text-amber-200/80 leading-snug">
                  No WesternBid parcel matched this recipient
                  {broadened ? '' : ' in this country'}. If the parcel is a
                  NovaPoshtaGlobal shipment, print its label from the WesternBid cabinet.
                </p>
              </div>
              {!broadened && (
                <Button
                  variant="outline"
                  className="w-full h-8 text-[10px] font-bold uppercase tracking-wider gap-2"
                  disabled={busy}
                  onClick={() => start(true)}
                >
                  {busy ? <Loader2 size={13} className="animate-spin" /> : null}
                  Broaden search (any country)
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
