import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Edit2,
  PackagePlus,
  ClipboardEdit,
  Truck,
  Coins,
  Layers,
  Percent,
} from 'lucide-react'

import ShellPage from './ShellPage'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import MaterialFormModal from '@/components/inventory/MaterialFormModal'
import MaterialReceiptModal from '@/components/inventory/MaterialReceiptModal'
import MaterialAdjustModal from '@/components/inventory/MaterialAdjustModal'
import { cn } from '@/lib/utils'
import {
  useAdjustMaterialStock,
  useCreateMaterialReceipt,
  useMaterial,
  useMaterialMovements,
  useMaterialReceipts,
  useUpdateMaterial,
} from '@/hooks/useMaterials'
import type {
  MaterialMovementReason,
  MaterialUpdate,
} from '@/types/inventory'

const REASON_FILTER_VALUES = [
  'all',
  'receipt',
  'adjustment',
  'waste',
  'consumption',
] as const

type ReasonFilter = (typeof REASON_FILTER_VALUES)[number]

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('uk-UA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function reasonBadgeClass(reason: MaterialMovementReason): string {
  switch (reason) {
    case 'receipt':
      return 'border-amber-500/20 bg-amber-500/5 text-amber-400'
    case 'consumption':
      return 'border-sky-500/20 bg-sky-500/5 text-sky-400'
    case 'waste':
      return 'border-red-500/20 bg-red-500/5 text-red-400'
    case 'adjustment':
    default:
      return 'border-zinc-700 bg-zinc-800/40 text-zinc-300'
  }
}

export default function MaterialDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: material, isLoading } = useMaterial(id)
  const { data: receipts } = useMaterialReceipts(id, { page: 1, limit: 10 })
  const [reasonFilter, setReasonFilter] = useState<ReasonFilter>('all')
  const { data: movements } = useMaterialMovements(id, {
    page: 1,
    limit: 50,
    reason: reasonFilter === 'all' ? undefined : reasonFilter,
  })

  const [isReceiptOpen, setIsReceiptOpen] = useState(false)
  const [isAdjustOpen, setIsAdjustOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)

  const createReceipt = useCreateMaterialReceipt(id)
  const adjustStock = useAdjustMaterialStock(id)
  const updateMaterial = useUpdateMaterial()

  const thresholdNum = material ? Number(material.low_stock_threshold) : 0
  const stockNum = material ? Number(material.stock_quantity) : 0
  const isLowStock = thresholdNum > 0 && stockNum <= thresholdNum

  const handleSaveEdit = async (payload: MaterialUpdate) => {
    if (!material) return
    await updateMaterial.mutateAsync({ id: material.id, data: payload })
  }

  const headerActions = useMemo(
    () => (
      <div className="flex items-center gap-2">
        <Button
          onClick={() => setIsReceiptOpen(true)}
          className="bg-amber-600 hover:bg-amber-500 text-white shadow-lg"
          disabled={!material}
        >
          <PackagePlus className="size-4 mr-2" />
          Receipt
        </Button>
        <Button
          onClick={() => setIsAdjustOpen(true)}
          variant="outline"
          className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
          disabled={!material}
        >
          <ClipboardEdit className="size-4 mr-2" />
          Adjust Stock
        </Button>
        <Button
          onClick={() => setIsEditOpen(true)}
          variant="ghost"
          className="text-zinc-400 hover:text-zinc-100"
          disabled={!material}
        >
          <Edit2 className="size-4 mr-2" />
          Edit
        </Button>
      </div>
    ),
    [material],
  )

  return (
    <ShellPage
      title={material?.name ?? 'Material'}
      description="Material detail — stock summary, receipts, and ledger."
      actions={headerActions}
    >
      <div className="space-y-6">
        <Link
          to="/inventory/materials"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="size-3" />
          Back to Materials
        </Link>

        {isLoading || !material ? (
          <Skeleton className="h-40 w-full bg-zinc-800/40" />
        ) : (
          <Card
            className={cn(
              'border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md rounded-3xl shadow-2xl',
              isLowStock && 'border-amber-500/30',
            )}
          >
            <CardContent className="p-8">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <h2 className="text-lg font-bold tracking-tight text-zinc-100">
                    {material.name}
                  </h2>
                  {material.is_active ? (
                    <Badge
                      variant="outline"
                      className="border-teal-500/20 bg-teal-500/5 text-teal-400 text-[9px] px-1.5 h-4"
                    >
                      Active
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="border-amber-500/20 bg-amber-500/5 text-amber-400 text-[9px] px-1.5 h-4"
                    >
                      Archived
                    </Badge>
                  )}
                  {isLowStock && (
                    <Badge
                      variant="outline"
                      className="border-l-2 border-amber-500 border-y-0 border-r-0 rounded-none bg-amber-500/10 text-amber-400 text-[9px] font-bold uppercase tracking-widest px-1.5 h-4"
                    >
                      Low
                    </Badge>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                <SummaryCell
                  icon={<Layers className="size-3" />}
                  label="Current stock"
                  value={`${material.stock_quantity} ${material.unit}`}
                  accent={isLowStock}
                />
                <SummaryCell
                  icon={<Coins className="size-3" />}
                  label="Avg unit cost"
                  value={`${Number(material.current_unit_cost).toFixed(2)} ${material.currency}/${material.unit}`}
                />
                <SummaryCell
                  icon={<Layers className="size-3" />}
                  label="Low-stock threshold"
                  value={
                    thresholdNum > 0
                      ? `${material.low_stock_threshold} ${material.unit}`
                      : '— not set —'
                  }
                />
                <SummaryCell
                  icon={<Percent className="size-3" />}
                  label="Waste percent"
                  value={`${material.waste_percent}%`}
                />
              </div>

              {material.supplier_name && (
                <div className="mt-6 pt-6 border-t border-zinc-800/50 flex items-center gap-2 text-xs text-zinc-400">
                  <Truck className="size-3" />
                  <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                    Supplier
                  </span>
                  <span>{material.supplier_name}</span>
                </div>
              )}
              {material.notes && (
                <div className="mt-3 text-xs text-zinc-500 whitespace-pre-wrap">
                  {material.notes}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md rounded-2xl overflow-hidden">
          <CardContent className="p-0">
            <div className="px-8 py-5 border-b border-zinc-800/50">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Recent receipts
              </h3>
            </div>
            <Table>
              <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                <TableRow className="border-none hover:bg-transparent">
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-4">
                    Date
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Qty
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Unit cost
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Shipping
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Supplier
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Invoice
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-4">
                    Notes
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(receipts ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="h-24 text-center text-xs text-zinc-500 italic"
                    >
                      No receipts yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  (receipts ?? []).map((r) => (
                    <TableRow
                      key={r.id}
                      className="border-b border-white/[0.02] hover:bg-white/[0.02]"
                    >
                      <TableCell className="px-8 py-4 text-xs text-zinc-300">
                        {formatDate(r.received_at)}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-zinc-100">
                        +{r.qty} {material?.unit ?? ''}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-zinc-300">
                        {Number(r.unit_cost).toFixed(2)} {r.currency}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-zinc-400">
                        {r.shipping_cost
                          ? `${Number(r.shipping_cost).toFixed(2)}`
                          : '—'}
                      </TableCell>
                      <TableCell className="text-xs text-zinc-400">
                        {r.supplier || '—'}
                      </TableCell>
                      <TableCell className="text-xs text-zinc-400">
                        {r.invoice_no || '—'}
                      </TableCell>
                      <TableCell className="px-8 py-4 text-xs text-zinc-500 truncate max-w-xs">
                        {r.notes || '—'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md rounded-2xl overflow-hidden">
          <CardContent className="p-0">
            <div className="px-8 py-5 border-b border-zinc-800/50 flex items-center justify-between">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Movements ledger
              </h3>
              <div className="w-48">
                <Select
                  value={reasonFilter}
                  onValueChange={(v) => setReasonFilter(v as ReasonFilter)}
                >
                  <SelectTrigger className="border-zinc-800 bg-zinc-900/50 h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-zinc-800 bg-zinc-950">
                    {REASON_FILTER_VALUES.map((v) => (
                      <SelectItem key={v} value={v}>
                        {v === 'all' ? 'All reasons' : v}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Table>
              <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                <TableRow className="border-none hover:bg-transparent">
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-4">
                    Date
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Reason
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Delta
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">
                    Linked
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-4">
                    Notes
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(movements ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="h-24 text-center text-xs text-zinc-500 italic"
                    >
                      No movements yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  (movements ?? []).map((m) => {
                    const deltaNum = Number(m.delta)
                    return (
                      <TableRow
                        key={m.id}
                        className="border-b border-white/[0.02] hover:bg-white/[0.02]"
                      >
                        <TableCell className="px-8 py-4 text-xs text-zinc-300">
                          {formatDate(m.created_at)}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-[9px] px-1.5 h-4 uppercase',
                              reasonBadgeClass(m.reason),
                            )}
                          >
                            {m.reason}
                          </Badge>
                        </TableCell>
                        <TableCell
                          className={cn(
                            'text-xs font-mono font-bold',
                            deltaNum > 0
                              ? 'text-teal-400'
                              : deltaNum < 0
                                ? 'text-red-400'
                                : 'text-zinc-400',
                          )}
                        >
                          {deltaNum > 0 ? '+' : ''}
                          {m.delta} {material?.unit ?? ''}
                        </TableCell>
                        <TableCell className="text-xs text-zinc-500 font-mono">
                          {m.receipt_id
                            ? `Receipt ${m.receipt_id.slice(0, 8)}`
                            : m.order_code
                              ? m.order_code
                              : '—'}
                        </TableCell>
                        <TableCell className="px-8 py-4 text-xs text-zinc-500 truncate max-w-xs">
                          {m.notes || '—'}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <MaterialReceiptModal
        isOpen={isReceiptOpen}
        onClose={() => setIsReceiptOpen(false)}
        material={material ?? null}
        onSubmit={(p) => createReceipt.mutateAsync(p).then(() => undefined)}
        isLoading={createReceipt.isPending}
      />
      <MaterialAdjustModal
        isOpen={isAdjustOpen}
        onClose={() => setIsAdjustOpen(false)}
        material={material ?? null}
        onSubmit={(p) => adjustStock.mutateAsync(p).then(() => undefined)}
        isLoading={adjustStock.isPending}
      />
      <MaterialFormModal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        onSave={(p) => handleSaveEdit(p as MaterialUpdate)}
        initialData={material ?? null}
        isLoading={updateMaterial.isPending}
      />
    </ShellPage>
  )
}

function SummaryCell({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode
  label: string
  value: string
  accent?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 text-zinc-500">
        {icon}
        <p className="text-[10px] font-bold uppercase tracking-widest">{label}</p>
      </div>
      <p
        className={cn(
          'text-lg font-bold tracking-tight',
          accent ? 'text-amber-400' : 'text-zinc-100',
        )}
      >
        {value}
      </p>
    </div>
  )
}
