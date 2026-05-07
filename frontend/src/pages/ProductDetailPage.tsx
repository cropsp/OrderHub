import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Archive, Plus, Save, Trash2, Undo2, X } from 'lucide-react'

import { useProduct, useUpdateProduct } from '@/hooks/useProducts'
import { useShops } from '@/hooks/useShops'
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
import { useToastStore } from '@/components/ui/Toast'
import type { Product, ProductUpdate, ProductVariantPatch } from '@/types/inventory'

type VariantDraft = {
  _key: string
  id?: string
  sku: string
  variant_name: string
  weight_g: string
  length_mm: string
  width_mm: string
  height_mm: string
  price: string
  cost_price: string
  stock_quantity: string
}

type ProductDraft = {
  title: string
  description: string
  variants: VariantDraft[]
}

function toStr(v: number | string | null | undefined): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

function buildDraft(product: Product): ProductDraft {
  return {
    title: product.title ?? '',
    description: product.description ?? '',
    variants: product.variants.map(v => ({
      _key: v.id,
      id: v.id,
      sku: toStr(v.sku),
      variant_name: toStr(v.variant_name),
      weight_g: toStr(v.weight_g),
      length_mm: toStr(v.length_mm),
      width_mm: toStr(v.width_mm),
      height_mm: toStr(v.height_mm),
      price: toStr(v.price),
      cost_price: toStr(v.cost_price),
      stock_quantity: toStr(v.stock_quantity),
    })),
  }
}

function marginPercent(price: string, cost: string): number | null {
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

function computeVolume(l: string, w: string, h: string): number | null {
  const L = Number(l)
  const W = Number(w)
  const H = Number(h)
  if (!isFinite(L) || !isFinite(W) || !isFinite(H) || L <= 0 || W <= 0 || H <= 0) return null
  return (L * W * H) / 1000
}

function newVariantKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `new-${crypto.randomUUID()}`
  }
  return `new-${Math.random().toString(36).slice(2)}-${Date.now()}`
}

function emptyVariant(): VariantDraft {
  return {
    _key: newVariantKey(),
    id: undefined,
    sku: '',
    variant_name: '',
    weight_g: '',
    length_mm: '',
    width_mm: '',
    height_mm: '',
    price: '',
    cost_price: '',
    stock_quantity: '0',
  }
}

const cellInputCls =
  'w-full bg-transparent border border-transparent rounded-md px-2 py-1 text-xs text-zinc-300 font-mono focus:outline-none focus:border-teal-500/40 focus:bg-zinc-900/40 hover:border-zinc-700/60 transition-colors'

const numericCellCls = `${cellInputCls} text-right`

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const addToast = useToastStore(s => s.addToast)

  const { data: product, isLoading, isError } = useProduct(id)
  const { data: shops } = useShops()
  const updateProduct = useUpdateProduct()

  const [draft, setDraft] = useState<ProductDraft | null>(null)
  const [original, setOriginal] = useState<string>('')
  const [syncedProductId, setSyncedProductId] = useState<string | undefined>(undefined)

  // Reset draft only when navigating to a different product. Background
  // refetches must not clobber in-progress edits, so we key on product.id
  // (not the full product reference). React's "adjust state during render"
  // pattern: https://react.dev/learn/you-might-not-need-an-effect
  if (product && product.id !== syncedProductId) {
    const d = buildDraft(product)
    setDraft(d)
    setOriginal(JSON.stringify(d))
    setSyncedProductId(product.id)
  }

  if (!id) return null

  const shopName = shops?.find(s => s.id === product?.shop_id)?.name
  const isDirty = draft !== null && JSON.stringify(draft) !== original

  const handleArchiveToggle = () => {
    if (!product) return
    updateProduct.mutate({
      id: product.id,
      shopId: product.shop_id,
      data: { is_active: !product.is_active },
    })
  }

  const updateField = <K extends keyof ProductDraft>(key: K, value: ProductDraft[K]) => {
    setDraft(d => (d ? { ...d, [key]: value } : d))
  }

  const updateVariant = (key: string, field: keyof VariantDraft, value: string) => {
    setDraft(d => {
      if (!d) return d
      return {
        ...d,
        variants: d.variants.map(v => (v._key === key ? { ...v, [field]: value } : v)),
      }
    })
  }

  const addVariant = () => {
    setDraft(d => (d ? { ...d, variants: [...d.variants, emptyVariant()] } : d))
  }

  const removeVariant = (key: string) => {
    // TODO: persist variant deletion (out of PC-B.1 scope). Existing variants
    // disappear locally but reappear after refetch since the backend doesn't
    // delete missing variants.
    setDraft(d => (d ? { ...d, variants: d.variants.filter(v => v._key !== key) } : d))
  }

  const handleCancel = () => {
    if (product) {
      const d = buildDraft(product)
      setDraft(d)
      setOriginal(JSON.stringify(d))
    }
  }

  const handleSave = async () => {
    if (!draft || !product) return

    for (const v of draft.variants) {
      const dims = [v.weight_g, v.length_mm, v.width_mm, v.height_mm]
      for (const x of dims) {
        const n = Number(x)
        if (!isFinite(n) || n <= 0 || !Number.isInteger(n)) {
          addToast('Each variant needs positive integer weight and dimensions', 'error')
          return
        }
      }
      if (v.price !== '' && !(Number(v.price) >= 0)) {
        addToast('Price must be ≥ 0', 'error')
        return
      }
      if (v.cost_price !== '' && !(Number(v.cost_price) >= 0)) {
        addToast('Cost must be ≥ 0', 'error')
        return
      }
      if (v.sku.length > 100) {
        addToast('SKU must be ≤ 100 characters', 'error')
        return
      }
    }

    const variants: ProductVariantPatch[] = draft.variants.map(v => {
      const patch: ProductVariantPatch = {
        weight_g: Number(v.weight_g),
        length_mm: Number(v.length_mm),
        width_mm: Number(v.width_mm),
        height_mm: Number(v.height_mm),
        sku: v.sku === '' ? null : v.sku,
        variant_name: v.variant_name === '' ? null : v.variant_name,
        price: v.price === '' ? null : Number(v.price),
        cost_price: v.cost_price === '' ? null : Number(v.cost_price),
        stock_quantity: v.stock_quantity === '' ? 0 : Number(v.stock_quantity),
      }
      if (v.id) patch.id = v.id
      return patch
    })

    const data: ProductUpdate = {
      title: draft.title,
      description: draft.description === '' ? null : draft.description,
      variants,
    }

    try {
      const saved = await updateProduct.mutateAsync({
        id: product.id,
        shopId: product.shop_id,
        data,
      })
      // Re-derive draft from response so newly created variants pick up their
      // server-generated ids; this also clears the dirty flag.
      const next = buildDraft(saved)
      setDraft(next)
      setOriginal(JSON.stringify(next))
    } catch {
      // Toast is already surfaced by the mutation hook.
    }
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
          {isLoading || !draft ? (
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
                  <div className="flex-1 min-w-0 space-y-1">
                    <input
                      type="text"
                      value={draft.title}
                      onChange={e => updateField('title', e.target.value)}
                      placeholder="Product title"
                      className="w-full bg-transparent text-2xl font-bold text-zinc-100 tracking-tight border border-transparent rounded-md px-2 py-1 -ml-2 focus:outline-none focus:border-teal-500/40 focus:bg-zinc-900/40 hover:border-zinc-800 transition-colors"
                    />
                    <textarea
                      value={draft.description}
                      onChange={e => updateField('description', e.target.value)}
                      placeholder="Description"
                      rows={2}
                      className="w-full bg-transparent text-sm text-zinc-400 border border-transparent rounded-md px-2 py-1 -ml-2 resize-none focus:outline-none focus:border-teal-500/40 focus:bg-zinc-900/40 hover:border-zinc-800 transition-colors"
                    />
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {isDirty && (
                      <>
                        <Button
                          variant="outline"
                          onClick={handleCancel}
                          disabled={updateProduct.isPending}
                          className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
                        >
                          <X className="size-4 mr-2 text-zinc-500" />
                          Cancel
                        </Button>
                        <Button
                          onClick={handleSave}
                          disabled={updateProduct.isPending}
                          className="bg-teal-500 hover:bg-teal-400 text-zinc-950 font-bold"
                        >
                          <Save className="size-4 mr-2" />
                          Save Changes
                        </Button>
                      </>
                    )}
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

              <div className="flex justify-end">
                <Button
                  variant="ghost"
                  onClick={addVariant}
                  className="text-zinc-400 hover:text-teal-400 hover:bg-white/[0.02]"
                >
                  <Plus className="size-4 mr-2" />
                  Add Variant
                </Button>
              </div>

              <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl overflow-hidden rounded-2xl">
                <CardContent className="p-0">
                  <Table>
                    <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                      <TableRow className="border-none hover:bg-transparent">
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-8 py-5">SKU</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Name</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Weight</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Dimensions (mm)</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Volume</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Price</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Cost</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Stock</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5">Margin %</TableHead>
                        <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-5 px-8 w-12"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {draft.variants.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={10} className="h-40 text-center">
                            <p className="text-sm text-zinc-500 italic">No variants yet. Click "Add Variant" to create one.</p>
                          </TableCell>
                        </TableRow>
                      ) : (
                        draft.variants.map(v => {
                          const margin = marginPercent(v.price, v.cost_price)
                          const volume = computeVolume(v.length_mm, v.width_mm, v.height_mm)
                          const stock = Number(v.stock_quantity) || 0
                          return (
                            <TableRow
                              key={v._key}
                              className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors"
                            >
                              <TableCell className="px-8 py-3 align-middle">
                                <input
                                  type="text"
                                  value={v.sku}
                                  onChange={e => updateVariant(v._key, 'sku', e.target.value)}
                                  placeholder="SKU"
                                  className={cellInputCls}
                                />
                              </TableCell>
                              <TableCell className="py-3 align-middle">
                                <input
                                  type="text"
                                  value={v.variant_name}
                                  onChange={e => updateVariant(v._key, 'variant_name', e.target.value)}
                                  placeholder="Name"
                                  className={cellInputCls}
                                />
                              </TableCell>
                              <TableCell className="py-3 align-middle">
                                <div className="flex items-center gap-1">
                                  <input
                                    type="number"
                                    min={1}
                                    step={1}
                                    value={v.weight_g}
                                    onChange={e => updateVariant(v._key, 'weight_g', e.target.value)}
                                    placeholder="g"
                                    className={`${numericCellCls} w-20`}
                                  />
                                  <span className="text-[10px] text-zinc-600">g</span>
                                </div>
                              </TableCell>
                              <TableCell className="py-3 align-middle">
                                <div className="flex items-center gap-1 font-mono text-zinc-600 text-xs">
                                  <input
                                    type="number"
                                    min={1}
                                    step={1}
                                    value={v.length_mm}
                                    onChange={e => updateVariant(v._key, 'length_mm', e.target.value)}
                                    placeholder="L"
                                    className={`${numericCellCls} w-16`}
                                  />
                                  <span>×</span>
                                  <input
                                    type="number"
                                    min={1}
                                    step={1}
                                    value={v.width_mm}
                                    onChange={e => updateVariant(v._key, 'width_mm', e.target.value)}
                                    placeholder="W"
                                    className={`${numericCellCls} w-16`}
                                  />
                                  <span>×</span>
                                  <input
                                    type="number"
                                    min={1}
                                    step={1}
                                    value={v.height_mm}
                                    onChange={e => updateVariant(v._key, 'height_mm', e.target.value)}
                                    placeholder="H"
                                    className={`${numericCellCls} w-16`}
                                  />
                                </div>
                              </TableCell>
                              <TableCell className="text-xs text-zinc-400 font-mono py-3 align-middle">
                                {volume === null ? '—' : `${volume.toFixed(2)} cm³`}
                              </TableCell>
                              <TableCell className="py-3 align-middle">
                                <input
                                  type="number"
                                  min={0}
                                  step={0.01}
                                  value={v.price}
                                  onChange={e => updateVariant(v._key, 'price', e.target.value)}
                                  placeholder="0.00"
                                  className={`${numericCellCls} w-24`}
                                />
                              </TableCell>
                              <TableCell className="py-3 align-middle">
                                <input
                                  type="number"
                                  min={0}
                                  step={0.01}
                                  value={v.cost_price}
                                  onChange={e => updateVariant(v._key, 'cost_price', e.target.value)}
                                  placeholder="0.00"
                                  className={`${numericCellCls} w-24`}
                                />
                              </TableCell>
                              <TableCell className="py-3 align-middle">
                                <input
                                  type="number"
                                  min={0}
                                  step={1}
                                  value={v.stock_quantity}
                                  onChange={e => updateVariant(v._key, 'stock_quantity', e.target.value)}
                                  className={`${numericCellCls} w-20 ${stockColorClass(stock)} font-bold`}
                                />
                              </TableCell>
                              <TableCell className="py-3 align-middle">
                                {margin === null ? (
                                  <span className="text-xs text-zinc-600 font-mono">—</span>
                                ) : (
                                  <span className={`text-xs font-bold font-mono ${marginColorClass(margin)}`}>
                                    {margin.toFixed(1)}%
                                  </span>
                                )}
                              </TableCell>
                              <TableCell className="px-8 py-3 align-middle">
                                <button
                                  type="button"
                                  onClick={() => removeVariant(v._key)}
                                  className="text-zinc-600 hover:text-red-400 transition-colors p-1 rounded"
                                  aria-label="Remove variant"
                                >
                                  <Trash2 className="size-3.5" />
                                </button>
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
    </div>
  )
}
