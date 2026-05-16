import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface ConfirmDialogProps {
  isOpen: boolean
  onClose: () => void
  title: string
  body: ReactNode
  confirmLabel?: string
  confirmVariant?: 'destructive' | 'default'
  onConfirm: () => void | Promise<void>
  isLoading?: boolean
}

export default function ConfirmDialog({
  isOpen,
  onClose,
  title,
  body,
  confirmLabel = 'Delete',
  confirmVariant = 'destructive',
  onConfirm,
  isLoading = false,
}: ConfirmDialogProps) {
  const confirmClasses =
    confirmVariant === 'destructive'
      ? 'bg-red-600 hover:bg-red-500 text-white shadow-lg'
      : 'bg-teal-600 hover:bg-teal-500 text-white shadow-lg'

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(o) => {
        if (!o && !isLoading) onClose()
      }}
    >
      <DialogContent
        showCloseButton={false}
        className="max-w-md border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl"
      >
        <DialogHeader className="p-6 border-b border-zinc-800">
          <DialogTitle className="text-lg font-bold tracking-tight">
            {title}
          </DialogTitle>
          <DialogDescription className="text-sm text-zinc-400">
            {body}
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="bg-zinc-900/30 p-6 border-t border-zinc-800">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={isLoading}
            className="text-zinc-400 hover:text-zinc-100"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => {
              void onConfirm()
            }}
            disabled={isLoading}
            className={confirmClasses}
          >
            {isLoading && (
              <Loader2
                data-testid="confirm-spinner"
                className="size-4 animate-spin"
              />
            )}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
