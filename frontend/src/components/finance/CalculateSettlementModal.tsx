import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, Calculator } from 'lucide-react'

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
import PartnerNameInput from './PartnerNameInput'
import { useDebounce } from '@/hooks/useDebounce'
import {
  useCreateSettlement,
  usePartnerNames,
  usePreviewSettlement,
} from '@/hooks/usePartnerPayouts'
import type { FormulaType } from '@/api/partnerPayouts'

interface CalculateSettlementModalProps {
  isOpen: boolean
  onClose: () => void
  shopId: string
  defaultPeriodStart: string
  defaultPeriodEnd: string
}

export default function CalculateSettlementModal({
  isOpen,
  onClose,
  shopId,
  defaultPeriodStart,
  defaultPeriodEnd,
}: CalculateSettlementModalProps) {
  const [partner, setPartner] = useState('')
  const [formula, setFormula] = useState<FormulaType>('net_profit_product_only')
  const [percent, setPercent] = useState('25')
  const [start, setStart] = useState(defaultPeriodStart)
  const [end, setEnd] = useState(defaultPeriodEnd)
  const [currency, setCurrency] = useState<string | undefined>(undefined)
  const [saveRecord, setSaveRecord] = useState(true)
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Reset state on open via the resetKey pattern from MaterialReceiptModal —
  // setState-during-render keyed off an isOpen change is React's documented
  // way to derive state from props without triggering effect cascades. Seed
  // with isOpen=false so the reset branch also runs on a first-render mount
  // that happens to be already-open.
  const [resetKey, setResetKey] = useState({ isOpen: false })
  if (resetKey.isOpen !== isOpen) {
    setResetKey({ isOpen })
    if (isOpen) {
      setPartner('')
      setFormula('net_profit_product_only')
      setPercent('25')
      setStart(defaultPeriodStart)
      setEnd(defaultPeriodEnd)
      setCurrency(undefined)
      setSaveRecord(true)
      setNotes('')
      setError(null)
    }
  }

  const names = usePartnerNames(shopId)
  const previewMutation = usePreviewSettlement(shopId)
  const createMutation = useCreateSettlement(shopId)

  const debouncedPercent = useDebounce(percent, 200)

  useEffect(() => {
    const pct = Number(debouncedPercent)
    if (!Number.isFinite(pct) || pct <= 0 || pct > 100) return
    if (!start || !end) return
    previewMutation.mutate({
      formula_type: formula,
      percent: pct.toString(),
      period_start: start,
      period_end: end,
      currency,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formula, debouncedPercent, start, end, currency])

  const preview = previewMutation.data
  const isNegative = useMemo(() => {
    if (!preview?.base_amount) return false
    return Number(preview.base_amount) < 0
  }, [preview])

  const handleSave = async () => {
    setError(null)
    if (!partner.trim()) {
      setError('Partner name is required')
      return
    }
    const pct = Number(percent)
    if (!Number.isFinite(pct) || pct <= 0 || pct > 100) {
      setError('Percent must be in (0, 100]')
      return
    }
    try {
      await createMutation.mutateAsync({
        partner_name: partner.trim(),
        formula_type: formula,
        percent: pct.toString(),
        period_start: start,
        period_end: end,
        currency,
        notes: notes.trim() || null,
      })
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail || 'Failed to save settlement')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <DialogHeader className="p-6 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="size-10 rounded-xl flex items-center justify-center border border-teal-500/20 bg-teal-500/10 text-teal-400">
              <Calculator className="size-5" />
            </div>
            <div>
              <DialogTitle className="text-xl font-bold tracking-tight">
                Calculate Partner Settlement
              </DialogTitle>
              <DialogDescription className="text-zinc-400">
                Snapshot the partner's share for the selected period.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="p-6 space-y-5">
          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              Partner name
            </p>
            <PartnerNameInput
              autoFocus
              value={partner}
              onChange={setPartner}
              suggestions={names.data?.items ?? []}
              placeholder="e.g. Олег"
            />
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              Formula
            </p>
            <select
              value={formula}
              onChange={(e) => setFormula(e.target.value as FormulaType)}
              className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-100"
            >
              <option value="net_profit_product_only">
                % of Net Profit (product-only)
              </option>
              <option value="revenue_items_minus_fees">
                % of Items Revenue minus Platform Fees
              </option>
            </select>
            <p className="text-[10px] text-zinc-600">
              {formula === 'net_profit_product_only'
                ? 'Excludes shipping margin/cost. Partners share product-only profit.'
                : 'Items revenue minus Shopify/Etsy fees, no COGS subtracted.'}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Percent
              </p>
              <Input
                type="number"
                step="0.01"
                min="0.01"
                max="100"
                value={percent}
                onChange={(e) => setPercent(e.target.value)}
                className="border-zinc-800 bg-zinc-900/50"
              />
            </div>
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Currency
              </p>
              <select
                value={currency ?? ''}
                onChange={(e) =>
                  setCurrency(e.target.value === '' ? undefined : e.target.value)
                }
                className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-100"
              >
                <option value="">(auto-pick)</option>
                <option value="UAH">UAH</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
              {(preview?.available_currencies?.length ?? 0) > 1 && (
                <p className="text-[10px] text-amber-400">
                  Multiple currencies in period — pick one.
                </p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Period start
              </p>
              <Input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="border-zinc-800 bg-zinc-900/50"
              />
            </div>
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Period end
              </p>
              <Input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="border-zinc-800 bg-zinc-900/50"
              />
            </div>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-sm">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              Live preview
            </p>
            {previewMutation.isPending ? (
              <p className="mt-2 text-zinc-400">Calculating…</p>
            ) : preview?.base_amount && preview?.base_currency ? (
              <div className="mt-2 space-y-1">
                <p>
                  Base:{' '}
                  <span className="font-semibold text-zinc-100">
                    {Number(preview.base_amount).toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                    })}{' '}
                    {preview.base_currency}
                  </span>
                </p>
                <p>
                  Share:{' '}
                  <span className="font-semibold text-teal-300">
                    {Number(preview.computed_amount ?? 0).toLocaleString(
                      'en-US',
                      { minimumFractionDigits: 2 },
                    )}{' '}
                    {preview.base_currency}
                  </span>
                </p>
              </div>
            ) : (
              <p className="mt-2 text-zinc-500">
                Enter percent + period to compute.
              </p>
            )}
            {isNegative && (
              <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-300">
                <AlertCircle className="size-3 mt-0.5" />
                <span>
                  Base is negative (loss period). Saving will record a
                  negative settlement. Sergii usually absorbs losses;
                  consider skipping.
                </span>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              Notes (optional)
            </p>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full min-h-[60px] rounded-md border border-zinc-800 bg-zinc-900/50 p-2 text-sm text-zinc-100"
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={saveRecord}
              onChange={(e) => setSaveRecord(e.target.checked)}
            />
            Save as settlement record
          </label>

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
            onClick={saveRecord ? handleSave : onClose}
            disabled={createMutation.isPending}
            className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg"
          >
            {saveRecord
              ? createMutation.isPending
                ? 'Saving…'
                : 'Save Settlement'
              : 'Close'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
