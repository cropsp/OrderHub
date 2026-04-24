import { useState } from 'react'
import { Scale, Maximize2, Layers } from 'lucide-react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface PackagingFormProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: any) => Promise<void>
  initialData?: any
  isLoading?: boolean
}

export default function PackagingForm({
  isOpen,
  onClose,
  onSave,
  initialData,
  isLoading
}: PackagingFormProps) {
  const [name, setName] = useState(initialData?.name || '')
  const [type, setType] = useState<'BOX' | 'ENVELOPE'>(initialData?.packaging_type || 'BOX')
  const [length, setLength] = useState(initialData?.inner_length_mm || 0)
  const [width, setWidth] = useState(initialData?.inner_width_mm || 0)
  const [height, setHeight] = useState(initialData?.inner_height_mm || 0)
  const [maxWeight, setMaxWeight] = useState(initialData?.max_weight_g || 0)
  const [tareWeight, setTareWeight] = useState(initialData?.tare_weight_g || 0)
  const [maxThickness, setMaxThickness] = useState<number | null>(initialData?.max_thickness_mm || null)
  const [sortOrder, setSortOrder] = useState(initialData?.sort_order || 0)
  const [error, setError] = useState<string | null>(null)

  // Reset form state when the dialog opens or the target row changes.
  // Derives state during render (not inside an effect) to avoid cascading re-renders.
  const [resetKey, setResetKey] = useState({ isOpen, initialData })
  if (resetKey.isOpen !== isOpen || resetKey.initialData !== initialData) {
    setResetKey({ isOpen, initialData })
    setName(initialData?.name || '')
    setType(initialData?.packaging_type || 'BOX')
    setLength(initialData?.inner_length_mm || 0)
    setWidth(initialData?.inner_width_mm || 0)
    setHeight(initialData?.inner_height_mm || 0)
    setMaxWeight(initialData?.max_weight_g || 0)
    setTareWeight(initialData?.tare_weight_g || 0)
    setMaxThickness(initialData?.max_thickness_mm || null)
    setSortOrder(initialData?.sort_order || 0)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!name.trim()) {
      setError('Packaging name is required')
      return
    }

    const payload = {
      name,
      packaging_type: type,
      inner_length_mm: length,
      inner_width_mm: width,
      inner_height_mm: height,
      max_weight_g: maxWeight,
      tare_weight_g: tareWeight,
      max_thickness_mm: type === 'ENVELOPE' ? maxThickness : null,
      sort_order: sortOrder
    }

    try {
      await onSave(payload)
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save packaging')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader className="p-6 border-b border-zinc-800">
            <DialogTitle className="text-xl font-bold tracking-tight">
              {initialData ? 'Edit Packaging Specs' : 'Register New Packaging'}
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Configure internal dimensions and weight limits for automated parcel selection.
            </DialogDescription>
          </DialogHeader>

          <div className="p-8 space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Internal Name</p>
                <Input 
                  className="border-zinc-800 bg-zinc-900/50" 
                  placeholder="e.g. Standard Box M" 
                  value={name}
                  onChange={e => setName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Packaging Type</p>
                <Select value={type} onValueChange={(v: any) => setType(v)}>
                  <SelectTrigger className="border-zinc-800 bg-zinc-900/50">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-zinc-800 bg-zinc-950">
                    <SelectItem value="BOX">Rigid Box</SelectItem>
                    <SelectItem value="ENVELOPE">Soft Envelope</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                  <Maximize2 className="size-3" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">Length (mm)</p>
                </div>
                <Input 
                  type="number"
                  className="border-zinc-800 bg-zinc-900/50" 
                  value={length}
                  onChange={e => setLength(parseInt(e.target.value) || 0)}
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
                  value={width}
                  onChange={e => setWidth(parseInt(e.target.value) || 0)}
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
                  value={height}
                  onChange={e => setHeight(parseInt(e.target.value) || 0)}
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                  <Scale className="size-3" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">Max Weight (g)</p>
                </div>
                <Input 
                  type="number"
                  className="border-zinc-800 bg-zinc-900/50" 
                  value={maxWeight}
                  onChange={e => setMaxWeight(parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                  <Layers className="size-3" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">Tare Weight (g)</p>
                </div>
                <Input 
                  type="number"
                  className="border-zinc-800 bg-zinc-900/50" 
                  value={tareWeight}
                  onChange={e => setTareWeight(parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
                  <Maximize2 className="size-3 text-teal-500" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">Sort Order</p>
                </div>
                <Input 
                  type="number"
                  className="border-zinc-800 bg-zinc-900/50" 
                  value={sortOrder}
                  onChange={e => setSortOrder(parseInt(e.target.value) || 0)}
                />
              </div>
            </div>

            {type === 'ENVELOPE' && (
              <div className="p-4 rounded-2xl border border-teal-500/10 bg-teal-500/5 space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-teal-400">Envelope Specifics</p>
                <div className="flex items-center gap-4">
                  <div className="flex-1 space-y-1">
                    <p className="text-xs text-zinc-300 font-medium">Max Thickness (mm)</p>
                    <p className="text-[10px] text-zinc-500">Sum of item heights cannot exceed this limit. Leave empty for no limit.</p>
                  </div>
                  <Input 
                    type="number"
                    className="w-32 border-zinc-800 bg-zinc-900/50" 
                    placeholder="None"
                    value={maxThickness || ''}
                    onChange={e => setMaxThickness(e.target.value ? parseInt(e.target.value) : null)}
                  />
                </div>
              </div>
            )}

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
              {isLoading ? 'Saving...' : 'Save Packaging'}
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
