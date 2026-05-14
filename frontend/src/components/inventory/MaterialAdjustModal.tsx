import { useState } from 'react'
import { AlertCircle, ClipboardEdit, FileText } from 'lucide-react'
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
import type { Material, MaterialStockAdjustment } from '@/types/inventory'

interface MaterialAdjustModalProps {
  isOpen: boolean
  onClose: () => void
  material: Material | null
  onSubmit: (payload: MaterialStockAdjustment) => Promise<void>
  isLoading?: boolean
}

export default function MaterialAdjustModal({
  isOpen,
  onClose,
  material,
  onSubmit,
  isLoading,
}: MaterialAdjustModalProps) {
  const [delta, setDelta] = useState('')
  const [reason, setReason] = useState<'waste' | 'adjustment'>('adjustment')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const [resetKey, setResetKey] = useState({ isOpen, materialId: material?.id })
  if (resetKey.isOpen !== isOpen || resetKey.materialId !== material?.id) {
    setResetKey({ isOpen, materialId: material?.id })
    if (isOpen) {
      setDelta('')
      setReason('adjustment')
      setNotes('')
      setError(null)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!material) return

    const deltaNum = parseFloat(delta)
    if (!Number.isFinite(deltaNum) || deltaNum === 0) {
      setError('Adjustment delta must be a non-zero number')
      return
    }

    const payload: MaterialStockAdjustment = {
      delta: deltaNum,
      reason,
      notes: notes.trim() || null,
    }

    try {
      await onSubmit(payload)
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      setError(detail || 'Failed to adjust stock')
    }
  }

  const unit = material?.unit ?? ''

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader className="p-6 border-b border-zinc-800">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-xl flex items-center justify-center border border-zinc-700 bg-zinc-800 text-zinc-300">
                <ClipboardEdit className="size-5" />
              </div>
              <div>
                <DialogTitle className="text-xl font-bold tracking-tight">
                  Adjust Stock
                </DialogTitle>
                <DialogDescription className="text-zinc-400">
                  {material
                    ? `Current: ${material.stock_quantity} ${unit}. Use signed numbers (e.g. -3 or +5).`
                    : 'Loading…'}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          <div className="p-8 space-y-6">
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Adjust by ({unit})
              </p>
              <Input
                type="number"
                step="0.01"
                autoFocus
                className="border-zinc-800 bg-zinc-900/50"
                placeholder="-3 or +5"
                value={delta}
                onChange={(e) => setDelta(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Reason
              </p>
              <Select
                value={reason}
                onValueChange={(v) => setReason(v as 'waste' | 'adjustment')}
              >
                <SelectTrigger className="border-zinc-800 bg-zinc-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-950">
                  <SelectItem value="adjustment">
                    Stock count correction (adjustment)
                  </SelectItem>
                  <SelectItem value="waste">Loss / damage (waste)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-500">
                <FileText className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">
                  Notes (optional)
                </p>
              </div>
              <Input
                className="border-zinc-800 bg-zinc-900/50"
                placeholder="e.g. Cut error / Stock count 2026-05"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={500}
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
              {isLoading ? 'Saving...' : 'Save Adjustment'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
