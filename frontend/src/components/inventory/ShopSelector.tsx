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
  /** When true (default), only MANUAL-platform shops are listed. Set false to list all platforms. */
  manualOnly?: boolean
}

export default function ShopSelector({
  selectedShopId,
  onShopChange,
  className,
  manualOnly = true,
}: ShopSelectorProps) {
  const { data: shops, isLoading } = useShops()

  const filteredShops = (shops || []).filter(s => manualOnly ? s.platform === 'manual' : true)

  const placeholder = isLoading
    ? 'Loading shops...'
    : manualOnly
      ? 'Select a manual shop'
      : 'Select a shop'
  const emptyText = manualOnly ? 'No manual shops found.' : 'No shops found.'

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className="flex items-center gap-2 text-zinc-400 whitespace-nowrap">
        <Store className="size-4" />
        <span className="text-xs font-bold uppercase tracking-wider">Active Shop:</span>
      </div>

      <Select
        value={selectedShopId || ''}
        onValueChange={onShopChange}
        disabled={isLoading || filteredShops.length === 0}
      >
        <SelectTrigger className="w-[280px] border-zinc-800 bg-zinc-900/50 text-zinc-100">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent className="border-zinc-800 bg-zinc-950">
          {filteredShops.map((shop) => (
            <SelectItem
              key={shop.id}
              value={shop.id}
              className="focus:bg-teal-500/10 focus:text-teal-400"
            >
              {shop.name}
            </SelectItem>
          ))}
          {filteredShops.length === 0 && !isLoading && (
            <div className="p-2 text-xs text-zinc-400 text-center">
              {emptyText}
            </div>
          )}
        </SelectContent>
      </Select>
    </div>
  )
}
