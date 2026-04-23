import { Store } from 'lucide-react'
import { useShops } from '@/hooks/useShops'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

interface ShopSelectorProps {
  selectedShopId: string | null
  onShopChange: (id: string) => void
  className?: string
}

export default function ShopSelector({ selectedShopId, onShopChange, className }: ShopSelectorProps) {
  const { data: shops, isLoading } = useShops()
  
  const manualShops = (shops || []).filter(s => s.platform === 'manual')

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className="flex items-center gap-2 text-zinc-500 whitespace-nowrap">
        <Store className="size-4" />
        <span className="text-xs font-bold uppercase tracking-wider">Active Shop:</span>
      </div>
      
      <Select 
        value={selectedShopId || ''} 
        onValueChange={onShopChange}
        disabled={isLoading || manualShops.length === 0}
      >
        <SelectTrigger className="w-[280px] border-zinc-800 bg-zinc-900/50 text-zinc-100">
          <SelectValue placeholder={isLoading ? "Loading shops..." : "Select a manual shop"} />
        </SelectTrigger>
        <SelectContent className="border-zinc-800 bg-zinc-950">
          {manualShops.map((shop) => (
            <SelectItem 
              key={shop.id} 
              value={shop.id}
              className="focus:bg-teal-500/10 focus:text-teal-400"
            >
              {shop.name}
            </SelectItem>
          ))}
          {manualShops.length === 0 && !isLoading && (
            <div className="p-2 text-xs text-zinc-500 text-center">
              No manual shops found.
            </div>
          )}
        </SelectContent>
      </Select>
    </div>
  )
}
