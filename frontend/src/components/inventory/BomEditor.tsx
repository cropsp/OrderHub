import { useCallback, useMemo, useState } from 'react'
import { AlertTriangle, Plus, RefreshCw, Save, Trash2, Undo2 } from 'lucide-react'

import { useBom, useBomCost, useReplaceBom } from '@/hooks/useBom'
import { useMaterials } from '@/hooks/useMaterials'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { BomItem, BomItemCreate, Material } from '@/types/inventory'

type RowDraft = {
  _key: string
  // Empty string for not-yet-picked rows.
  material_id: string
  qty_per_unit: string
  notes: string
  // Captured from the fetched recipe so we keep rendering material details
  // for soft-deleted materials (which won't be in the active-materials list).
  fallback?: {
    name: string
    unit: string
    currency: string
    current_unit_cost: string
    is_active: boolean
  }
}

function nextKey() {
  return Math.random().toString(36).slice(2, 10)
}

function toDraft(items: BomItem[]): RowDraft[] {
  return items.map((it) => ({
    _key: it.id,
    material_id: it.material_id,
    qty_per_unit: it.qty_per_unit,
    notes: it.notes ?? '',
    fallback: {
      name: it.material_name,
      unit: it.material_unit,
      currency: it.material_currency,
      current_unit_cost: it.material_current_unit_cost,
      is_active: it.material_is_active,
    },
  }))
}

function draftsEqual(a: RowDraft[], b: RowDraft[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (
      a[i].material_id !== b[i].material_id ||
      a[i].qty_per_unit !== b[i].qty_per_unit ||
      (a[i].notes ?? '') !== (b[i].notes ?? '')
    ) {
      return false
    }
  }
  return true
}

function formatAmount(n: string | number): string {
  const v = Number(n)
  if (!isFinite(v)) return '—'
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const cellInputCls =
  'w-full bg-transparent border-0 text-zinc-200 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-teal-500/30 rounded px-1.5 py-1'

export interface BomEditorProps {
  productId: string
}

export default function BomEditor({ productId }: BomEditorProps) {
  const bomQuery = useBom(productId)
  const costQuery = useBomCost(productId)
  const materialsQuery = useMaterials({ includeInactive: false })
  const replaceBom = useReplaceBom(productId)

  const [draft, setDraft] = useState<RowDraft[]>([])
  const [baseline, setBaseline] = useState<RowDraft[]>([])
  // Sync server BOM into local draft when the fetched items reference changes,
  // per React's "adjusting state when a prop changes" pattern — avoids the
  // setState-in-useEffect smell.
  const [loadedItems, setLoadedItems] = useState<BomItem[] | null>(null)
  if (bomQuery.data && bomQuery.data.items !== loadedItems) {
    const d = toDraft(bomQuery.data.items)
    setDraft(d)
    setBaseline(d)
    setLoadedItems(bomQuery.data.items)
  }

  const isDirty = useMemo(() => !draftsEqual(draft, baseline), [draft, baseline])

  const activeMaterials: Material[] = useMemo(() => {
    const list = materialsQuery.data ?? []
    return [...list].sort((a, b) => a.name.localeCompare(b.name))
  }, [materialsQuery.data])

  // For preserving the display of soft-deleted materials referenced by existing rows.
  const materialIndex = useMemo(() => {
    const m = new Map<string, Material>()
    for (const mat of activeMaterials) m.set(mat.id, mat)
    return m
  }, [activeMaterials])

  function addRow() {
    setDraft((d) => [
      ...d,
      { _key: nextKey(), material_id: '', qty_per_unit: '', notes: '' },
    ])
  }

  function updateRow(key: string, patch: Partial<RowDraft>) {
    setDraft((d) => d.map((r) => (r._key === key ? { ...r, ...patch } : r)))
  }

  function removeRow(key: string) {
    setDraft((d) => d.filter((r) => r._key !== key))
  }

  function cancel() {
    setDraft(baseline)
  }

  async function save() {
    // Only rows with a picked material and a positive qty are submitted.
    const items: BomItemCreate[] = draft
      .filter((r) => r.material_id && Number(r.qty_per_unit) > 0)
      .map((r) => ({
        material_id: r.material_id,
        qty_per_unit: r.qty_per_unit,
        notes: r.notes.trim() ? r.notes.trim() : null,
      }))
    await replaceBom.mutateAsync(items)
  }

  const describeRow = useCallback(
    (row: RowDraft) => {
      if (!row.material_id) return null
      const live = materialIndex.get(row.material_id)
      if (live) {
        return {
          name: live.name,
          unit: live.unit,
          currency: live.currency,
          current_unit_cost: live.current_unit_cost,
          is_active: live.is_active,
        }
      }
      return row.fallback ?? null
    },
    [materialIndex],
  )

  const liveCost = useMemo(() => {
    // Group draft rows by currency for an immediate preview while editing.
    const buckets = new Map<string, number>()
    for (const row of draft) {
      const m = describeRow(row)
      if (!m) continue
      const qty = Number(row.qty_per_unit)
      const cost = Number(m.current_unit_cost)
      if (!isFinite(qty) || !isFinite(cost)) continue
      buckets.set(m.currency, (buckets.get(m.currency) ?? 0) + qty * cost)
    }
    return Array.from(buckets.entries()).map(([currency, amount]) => ({
      currency,
      amount,
    }))
  }, [draft, describeRow])

  const hasInactiveInDraft = draft.some((row) => {
    const m = describeRow(row)
    return m !== null && !m.is_active
  })

  if (bomQuery.isLoading) {
    return (
      <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
        <CardContent className="p-8 space-y-3">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
      <CardContent className="p-0">
        <div className="px-8 py-6 border-b border-white/[0.03] flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-zinc-200">Recipe (BOM)</h2>
            <p className="text-xs text-zinc-400 mt-1">
              Materials per finished product unit. Used for cost preview now; consumption decrements stock on shipment (coming in MAT-4).
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isDirty ? (
              <span className="text-xs text-amber-400 font-medium">
                Unsaved recipe changes
              </span>
            ) : null}
            <Button
              variant="ghost"
              onClick={() => costQuery.refetch()}
              disabled={costQuery.isFetching}
              className="text-zinc-400 hover:text-teal-400 hover:bg-white/[0.02]"
            >
              <RefreshCw className={`size-4 mr-2 ${costQuery.isFetching ? 'animate-spin' : ''}`} />
              Refresh cost
            </Button>
            <Button
              variant="ghost"
              onClick={cancel}
              disabled={!isDirty}
              className="text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.02]"
            >
              <Undo2 className="size-4 mr-2" />
              Cancel
            </Button>
            <Button
              onClick={save}
              disabled={!isDirty || replaceBom.isPending}
              className="bg-teal-500/90 hover:bg-teal-500 text-zinc-950"
            >
              <Save className="size-4 mr-2" />
              Save Recipe
            </Button>
          </div>
        </div>

        {hasInactiveInDraft ? (
          <div className="px-8 py-4 bg-amber-500/10 border-b border-amber-500/20 text-amber-300 text-sm flex items-start gap-3">
            <AlertTriangle className="size-4 mt-0.5 shrink-0" />
            <p>
              This recipe references one or more discontinued materials. Keep them if you still produce this product from old stock, or remove them to refresh the recipe.
            </p>
          </div>
        ) : null}

        {draft.length === 0 ? (
          <div className="px-8 py-16 text-center">
            <p className="text-sm text-zinc-400 italic mb-4">
              No recipe defined yet. Add materials to compute a production cost preview.
            </p>
            <Button
              variant="ghost"
              onClick={addRow}
              className="text-zinc-400 hover:text-teal-400 hover:bg-white/[0.02]"
            >
              <Plus className="size-4 mr-2" />
              Add Material
            </Button>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                <TableRow className="border-none hover:bg-transparent">
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-5">Material</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Qty / unit</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Unit</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Current cost</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Line cost</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Notes</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5 px-8 w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {draft.map((row) => {
                  const m = describeRow(row)
                  const qtyNum = Number(row.qty_per_unit)
                  const costNum = m ? Number(m.current_unit_cost) : NaN
                  const lineCost =
                    isFinite(qtyNum) && isFinite(costNum) ? qtyNum * costNum : null
                  const inactive = m !== null && !m.is_active
                  return (
                    <TableRow
                      key={row._key}
                      className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors"
                    >
                      <TableCell className="px-8 py-3 align-middle">
                        <div className="flex items-center gap-2">
                          <select
                            value={row.material_id}
                            onChange={(e) => updateRow(row._key, { material_id: e.target.value })}
                            className="bg-zinc-900/60 border border-white/[0.06] text-zinc-200 text-sm rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-teal-500/40 max-w-[260px]"
                          >
                            <option value="">— pick a material —</option>
                            {/* Existing inactive ref shown as a disabled, pre-selected option. */}
                            {inactive && m ? (
                              <option value={row.material_id} disabled>
                                {m.name} (discontinued)
                              </option>
                            ) : null}
                            {activeMaterials.map((mat) => (
                              <option key={mat.id} value={mat.id}>
                                {mat.name}
                              </option>
                            ))}
                          </select>
                          {inactive ? (
                            <span
                              data-testid="discontinued-badge"
                              className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border-l-2 border-amber-500 rounded"
                            >
                              <AlertTriangle className="size-3" />
                              Discontinued
                            </span>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="py-3 align-middle">
                        <input
                          type="number"
                          min={0}
                          step={0.01}
                          value={row.qty_per_unit}
                          onChange={(e) => updateRow(row._key, { qty_per_unit: e.target.value })}
                          placeholder="0.00"
                          className={`${cellInputCls} w-24`}
                        />
                      </TableCell>
                      <TableCell className="text-xs text-zinc-400 font-mono py-3 align-middle">
                        {m?.unit ?? '—'}
                      </TableCell>
                      <TableCell className="text-xs text-zinc-400 font-mono py-3 align-middle">
                        {m ? `${formatAmount(m.current_unit_cost)} ${m.currency}` : '—'}
                      </TableCell>
                      <TableCell className="text-xs text-zinc-200 font-mono py-3 align-middle">
                        {lineCost !== null && m
                          ? `${formatAmount(lineCost)} ${m.currency}`
                          : '—'}
                      </TableCell>
                      <TableCell className="py-3 align-middle">
                        <input
                          type="text"
                          value={row.notes}
                          onChange={(e) => updateRow(row._key, { notes: e.target.value })}
                          placeholder="e.g. back panel"
                          className={cellInputCls}
                        />
                      </TableCell>
                      <TableCell className="px-8 py-3 align-middle">
                        <button
                          type="button"
                          onClick={() => removeRow(row._key)}
                          className="text-zinc-600 hover:text-red-400 transition-colors p-1 rounded"
                          aria-label="Remove material"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>

            <div className="px-8 py-4 flex items-center justify-between border-t border-white/[0.03]">
              <Button
                variant="ghost"
                onClick={addRow}
                className="text-zinc-400 hover:text-teal-400 hover:bg-white/[0.02]"
              >
                <Plus className="size-4 mr-2" />
                Add Material
              </Button>
              <div className="text-right text-sm text-zinc-300">
                <span className="text-zinc-400 mr-2">Recipe unit cost:</span>
                {liveCost.length === 0 ? (
                  <span className="font-mono">—</span>
                ) : (
                  liveCost.map((c, idx) => (
                    <span key={c.currency} className="font-mono ml-2">
                      {formatAmount(c.amount)} {c.currency}
                      {idx < liveCost.length - 1 ? ',' : ''}
                    </span>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
