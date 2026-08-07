import { useState } from 'react'
import { AlertCircle, Banknote } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCreatePayment, useSettlements } from '@/hooks/usePartnerPayouts'
import { useShopPartnerConfigs } from '@/hooks/usePartners'
import type { PartnerSettlement } from '@/api/partnerPayouts'

interface RecordPaymentModalProps {
  isOpen: boolean
  onClose: () => void
  shopId: string
  prefillSettlement?: PartnerSettlement | null
}

export default function RecordPaymentModal({
  isOpen,
  onClose,
  shopId,
  prefillSettlement,
}: RecordPaymentModalProps) {
  const [partnerId, setPartnerId] = useState('')
  const [settlementId, setSettlementId] = useState<string | ''>('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('UAH')
  const [paidAt, setPaidAt] = useState(() => new Date().toISOString().slice(0, 10))
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Reset state when the modal opens or the prefilled settlement changes —
  // setState-during-render pattern from MaterialReceiptModal. Initial resetKey
  // intentionally seeded with isOpen=false so the first render also triggers
  // the prefill branch if the modal mounts already open.
  const [resetKey, setResetKey] = useState<{
    isOpen: boolean
    settlementId: string | undefined
  }>({ isOpen: false, settlementId: undefined })
  if (
    resetKey.isOpen !== isOpen ||
    resetKey.settlementId !== prefillSettlement?.id
  ) {
    setResetKey({ isOpen, settlementId: prefillSettlement?.id })
    if (isOpen) {
      setPartnerId(prefillSettlement?.partner_id ?? '')
      setSettlementId(prefillSettlement?.id ?? '')
      setAmount('')
      setCurrency(prefillSettlement?.base_currency ?? 'UAH')
      setPaidAt(new Date().toISOString().slice(0, 10))
      setNotes('')
      setError(null)
    }
  }

  const configs = useShopPartnerConfigs(shopId)
  // Filtered by partner_id, not by the name snapshot — a renamed partner's older
  // settlements must still be linkable.
  const settlements = useSettlements(shopId, { partner_id: partnerId || undefined })
  const createMutation = useCreatePayment(shopId)

  const linkedSettlement = settlements.data?.items.find(
    (s) => s.id === settlementId,
  )
  const currencyMismatch =
    linkedSettlement && linkedSettlement.base_currency !== currency

  const handleSave = async () => {
    setError(null)
    if (!partnerId) {
      setError('Select a partner')
      return
    }
    const amt = Number(amount)
    if (!Number.isFinite(amt) || amt <= 0) {
      setError('Amount must be greater than 0')
      return
    }
    try {
      await createMutation.mutateAsync({
        partner_id: partnerId,
        settlement_id: settlementId || null,
        amount: amt.toString(),
        currency,
        paid_at: paidAt,
        notes: notes.trim() || null,
      })
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail || 'Failed to record payment')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <DialogHeader className="p-6 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="size-10 rounded-xl flex items-center justify-center border border-emerald-500/20 bg-emerald-500/10 text-emerald-400">
              <Banknote className="size-5" />
            </div>
            <div>
              <DialogTitle className="text-xl font-bold tracking-tight">
                Record Partner Payment
              </DialogTitle>
              <DialogDescription className="text-zinc-400">
                Tracks actual money out — supports partial payments.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="p-6 space-y-5">
          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Partner
            </p>
            <select
              autoFocus
              aria-label="Partner"
              value={partnerId}
              onChange={(e) => {
                setPartnerId(e.target.value)
                setSettlementId('')
              }}
              className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-100"
            >
              <option value="">Select a partner…</option>
              {configs.data?.items.map((c) => (
                <option key={c.partner_id} value={c.partner_id}>
                  {c.partner_name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Linked settlement (optional)
            </p>
            <select
              value={settlementId}
              onChange={(e) => {
                setSettlementId(e.target.value)
                const sel = settlements.data?.items.find(
                  (s) => s.id === e.target.value,
                )
                if (sel) setCurrency(sel.base_currency)
              }}
              className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-100"
            >
              <option value="">(none — counts toward balance only)</option>
              {(settlements.data?.items ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.period_start} — {s.period_end}:{' '}
                  {Number(s.computed_amount).toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                  })}{' '}
                  {s.base_currency} (paid{' '}
                  {Number(s.paid_amount).toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                  })}
                  )
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Amount
              </p>
              <Input
                type="number"
                step="0.01"
                min="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="border-zinc-800 bg-zinc-900/50"
              />
            </div>
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Currency
              </p>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-100"
              >
                <option value="UAH">UAH</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
          </div>

          {currencyMismatch && (
            <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-300">
              <AlertCircle className="size-3 mt-0.5" />
              <span>
                Currency differs from linked settlement (
                {linkedSettlement?.base_currency}). The payment will not
                contribute to the {linkedSettlement?.base_currency} balance
                for this partner.
              </span>
            </div>
          )}

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Paid on
            </p>
            <Input
              type="date"
              value={paidAt}
              onChange={(e) => setPaidAt(e.target.value)}
              className="border-zinc-800 bg-zinc-900/50"
            />
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Notes (optional)
            </p>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full min-h-[60px] rounded-md border border-zinc-800 bg-zinc-900/50 p-2 text-sm text-zinc-100"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-xs text-red-400">
              <AlertCircle className="size-4" />
              {error}
            </div>
          )}
        </div>

        <DialogFooter className="bg-zinc-900/30 p-6 border-t border-zinc-800">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={createMutation.isPending}
            className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg"
          >
            {createMutation.isPending ? 'Saving…' : 'Record Payment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
