import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Receipt, Store } from 'lucide-react'

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
import OverheadMaterialReceiptModal from '@/components/inventory/OverheadMaterialReceiptModal'
import {
  useCreateOverheadMaterialReceipt,
  useOverheadMaterial,
  useOverheadMaterialReceipts,
} from '@/hooks/useOverheadMaterials'
import { formatDateTime, formatMoney } from '@/lib/format'

export default function OverheadMaterialDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: overhead, isLoading } = useOverheadMaterial(id)
  const { data: receipts } = useOverheadMaterialReceipts(id, {
    page: 1,
    limit: 50,
  })
  const [isReceiptOpen, setIsReceiptOpen] = useState(false)
  const createReceipt = useCreateOverheadMaterialReceipt(id)

  const headerActions = (
    <Button
      onClick={() => setIsReceiptOpen(true)}
      className="bg-amber-600 hover:bg-amber-500 text-white shadow-lg"
      disabled={!overhead}
    >
      <Receipt className="size-4 mr-2" />
      Receipt
    </Button>
  )

  return (
    <ShellPage
      title={overhead?.name ?? 'Overhead Material'}
      description="Overhead expense events — recorded as flat workshop expenses, no stock tracking."
      actions={headerActions}
    >
      <div className="space-y-6">
        <Link
          to="/inventory/overhead-materials"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="size-3" />
          Back to Overhead
        </Link>

        {isLoading || !overhead ? (
          <Skeleton className="h-24 w-full bg-zinc-800/40" />
        ) : (
          <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md rounded-3xl shadow-2xl">
            <CardContent className="p-8 flex items-center gap-3">
              <h2 className="text-lg font-bold tracking-tight text-zinc-100">
                {overhead.name}
              </h2>
              <span className="text-xs font-mono text-zinc-400">
                ({overhead.unit})
              </span>
              {overhead.is_active ? (
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
            </CardContent>
          </Card>
        )}

        <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md rounded-2xl overflow-hidden">
          <CardContent className="p-0">
            <div className="px-8 py-5 border-b border-zinc-800/50">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                Receipts
              </h3>
            </div>
            <Table>
              <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                <TableRow className="border-none hover:bg-transparent">
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-4">
                    Date
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4">
                    Qty
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4">
                    Total cost
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4">
                    Currency
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4">
                    Allocated to
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4">
                    Supplier
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-4">
                    Notes
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(receipts ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="h-24 text-center text-xs text-zinc-400 italic"
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
                        {formatDateTime(r.received_at)}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-zinc-300">
                        {r.qty ? `${r.qty} ${overhead?.unit ?? ''}` : '—'}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-zinc-100">
                        {formatMoney(r.total_cost)}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-zinc-400">
                        {r.currency}
                      </TableCell>
                      <TableCell className="text-xs text-zinc-400">
                        {r.shop_name ? (
                          <span className="inline-flex items-center gap-1">
                            <Store className="size-3 text-zinc-400" />
                            {r.shop_name}
                          </span>
                        ) : (
                          <span className="text-zinc-600 italic">Unallocated</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-zinc-400">
                        {r.supplier || '—'}
                      </TableCell>
                      <TableCell className="px-8 py-4 text-xs text-zinc-400 truncate max-w-xs">
                        {r.notes || '—'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <OverheadMaterialReceiptModal
        isOpen={isReceiptOpen}
        onClose={() => setIsReceiptOpen(false)}
        overhead={overhead ?? null}
        onSubmit={(p) => createReceipt.mutateAsync(p).then(() => undefined)}
        isLoading={createReceipt.isPending}
      />
    </ShellPage>
  )
}
