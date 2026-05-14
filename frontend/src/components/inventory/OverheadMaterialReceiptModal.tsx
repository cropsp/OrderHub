import { useState } from 'react'
import {
  AlertCircle,
  Receipt,
  Store,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useShops } from '@/hooks/useShops'
import type {
  OverheadMaterial,
  OverheadMaterialReceiptCreate,
} from '@/types/inventory'

const CURRENCY_OPTIONS = ['UAH', 'USD', 'EUR']
const UNALLOCATED_VALUE = '__unallocated__'

interface OverheadMaterialReceiptModalProps {
  isOpen: boolean
  onClose: () => void
  overhead: OverheadMaterial | null
  onSubmit: (payload: OverheadMaterialReceiptCreate) => Promise<void>
  isLoading?: boolean
}

export default function OverheadMaterialReceiptModal({
  isOpen,
  onClose,
  overhead,
  onSubmit,
  isLoading,
}: OverheadMaterialReceiptModalProps) {
  const { data: shops } = useShops()
  const [shopId, setShopId] = useState<string>(UNALLOCATED_VALUE)
  const [qty, setQty] = useState('')
  const [totalCost, setTotalCost] = useState('')
  const [currency, setCurrency] = useState('UAH')
  const [supplier, setSupplier] = useState('')
  const [invoiceNo, setInvoiceNo] = useState('')
  const [receivedAt, setReceivedAt] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const [resetKey, setResetKey] = useState({ isOpen, overheadId: overhead?.id })
  if (resetKey.isOpen !== isOpen || resetKey.overheadId !== overhead?.id) {
    setResetKey({ isOpen, overheadId: overhead?.id })
    if (isOpen) {
      setShopId(UNALLOCATED_VALUE)
      setQty('')
      setTotalCost('')
      setCurrency('UAH')
      setSupplier('')
      setInvoiceNo('')
      setReceivedAt('')
      setNotes('')
      setError(null)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!overhead) return

    const totalNum = parseFloat(totalCost)
    if (!Number.isFinite(totalNum) || totalNum < 0) {
      setError('Total cost must be a non-negative number')
      return
    }
    const qtyNum = qty.trim() ? parseFloat(qty) : null
    if (qtyNum !== null && (!Number.isFinite(qtyNum) || qtyNum < 0)) {
      setError('Quantity must be a non-negative number when provided')
      return
    }

    const payload: OverheadMaterialReceiptCreate = {
      qty: qtyNum,
      total_cost: totalNum,
      currency,
      shop_id: shopId === UNALLOCATED_VALUE ? null : shopId,
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

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader className="p-6 border-b border-zinc-800">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-xl flex items-center justify-center border border-amber-500/20 bg-amber-500/10 text-amber-500">
                <Receipt className="size-5" />
              </div>
              <div>
                <DialogTitle className="text-xl font-bold tracking-tight">
                  Register Expense
                </DialogTitle>
                <DialogDescription className="text-zinc-400">
                  {overhead
                    ? `Recording a purchase of «${overhead.name}» — surfaces as overhead expense.`
                    : 'Loading…'}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          <div className="p-8 space-y-6">
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-500">
                <Store className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">
                  Allocate to shop
                </p>
              </div>
              <Select value={shopId} onValueChange={setShopId}>
                <SelectTrigger className="border-zinc-800 bg-zinc-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-950">
                  <SelectItem value={UNALLOCATED_VALUE}>
                    — Unallocated —
                  </SelectItem>
                  {(shops ?? []).map((shop) => (
                    <SelectItem key={shop.id} value={shop.id}>
                      {shop.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-zinc-600">
                Tagged expenses surface on the shop's finance page (MAT-5);
                unallocated stays on the global overhead card.
              </p>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                  Quantity (optional)
                </p>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder={overhead?.unit ?? ''}
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                  Total cost
                </p>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder="e.g. 450"
                  value={totalCost}
                  onChange={(e) => setTotalCost(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                  Currency
                </p>
                <Select value={currency} onValueChange={setCurrency}>
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

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-500">
                  <Truck className="size-3" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">
                    Supplier
                  </p>
                </div>
                <Input
                  className="border-zinc-800 bg-zinc-900/50"
                  placeholder="e.g. ATB"
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-500">
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
              <div className="flex items-center gap-1.5 text-zinc-500">
                <Calendar className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">
                  Received at (optional)
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
              <div className="flex items-center gap-1.5 text-zinc-500">
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
              className="bg-amber-600 hover:bg-amber-500 text-white shadow-lg"
            >
              {isLoading ? 'Saving...' : 'Save Expense'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
