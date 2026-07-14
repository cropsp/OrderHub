import { useEffect, useMemo, useRef } from 'react'
import { Download, ImageIcon, Trash2, Upload } from 'lucide-react'

import {
  useDeleteProductImage,
  useProductImage,
  usePullProductImageFromShopify,
  useUploadProductImage,
} from '@/hooks/useProducts'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useToastStore } from '@/components/ui/Toast'
import type { Product } from '@/types/inventory'

const ACCEPT = 'image/jpeg,image/png,image/webp'
const MAX_BYTES = 5 * 1024 * 1024 // keep in sync with PRODUCT_IMAGE_MAX_BYTES (backend)

type Props = {
  product: Product
  /** Shopify-sourced products get a "Pull from Shopify" action; others don't. */
  isShopify: boolean
}

export default function ProductImageWidget({ product, isShopify }: Props) {
  const addToast = useToastStore(s => s.addToast)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const hasImage = !!product.image_url
  const { data: blob, isLoading } = useProductImage(product.id, hasImage)
  const uploadImage = useUploadProductImage()
  const deleteImage = useDeleteProductImage()
  const pullImage = usePullProductImageFromShopify()

  // The image arrives as an authenticated blob (a bare <img src> would 401),
  // so it needs an object URL, revoked on change/unmount to avoid a leak.
  const objectUrl = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob])
  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [objectUrl])

  const isBusy = uploadImage.isPending || deleteImage.isPending || pullImage.isPending

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-picking the same file after a failure
    if (!file) return
    if (file.size > MAX_BYTES) {
      addToast('Image exceeds maximum size of 5 MB', 'error')
      return
    }
    uploadImage.mutate({ id: product.id, shopId: product.shop_id, file })
  }

  return (
    <Card className="border-zinc-800 bg-zinc-950/40">
      <CardContent className="flex items-start gap-6 p-6">
        <div className="size-32 flex-shrink-0 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
          {hasImage && isLoading ? (
            <Skeleton className="size-full" />
          ) : objectUrl ? (
            <img
              src={objectUrl}
              alt={product.title}
              className="size-full object-cover"
            />
          ) : (
            <div
              data-testid="product-image-placeholder"
              className="flex size-full flex-col items-center justify-center gap-1 text-zinc-600"
            >
              <ImageIcon className="size-7" />
              <span className="text-[10px] font-bold uppercase tracking-widest">No image</span>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-zinc-300">
              Product Image
            </p>
            <p className="mt-1 text-[11px] text-zinc-500">
              JPEG, PNG or WebP · up to 5 MB
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              onChange={handleFileChange}
              className="hidden"
              data-testid="product-image-input"
            />
            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={isBusy}
              className="border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
            >
              <Upload className="mr-2 size-4 text-teal-400" />
              {hasImage ? 'Replace' : 'Upload'}
            </Button>

            {isShopify && (
              <Button
                variant="outline"
                onClick={() => pullImage.mutate({ id: product.id, shopId: product.shop_id })}
                disabled={isBusy}
                className="border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
              >
                <Download className="mr-2 size-4 text-teal-400" />
                Pull from Shopify
              </Button>
            )}

            {hasImage && (
              <Button
                variant="ghost"
                onClick={() => deleteImage.mutate({ id: product.id, shopId: product.shop_id })}
                disabled={isBusy}
                className="text-zinc-400 hover:bg-white/[0.02] hover:text-red-400"
              >
                <Trash2 className="mr-2 size-4" />
                Remove
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
