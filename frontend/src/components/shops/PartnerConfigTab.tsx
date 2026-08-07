import { useState } from 'react'
import { AlertCircle, Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useCreatePartner,
  useDeleteShopPartnerConfig,
  usePartners,
  useShopPartnerConfigs,
  useUpsertShopPartnerConfig,
} from '@/hooks/usePartners'
import { BASIS_HELP, type SelectableBasis } from '@/types/partner'

const CURRENCIES = ['USD', 'UAH', 'EUR']

interface Props {
  shopId: string | null
}

/**
 * The Partners tab of Edit Store Settings (PARTNER-CONFIG-1).
 *
 * Two things live here because they are one job for the operator: attaching a
 * partner to this shop, and creating the partner identity if they are new.
 * The identity is global — the same person on two shops is one row with one
 * aggregate balance — so "add" first looks for an existing partner by name.
 *
 * Changing a rate here never moves a settlement that already exists: each
 * settlement snapshots the percent and basis it was computed with. It changes
 * the defaults the NEXT settlement starts from.
 */
export function PartnerConfigTab({ shopId }: Props) {
  const { data: configs, isLoading } = useShopPartnerConfigs(shopId)
  const { data: partners } = usePartners()
  const createPartner = useCreatePartner()
  const upsert = useUpsertShopPartnerConfig(shopId ?? '')
  const remove = useDeleteShopPartnerConfig(shopId ?? '')

  const [newName, setNewName] = useState('')
  const [percent, setPercent] = useState('25')
  const [basis, setBasis] = useState<SelectableBasis>('profit')
  const [currency, setCurrency] = useState('USD')
  const [error, setError] = useState<string | null>(null)

  if (!shopId) {
    return (
      <div className="flex h-[220px] items-center justify-center rounded-md border border-dashed border-zinc-800 text-sm text-zinc-500">
        Save the store first — partners are configured per existing store.
      </div>
    )
  }

  const percentValue = Number(percent)
  const percentValid = percent !== '' && percentValue > 0 && percentValue <= 100
  const canAdd = newName.trim().length > 0 && percentValid

  const handleAdd = async () => {
    setError(null)
    const name = newName.trim()
    try {
      // One identity per person: reuse the existing partner if the name already
      // exists, otherwise create it. Matching is case-insensitive here even
      // though the DB constraint is not — a near-duplicate is almost always a
      // typo, and the 409 from the backend catches the exact-match case.
      const existing = partners?.items.find(
        p => p.name.toLowerCase() === name.toLowerCase(),
      )
      const partner = existing ?? (await createPartner.mutateAsync({ name }))
      await upsert.mutateAsync({
        partnerId: partner.id,
        payload: {
          percent,
          basis,
          settlement_currency: currency,
          is_active: true,
        },
      })
      setNewName('')
    } catch {
      // Toasts already carry the server message; this only guards the inline row.
      setError('Could not add this partner. See the message above.')
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">
          Partners on this store
        </p>
        {isLoading ? (
          <p className="text-sm text-zinc-500">Loading…</p>
        ) : configs?.items.length ? (
          <div className="overflow-x-auto rounded-md border border-zinc-800">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900/60 text-xs uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Partner</th>
                  <th className="px-3 py-2 text-left font-semibold">%</th>
                  <th className="px-3 py-2 text-left font-semibold">Basis</th>
                  <th className="px-3 py-2 text-left font-semibold">Settles in</th>
                  <th className="px-3 py-2 text-left font-semibold">Last settled</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {configs.items.map(cfg => (
                  <tr key={cfg.id} className="border-t border-zinc-800">
                    <td className="px-3 py-2 text-zinc-100">{cfg.partner_name}</td>
                    <td className="px-3 py-2">
                      <Input
                        type="number"
                        step="0.01"
                        aria-label={`Percent for ${cfg.partner_name}`}
                        className="h-8 w-20 border-zinc-800 bg-zinc-900/50"
                        defaultValue={cfg.percent}
                        onBlur={(e) => {
                          const next = e.target.value
                          if (next === cfg.percent) return
                          const n = Number(next)
                          if (!(n > 0 && n <= 100)) {
                            e.target.value = cfg.percent
                            return
                          }
                          upsert.mutate({
                            partnerId: cfg.partner_id,
                            payload: {
                              percent: next,
                              basis: cfg.basis,
                              settlement_currency: cfg.settlement_currency,
                              is_active: cfg.is_active,
                            },
                          })
                        }}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Select
                        value={cfg.basis}
                        onValueChange={(v) =>
                          upsert.mutate({
                            partnerId: cfg.partner_id,
                            payload: {
                              percent: cfg.percent,
                              basis: v as SelectableBasis,
                              settlement_currency: cfg.settlement_currency,
                              is_active: cfg.is_active,
                            },
                          })
                        }
                      >
                        <SelectTrigger
                          size="sm"
                          className="w-32 border-zinc-800 bg-zinc-900/50"
                          aria-label={`Basis for ${cfg.partner_name}`}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="turnover">Turnover</SelectItem>
                          <SelectItem value="profit">Profit</SelectItem>
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-3 py-2 text-zinc-300">
                      {cfg.settlement_currency}
                    </td>
                    <td className="px-3 py-2 text-zinc-500">
                      {cfg.last_period_end ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove ${cfg.partner_name}`}
                        onClick={() => remove.mutate(cfg.partner_id)}
                      >
                        <Trash2 className="size-4 text-red-400" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rounded-md border border-dashed border-zinc-800 px-3 py-6 text-center text-sm text-zinc-500">
            No partners on this store yet.
          </p>
        )}
      </div>

      <div className="space-y-3 rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
        <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">
          Add a partner
        </p>
        <div className="grid grid-cols-[1fr_auto_auto_auto_auto] items-end gap-2">
          <div className="space-y-1">
            <label className="text-[11px] text-zinc-500" htmlFor="partner-name">
              Name
            </label>
            <Input
              id="partner-name"
              className="border-zinc-800 bg-zinc-900/50"
              placeholder="e.g. Ксенія"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-[11px] text-zinc-500" htmlFor="partner-percent">
              %
            </label>
            <Input
              id="partner-percent"
              type="number"
              step="0.01"
              className="w-20 border-zinc-800 bg-zinc-900/50"
              value={percent}
              onChange={(e) => setPercent(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-[11px] text-zinc-500">Basis</label>
            <Select value={basis} onValueChange={(v) => setBasis(v as SelectableBasis)}>
              <SelectTrigger
                className="w-32 border-zinc-800 bg-zinc-900/50"
                aria-label="Basis for new partner"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="turnover">Turnover</SelectItem>
                <SelectItem value="profit">Profit</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-[11px] text-zinc-500">Settles in</label>
            <Select value={currency} onValueChange={setCurrency}>
              <SelectTrigger
                className="w-24 border-zinc-800 bg-zinc-900/50"
                aria-label="Settlement currency"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CURRENCIES.map(c => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {/* type="button" is load-bearing: this whole tab lives inside the
              shop's <form onSubmit={handleSaveShop}>, and a bare <button>
              would submit it. */}
          <Button type="button" disabled={!canAdd} onClick={handleAdd}>
            <Plus className="mr-1 size-4" /> Add
          </Button>
        </div>
        <p className="text-xs text-zinc-500">{BASIS_HELP[basis]}</p>
        {!percentValid && percent !== '' && (
          <p className="text-xs text-red-400">Percent must be between 0 and 100.</p>
        )}
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-300">
            <AlertCircle className="mt-0.5 size-3 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      <p className="text-xs text-zinc-500">
        Changing a rate here never re-prices a settlement that already exists —
        each one freezes the percent and basis it was calculated with. It sets
        the defaults the next settlement starts from.
      </p>
    </div>
  )
}

export default PartnerConfigTab
