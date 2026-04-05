import Link from "next/link"
import Image from "next/image"

interface ProductCardProps {
  product: {
    id: string
    title: string
    handle: string
    thumbnail: string | null
    images: Array<{ url: string }>
    metadata: Record<string, unknown>
    collection: { title: string; handle: string } | null
    tags: Array<{ value: string }>
    variants: Array<{
      sku: string
      prices: Array<{ amount: number; currency_code: string }>
      length: number | null
      width: number | null
      height: number | null
    }>
  }
  brandSlug: string
  showPrice: boolean
}

export function ProductCard({ product, brandSlug, showPrice }: ProductCardProps) {
  const variant = product.variants?.[0]
  const imageUrl = product.thumbnail || product.images?.[0]?.url
  const price = variant?.prices?.find((p) => p.currency_code === "usd")
  const specs = (product.metadata?.specifications || {}) as Record<string, unknown>
  const isNew = product.tags?.some((t) => t.value === "new")
  const seriesName = (product.metadata?.series_name as string) || product.collection?.title

  const dims =
    variant?.length && variant?.width
      ? `${variant.length} x ${variant.width}${variant.height ? ` x ${variant.height}` : ""} cm`
      : ""

  return (
    <Link href={`/${brandSlug}/${product.handle}`} className="card group">
      {/* Image */}
      <div className="relative aspect-square bg-gray-50 overflow-hidden">
        {imageUrl ? (
          <Image
            src={imageUrl}
            alt={product.title}
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
            className="object-contain p-2 group-hover:scale-105 transition-transform"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-4xl text-gray-200">
            📦
          </div>
        )}
        {seriesName && (
          <span className="absolute top-2 left-2 badge badge-navy text-xs px-2 py-0.5">
            {seriesName}
          </span>
        )}
        {isNew && (
          <span className="absolute top-2 right-2 badge badge-amber text-xs px-2 py-0.5">
            NEW
          </span>
        )}
      </div>

      {/* Body */}
      <div className="p-3">
        <div className="text-xs text-gray-400 font-mono">{variant?.sku}</div>
        <div className="text-sm font-semibold text-leka-navy mt-0.5 line-clamp-2 group-hover:text-leka-purple transition-colors">
          {product.title}
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {specs.age_group && (
            <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
              {specs.age_group as string}
            </span>
          )}
          {specs.num_users && (
            <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
              {String(specs.num_users)} users
            </span>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="px-3 pb-3 flex items-center justify-between">
        <span className="text-xs text-gray-400">{dims}</span>
        {showPrice && price && (
          <span className="text-sm font-semibold text-leka-purple">
            ${(price.amount / 100).toFixed(2)}
          </span>
        )}
      </div>
    </Link>
  )
}
