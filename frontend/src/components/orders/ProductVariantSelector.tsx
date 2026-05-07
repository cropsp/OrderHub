import { useState, useEffect, useMemo, useRef } from 'react';
import { Search, Package, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { useProducts } from '@/hooks/useProducts';

type Variant = {
  id: string;
  sku: string | null;
  variant_name: string | null;
  price: number | string | null;
  product_title: string;
};

type ProductVariantSelectorProps = {
  shopId: string;
  value: string;
  onChange: (value: string, variantId?: string, price?: number) => void;
  className?: string;
};

export function ProductVariantSelector({ 
  shopId, 
  value, 
  onChange, 
  className 
}: ProductVariantSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const { data: products = [], isLoading: loading, isError } = useProducts(shopId);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Filter variants based on search text — pure derivation, no effect needed.
  const filteredVariants = useMemo<Array<Variant & { productId: string }>>(() => {
    if (!value) return [];

    const search = value.toLowerCase();
    const matches: Array<Variant & { productId: string }> = [];

    products.forEach(p => {
      p.variants.forEach(v => {
        const titleMatch = p.title.toLowerCase().includes(search);
        const variantMatch = v.variant_name?.toLowerCase().includes(search);
        const skuMatch = v.sku?.toLowerCase().includes(search);

        if (titleMatch || variantMatch || skuMatch) {
          matches.push({
            ...v,
            product_title: p.title,
            productId: p.id
          });
        }
      });
    });

    return matches.slice(0, 10); // Limit to 10
  }, [value, products]);

  const handleSelect = (v: Variant) => {
    const title = v.variant_name ? `${v.product_title} (${v.variant_name})` : v.product_title;
    const priceNum = v.price != null ? Number(v.price) : NaN;
    onChange(title, v.id, Number.isFinite(priceNum) && priceNum > 0 ? priceNum : undefined);
    setIsOpen(false);
  };

  return (
    <div ref={wrapperRef} className={cn("relative", className)}>
      <div className="relative">
        <Input 
          className="h-9 pr-9 border-zinc-800 bg-zinc-900/40 rounded-lg text-zinc-100 focus-visible:ring-teal-500/30 focus-visible:border-teal-500/50"
          placeholder="Search catalog or type manually..."
          value={value}
          onChange={e => {
            onChange(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
        />
        <div className="absolute right-3 top-2.5 text-zinc-500">
          {loading ? (
            <Loader2 className="size-4 animate-spin text-teal-500" />
          ) : (
            <Search className="size-4" />
          )}
        </div>
      </div>

      {isOpen && (value.length > 0 || loading) && (
        <div className="absolute z-50 mt-1 w-full max-h-60 overflow-auto rounded-xl border border-zinc-800 bg-zinc-950/95 p-1.5 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-200">
          {loading ? (
            <div className="flex items-center justify-center py-6 text-xs text-zinc-500">
               <Loader2 className="mr-2 size-3 animate-spin" />
               Searching Catalog...
            </div>
          ) : isError ? (
            <div className="py-6 text-center text-xs text-rose-400/80">
               Failed to load catalog — try again.
            </div>
          ) : filteredVariants.length > 0 ? (
            <div className="space-y-1">
              {filteredVariants.map(v => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => handleSelect(v)}
                  className="flex w-full items-start gap-3 rounded-lg p-2.5 text-left transition-all hover:bg-zinc-900 group"
                >
                  <div className="mt-0.5 rounded-md bg-zinc-900 p-1.5 text-zinc-400 group-hover:bg-teal-500/10 group-hover:text-teal-400">
                    <Package className="size-4" />
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <div className="flex items-center justify-between gap-2">
                       <span className="truncate text-xs font-semibold text-zinc-200 group-hover:text-teal-400">
                          {v.product_title}
                       </span>
                       {v.price && (
                         <span className="text-[10px] font-bold text-teal-500/80">
                           ${v.price}
                         </span>
                       )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                       {v.variant_name && (
                         <span className="text-[10px] text-zinc-500 group-hover:text-zinc-400">
                           {v.variant_name}
                         </span>
                       )}
                       {v.sku && (
                         <span className="text-[10px] font-mono text-zinc-600 bg-zinc-900 px-1 rounded">
                           {v.sku}
                         </span>
                       )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : !shopId ? (
            <div className="py-6 text-center text-xs text-amber-500/80">
               Please select a shop first to search catalog.
            </div>
          ) : (
            <div className="py-6 text-center text-xs text-zinc-600">
               No matches found. Using manual entry.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
