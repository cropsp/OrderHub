import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Archive, Edit2, Undo2 } from 'lucide-react'

import { useProduct, useUpdateProduct } from '@/hooks/useProducts'
import { useShops } from '@/hooks/useShops'
import ProductForm from '@/components/inventory/ProductForm'
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
import type { ProductUpdate, ProductVariant } from '@/types/inventory'

function fmtMoney(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (!isFinite(n)) return '—'
  return `$${n.toFixed(2)}`
}

function marginPercent(price: number | string | null | undefined, cost: number | string | null | undefined): number | null {
  const p = Number(price)
  const c = Number(cost)
  if (!isFinite(p) || !isFinite(c) || p <= 0 || c <= 0) return null
  return ((p - c) / p) * 100
}

function marginColorClass(margin: number) {
  if (margin >= 30) return 'text-emerald-400'
  if (margin >= 10) return 'text-amber-400'
  return 'text-red-400'
}

function stockColorClass(qty: number) {
  if (qty === 0) return 'text-red-400'
  if (qty < 5) return 'text-amber-400'
  return 'text-emerald-400'
}

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [isEditOpen, setIsEditOpen] = useState(false)

  const { data: product, isLoading, isError } = useProduct(id)
  const { data: shops } = useShops()
  const updateProduct = useUpdateProduct()

  if (!id) return null

  const shopName = shops?.find(s => s.id === product?.shop_id)?.name

  const handleArchiveToggle = () => {
    if (!product) return
    updateProduct.mutate({
      id: product.id,
      shopId: product.shop_id,
      data: { is_active: !product.is_active },
    })
  }

  const handleEditSave = async (data: unknown) => {
    if (!product) return
    await updateProduct.mutateAsync({
      id: product.id,
      shopId: product.shop_id,
      data: data as ProductUpdate,
    })
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      <nav className="border-b border-zinc-900 bg-zinc-950/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-3">
          <button
            onClick={() => navigate('/products')}
            className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500 hover:text-teal-400 transition-colors group cursor-pointer"
          >
            <ArrowLeft size={12} className="group-hover:-translate-x-1 transition-transform" />
            Back to Products
          </button>
        </div>
      </nav>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
          {isLoading ? (
            <div className="space-y-4">
              <Skeleton className="h-10 w-96 bg-zinc-800" />
              <Skeleton className="h-64 w-full bg-zinc-800" />
            </div>
          ) : isError || !product ? (
            <div className="flex flex-col items-center justify-center p-20 border-2 border-dashed border-zinc-800 rounded-3xl bg-zinc-900/5">
              <h3 className="text-lg font-bold text-zinc-300">Product not found</h3>
              <p className="text-sm text-zinc-500 mt-1 mb-4">
                This product may have been deleted or you may not have access.
              </p>
              <Link
                to="/products"
                className="text-xs font-bold uppercase tracking-widest text-teal-400 hover:text-teal-300"
              >
                Back to Products
              </Link>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  {shopName && (
                    <Badge
                      variant="outline"
                      className="border-l-2 border-teal-500 bg-teal-500/10 text-teal-400 text-[10px] font-bold uppercase tracking-widest"
                    >
                      {shopName}
                    </Badge>
                  )}
                  {product.is_active ? (
                    <Badge
                      variant="outline"
                      className="border-emerald-500/20 bg-emerald-500/5 text-emerald-400 text-[10px] font-bold uppercase tracking-widest"
                    >
                      Active
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="border-zinc-700 bg-zinc-800/40 text-zinc-400 text-[10px] font-bold uppercase tracking-widest"
                    >
                      Archived
                    </Badge>
                  )}
                </div>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">{product.title}</h1>
                    {product.description && (
                      <p className="text-sm text-zinc-500 mt-1">{product.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Button
                      variant="outline"
                      onClick={() => setIsEditOpen(true)}
                      className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
                    >
                      <Edit2 className="size-4 mr-2 text-teal-500" />
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleArchiveToggle}
                      disabled={updateProduct.isPending}
                      className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
                    >
                      {product.is_active ? (
                        <>
                          <Archive className="size-4 mr-2 text-amber-500" />
                          Archive
                        </>
                      ) : (
                        <>
                          <Undo2 className="size-4 mr-2 text-emerald-500" />
                          Restore
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </div>

              <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
                <CardContent className="p-0">
                  <Table>
                    <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                      <TableRow className="border-none hover:bg-transparent">
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-5">SKU</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Name</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Weight</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Dimensions</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Volume</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Price</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Cost</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Stock</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5 px-8">Margin %</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {product.variants.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={9} className="h-40 text-center">
                            <p className="text-sm text-zinc-500 italic">No variants defined.</p>
                          </TableCell>
                        </TableRow>
                      ) : (
                        product.variants.map((v: ProductVariant) => {
                          const margin = marginPercent(v.price, v.cost_price)
                          const volume = typeof v.volume_cm3 === 'number'
                            ? v.volume_cm3
                            : (v.length_mm * v.width_mm * v.height_mm) / 1000
                          const stock = Number(v.stock_quantity) || 0
                          return (
                            <TableRow
                              key={v.id}
                              className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors"
                            >
                              <TableCell className="px-8 py-5">
                                <code className="text-xs bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-300 border border-zinc-700">
                                  {v.sku || '—'}
                                </code>
                              </TableCell>
                              <TableCell className="text-xs text-zinc-300">{v.variant_name || '—'}</TableCell>
                              <TableCell className="text-xs text-zinc-400 font-mono">{v.weight_g}g</TableCell>
                              <TableCell className="text-xs text-zinc-400 font-mono">
                                {v.length_mm} × {v.width_mm} × {v.height_mm} mm
                              </TableCell>
                              <TableCell className="text-xs text-zinc-400 font-mono">
                                {volume.toFixed(2)} cm³
                              </TableCell>
                              <TableCell className="text-xs text-zinc-300 font-mono">{fmtMoney(v.price)}</TableCell>
                              <TableCell className="text-xs text-zinc-300 font-mono">{fmtMoney(v.cost_price)}</TableCell>
                              <TableCell>
                                <span className={`text-xs font-bold font-mono ${stockColorClass(stock)}`}>
                                  {stock}
                                </span>
                              </TableCell>
                              <TableCell className="px-8">
                                {margin === null ? (
                                  <span className="text-xs text-zinc-600">—</span>
                                ) : (
                                  <span className={`text-xs font-bold font-mono ${marginColorClass(margin)}`}>
                                    {margin.toFixed(1)}%
                                  </span>
                                )}
                              </TableCell>
                            </TableRow>
                          )
                        })
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </main>

      {product && (
        <ProductForm
          isOpen={isEditOpen}
          onClose={() => setIsEditOpen(false)}
          onSave={handleEditSave}
          initialData={product}
          isLoading={updateProduct.isPending}
        />
      )}
    </div>
  )
}
