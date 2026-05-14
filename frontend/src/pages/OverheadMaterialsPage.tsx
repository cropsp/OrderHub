import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Edit2, Trash2, Layers, Search } from 'lucide-react'
import ShellPage from './ShellPage'
import OverheadMaterialFormModal from '@/components/inventory/OverheadMaterialFormModal'
import ConfirmSoftDeleteModal from '@/components/inventory/ConfirmSoftDeleteModal'
import {
  useOverheadMaterials,
  useCreateOverheadMaterial,
  useUpdateOverheadMaterial,
  useSoftDeleteOverheadMaterial,
} from '@/hooks/useOverheadMaterials'
import type {
  OverheadMaterial,
  OverheadMaterialCreate,
  OverheadMaterialUpdate,
} from '@/types/inventory'
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

export default function OverheadMaterialsPage() {
  const navigate = useNavigate()
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editing, setEditing] = useState<OverheadMaterial | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<OverheadMaterial | null>(null)
  const [search, setSearch] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)

  const { data: items, isLoading } = useOverheadMaterials({
    search: search.trim() || undefined,
    includeInactive,
  })
  const createItem = useCreateOverheadMaterial()
  const updateItem = useUpdateOverheadMaterial()
  const softDelete = useSoftDeleteOverheadMaterial()

  const handleSave = async (payload: OverheadMaterialCreate | OverheadMaterialUpdate) => {
    if (editing) {
      await updateItem.mutateAsync({ id: editing.id, data: payload as OverheadMaterialUpdate })
    } else {
      await createItem.mutateAsync(payload as OverheadMaterialCreate)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    await softDelete.mutateAsync(deleteTarget.id)
    setDeleteTarget(null)
  }

  return (
    <ShellPage
      title="Overhead Materials"
      description="Indirect consumables — threads, glue, sandpaper. Tracked as flat workshop expenses."
    >
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-zinc-900/20 p-6 rounded-3xl border border-zinc-800/50 backdrop-blur-sm">
          <div className="flex items-center gap-3 flex-1 max-w-md">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-zinc-500 pointer-events-none" />
              <Input
                placeholder="Search overhead materials..."
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
            New Overhead Material
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
                    Notes
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
                        <Skeleton className="h-5 w-16 bg-zinc-800" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-40 bg-zinc-800" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-16 bg-zinc-800" />
                      </TableCell>
                      <TableCell className="px-8 py-6">
                        <Skeleton className="h-5 w-16 ml-auto bg-zinc-800" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : items?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="h-60 text-center">
                      <div className="flex flex-col items-center justify-center gap-3">
                        <Layers className="size-10 text-zinc-800" />
                        <p className="text-sm text-zinc-500 italic">
                          No overhead materials registered yet.
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
                          Register your first overhead material
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  items?.map((item) => (
                    <TableRow
                      key={item.id}
                      onClick={() => navigate(`/inventory/overhead-materials/${item.id}`)}
                      className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors group cursor-pointer"
                    >
                      <TableCell className="px-8 py-6">
                        <p className="text-sm font-bold text-zinc-100 tracking-tight">
                          {item.name}
                        </p>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs font-mono text-zinc-300">{item.unit}</span>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-zinc-400 truncate block max-w-md">
                          {item.notes || <span className="text-zinc-700">—</span>}
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
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <OverheadMaterialFormModal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        onSave={handleSave}
        initialData={editing}
        isLoading={createItem.isPending || updateItem.isPending}
      />

      <ConfirmSoftDeleteModal
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
        entityName={deleteTarget?.name || ''}
        entityType="Overhead material"
        isLoading={softDelete.isPending}
      />
    </ShellPage>
  )
}
