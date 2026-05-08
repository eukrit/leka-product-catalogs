"use client"

import { useState } from "react"
import Link from "next/link"
import Image from "next/image"
import type { VendorTheme } from "@/lib/vendor-themes"
import { pickPrimaryImage } from "@/lib/image-scoring"

interface Product {
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

interface Props {
  product: Product
  brandSlug: string
  showPrice: boolean
  theme: VendorTheme
}

export function VendorProductCard({ product, brandSlug, showPrice, theme }: Props) {
  const variant = product.variants?.[0]
  const initialImage = pickPrimaryImage(product.thumbnail, product.images)
  const [imageUrl, setImageUrl] = useState<string | null>(initialImage)
  const onImgError = () => setImageUrl(null)
  const price =
    variant?.prices?.find((p) => p.currency_code === "usd") ||
    variant?.prices?.find((p) => p.currency_code === "nok")
  const meta = product.metadata || ({} as Record<string, unknown>)
  const specs = (meta.specifications || {}) as Record<string, unknown>
  const downloads = (meta.downloads || []) as Array<unknown>
  const isNew = product.tags?.some((t) => t.value === "new") || !!meta.is_new
  const seriesName =
    (meta.series_name as string) ||
    (meta.product_group as string) ||
    product.collection?.title
  const l = (variant?.length || (meta.length_cm as number) || 0) as number
  const w = (variant?.width || (meta.width_cm as number) || 0) as number
  const h = (variant?.height || (meta.height_cm as number) || 0) as number
  const dims = l && w ? `${l} × ${w}${h ? ` × ${h}` : ""} cm` : ""
  const { colors } = theme

  // ── Berliner Seilfabrik: industrial, left-accented border ──────────────
  if (brandSlug === "berliner") {
    return (
      <Link
        href={`/${brandSlug}/${product.handle}`}
        className="group block bg-white border border-gray-200 hover:border-gray-300 transition-colors overflow-hidden"
        style={{ borderLeft: `3px solid ${colors.accent}` }}
      >
        <div className="relative aspect-square bg-gray-50">
          {imageUrl ? (
            <Image
              src={imageUrl}
              alt={product.title}
              fill
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
              className="object-contain p-2 group-hover:scale-105 transition-transform duration-300"
              onError={onImgError}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-4xl text-gray-200">
              📦
            </div>
          )}
          {isNew && (
            <span
              className="absolute top-2 right-2 text-xs px-2 py-0.5 text-white font-bold uppercase tracking-wide"
              style={{ backgroundColor: colors.accent }}
            >
              NEW
            </span>
          )}
        </div>
        <div className="p-3 border-t border-gray-100">
          <div className="text-xs text-gray-400 font-mono">{variant?.sku}</div>
          <div
            className="text-sm font-semibold mt-0.5 line-clamp-2"
            style={{ color: colors.primary }}
          >
            {product.title}
          </div>
          {seriesName && (
            <div className="text-xs mt-1 font-medium" style={{ color: colors.accent }}>
              {seriesName}
            </div>
          )}
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-gray-400">{dims}</span>
            {downloads.length > 0 && (
              <span className="text-xs text-gray-400" title={`${downloads.length} downloads`}>
                📥 {downloads.length}
              </span>
            )}
          </div>
        </div>
      </Link>
    )
  }

  // ── Eurotramp: athletic, rounded, red underline on hover ────────────────
  if (brandSlug === "eurotramp") {
    return (
      <Link
        href={`/${brandSlug}/${product.handle}`}
        className="group block bg-white rounded-lg overflow-hidden border border-gray-100 hover:shadow-lg transition-shadow"
      >
        <div className="relative aspect-square bg-gray-50">
          {imageUrl ? (
            <Image
              src={imageUrl}
              alt={product.title}
              fill
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
              className="object-contain p-3 group-hover:scale-105 transition-transform duration-300"
              onError={onImgError}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-4xl text-gray-200">
              📦
            </div>
          )}
          <div
            className="absolute bottom-0 left-0 right-0 h-0.5 scale-x-0 group-hover:scale-x-100 transition-transform origin-left"
            style={{ backgroundColor: colors.accent }}
          />
          {isNew && (
            <span
              className="absolute top-2 left-2 text-xs px-2 py-0.5 text-white font-bold rounded"
              style={{ backgroundColor: colors.accent }}
            >
              NEW
            </span>
          )}
        </div>
        <div className="p-3">
          <div className="text-xs text-gray-400 font-mono">{variant?.sku}</div>
          <div
            className="text-sm font-semibold mt-0.5 line-clamp-2 transition-colors"
            style={{ color: colors.primary }}
          >
            {product.title}
          </div>
          {seriesName && <div className="text-xs text-gray-500 mt-1">{seriesName}</div>}
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-gray-400">{dims}</span>
            {showPrice && price && (
              <span className="text-sm font-semibold" style={{ color: colors.accent }}>
                ${(price.amount / 100).toFixed(2)}
              </span>
            )}
          </div>
        </div>
      </Link>
    )
  }

  // ── Rampline: Nordic minimal, full-bleed image, lime underline ──────────
  if (brandSlug === "rampline") {
    return (
      <Link
        href={`/${brandSlug}/${product.handle}`}
        className="group block overflow-hidden"
      >
        <div className="relative aspect-square bg-gray-200">
          {imageUrl ? (
            <Image
              src={imageUrl}
              alt={product.title}
              fill
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
              className="object-cover group-hover:scale-105 transition-transform duration-500"
              onError={onImgError}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-4xl text-gray-300">
              📦
            </div>
          )}
          {isNew && (
            <span
              className="absolute top-2 left-2 text-xs px-2 py-0.5 font-bold uppercase tracking-wide"
              style={{ backgroundColor: colors.accent, color: colors.accentContrast }}
            >
              New
            </span>
          )}
        </div>
        <div className="py-3 px-1 bg-white">
          <div className="text-xs text-gray-400 font-mono">{variant?.sku}</div>
          <div className="text-sm font-medium mt-0.5 line-clamp-2 text-gray-900">
            {product.title}
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-gray-400">{dims}</span>
            {showPrice && price && (
              <span className="text-sm font-semibold text-gray-900">
                kr {(price.amount / 100).toFixed(0)}
              </span>
            )}
          </div>
        </div>
        <div
          className="h-0.5 scale-x-0 group-hover:scale-x-100 transition-transform origin-left"
          style={{ backgroundColor: colors.accent }}
        />
      </Link>
    )
  }

  // ── 4soft: playful, rounded, colorful pastel backgrounds ───────────────
  if (brandSlug === "4soft") {
    const cardBgs = ["#FFF0E6", "#E6F4FF", "#F0FFE6", "#F5E6FF", "#FFF8E6", "#E6FFF8"]
    const cardBg = cardBgs[product.id.charCodeAt(product.id.length - 1) % cardBgs.length]
    const ageGroup = (specs.age_group || meta.age_group) as string | undefined

    return (
      <Link
        href={`/${brandSlug}/${product.handle}`}
        className="group block rounded-2xl overflow-hidden hover:shadow-md transition-shadow border border-transparent hover:border-orange-100"
      >
        <div className="relative aspect-square" style={{ backgroundColor: cardBg }}>
          {imageUrl ? (
            <Image
              src={imageUrl}
              alt={product.title}
              fill
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
              className="object-contain p-3 group-hover:scale-105 transition-transform duration-300"
              onError={onImgError}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-4xl">🎪</div>
          )}
          {isNew && (
            <span
              className="absolute top-2 right-2 text-xs px-2 py-0.5 text-white font-bold rounded-full"
              style={{ backgroundColor: colors.accent }}
            >
              NEW
            </span>
          )}
        </div>
        <div className="p-3 bg-white">
          <div className="text-xs text-gray-400 font-mono">{variant?.sku}</div>
          <div className="text-sm font-semibold mt-0.5 line-clamp-2 text-gray-900 group-hover:text-orange-500 transition-colors">
            {product.title}
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            {ageGroup && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                {String(ageGroup)}
              </span>
            )}
            {seriesName && (
              <span
                className="text-xs px-2 py-0.5 rounded-full text-white font-medium"
                style={{ backgroundColor: colors.accent }}
              >
                {seriesName}
              </span>
            )}
          </div>
        </div>
      </Link>
    )
  }

  // ── Vortex Aquatics: aquatic, cyan accent, deep navy text ──────────────
  if (brandSlug === "vortex") {
    return (
      <Link
        href={`/${brandSlug}/${product.handle}`}
        className="group block bg-white rounded-lg overflow-hidden border border-gray-100 hover:shadow-md transition-shadow"
      >
        <div className="relative aspect-square bg-gradient-to-br from-cyan-50 to-blue-50">
          {imageUrl ? (
            <Image
              src={imageUrl}
              alt={product.title}
              fill
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
              className="object-contain p-3 group-hover:scale-105 transition-transform duration-300"
              onError={onImgError}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-4xl text-cyan-200">
              💦
            </div>
          )}
          {isNew && (
            <span
              className="absolute top-2 right-2 text-xs px-2 py-0.5 font-bold rounded"
              style={{ backgroundColor: colors.accent, color: colors.accentContrast }}
            >
              NEW
            </span>
          )}
        </div>
        <div className="p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-gray-400 font-mono truncate">{variant?.sku}</div>
            {seriesName && (
              <div
                className="text-xs truncate max-w-[60%]"
                style={{ color: colors.accent }}
                title={seriesName}
              >
                {seriesName}
              </div>
            )}
          </div>
          <div
            className="text-sm font-semibold mt-0.5 line-clamp-2"
            style={{ color: colors.primary }}
          >
            {product.title}
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-gray-400">{dims}</span>
            {showPrice && price && (
              <span className="text-sm font-semibold" style={{ color: colors.primary }}>
                ${(price.amount / 100).toFixed(2)}
              </span>
            )}
          </div>
        </div>
      </Link>
    )
  }

  return null
}
