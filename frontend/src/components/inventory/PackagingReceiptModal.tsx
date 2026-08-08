import { useQueryClient } from '@tanstack/react-query'
import MaterialReceiptModal from './MaterialReceiptModal'
import { useCreateMaterialReceipt, useMaterial } from '@/hooks/useMaterials'
import type { PackagingBox } from '@/types/inventory'

interface PackagingReceiptModalProps {
  box: PackagingBox | null
  onClose: () => void
}

/**
 * WH-2: replenishing a box is recording a purchase against its paired material.
 *
 * This is a seam, not a new modal — it loads the material behind the box and hands
 * it to the existing MaterialReceiptModal, which already knows how to lock the
 * currency to the material, pre-fill the supplier and post a dated receipt. The old
 * RestockModal asked only for a quantity, which is how packaging ended up with
 * stock nobody had priced.
 *
 * Mounted only while a box is targeted (`{box && <PackagingReceiptModal .../>}`),
 * so the hooks below always get a real id rather than an `enabled: false` shell.
 */
export default function PackagingReceiptModal({ box, onClose }: PackagingReceiptModalProps) {
  const queryClient = useQueryClient()
  const { data: material } = useMaterial(box?.material_id)
  const createReceipt = useCreateMaterialReceipt(box?.material_id)

  return (
    <MaterialReceiptModal
      isOpen={box !== null}
      onClose={onClose}
      material={material ?? null}
      isLoading={createReceipt.isPending}
      onSubmit={async (payload) => {
        await createReceipt.mutateAsync(payload)
        // useCreateMaterialReceipt only refreshes the materials views. The box row
        // and the dashboard's low-stock card read the same counter and would sit
        // stale until a reload — useRestockPackaging invalidated both, so this
        // does too.
        queryClient.invalidateQueries({ queryKey: ['packaging'] })
        queryClient.invalidateQueries({ queryKey: ['dashboard'] })
        onClose()
      }}
    />
  )
}
