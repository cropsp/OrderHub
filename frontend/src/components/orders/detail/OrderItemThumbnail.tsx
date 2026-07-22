import { useEffect, useMemo } from 'react';
import { ImageIcon } from 'lucide-react';

import { useProductImage } from '@/hooks/useProducts';
import { Skeleton } from '@/components/ui/skeleton';
import type { OrderItem } from '@/types/common';

interface OrderItemThumbnailProps {
  item: OrderItem;
}

/**
 * Small product thumbnail for an order item (ORDER-CARD-1 Part 2), reusing the
 * PC-F-1 image pipeline: the same authenticated-blob → object-URL fetch and the
 * shared `['product-image', id]` cache as the inventory ProductImageWidget.
 * Neutral placeholder when the item has no linked product image — custom lines,
 * or a product whose image hasn't been pulled yet.
 */
export function OrderItemThumbnail({ item }: OrderItemThumbnailProps) {
  const hasImage = !!item.image_url;
  const { data: blob, isLoading } = useProductImage(item.product_id ?? undefined, hasImage);

  // The image arrives as an authenticated blob (a bare <img src> would 401),
  // so it needs an object URL, revoked on change/unmount to avoid a leak.
  const objectUrl = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [objectUrl]);

  return (
    <div className="size-10 shrink-0 overflow-hidden rounded-md border border-zinc-800 bg-zinc-900/60">
      {hasImage && isLoading ? (
        <Skeleton className="size-full" />
      ) : objectUrl ? (
        <img src={objectUrl} alt={item.title} className="size-full object-cover" />
      ) : (
        <div className="flex size-full items-center justify-center text-zinc-700">
          <ImageIcon className="size-4" />
        </div>
      )}
    </div>
  );
}
