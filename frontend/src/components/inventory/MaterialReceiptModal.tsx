import { useState } from 'react'
import {
  AlertCircle,
  PackagePlus,
  Truck,
  FileText,
  Calendar,
  Hash,
} from 'lucide-react'
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
import type { Material, MaterialReceiptCreate } from '@/types/inventory'

interface MaterialReceiptModalProps {
  isOpen: boolean
  onClose: () => void
  material: Material | null
  onSubmit: (payload: MaterialReceiptCreate) => Promise<void>
  isLoading?: boolean
}

export default function MaterialReceiptModal({
  isOpen,
  onClose,
  material,
  onSubmit,
  isLoading,
}: MaterialReceiptModalProps) {
  const [qty, setQty] = useState('')
  const [unitCost, setUnitCost] = useState('')
  const [shippingCost, setShippingCost] = useState('')
  const [supplier, setSupplier] = useState('')
  const [invoiceNo, setInvoiceNo] = useState('')
  const [receivedAt, setReceivedAt] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const [resetKey, setResetKey] = useState({ isOpen, materialId: material?.id })
  if (
    resetKey.isOpen !== isOpen ||
    resetKey.materialId !== material?.id
  ) {
    setResetKey({ isOpen, materialId: material?.id })
    if (isOpen) {
      setQty('')
      setUnitCost('')
      setShippingCost('')
      setSupplier(material?.supplier_name ?? '')
      setInvoiceNo('')
      setReceivedAt('')
      setNotes('')
      setError(null)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!material) return

    const qtyNum = parseFloat(qty)
    const unitCostNum = parseFloat(unitCost)
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) {
      setError('Quantity must be greater than 0')
      return
    }
    if (!Number.isFinite(unitCostNum) || unitCostNum < 0) {
      setError('Unit cost must be a non-negative number')
      return
    }
    const shipNum = shippingCost.trim() ? parseFloat(shippingCost) : null
    if (shipNum !== null && (!Number.isFinite(shipNum) || shipNum < 0)) {
      setError('Shipping cost must be a non-negative number')
      return
    }

    const payload: MaterialReceiptCreate = {
      qty: qtyNum,
      unit_cost: unitCostNum,
      currency: material.currency,
      shipping_cost: shipNum,
      supplier: supplier.trim() || null,
      invoice_no: invoiceNo.trim() || null,
      received_at: receivedAt ? new Date(receivedAt).toISOString() : null,
      notes: notes.trim() || null,
    }

    try {
      await onSubmit(payload)
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      setError(detail || 'Failed to register receipt')
    }
  }

  const unit = material?.unit ?? ''

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        {/* max-h-[inherit] takes the cap from DialogContent, so the number stays
            in the primitive; header and footer are pinned outside the scroller
            so the submit button can never leave the viewport. */}
        <form onSubmit={handleSubmit} className="flex max-h-[inherit] flex-col overflow-hidden">
          <DialogHeader className="shrink-0 p-6 border-b border-zinc-800">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-xl flex items-center justify-center border border-amber-500/20 bg-amber-500/10 text-amber-500">
                <PackagePlus className="size-5" />
              </div>
              <div>
                <DialogTitle className="text-xl font-bold tracking-tight">
                  Register Receipt
                </DialogTitle>
                <DialogDescription className="text-zinc-400">
                  {material
                    ? `Recording a purchase of «${material.name}» — weighted-average cost will recompute.`
                    : 'Loading…'}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          <div className="min-h-0 overflow-y-auto p-8 space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                  Quantity ({unit})
                </p>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  autoFocus
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder="e.g. 25"
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                  Currency <span className="text-zinc-600">(locked)</span>
                </p>
                <Input
                  className="border-zinc-800 bg-zinc-900/50 text-zinc-400"
                  value={material?.currency ?? ''}
                  disabled
                  readOnly
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                  Unit cost ({material?.currency || ''}/{unit})
                </p>
                <Input
                  type="number"
                  step="0.0001"
                  min="0"
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder="e.g. 580"
                  value={unitCost}
                  onChange={(e) => setUnitCost(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                  Shipping cost (optional)
                </p>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder="0"
                  value={shippingCost}
                  onChange={(e) => setShippingCost(e.target.value)}
                />
                <p className="text-[10px] text-zinc-600">
                  Adds pro-rata: (qty × unit_cost + shipping) / qty.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-400">
                  <Truck className="size-3" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">
                    Supplier
                  </p>
                </div>
                <Input
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder="e.g. Conceria Walpier"
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-400">
                  <Hash className="size-3" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">
                    Invoice #
                  </p>
                </div>
                <Input
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder="INV-…"
                  value={invoiceNo}
                  onChange={(e) => setInvoiceNo(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-400">
                <Calendar className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">
                  Received at (optional — defaults to now)
                </p>
              </div>
              <Input
                type="datetime-local"
                className="border-zinc-800 bg-zinc-900/50"
                value={receivedAt}
                onChange={(e) => setReceivedAt(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-400">
                <FileText className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">
                  Notes (optional)
                </p>
              </div>
              <textarea
                className="w-full min-h-[60px] rounded-md border border-zinc-800 bg-zinc-900/50 p-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-amber-500"
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
              className="bg-amber-600 hover:bg-amber-500 text-white shadow-lg"
            >
              {isLoading ? 'Saving...' : 'Register Receipt'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
