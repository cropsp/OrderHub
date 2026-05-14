import { useState } from 'react'
import { AlertCircle, Package, Truck, FileText, Layers, Percent } from 'lucide-react'
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
import type { Material, MaterialCreate, MaterialUpdate } from '@/types/inventory'

const UNIT_OPTIONS = ['dm2', 'm2', 'pcs', 'm', 'kg']
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
  const [notes, setNotes] = useState(initialData?.notes || '')
  const [lowStockThreshold, setLowStockThreshold] = useState(
    initialData?.low_stock_threshold ? String(initialData.low_stock_threshold) : '',
  )
  const [wastePercent, setWastePercent] = useState(
    initialData?.waste_percent ? String(initialData.waste_percent) : '',
  )
  const [error, setError] = useState<string | null>(null)

  // Reset state on open/target change — derive during render, matches PackagingForm pattern.
  const [resetKey, setResetKey] = useState({ isOpen, initialData })
  if (resetKey.isOpen !== isOpen || resetKey.initialData !== initialData) {
    setResetKey({ isOpen, initialData })
    setName(initialData?.name || '')
    setUnit(initialData?.unit || 'dm2')
    setCurrency(initialData?.currency || 'UAH')
    setSupplierName(initialData?.supplier_name || '')
    setNotes(initialData?.notes || '')
    setLowStockThreshold(
      initialData?.low_stock_threshold ? String(initialData.low_stock_threshold) : '',
    )
    setWastePercent(
      initialData?.waste_percent ? String(initialData.waste_percent) : '',
    )
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
        notes: notes.trim() || null,
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
        notes: notes.trim() || null,
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
      <DialogContent className="max-w-2xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader className="p-6 border-b border-zinc-800">
            <DialogTitle className="text-xl font-bold tracking-tight">
              {isEdit ? 'Edit Material' : 'Register New Material'}
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Direct materials feed Bills of Materials and per-Order COGS in later sprints.
            </DialogDescription>
          </DialogHeader>

          <div className="p-8 space-y-6">
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
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

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Unit</p>
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
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
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
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
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

            {isEdit && (
              <div className="space-y-3 p-4 rounded-2xl border border-zinc-800/50 bg-zinc-900/30">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                  Stock policy
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5 text-zinc-500">
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
                    <div className="flex items-center gap-1.5 text-zinc-500">
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

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                <FileText className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">Notes (optional)</p>
              </div>
              <textarea
                className="w-full min-h-[80px] rounded-md border border-zinc-800 bg-zinc-900/50 p-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-teal-500"
                placeholder="Grade, color descriptors, lot info..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
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
