import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Edit2, Trash2, Layers, Search } from 'lucide-react'
import ShellPage from './ShellPage'
import MaterialFormModal from '@/components/inventory/MaterialFormModal'
import ConfirmSoftDeleteModal from '@/components/inventory/ConfirmSoftDeleteModal'
import {
  useMaterials,
  useCreateMaterial,
  useUpdateMaterial,
  useSoftDeleteMaterial,
} from '@/hooks/useMaterials'
import type { Material, MaterialCreate, MaterialUpdate } from '@/types/inventory'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

export default function MaterialsPage() {
  const navigate = useNavigate()
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editing, setEditing] = useState<Material | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Material | null>(null)
  const [search, setSearch] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)

  const { data: materials, isLoading } = useMaterials({
    search: search.trim() || undefined,
    includeInactive,
  })
  const createMaterial = useCreateMaterial()
  const updateMaterial = useUpdateMaterial()
  const softDelete = useSoftDeleteMaterial()

  const handleSave = async (payload: MaterialCreate | MaterialUpdate) => {
    if (editing) {
      await updateMaterial.mutateAsync({ id: editing.id, data: payload as MaterialUpdate })
    } else {
      await createMaterial.mutateAsync(payload as MaterialCreate)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    await softDelete.mutateAsync(deleteTarget.id)
    setDeleteTarget(null)
  }

  return (
    <ShellPage
      title="Materials"
      description="Direct materials catalog. Bills of Materials and per-Order COGS land in later sprints."
    >
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-zinc-900/20 p-6 rounded-3xl border border-zinc-800/50 backdrop-blur-sm">
          <div className="flex items-center gap-3 flex-1 max-w-md">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-zinc-500 pointer-events-none" />
              <Input
                placeholder="Search materials..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 border-zinc-800 bg-zinc-900/50"
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-zinc-400 whitespace-nowrap cursor-pointer">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(e) => setIncludeInactive(e.target.checked)}
                className="size-4 rounded border-zinc-700 bg-zinc-900 accent-teal-500"
              />
              Show archived
            </label>
          </div>
          <Button
            onClick={() => {
              setEditing(null)
              setIsFormOpen(true)
            }}
            className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg shadow-teal-900/20"
          >
            <Plus className="size-4 mr-2" />
            New Material
          </Button>
        </div>

        <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
          <CardContent className="p-0">
            <Table>
              <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                <TableRow className="border-none hover:bg-transparent">
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-5">
                    Name
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">
                    Unit
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">
                    Currency
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">
                    Stock
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">
                    Supplier
                  </TableHead>
                  <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">
                    Status
                  </TableHead>
                  <TableHead className="text-right text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-5">
                    Actions
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  [1, 2, 3].map((i) => (
                    <TableRow key={i} className="border-b border-white/[0.02]">
                      <TableCell className="px-8 py-6">
                        <Skeleton className="h-5 w-48 bg-zinc-800" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-12 bg-zinc-800" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-12 bg-zinc-800" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-20 bg-zinc-800" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-32 bg-zinc-800" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-16 bg-zinc-800" />
                      </TableCell>
                      <TableCell className="px-8 py-6">
                        <Skeleton className="h-5 w-16 ml-auto bg-zinc-800" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : materials?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="h-60 text-center">
                      <div className="flex flex-col items-center justify-center gap-3">
                        <Layers className="size-10 text-zinc-800" />
                        <p className="text-sm text-zinc-500 italic">
                          No materials registered yet.
                        </p>
                        <Button
                          variant="outline"
                          onClick={() => {
                            setEditing(null)
                            setIsFormOpen(true)
                          }}
                          className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 mt-2"
                        >
                          <Plus className="size-4 mr-2" />
                          Register your first material
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  materials?.map((item) => {
                    const thresholdNum = Number(item.low_stock_threshold)
                    const stockNum = Number(item.stock_quantity)
                    const isLowStock = thresholdNum > 0 && stockNum <= thresholdNum
                    return (
                    <TableRow
                      key={item.id}
                      onClick={() => navigate(`/inventory/materials/${item.id}`)}
                      className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors group cursor-pointer"
                    >
                      <TableCell className="px-8 py-6">
                        <div className="flex flex-col">
                          <p className="text-sm font-bold text-zinc-100 tracking-tight">
                            {item.name}
                          </p>
                          {item.notes && (
                            <span className="text-[10px] text-zinc-500 truncate max-w-md">
                              {item.notes}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs font-mono text-zinc-300">{item.unit}</span>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs font-mono text-zinc-300">{item.currency}</span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              'text-xs font-mono tabular-nums',
                              isLowStock ? 'text-amber-400 font-bold' : 'text-zinc-200',
                            )}
                          >
                            {item.stock_quantity} {item.unit}
                          </span>
                          {isLowStock && (
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
                        <span className="text-xs text-zinc-400">
                          {item.supplier_name || <span className="text-zinc-700">—</span>}
                        </span>
                      </TableCell>
                      <TableCell>
                        {item.is_active ? (
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
                      </TableCell>
                      <TableCell className="px-8 py-6 text-right">
                        <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.05] rounded-xl"
                            onClick={(e) => {
                              e.stopPropagation()
                              setEditing(item)
                              setIsFormOpen(true)
                            }}
                            title="Edit"
                          >
                            <Edit2 className="h-3.5 w-3.5" />
                          </Button>
                          {item.is_active && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-zinc-600 hover:text-amber-400 hover:bg-amber-400/10 rounded-xl"
                              onClick={(e) => {
                                e.stopPropagation()
                                setDeleteTarget(item)
                              }}
                              title="Archive"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
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

      <MaterialFormModal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        onSave={handleSave}
        initialData={editing}
        isLoading={createMaterial.isPending || updateMaterial.isPending}
      />

      <ConfirmSoftDeleteModal
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
        entityName={deleteTarget?.name || ''}
        entityType="Material"
        isLoading={softDelete.isPending}
      />
    </ShellPage>
  )
}
