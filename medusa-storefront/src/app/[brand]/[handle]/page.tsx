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
  const meta = product.metadata || {} as Record<string, unknown>
  const specs = (meta.specifications || {}) as Record<string, unknown>
  // Downloads: handle both Wisdom format and vendor format
  const rawDownloads = (meta.downloads || []) as Array<Record<string, string>>
  const downloads = rawDownloads.map((d) => ({
    type: d.type || "",
    format: d.format || d.type || "",
    url: d.gcs_url || d.url || d.original_url || "",
    label: d.label || d.filename || d.type || "Download",
  }))
  const certifications = (meta.certifications || []) as string[]
  const seriesName = (meta.series_name as string) || (meta.product_group as string) || product.collection?.title
  const sourceUrl = (meta.source_url || meta.vendor_url) as string | undefined
  const price = variant?.prices?.find((p) => p.currency_code === "usd") || variant?.prices?.find((p) => p.currency_code === "nok")
  const priceCurrency = price?.currency_code?.toUpperCase() || "USD"
  const images = product.images || []

  // Build spec entries from both formats
  const specEntries = [
    ["Length", (variant?.length || meta.length_cm) ? `${variant?.length || meta.length_cm} cm` : null],
    ["Width", (variant?.width || meta.width_cm) ? `${variant?.width || meta.width_cm} cm` : null],
    ["Height", (variant?.height || meta.height_cm) ? `${variant?.height || meta.height_cm} cm` : null],
    ["Weight", (variant?.weight || meta.weight_kg) ? `${variant?.weight || meta.weight_kg} kg` : null],
    ["Age Group", specs.age_group || meta.age_group],
    ["Users", specs.num_users || meta.max_users],
    ["Safety Zone", specs.safety_zone_m2 ? `${specs.safety_zone_m2} m\u00B2` : null],
    ["Fall Height", (specs.free_fall_height_cm || meta.fall_height_cm) ? `${specs.free_fall_height_cm || meta.fall_height_cm} cm` : null],
    ["EN Standard", specs.en_standard],
    ["Materials", (meta.materials as string[])?.join(", ")],
    ["Country", meta.brand_country],
  ].filter(([, v]) => v != null && v !== "" && v !== "0 cm" && v !== "0 kg") as [string, string][]

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

          {price && price.amount > 0 ? (
            <div className="mt-4">
              <span className="text-3xl font-bold text-leka-purple">
                {priceCurrency === "NOK" ? "kr " : "$"}{(price.amount / 100).toFixed(2)}
              </span>
              <span className="text-sm text-gray-400 ml-2">FOB {priceCurrency}</span>
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
