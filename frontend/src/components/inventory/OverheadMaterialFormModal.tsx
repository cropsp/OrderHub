import { useState } from 'react'
import { AlertCircle, Package, FileText } from 'lucide-react'
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
import type {
  OverheadMaterial,
  OverheadMaterialCreate,
  OverheadMaterialUpdate,
} from '@/types/inventory'

const UNIT_SUGGESTIONS = ['spool', 'liter', 'pack', 'kg', 'bottle']

interface OverheadMaterialFormModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (payload: OverheadMaterialCreate | OverheadMaterialUpdate) => Promise<void>
  initialData?: OverheadMaterial | null
  isLoading?: boolean
}

export default function OverheadMaterialFormModal({
  isOpen,
  onClose,
  onSave,
  initialData,
  isLoading,
}: OverheadMaterialFormModalProps) {
  const [name, setName] = useState(initialData?.name || '')
  const [unit, setUnit] = useState(initialData?.unit || '')
  const [notes, setNotes] = useState(initialData?.notes || '')
  const [error, setError] = useState<string | null>(null)

  const [resetKey, setResetKey] = useState({ isOpen, initialData })
  if (resetKey.isOpen !== isOpen || resetKey.initialData !== initialData) {
    setResetKey({ isOpen, initialData })
    setName(initialData?.name || '')
    setUnit(initialData?.unit || '')
    setNotes(initialData?.notes || '')
    setError(null)
  }

  const isEdit = !!initialData

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!name.trim()) {
      setError('Name is required')
      return
    }
    if (!unit.trim()) {
      setError('Unit is required')
      return
    }

    const payload = {
      name,
      unit,
      notes: notes.trim() || null,
    }

    try {
      await onSave(payload)
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Failed to save overhead material')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader className="p-6 border-b border-zinc-800">
            <DialogTitle className="text-xl font-bold tracking-tight">
              {isEdit ? 'Edit Overhead Material' : 'Register Overhead Material'}
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Indirect consumables tracked as flat expenses, not per-product COGS.
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
                placeholder="e.g. Нитка бавовняна чорна"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>

            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Unit</p>
              <Input
                className="border-zinc-800 bg-zinc-900/50"
                placeholder="e.g. spool, liter, pack, kg"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                list="overhead-unit-suggestions"
              />
              <datalist id="overhead-unit-suggestions">
                {UNIT_SUGGESTIONS.map((u) => (
                  <option key={u} value={u} />
                ))}
              </datalist>
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                <FileText className="size-3" />
                <p className="text-[10px] font-bold uppercase tracking-widest">Notes (optional)</p>
              </div>
              <textarea
                className="w-full min-h-[80px] rounded-md border border-zinc-800 bg-zinc-900/50 p-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-teal-500"
                placeholder="Usage notes, supplier hints..."
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
              {isLoading ? 'Saving...' : isEdit ? 'Save Changes' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
