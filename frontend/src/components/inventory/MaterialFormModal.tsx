import { useState } from 'react'
import { AlertCircle, Package, Truck, FileText, Hash, Layers, Percent } from 'lucide-react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { Material, MaterialCreate, MaterialUpdate } from '@/types/inventory'

// 'шт' is the canonical piece unit for this business and what the backend mints
// packaging materials with (catalog_service.PACKAGING_MATERIAL_UNIT). 'pcs' stays
// for the rows already using it — WH-1-followup-1 deliberately does not migrate
// them; both mean the same thing and rewriting historical rows would be churn.
const UNIT_OPTIONS = ['dm2', 'm2', 'шт', 'pcs', 'm', 'kg']
const CURRENCY_OPTIONS = ['UAH', 'USD', 'EUR']

interface MaterialFormModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (payload: MaterialCreate | MaterialUpdate) => Promise<void>
  initialData?: Material | null
  isLoading?: boolean
}

export default function MaterialFormModal({
  isOpen,
  onClose,
  onSave,
  initialData,
  isLoading,
}: MaterialFormModalProps) {
  const [name, setName] = useState(initialData?.name || '')
  const [unit, setUnit] = useState(initialData?.unit || 'dm2')
  const [currency, setCurrency] = useState(initialData?.currency || 'UAH')
  const [supplierName, setSupplierName] = useState(initialData?.supplier_name || '')
  const [supplierSku, setSupplierSku] = useState(initialData?.supplier_sku || '')
  const [notes, setNotes] = useState(initialData?.notes || '')
  const [lowStockThreshold, setLowStockThreshold] = useState(
    initialData?.low_stock_threshold ? String(initialData.low_stock_threshold) : '',
  )
  const [wastePercent, setWastePercent] = useState(
    initialData?.waste_percent ? String(initialData.waste_percent) : '',
  )
  // WH-1. `category` is deliberately not editable here — for a material that backs
  // a packaging box the API refuses to change it (and the name) from this surface.
  const [isStockTracked, setIsStockTracked] = useState(
    initialData?.is_stock_tracked !== false,
  )
  const [error, setError] = useState<string | null>(null)

  // MAT-UI-1. Reset on the open transition and on a change of *which* material is being
  // edited — never on the object identity of `initialData`. The parent feeds this from a
  // React Query result, and a refetch (a receipt or a stock adjustment invalidates
  // ['materials', id]) resolves to a fresh reference; keying on that reference re-synced
  // the form from server data mid-edit, silently discarding whatever the user had already
  // typed and then saving the old values back. In-progress edits always win.
  // Still derived during render rather than in an effect, to avoid a cascading re-render.
  const targetId = initialData?.id ?? null
  const [resetKey, setResetKey] = useState({ isOpen, targetId })
  if (resetKey.isOpen !== isOpen || resetKey.targetId !== targetId) {
    setResetKey({ isOpen, targetId })
    setName(initialData?.name || '')
    setUnit(initialData?.unit || 'dm2')
    setCurrency(initialData?.currency || 'UAH')
    setSupplierName(initialData?.supplier_name || '')
    setSupplierSku(initialData?.supplier_sku || '')
    setNotes(initialData?.notes || '')
    setLowStockThreshold(
      initialData?.low_stock_threshold ? String(initialData.low_stock_threshold) : '',
    )
    setWastePercent(
      initialData?.waste_percent ? String(initialData.waste_percent) : '',
    )
    setIsStockTracked(initialData?.is_stock_tracked !== false)
    setError(null)
  }

  const isEdit = !!initialData

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!name.trim()) {
      setError('Material name is required')
      return
    }

    let payload: MaterialCreate | MaterialUpdate
    if (isEdit) {
      const update: MaterialUpdate = {
        name,
        unit,
        supplier_name: supplierName.trim() || null,
        supplier_sku: supplierSku.trim() || null,
        notes: notes.trim() || null,
        is_stock_tracked: isStockTracked,
      }
      if (lowStockThreshold.trim() !== '') {
        const n = parseFloat(lowStockThreshold)
        if (!Number.isFinite(n) || n < 0) {
          setError('Low-stock threshold must be ≥ 0')
          return
        }
        update.low_stock_threshold = n
      }
      if (wastePercent.trim() !== '') {
        const n = parseFloat(wastePercent)
        if (!Number.isFinite(n) || n < 0 || n > 100) {
          setError('Waste percent must be between 0 and 100')
          return
        }
        update.waste_percent = n
      }
      payload = update
    } else {
      payload = {
        name,
        unit,
        currency,
        supplier_name: supplierName.trim() || null,
        supplier_sku: supplierSku.trim() || null,
        notes: notes.trim() || null,
        is_stock_tracked: isStockTracked,
      }
    }

    try {
      await onSave(payload)
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Failed to save material')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      {/* MAT-UI-1: the dialog primitive is `fixed` + `-translate-y-1/2` with no height
          cap, so a form taller than the viewport overflowed off both ends with body
          scroll locked — the footer, and with it Save, became physically unreachable and
          a click aimed at it landed on the overlay, closing the dialog with nothing
          saved. Capping the shell and scrolling the body (the ProductForm pattern) keeps
          header and footer pinned and Save clickable at any viewport height. */}
      {/* `sm:max-w-3xl`, not `max-w-3xl`: the primitive's own `sm:max-w-sm`
          (ui/dialog.tsx) is a media-query utility, so an unconditional max-w from the
          caller loses to it above 640px and the dialog renders 384px wide. That is the
          "cramped single narrow column" — it was never honouring max-w-2xl either. */}
      <DialogContent className="sm:max-w-3xl max-h-[94vh] border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit} className="flex flex-col max-h-[94vh] overflow-hidden">
          <DialogHeader className="shrink-0 p-6 border-b border-zinc-800">
            <DialogTitle className="text-xl font-bold tracking-tight">
              {isEdit ? 'Edit Material' : 'Register New Material'}
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Direct materials feed Bills of Materials and per-Order COGS in later sprints.
            </DialogDescription>
          </DialogHeader>

          {/* Two columns from md up, so eight fields fit 1440×900 without scrolling.
              Short fields pair; anything that needs the full width says col-span-2. */}
          <div className="min-h-0 overflow-y-auto px-8 py-5 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
            <div className="space-y-2 md:col-span-2">
              <div className="flex items-center gap-1.5 text-zinc-400 mb-1">
                <Package className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">Name</p>
              </div>
              <Input
                className="border-zinc-800 bg-zinc-900/50"
                placeholder="e.g. Шкіра італійська чорна"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>

            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Unit</p>
              <Select value={unit} onValueChange={setUnit}>
                <SelectTrigger className="border-zinc-800 bg-zinc-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-950">
                  {UNIT_OPTIONS.map((u) => (
                    <SelectItem key={u} value={u}>
                      {u}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Currency {isEdit && <span className="text-zinc-600">(locked)</span>}
              </p>
              <Select value={currency} onValueChange={setCurrency} disabled={isEdit}>
                <SelectTrigger className="border-zinc-800 bg-zinc-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-950">
                  {CURRENCY_OPTIONS.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-400 mb-1">
                <Truck className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">Supplier (optional)</p>
              </div>
              <Input
                className="border-zinc-800 bg-zinc-900/50"
                placeholder="e.g. Conceria Walpier"
                value={supplierName}
                onChange={(e) => setSupplierName(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-400 mb-1">
                <Hash className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">
                  Supplier article (optional)
                </p>
              </div>
              <Input
                className="border-zinc-800 bg-zinc-900/50 font-mono"
                placeholder="e.g. 027515"
                value={supplierSku}
                onChange={(e) => setSupplierSku(e.target.value)}
              />
              <p className="text-[10px] text-zinc-500">
                The code on the supplier's invoice — it is what matches this material
                on the next delivery.
              </p>
            </div>

            {/* WH-1: settable at creation too, so a service position can be entered
                correctly the first time instead of being fixed after it has already
                driven its stock negative. */}
            <label
              className={cn(
                'flex items-start gap-3 p-4 rounded-2xl border cursor-pointer transition-colors',
                // On edit it shares a row with the Stock policy card — both govern
                // stock, and pairing them is what keeps the form off a scrollbar.
                !isEdit && 'md:col-span-2',
                // MAT-UI-1: this decides whether shipping decrements stock — the most
                // consequential control on the form. It read as filler between two
                // blocks; the accent makes the chosen state legible at a glance.
                isStockTracked
                  ? 'border-zinc-800/50 bg-zinc-900/30 hover:border-zinc-700'
                  : 'border-teal-500/30 bg-teal-500/[0.07]',
              )}
            >
              <input
                type="checkbox"
                checked={!isStockTracked}
                onChange={(e) => setIsStockTracked(!e.target.checked)}
                className="mt-0.5 size-4 rounded border-zinc-700 bg-zinc-900 accent-teal-500"
              />
              <span>
                <span
                  className={cn(
                    'block text-xs font-bold uppercase tracking-widest',
                    isStockTracked ? 'text-zinc-300' : 'text-teal-300',
                  )}
                >
                  Does not consume stock
                </span>
                <span className="block text-[10px] text-zinc-500 mt-1">
                  For services such as laser cutting or sewing: the cost still lands on
                  every order that uses it, but shipping never decrements a quantity.
                </span>
              </span>
            </label>

            {isEdit && (
              <div className="space-y-3 p-4 rounded-2xl border border-zinc-800/50 bg-zinc-900/30">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                  Stock policy
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5 text-zinc-400">
                      <Layers className="size-3" />
                      <p className="text-[10px] font-bold uppercase tracking-widest">
                        Low-stock threshold
                      </p>
                    </div>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      className="border-zinc-800 bg-zinc-900/50"
                      placeholder="0"
                      value={lowStockThreshold}
                      onChange={(e) => setLowStockThreshold(e.target.value)}
                    />
                    <p className="text-[10px] text-zinc-600">
                      Row is flagged when stock ≤ this value.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5 text-zinc-400">
                      <Percent className="size-3" />
                      <p className="text-[10px] font-bold uppercase tracking-widest">
                        Waste percent
                      </p>
                    </div>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      max="100"
                      className="border-zinc-800 bg-zinc-900/50"
                      placeholder="0"
                      value={wastePercent}
                      onChange={(e) => setWastePercent(e.target.value)}
                    />
                    <p className="text-[10px] text-zinc-600">
                      Used automatically when BOMs apply (MAT-3+).
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="space-y-2 md:col-span-2">
              <div className="flex items-center gap-1.5 text-zinc-400 mb-1">
                <FileText className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">Notes (optional)</p>
              </div>
              {/* Six-plus lines without an inner scrollbar; these carry sourcing and
                  costing context that is useless when read three words at a time. */}
              <textarea
                className="w-full min-h-[8.5rem] resize-y rounded-md border border-zinc-800 bg-zinc-900/50 p-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-teal-500"
                placeholder="Grade, color descriptors, lot info..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            {error && (
              <div className="md:col-span-2 flex items-center gap-2 p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-xs text-red-400">
                <AlertCircle className="size-4" />
                {error}
              </div>
            )}
          </div>

          <DialogFooter className="shrink-0 bg-zinc-900/30 p-6 border-t border-zinc-800">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              className="text-zinc-400 hover:text-zinc-100"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg"
            >
              {isLoading ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Material'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
