import { useState } from 'react'
import { Plus, FileSpreadsheet, Box, Mail, Edit2, Trash2, Scale, PackagePlus } from 'lucide-react'
import ShellPage from './ShellPage'
import PackagingForm from '@/components/inventory/PackagingForm'
import RestockModal from '@/components/inventory/RestockModal'
import CSVImportModal from '@/components/inventory/CSVImportModal'
import {
  usePackaging,
  useCreatePackaging,
  useUpdatePackaging,
  useDeletePackaging,
  useRestockPackaging,
} from '@/hooks/usePackaging'
import { packagingApi } from '@/api/packaging'
import type { PackagingBox } from '@/types/inventory'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export default function PackagingPage() {
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isImportOpen, setIsImportOpen] = useState(false)
  const [editingPackaging, setEditingPackaging] = useState<any>(null)
  const [restockTarget, setRestockTarget] = useState<PackagingBox | null>(null)

  const { data: packaging, isLoading } = usePackaging()
  const createPackaging = useCreatePackaging()
  const updatePackaging = useUpdatePackaging()
  const deletePackaging = useDeletePackaging()
  const restockPackaging = useRestockPackaging()

  const handleSave = async (data: any) => {
    if (editingPackaging) {
      await updatePackaging.mutateAsync({ id: editingPackaging.id, data })
    } else {
      await createPackaging.mutateAsync({ data })
    }
  }

  const handleDelete = (item: any) => {
    if (window.confirm(`Delete packaging "${item.name}"?`)) {
      deletePackaging.mutate({ id: item.id })
    }
  }

  return (
    <ShellPage
      title="Packaging Inventory"
      description="Shared boxes and envelopes used for automated parcel calculation."
    >
      <div className="space-y-6">
        {/* Header Actions */}
        <div className="flex flex-col md:flex-row md:items-center justify-end gap-4 bg-zinc-900/20 p-6 rounded-3xl border border-zinc-800/50 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => setIsImportOpen(true)}
              className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
            >
              <FileSpreadsheet className="size-4 mr-2 text-teal-500" />
              Bulk Import
            </Button>
            <Button
              onClick={() => { setEditingPackaging(null); setIsFormOpen(true); }}
              className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg shadow-teal-900/20"
            >
              <Plus className="size-4 mr-2" />
              Add Packaging
            </Button>
          </div>
        </div>

        {/* Content */}
        <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
          <CardContent className="p-0">
            <Table>
              <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                <TableRow className="border-none hover:bg-transparent">
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-5">Name & Type</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Dimensions (LxWxH)</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Weight Limits</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Stock</TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Sort Order</TableHead>
                  <TableHead className="text-right text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-5">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  [1, 2, 3].map(i => (
                    <TableRow key={i} className="border-b border-white/[0.02]">
                      <TableCell className="px-8 py-6"><Skeleton className="h-5 w-48 bg-zinc-800" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-32 bg-zinc-800" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-24 bg-zinc-800" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-16 bg-zinc-800" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-12 bg-zinc-800" /></TableCell>
                      <TableCell className="px-8 py-6"><Skeleton className="h-5 w-16 ml-auto bg-zinc-800" /></TableCell>
                    </TableRow>
                  ))
                ) : packaging?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-60 text-center">
                      <div className="flex flex-col items-center justify-center gap-3">
                        <Box className="size-10 text-zinc-800" />
                        <p className="text-sm text-zinc-400 italic">No packaging types registered yet.</p>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  packaging?.map((item) => (
                    <TableRow key={item.id} className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors group">
                      <TableCell className="px-8 py-6">
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            "size-10 rounded-xl flex items-center justify-center border",
                            item.packaging_type === 'BOX' ? "border-amber-500/10 bg-amber-500/5 text-amber-500" : "border-teal-500/10 bg-teal-500/5 text-teal-500"
                          )}>
                            {item.packaging_type === 'BOX' ? <Box className="size-5" /> : <Mail className="size-5" />}
                          </div>
                          <div className="flex flex-col">
                             <p className="text-sm font-bold text-zinc-100 tracking-tight">{item.name}</p>
                             <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">{item.packaging_type}</span>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 text-xs font-mono text-zinc-400">
                           <span>{item.inner_length_mm}</span>
                           <span className="text-zinc-600">×</span>
                           <span>{item.inner_width_mm}</span>
                           <span className="text-zinc-600">×</span>
                           <span>{item.inner_height_mm}</span>
                           <span className="text-[10px] text-zinc-600 ml-1">mm</span>
                           {item.max_thickness_mm && (
                             <Badge variant="outline" className="ml-2 border-teal-500/20 bg-teal-500/5 text-teal-400 text-[9px] px-1.5 h-4">
                               {item.max_thickness_mm}mm Limit
                             </Badge>
                           )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                           <div className="flex items-center gap-1.5 text-xs text-zinc-300">
                             <Scale className="size-3 text-zinc-400" />
                             <span>Max: {item.max_weight_g}g</span>
                           </div>
                           <p className="text-[10px] text-zinc-600">Tare: {item.tare_weight_g}g</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            "text-sm font-bold tabular-nums",
                            item.stock_quantity <= item.low_stock_threshold ? "text-amber-400" : "text-zinc-200"
                          )}>
                            {item.stock_quantity}
                          </span>
                          {item.stock_quantity <= item.low_stock_threshold && (
                            <Badge
                              variant="outline"
                              className="border-l-2 border-amber-500 border-y-0 border-r-0 rounded-none bg-amber-500/10 text-amber-400 text-[9px] font-bold uppercase tracking-widest px-1.5 h-4"
                            >
                              Low
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs font-mono text-zinc-400">#{item.sort_order}</span>
                      </TableCell>
                      <TableCell className="px-8 py-6 text-right">
                        <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-zinc-400 hover:text-amber-400 hover:bg-amber-400/10 rounded-xl"
                            onClick={() => setRestockTarget(item)}
                            title="Restock"
                          >
                            <PackagePlus className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.05] rounded-xl"
                            onClick={() => { setEditingPackaging(item); setIsFormOpen(true); }}
                          >
                            <Edit2 className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-zinc-600 hover:text-red-400 hover:bg-red-400/10 rounded-xl"
                            onClick={() => handleDelete(item)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <PackagingForm
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        onSave={handleSave}
        initialData={editingPackaging}
        isLoading={createPackaging.isPending || updatePackaging.isPending}
      />

      <RestockModal
        isOpen={restockTarget !== null}
        onClose={() => setRestockTarget(null)}
        onRestock={async (data) => {
          if (!restockTarget) return
          await restockPackaging.mutateAsync({ id: restockTarget.id, data })
        }}
        box={restockTarget}
        isLoading={restockPackaging.isPending}
      />

      <CSVImportModal
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onPreview={(file) => packagingApi.bulkImportPreview(file)}
        onConfirm={(token) => packagingApi.bulkImportConfirm(token)}
        title="Import Packaging Specs"
        description="Upload a CSV to bulk-register boxes and envelopes."
        templateColumns={['name', 'packaging_type', 'inner_length_mm', 'inner_width_mm', 'inner_height_mm', 'max_weight_g', 'tare_weight_g', 'max_thickness_mm']}
      />
    </ShellPage>
  )
}
