import { useState, useEffect } from 'react'
import { Plus, Trash2, Box, Scale, Maximize2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

interface ProductFormProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: any) => Promise<void>
  initialData?: any
  isLoading?: boolean
}

const EMPTY_VARIANT = {
  sku: '',
  variant_name: '',
  weight_g: 0,
  length_mm: 0,
  width_mm: 0,
  height_mm: 0,
}

export default function ProductForm({
  isOpen,
  onClose,
  onSave,
  initialData,
  isLoading
}: ProductFormProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [variants, setVariants] = useState([EMPTY_VARIANT])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (initialData) {
      setTitle(initialData.title || '')
      setDescription(initialData.description || '')
      setVariants(initialData.variants || [EMPTY_VARIANT])
    } else {
      setTitle('')
      setDescription('')
      setVariants([EMPTY_VARIANT])
    }
  }, [initialData, isOpen])

  const addVariant = () => {
    setVariants([...variants, { ...EMPTY_VARIANT }])
  }

  const removeVariant = (index: number) => {
    if (variants.length <= 1) return
    setVariants(variants.filter((_, i) => i !== index))
  }

  const updateVariant = (index: number, field: string, value: any) => {
    const newVariants = [...variants]
    newVariants[index] = { ...newVariants[index], [field]: value }
    setVariants(newVariants)
  }

  const calculateVolume = (v: any) => {
    const vol = (v.length_mm * v.width_mm * v.height_mm) / 1000
    return isNaN(vol) ? 0 : vol.toFixed(2)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!title.trim()) {
      setError('Product title is required')
      return
    }

    if (variants.some(v => !v.sku.trim() || v.weight_g <= 0)) {
      setError('All variants must have a SKU and weight > 0')
      return
    }

    try {
      await onSave({ title, description, variants })
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save product')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader className="p-6 border-b border-zinc-800">
            <DialogTitle className="text-xl font-bold tracking-tight">
              {initialData ? 'Edit Product Catalog' : 'Add New Catalog Item'}
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Define the physical characteristics for automated logistics calculations.
            </DialogDescription>
          </DialogHeader>

          <div className="p-8 space-y-8 max-h-[60vh] overflow-y-auto custom-scrollbar">
            {/* Base Info */}
            <div className="grid grid-cols-1 gap-6">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Product Title</p>
                <Input 
                  className="border-zinc-800 bg-zinc-900/50" 
                  placeholder="e.g. Handmade Leather Wallet" 
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Internal Description (Optional)</p>
                <Textarea 
                  className="border-zinc-800 bg-zinc-900/50 resize-none" 
                  placeholder="Internal notes about the product..."
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                />
              </div>
            </div>

            <Separator className="bg-zinc-800" />

            {/* Variants Section */}
            <div className="space-y-6">
              <div className="flex items-center justify-between px-1">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-zinc-100 uppercase tracking-tight">Product Variants</h4>
                  <p className="text-[10px] text-zinc-500 font-medium">Physical specs used for parcel estimation</p>
                </div>
                <Button 
                  type="button" 
                  variant="outline" 
                  size="sm" 
                  onClick={addVariant}
                  className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-xs h-8"
                >
                  <Plus className="size-3 mr-2" /> Add Variant
                </Button>
              </div>

              <div className="space-y-4">
                {variants.map((v, i) => (
                  <div key={i} className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 space-y-6 group relative">
                    {variants.length > 1 && (
                      <Button 
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => removeVariant(i)}
                        className="absolute top-4 right-4 h-8 w-8 text-zinc-600 hover:text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">SKU / Reference</p>
                        <Input 
                          className="border-zinc-800 bg-zinc-900/50 font-mono text-xs" 
                          placeholder="LHW-BRN-M"
                          value={v.sku}
                          onChange={e => updateVariant(i, 'sku', e.target.value)}
                        />
                      </div>
                      <div className="space-y-2">
                        <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Variant Name (e.g. Brown / M)</p>
                        <Input 
                          className="border-zinc-800 bg-zinc-900/50" 
                          placeholder="Brown Leather, Medium Size"
                          value={v.variant_name}
                          onChange={e => updateVariant(i, 'variant_name', e.target.value)}
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-4 gap-4">
                      <div className="space-y-2">
                        <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                          <Scale className="size-3" />
                          <p className="text-[10px] font-bold uppercase tracking-widest">Weight (g)</p>
                        </div>
                        <Input 
                          type="number"
                          className="border-zinc-800 bg-zinc-900/50" 
                          value={v.weight_g}
                          onChange={e => updateVariant(i, 'weight_g', parseInt(e.target.value) || 0)}
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                          <Maximize2 className="size-3" />
                          <p className="text-[10px] font-bold uppercase tracking-widest">Length (mm)</p>
                        </div>
                        <Input 
                          type="number"
                          className="border-zinc-800 bg-zinc-900/50" 
                          value={v.length_mm}
                          onChange={e => updateVariant(i, 'length_mm', parseInt(e.target.value) || 0)}
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                          <Maximize2 className="size-3 rotate-90" />
                          <p className="text-[10px] font-bold uppercase tracking-widest">Width (mm)</p>
                        </div>
                        <Input 
                          type="number"
                          className="border-zinc-800 bg-zinc-900/50" 
                          value={v.width_mm}
                          onChange={e => updateVariant(i, 'width_mm', parseInt(e.target.value) || 0)}
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                          <Maximize2 className="size-3 -rotate-45" />
                          <p className="text-[10px] font-bold uppercase tracking-widest">Height (mm)</p>
                        </div>
                        <Input 
                          type="number"
                          className="border-zinc-800 bg-zinc-900/50" 
                          value={v.height_mm}
                          onChange={e => updateVariant(i, 'height_mm', parseInt(e.target.value) || 0)}
                        />
                      </div>
                    </div>

                    <div className="flex items-center gap-3 px-1">
                      <div className="flex items-center gap-2 bg-teal-500/5 border border-teal-500/10 rounded-full px-3 py-1">
                         <Box className="size-3 text-teal-400" />
                         <span className="text-[10px] font-bold text-teal-400 uppercase tracking-widest">Volume: {calculateVolume(v)} cm³</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-xs text-red-400">
                <AlertCircle className="size-4" />
                {error}
              </div>
            )}
          </div>

          <DialogFooter className="bg-zinc-900/30 p-6 border-t border-zinc-800">
            <Button 
              type="button" 
              variant="ghost" 
              onClick={onClose}
              className="text-zinc-400 hover:text-zinc-100"
            >
              Cancel
            </Button>
            <Button 
              type="submit" 
              disabled={isLoading}
              className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg"
            >
              {isLoading ? 'Saving...' : 'Save Catalog Item'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function AlertCircle(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}
