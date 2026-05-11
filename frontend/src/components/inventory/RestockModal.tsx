import { useState } from 'react'
import { PackagePlus, Layers } from 'lucide-react'
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
import type { PackagingBox, RestockRequest } from '@/types/inventory'

interface RestockModalProps {
  isOpen: boolean
  onClose: () => void
  onRestock: (data: RestockRequest) => Promise<void>
  box: PackagingBox | null
  isLoading?: boolean
}

export default function RestockModal({
  isOpen,
  onClose,
  onRestock,
  box,
  isLoading,
}: RestockModalProps) {
  const [quantity, setQuantity] = useState<number>(1)
  const [note, setNote] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  // Reset on open/box change without an effect.
  const [resetKey, setResetKey] = useState({ isOpen, boxId: box?.id })
  if (resetKey.isOpen !== isOpen || resetKey.boxId !== box?.id) {
    setResetKey({ isOpen, boxId: box?.id })
    setQuantity(1)
    setNote('')
    setError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!box) return
    if (!quantity || quantity < 1) {
      setError('Quantity must be at least 1')
      return
    }
    try {
      await onRestock({ quantity, note: note.trim() || null })
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Failed to restock packaging')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader className="p-6 border-b border-zinc-800">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-xl flex items-center justify-center border border-amber-500/20 bg-amber-500/10 text-amber-500">
                <PackagePlus className="size-5" />
              </div>
              <div>
                <DialogTitle className="text-xl font-bold tracking-tight">Restock Packaging</DialogTitle>
                <DialogDescription className="text-zinc-400">
                  {box ? `Adding units to «${box.name}» (current stock: ${box.stock_quantity})` : ''}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          <div className="p-8 space-y-6">
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                <Layers className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">Units Received</p>
              </div>
              <Input
                type="number"
                min={1}
                autoFocus
                className="border-zinc-800 bg-zinc-900/50"
                value={quantity}
                onChange={e => setQuantity(parseInt(e.target.value) || 0)}
              />
            </div>

            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Note (optional)</p>
              <Input
                className="border-zinc-800 bg-zinc-900/50"
                placeholder="e.g. shelf count after audit"
                value={note}
                onChange={e => setNote(e.target.value)}
                maxLength={500}
              />
            </div>

            {error && (
              <div className="p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-xs text-red-400">
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
              {isLoading ? 'Saving...' : 'Restock'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
