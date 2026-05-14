import { Archive } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface ConfirmSoftDeleteModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  entityName: string
  entityType?: 'Material' | 'Overhead material'
  isLoading?: boolean
}

export default function ConfirmSoftDeleteModal({
  isOpen,
  onClose,
  onConfirm,
  entityName,
  entityType = 'Material',
  isLoading,
}: ConfirmSoftDeleteModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md border-zinc-800 bg-zinc-950 text-zinc-100 rounded-3xl">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
              <Archive className="size-5 text-amber-400" />
            </div>
            <DialogTitle className="text-lg font-bold tracking-tight">
              Archive {entityType.toLowerCase()}?
            </DialogTitle>
          </div>
          <DialogDescription className="text-zinc-400 leading-relaxed">
            {entityType} «<span className="text-zinc-200 font-medium">{entityName}</span>» will be
            marked archived. Existing recipes that reference it stay intact but will show a
            warning badge.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="mt-4">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => void onConfirm()}
            disabled={isLoading}
            className="bg-amber-600 hover:bg-amber-500 text-white shadow-lg"
          >
            {isLoading ? 'Archiving...' : 'Archive'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
