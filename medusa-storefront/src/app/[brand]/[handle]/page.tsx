"use client"

import { useEffect, useState } from "react"
import { use } from "react"
import Image from "next/image"
import Link from "next/link"
import { notFound } from "next/navigation"
import { medusa, getBrand } from "@/lib/medusa-client"
import { addToCart } from "@/lib/cart"

interface ProductDetail {
  id: string
  title: string
  handle: string
  description: string | null
  status: string
  thumbnail: string | null
  images: Array<{ id: string; url: string }>
  metadata: Record<string, unknown>
  categories: Array<{ id: string; name: string }>
  collection: { id: string; title: string } | null
  tags: Array<{ id: string; value: string }>
  variants: Array<{
    id: string
    sku: string
    prices: Array<{ amount: number; currency_code: string }>
    length: number | null
    width: number | null
    height: number | null
    weight: number | null
    metadata: Record<string, unknown>
  }>
}

export default function ProductDetailPage({
  params,
}: {
  params: Promise<{ brand: string; handle: string }>
}) {
  const { brand: brandSlug, handle } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  const [product, setProduct] = useState<ProductDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedImage, setSelectedImage] = useState(0)
  const [addingToCart, setAddingToCart] = useState(false)
  const [addedToCart, setAddedToCart] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const { products } = await medusa.store.product.list(
          {
            handle,
            fields: "+metadata,+categories,+collection,+tags,+variants,+variants.prices,+images",
          },
          { "x-publishable-api-key": brand!.publishableKey } as any
        ) as any
        if (products?.length > 0) {
          setProduct(products[0])
        }
      } catch (err) {
        console.error("Failed to load product:", err)
      }
      setLoading(false)
    }
    load()
  }, [handle, brand])

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
      </div>
    )
  }

  if (!product) {
    return notFound()
  }

  const variant = product.variants?.[0]
  const specs = (product.metadata?.specifications || {}) as Record<string, unknown>
  const downloads = (product.metadata?.downloads || []) as Array<{
    type: string
    format: string
    url: string
    label: string
  }>
  const certifications = (product.metadata?.certifications || []) as string[]
  const seriesName = (product.metadata?.series_name as string) || product.collection?.title
  const sourceUrl = product.metadata?.source_url as string | undefined
  const price = variant?.prices?.find((p) => p.currency_code === "usd")
  const images = product.images || []

  const specEntries = [
    ["Length", variant?.length ? `${variant.length} cm` : null],
    ["Width", variant?.width ? `${variant.width} cm` : null],
    ["Height", variant?.height ? `${variant.height} cm` : null],
    ["Weight", variant?.weight ? `${variant.weight} kg` : null],
    ["Age Group", specs.age_group],
    ["Users", specs.num_users],
    ["Safety Zone", specs.safety_zone_m2 ? `${specs.safety_zone_m2} m\u00B2` : null],
    ["Free Fall Height", specs.free_fall_height_cm ? `${specs.free_fall_height_cm} cm` : null],
    ["EN Standard", specs.en_standard],
    ["Spare Parts", specs.spare_parts_available],
  ].filter(([, v]) => v != null) as [string, string][]

  return (
    <main className="max-w-7xl mx-auto px-6 py-8">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-400 mb-6">
        <Link href={`/${brandSlug}`} className="hover:text-leka-purple">
          {brand.name}
        </Link>
        {seriesName && (
          <>
            <span className="mx-2">/</span>
            <span>{seriesName}</span>
          </>
        )}
        <span className="mx-2">/</span>
        <span className="text-leka-navy">{variant?.sku}</span>
      </nav>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
        {/* Images */}
        <div>
          <div className="relative aspect-square bg-white rounded-card overflow-hidden shadow-card">
            {images.length > 0 ? (
              <Image
                src={images[selectedImage].url}
                alt={product.title}
                fill
                className="object-contain p-4"
                priority
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-6xl text-gray-200">
                📦
              </div>
            )}
          </div>
          {images.length > 1 && (
            <div className="flex gap-2 mt-4 overflow-x-auto">
              {images.map((img, i) => (
                <button
                  key={img.id}
                  onClick={() => setSelectedImage(i)}
                  className={`relative w-16 h-16 rounded-button overflow-hidden border-2 flex-shrink-0 ${
                    i === selectedImage
                      ? "border-leka-purple"
                      : "border-gray-200"
                  }`}
                >
                  <Image
                    src={img.url}
                    alt={`View ${i + 1}`}
                    fill
                    className="object-contain p-1"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Product Info */}
        <div>
          <h1 className="text-2xl font-bold text-leka-navy">{product.title}</h1>
          <p className="text-sm text-gray-400 mt-1 font-mono">
            {seriesName && `${seriesName} \u00B7 `}{variant?.sku}
          </p>

          {price ? (
            <div className="mt-4">
              <span className="text-3xl font-bold text-leka-purple">
                ${(price.amount / 100).toFixed(2)}
              </span>
              <span className="text-sm text-gray-400 ml-2">FOB USD</span>
              <p className="text-xs text-gray-400 mt-1">
                Dealer & distributor pricing available.{" "}
                <Link href={`/${brandSlug}/account`} className="text-leka-purple hover:underline">
                  Sign in
                </Link>{" "}
                for your group price.
              </p>
            </div>
          ) : (
            <div className="mt-4">
              <p className="text-sm text-gray-500">
                Price available on request.{" "}
                <Link href={`/${brandSlug}/account`} className="text-leka-purple hover:underline">
                  Sign in
                </Link>{" "}
                or contact your account manager.
              </p>
            </div>
          )}

          {product.description && (
            <p className="mt-4 text-gray-600 leading-relaxed">
              {product.description}
            </p>
          )}

          {/* Add to Cart */}
          <div className="mt-6 flex gap-3">
            <button
              onClick={async () => {
                if (!variant?.id) return
                setAddingToCart(true)
                try {
                  await addToCart(brandSlug, variant.id, 1)
                  setAddedToCart(true)
                  setTimeout(() => setAddedToCart(false), 2000)
                } catch (err) {
                  console.error("Failed to add to cart:", err)
                }
                setAddingToCart(false)
              }}
              disabled={addingToCart}
              className="btn-primary flex-1 disabled:opacity-50"
            >
              {addingToCart ? "Adding..." : addedToCart ? "Added!" : "Add to Cart"}
            </button>
          </div>

          {/* Tags */}
          {product.tags?.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-4">
              {product.tags.map((tag) => (
                <span key={tag.id} className="badge badge-outline text-xs">
                  {tag.value}
                </span>
              ))}
            </div>
          )}

          {/* Specifications */}
          {specEntries.length > 0 && (
            <div className="mt-8">
              <h3 className="text-lg font-semibold text-leka-navy mb-3">
                Specifications
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {specEntries.map(([label, value]) => (
                  <div key={label} className="bg-gray-50 p-3 rounded-button">
                    <div className="text-xs text-gray-400">{label}</div>
                    <div className="text-sm font-semibold text-leka-navy mt-0.5">
                      {String(value)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Downloads */}
          {downloads.length > 0 && (
            <div className="mt-8">
              <h3 className="text-lg font-semibold text-leka-navy mb-3">
                Downloads
              </h3>
              <div className="flex flex-col gap-2">
                {downloads.map((dl, i) => (
                  <a
                    key={i}
                    href={dl.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 p-3 bg-gray-50 rounded-button hover:bg-gray-100 transition-colors"
                  >
                    <span className="text-lg">
                      {dl.format === "dwg" ? "\uD83D\uDCD0" : "\uD83D\uDCC4"}
                    </span>
                    <span className="text-sm font-medium text-leka-navy">
                      {dl.label}
                    </span>
                    <span className="text-xs text-gray-400 ml-auto uppercase">
                      {dl.format}
                    </span>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* Certifications */}
          {certifications.length > 0 && (
            <div className="mt-8">
              <h3 className="text-lg font-semibold text-leka-navy mb-3">
                Certifications
              </h3>
              <div className="flex flex-wrap gap-2">
                {certifications.map((cert, i) => (
                  <span
                    key={i}
                    className="px-3 py-1.5 bg-green-50 text-green-700 text-sm rounded-badge font-medium"
                  >
                    {cert}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* External link */}
          {sourceUrl && (
            <div className="mt-8">
              <a
                href={sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-leka-purple hover:underline"
              >
                View on manufacturer website &rarr;
              </a>
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
