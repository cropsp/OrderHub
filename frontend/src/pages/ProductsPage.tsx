import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, FileSpreadsheet, Search, Filter, Edit2, Trash2, Package, Layers, Archive, CheckCircle2, Columns3 } from 'lucide-react'
import ShellPage from './ShellPage'
import { formatMoney } from '@/lib/format'
import ShopSelector from '@/components/inventory/ShopSelector'
import ProductForm from '@/components/inventory/ProductForm'
import CSVImportModal from '@/components/inventory/CSVImportModal'
import { useProducts, useCreateProduct, useUpdateProduct, useDeleteProduct } from '@/hooks/useProducts'
import { useShops } from '@/hooks/useShops'
import { productsApi } from '@/api/products'
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
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuCheckboxItem,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { ProductVariant } from '@/types/inventory'

const TOGGLEABLE_COLUMNS = [
  { key: 'variants',    label: 'Variants' },
  { key: 'skus',        label: 'SKUs' },
  { key: 'weightRange', label: 'Weight Range' },
  { key: 'priceRange',  label: 'Price Range' },
  { key: 'stock',       label: 'Stock' },
  { key: 'status',      label: 'Status' },
] as const

type ColumnKey = typeof TOGGLEABLE_COLUMNS[number]['key']
type Visibility = Record<ColumnKey, boolean>

const DEFAULT_VISIBILITY: Visibility = {
  variants: true,
  skus: true,
  weightRange: true,
  priceRange: true,
  stock: true,
  status: true,
}

const STORAGE_KEY = 'orderhub:productsTable:columnVisibility'
const SHOP_KEY = 'orderhub:productsPage:lastShopId'


export default function ProductsPage() {
  const navigate = useNavigate()
  const [selectedShopId, setSelectedShopId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(SHOP_KEY)
    } catch {
      return null
    }
  })
  const [searchQuery, setSearchQuery] = useState('')
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isImportOpen, setIsImportOpen] = useState(false)
  const [editingProduct, setEditingProduct] = useState<any>(null)
  const [viewMode, setViewMode] = useState<'active' | 'archived'>('active')
  const [visibility, setVisibility] = useState<Visibility>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return DEFAULT_VISIBILITY
      const parsed = JSON.parse(raw)
      return { ...DEFAULT_VISIBILITY, ...parsed }
    } catch {
      return DEFAULT_VISIBILITY
    }
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(visibility))
  }, [visibility])

  const { data: shops } = useShops()

  const effectiveShopId = useMemo(() => {
    if (!shops || !selectedShopId) return null
    return shops.some(s => s.id === selectedShopId) ? selectedShopId : null
  }, [shops, selectedShopId])

  const activeShop = useMemo(
    () => shops?.find(s => s.id === effectiveShopId) ?? null,
    [shops, effectiveShopId]
  )
  const isManual = activeShop?.platform === 'manual'

  useEffect(() => {
    if (selectedShopId !== null) {
      localStorage.setItem(SHOP_KEY, selectedShopId)
    }
  }, [selectedShopId])

  const visibleColumnCount = 2 + Object.values(visibility).filter(Boolean).length

  const { data: products, isLoading } = useProducts(effectiveShopId || '', viewMode === 'active')
  const createProduct = useCreateProduct()
  const updateProduct = useUpdateProduct()
  const deleteProduct = useDeleteProduct()

  const filteredProducts = (products || []).filter(p => 
    p.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.variants.some((v: any) => v.sku?.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  const handleSave = async (data: any) => {
    if (!effectiveShopId) return
    if (editingProduct) {
      await updateProduct.mutateAsync({ id: editingProduct.id, shopId: effectiveShopId, data })
    } else {
      await createProduct.mutateAsync({ shopId: effectiveShopId, data })
    }
  }

  const handleDelete = (product: any) => {
    if (!effectiveShopId) return
    if (window.confirm(`Are you sure you want to archive "${product.title}"?`)) {
      deleteProduct.mutate({ id: product.id, shopId: effectiveShopId })
    }
  }

  const getWeightRange = (variants: any[]) => {
    if (!variants?.length) return '-'
    const weights = variants.map(v => v.weight_g)
    const min = Math.min(...weights)
    const max = Math.max(...weights)
    return min === max ? `${min}g` : `${min}g - ${max}g`
  }

  const getPriceRange = (variants: ProductVariant[]) => {
    if (!variants?.length) return '—'
    const prices = variants
      .map(v => (v.price === null || v.price === undefined || v.price === '' ? null : Number(v.price)))
      .filter((p): p is number => p !== null && isFinite(p))
    if (!prices.length) return '—'
    const min = Math.min(...prices)
    const max = Math.max(...prices)
    const fmt = (n: number) => formatMoney(n)
    return min === max ? fmt(min) : `${fmt(min)} – ${fmt(max)}`
  }

  const getTotalStock = (variants: ProductVariant[]) => {
    if (!variants?.length) return 0
    return variants.reduce((acc, v) => acc + (Number(v.stock_quantity) || 0), 0)
  }

  const stockColorClass = (qty: number) => {
    if (qty === 0) return 'text-red-400'
    if (qty < 5) return 'text-amber-400'
    return 'text-emerald-400'
  }

  return (
    <ShellPage
      title="Product Catalog"
      description="Manage product catalog and physical specifications."
    >
      <div className="space-y-6">
        {/* Header Actions */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-zinc-900/20 p-6 rounded-3xl border border-zinc-800/50 backdrop-blur-sm">
          <ShopSelector
            selectedShopId={selectedShopId}
            onShopChange={setSelectedShopId}
            manualOnly={false}
          />

          {isManual && (
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                onClick={() => setIsImportOpen(true)}
                disabled={!effectiveShopId}
                className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
              >
                <FileSpreadsheet className="size-4 mr-2 text-teal-500" />
                Bulk Import
              </Button>
              <Button
                onClick={() => { setEditingProduct(null); setIsFormOpen(true); }}
                disabled={!effectiveShopId}
                className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg shadow-teal-900/20"
              >
                <Plus className="size-4 mr-2" />
                Add Product
              </Button>
            </div>
          )}
        </div>

        {/* Content */}
        {!effectiveShopId ? (
          <div className="flex flex-col items-center justify-center p-20 border-2 border-dashed border-zinc-800 rounded-3xl bg-zinc-900/5">
             <div className="size-16 rounded-2xl bg-zinc-900 flex items-center justify-center mb-4">
                <Filter className="size-8 text-zinc-700" />
             </div>
             <h3 className="text-lg font-bold text-zinc-300">No shop selected</h3>
             <p className="text-sm text-zinc-400 mt-1">Please select a shop to view its product catalog.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Status tabs */}
            <div className="flex items-center gap-1 border-b border-zinc-800/60">
              <button
                type="button"
                onClick={() => setViewMode('active')}
                className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-widest border-b-2 transition-colors ${
                  viewMode === 'active'
                    ? 'border-teal-500 text-zinc-100'
                    : 'border-transparent text-zinc-400 hover:text-zinc-300'
                }`}
              >
                <CheckCircle2 className="size-3.5" />
                Active
              </button>
              <button
                type="button"
                onClick={() => setViewMode('archived')}
                className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-widest border-b-2 transition-colors ${
                  viewMode === 'archived'
                    ? 'border-teal-500 text-zinc-100'
                    : 'border-transparent text-zinc-400 hover:text-zinc-300'
                }`}
              >
                <Archive className="size-3.5" />
                Archived
              </button>
            </div>

            {/* Search & Stats */}
            <div className="flex items-center justify-between gap-4">
               <div className="relative flex-1 max-w-md">
                 <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-zinc-400" />
                 <Input 
                   placeholder="Search products or SKUs..." 
                   className="pl-10 border-zinc-800 bg-zinc-900/30"
                   value={searchQuery}
                   onChange={e => setSearchQuery(e.target.value)}
                 />
               </div>
               <div className="flex items-center gap-4">
                 <DropdownMenu>
                   <DropdownMenuTrigger asChild>
                     <Button
                       variant="outline"
                       size="sm"
                       className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
                     >
                       <Columns3 className="size-3.5 mr-2" />
                       Columns
                     </Button>
                   </DropdownMenuTrigger>
                   <DropdownMenuContent align="end" className="w-48">
                     <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
                     <DropdownMenuSeparator />
                     {TOGGLEABLE_COLUMNS.map(col => (
                       <DropdownMenuCheckboxItem
                         key={col.key}
                         checked={visibility[col.key]}
                         onCheckedChange={v =>
                           setVisibility(prev => ({ ...prev, [col.key]: !!v }))
                         }
                       >
                         {col.label}
                       </DropdownMenuCheckboxItem>
                     ))}
                   </DropdownMenuContent>
                 </DropdownMenu>
                 <div className="flex items-center gap-4 text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                    <div className="flex items-center gap-1.5">
                      <Package className="size-3" />
                      <span>{filteredProducts.length} Products</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Layers className="size-3" />
                      <span>{filteredProducts.reduce((acc, p) => acc + p.variants.length, 0)} Variants</span>
                    </div>
                 </div>
               </div>
            </div>

            {/* Table */}
            <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
              <CardContent className="p-0">
                <Table>
                  <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                    <TableRow className="border-none hover:bg-transparent">
                      <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-5">Product Title</TableHead>
                      {visibility.variants && <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Variants</TableHead>}
                      {visibility.skus && <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">SKUs</TableHead>}
                      {visibility.weightRange && <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Weight Range</TableHead>}
                      {visibility.priceRange && <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Price Range</TableHead>}
                      {visibility.stock && <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Stock</TableHead>}
                      {visibility.status && <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-5">Status</TableHead>}
                      <TableHead className="text-right text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-8 py-5">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isLoading ? (
                      [1, 2, 3].map(i => (
                        <TableRow key={i} className="border-b border-white/[0.02]">
                          <TableCell className="px-8 py-6"><Skeleton className="h-5 w-48 bg-zinc-800" /></TableCell>
                          {visibility.variants && <TableCell><Skeleton className="h-5 w-12 bg-zinc-800" /></TableCell>}
                          {visibility.skus && <TableCell><Skeleton className="h-5 w-32 bg-zinc-800" /></TableCell>}
                          {visibility.weightRange && <TableCell><Skeleton className="h-5 w-24 bg-zinc-800" /></TableCell>}
                          {visibility.priceRange && <TableCell><Skeleton className="h-5 w-24 bg-zinc-800" /></TableCell>}
                          {visibility.stock && <TableCell><Skeleton className="h-5 w-12 bg-zinc-800" /></TableCell>}
                          {visibility.status && <TableCell><Skeleton className="h-5 w-16 bg-zinc-800" /></TableCell>}
                          <TableCell className="px-8 py-6"><Skeleton className="h-5 w-16 ml-auto bg-zinc-800" /></TableCell>
                        </TableRow>
                      ))
                    ) : filteredProducts.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={visibleColumnCount} className="h-60 text-center">
                          <div className="flex flex-col items-center justify-center gap-3">
                            <Package className="size-10 text-zinc-800" />
                            <p className="text-sm text-zinc-400 italic">No products found matching your search.</p>
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredProducts.map((product) => (
                        <TableRow
                          key={product.id}
                          onClick={() => navigate(`/products/${product.id}`)}
                          className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors group cursor-pointer"
                        >
                          <TableCell className="px-8 py-6">
                            <div className="flex flex-col gap-1">
                               <p className="text-sm font-bold text-zinc-100 tracking-tight">{product.title}</p>
                               {product.description && (
                                 <p className="text-[10px] text-zinc-400 line-clamp-1">{product.description}</p>
                               )}
                            </div>
                          </TableCell>
                          {visibility.variants && (
                            <TableCell>
                              <Badge variant="outline" className="border-zinc-800 bg-zinc-900/50 text-zinc-400 font-mono text-[10px]">
                                {product.variants.length}
                              </Badge>
                            </TableCell>
                          )}
                          {visibility.skus && (
                            <TableCell>
                              <div className="flex flex-wrap gap-1">
                                 {product.variants.slice(0, 2).map((v: any) => (
                                   <code key={v.id} className="text-[9px] bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-400 border border-zinc-700">{v.sku}</code>
                                 ))}
                                 {product.variants.length > 2 && (
                                   <span className="text-[9px] text-zinc-600 font-bold">+{product.variants.length - 2} more</span>
                                 )}
                              </div>
                            </TableCell>
                          )}
                          {visibility.weightRange && (
                            <TableCell className="text-xs text-zinc-400 font-medium">
                              {getWeightRange(product.variants)}
                            </TableCell>
                          )}
                          {visibility.priceRange && (
                            <TableCell className="text-xs text-zinc-300 font-mono">
                              {getPriceRange(product.variants)}
                            </TableCell>
                          )}
                          {visibility.stock && (
                            <TableCell>
                              {(() => {
                                const qty = getTotalStock(product.variants)
                                return (
                                  <span className={`text-xs font-bold font-mono ${stockColorClass(qty)}`}>
                                    {qty}
                                  </span>
                                )
                              })()}
                            </TableCell>
                          )}
                          {visibility.status && (
                            <TableCell>
                              {product.is_active ? (
                                <Badge variant="outline" className="border-emerald-500/20 bg-emerald-500/5 text-emerald-400 text-[10px] font-bold uppercase tracking-widest">
                                  Active
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="border-zinc-700 bg-zinc-800/40 text-zinc-400 text-[10px] font-bold uppercase tracking-widest">
                                  Archived
                                </Badge>
                              )}
                            </TableCell>
                          )}
                          <TableCell className="px-8 py-6 text-right">
                            <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.05] rounded-xl"
                                onClick={(e) => { e.stopPropagation(); navigate(`/products/${product.id}`); }}
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-zinc-600 hover:text-red-400 hover:bg-red-400/10 rounded-xl"
                                onClick={(e) => { e.stopPropagation(); handleDelete(product); }}
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
        )}
      </div>

      {/* Modals */}
      <ProductForm 
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        onSave={handleSave}
        initialData={editingProduct}
        isLoading={createProduct.isPending || updateProduct.isPending}
      />

      <CSVImportModal 
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onPreview={(file) => productsApi.bulkImportPreview(effectiveShopId!, file)}
        onConfirm={(token) => productsApi.bulkImportConfirm(effectiveShopId!, token)}
        title="Import Products Catalog"
        description="Upload a CSV file to bulk-import products and variants into this shop."
        templateColumns={['title', 'sku', 'weight_g', 'length_mm', 'width_mm', 'height_mm']}
      />
    </ShellPage>
  )
}
