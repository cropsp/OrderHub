import { useEffect, useMemo, useState } from 'react'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { addDays, format, parseISO } from 'date-fns'
import { AlertCircle } from 'lucide-react'

import ShellPage from './ShellPage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import BaseQualityPanel from '@/components/finance/BaseQualityPanel'
import { rangeForPreset } from '@/components/finance/periodPresets'
import { useDebounce } from '@/hooks/useDebounce'
import { useShopPartnerConfigs } from '@/hooks/usePartners'
import {
  useCreateSettlement,
  usePreviewSettlement,
} from '@/hooks/usePartnerPayouts'
import { BASIS_HELP, type SelectableBasis } from '@/types/partner'

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

// The finance page hands its period over as ?start=&end= — already yyyy-MM-dd.
// Anything else (absent, hand-edited URL) falls back to the This Month preset
// rather than seeding a date input with a value it cannot render.
function seedPeriod(param: string | null, fallback: Date): string {
  if (param && ISO_DATE.test(param)) return param
  return format(fallback, 'yyyy-MM-dd')
}

function fmtMoney(value: string | null | undefined, currency: string | null) {
  if (value == null) return '—'
  return `${Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency ?? ''}`.trim()
}

export default function SettlementPage() {
  const { shopId } = useParams<{ shopId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [partnerId, setPartnerId] = useState('')
  // Percent and basis start from the partner's configuration and may be
  // overridden here (rule 9): rates change mid-relationship, and a settlement
  // already snapshots both, so an override is a first-class action rather than
  // a reason to edit the config.
  const [basis, setBasis] = useState<SelectableBasis>('profit')
  const [percent, setPercent] = useState('25')
  const [overridden, setOverridden] = useState(false)
  const [start, setStart] = useState(() =>
    seedPeriod(searchParams.get('start'), rangeForPreset('this_month').start),
  )
  const [end, setEnd] = useState(() =>
    seedPeriod(searchParams.get('end'), rangeForPreset('this_month').end),
  )
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const configs = useShopPartnerConfigs(shopId ?? null)
  const previewMutation = usePreviewSettlement(shopId ?? '')
  const createMutation = useCreateSettlement(shopId ?? '')

  const selectedConfig = useMemo(
    () => configs.data?.items.find(c => c.partner_id === partnerId) ?? null,
    [configs.data, partnerId],
  )

  // Adopt the partner's configured defaults on selection, unless the operator
  // has deliberately overridden them for this settlement. Adjusted DURING
  // render rather than in an effect — the same pattern (and for the same
  // reason) as RecordPaymentModal's resetKey: an effect here would render once
  // with the previous partner's percent before correcting itself.
  const [adoptedConfigId, setAdoptedConfigId] = useState<string | null>(null)
  if (selectedConfig && adoptedConfigId !== selectedConfig.id && !overridden) {
    setAdoptedConfigId(selectedConfig.id)
    setBasis(selectedConfig.basis)
    setPercent(selectedConfig.percent)
    // Rule 5: default the next period to the day after the last settled one, so
    // the common case never produces an overlap.
    if (selectedConfig.last_period_end) {
      setStart(
        format(addDays(parseISO(selectedConfig.last_period_end), 1), 'yyyy-MM-dd'),
      )
    }
  }

  const debouncedPercent = useDebounce(percent, 200)

  useEffect(() => {
    const pct = Number(debouncedPercent)
    if (!partnerId) return
    if (!Number.isFinite(pct) || pct <= 0 || pct > 100) return
    if (!start || !end) return
    previewMutation.mutate({
      partner_id: partnerId,
      formula_type: basis,
      percent: pct.toString(),
      period_start: start,
      period_end: end,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partnerId, basis, debouncedPercent, start, end])

  const preview = previewMutation.data
  const isNegative = preview?.base_amount != null && Number(preview.base_amount) < 0
  const overlapping = preview?.overlapping ?? []
  const fxBlocked = !!preview?.quality?.fx_blocker
  const blocked = overlapping.length > 0 || fxBlocked

  if (!shopId) {
    return <Navigate replace to="/shops" />
  }

  const goBack = () => navigate(`/shops/${shopId}/finance`)

  const handleSave = async () => {
    setError(null)
    if (!partnerId) {
      setError('Select a partner')
      return
    }
    const pct = Number(percent)
    if (!Number.isFinite(pct) || pct <= 0 || pct > 100) {
      setError('Percent must be in (0, 100]')
      return
    }
    try {
      await createMutation.mutateAsync({
        partner_id: partnerId,
        formula_type: basis,
        percent: pct.toString(),
        period_start: start,
        period_end: end,
        notes: notes.trim() || null,
      })
      goBack()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail || 'Failed to save settlement')
    }
  }

  const noConfigs = !configs.isLoading && !configs.data?.items.length

  return (
    <ShellPage
      title="Calculate Partner Settlement"
      description="Snapshot the partner's share for the selected period."
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        <div className="lg:col-span-2 rounded-3xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-5">
          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Partner
            </p>
            {noConfigs ? (
              <p className="rounded-md border border-dashed border-zinc-800 px-3 py-4 text-xs text-zinc-500">
                No partners are configured on this store. Add one in Shops → Edit
                Store Settings → Partners.
              </p>
            ) : (
              <select
                aria-label="Partner"
                value={partnerId}
                onChange={(e) => {
                  setPartnerId(e.target.value)
                  setOverridden(false)
                }}
                className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-100"
              >
                <option value="">Select a partner…</option>
                {configs.data?.items.map(c => (
                  <option key={c.partner_id} value={c.partner_id}>
                    {c.partner_name} — {Number(c.percent)}% of{' '}
                    {c.basis === 'turnover' ? 'turnover' : 'profit'} (
                    {c.settlement_currency})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Basis
              </p>
              {overridden && selectedConfig && (
                <button
                  type="button"
                  className="text-[10px] text-teal-300 hover:text-teal-200"
                  onClick={() => {
                    setOverridden(false)
                    setBasis(selectedConfig.basis)
                    setPercent(selectedConfig.percent)
                  }}
                >
                  Reset to configured defaults
                </button>
              )}
            </div>
            <select
              aria-label="Basis"
              value={basis}
              onChange={(e) => {
                setBasis(e.target.value as SelectableBasis)
                setOverridden(true)
              }}
              className="w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-100"
            >
              <option value="turnover">% of Turnover</option>
              <option value="profit">% of Profit</option>
            </select>
            <p className="text-[10px] text-zinc-600">{BASIS_HELP[basis]}</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Percent
              </p>
              <Input
                type="number"
                step="0.01"
                min="0.01"
                max="100"
                aria-label="Percent"
                value={percent}
                onChange={(e) => {
                  setPercent(e.target.value)
                  setOverridden(true)
                }}
                className="border-zinc-800 bg-zinc-900/50"
              />
            </div>
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Settles in
              </p>
              {/* Not a choice: the settlement currency is configuration, and
                  every base term is folded into it. */}
              <div className="rounded-md border border-zinc-800 bg-zinc-900/30 px-3 py-2 text-sm text-zinc-300">
                {selectedConfig?.settlement_currency ?? '—'}
              </div>
            </div>
          </div>

          {overridden && selectedConfig && (
            <p className="text-[10px] text-amber-400">
              Overriding the configured {Number(selectedConfig.percent)}% of{' '}
              {selectedConfig.basis} for this settlement only. The configuration
              is unchanged.
            </p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Period start
              </p>
              <Input
                type="date"
                aria-label="Period start"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="border-zinc-800 bg-zinc-900/50"
              />
            </div>
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Period end
              </p>
              <Input
                type="date"
                aria-label="Period end"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="border-zinc-800 bg-zinc-900/50"
              />
            </div>
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

          <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
            <Button
              type="button"
              variant="ghost"
              onClick={goBack}
              className="text-zinc-400 hover:text-zinc-100"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSave}
              disabled={createMutation.isPending || blocked || !partnerId}
              className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg"
            >
              {createMutation.isPending ? 'Saving…' : 'Save Settlement'}
            </Button>
          </div>
        </div>

        <div className="lg:sticky lg:top-6 space-y-4">
          <div className="rounded-3xl border border-zinc-800 bg-zinc-900/40 p-6 text-sm">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Live preview
            </p>
            {previewMutation.isPending ? (
              <p className="mt-2 text-zinc-400">Calculating…</p>
            ) : preview?.base_amount != null && preview.base_currency ? (
              <div className="mt-2 space-y-1">
                <p>
                  Base:{' '}
                  <span className="font-semibold text-zinc-100">
                    {fmtMoney(preview.base_amount, preview.base_currency)}
                  </span>
                </p>
                <p>
                  Share:{' '}
                  <span className="font-semibold text-teal-300">
                    {fmtMoney(preview.computed_amount, preview.base_currency)}
                  </span>
                </p>
                {preview.fx_rate_used && (
                  <p className="text-[10px] text-zinc-500">
                    Converted at {Number(preview.fx_rate_used)} UAH/USD — this rate
                    is frozen onto the settlement.
                  </p>
                )}
              </div>
            ) : (
              <p className="mt-2 text-zinc-400">
                Select a partner and a period to compute.
              </p>
            )}

            {preview?.terms?.length ? (
              <div className="mt-3 space-y-1 border-t border-zinc-800 pt-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                  How this base is built
                </p>
                {preview.terms.map((t, i) => (
                  <div
                    key={`${t.name}-${t.currency}-${i}`}
                    className="flex justify-between text-[11px] text-zinc-400"
                  >
                    <span>
                      {t.name.replace(/_/g, ' ')}
                      {t.currency !== preview.base_currency && ` (${t.currency})`}
                    </span>
                    <span className="tabular-nums">
                      {fmtMoney(t.converted, preview.base_currency)}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}

            {isNegative && (
              <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-300">
                <AlertCircle className="size-3 mt-0.5" />
                <span>
                  Base is negative (loss period). Saving records a negative
                  settlement — the partner owes back.
                </span>
              </div>
            )}

            {overlapping.length > 0 && (
              <div className="mt-3 flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
                <AlertCircle className="size-3 mt-0.5 shrink-0" />
                <span>
                  This period overlaps an existing settlement for this partner (
                  {overlapping
                    .map(o => `${o.period_start}…${o.period_end}`)
                    .join(', ')}
                  ). Overlapping periods double-pay. Start after the existing
                  period, or delete it first.
                </span>
              </div>
            )}
          </div>

          {preview?.quality && <BaseQualityPanel quality={preview.quality} />}
        </div>
      </div>
    </ShellPage>
  )
}
