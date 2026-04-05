"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { use } from "react"
import Link from "next/link"
import { notFound } from "next/navigation"
import { medusa, getBrand } from "@/lib/medusa-client"
import { ProductCard } from "@/components/product-card"

const PAGE_SIZE = 48

export default function SeriesPage({
  params,
}: {
  params: Promise<{ brand: string; slug: string }>
}) {
  const { brand: brandSlug, slug } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  const [collection, setCollection] = useState<any>(null)
  const [products, setProducts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const sentinelRef = useRef<HTMLDivElement>(null)

  const fetchProducts = useCallback(
    async (reset = false) => {
      if (!collection) return
      setLoading(true)
      const currentOffset = reset ? 0 : offset
      try {
        const { products: fetched, count } = await medusa.store.product.list(
          {
            collection_id: collection.id,
            limit: PAGE_SIZE,
            offset: currentOffset,
            fields: "+metadata,+categories,+collection,+tags,+variants,+variants.prices,+images",
          },
          { "x-publishable-api-key": brand!.publishableKey } as any
        ) as any

        if (reset) {
          setProducts(fetched)
          setOffset(PAGE_SIZE)
        } else {
          setProducts((prev) => [...prev, ...fetched])
          setOffset(currentOffset + PAGE_SIZE)
        }
        setHasMore(currentOffset + PAGE_SIZE < count)
      } catch (err) {
        console.error("Failed to fetch products:", err)
      }
      setLoading(false)
    },
    [collection, offset, brand]
  )

  // Load collection by handle
  useEffect(() => {
    async function loadCollection() {
      try {
        const { collections } = await medusa.store.collection.list(
          { handle: [slug], limit: 1 },
          { "x-publishable-api-key": brand!.publishableKey } as any
        ) as any
        if (collections?.length > 0) {
          setCollection(collections[0])
        }
      } catch (err) {
        console.error("Failed to load collection:", err)
      }
    }
    loadCollection()
  }, [slug, brand])

  // Fetch products when collection is loaded
  useEffect(() => {
    if (collection) fetchProducts(true)
  }, [collection])

  // Infinite scroll
  useEffect(() => {
    if (!sentinelRef.current) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          fetchProducts()
        }
      },
      { rootMargin: "400px" }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, fetchProducts])

  return (
    <main className="max-w-7xl mx-auto px-6 py-8">
      <nav className="text-sm text-gray-400 mb-6">
        <Link href={`/${brandSlug}`} className="hover:text-leka-purple">
          {brand.name}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-leka-navy">
          {collection?.title || slug}
        </span>
      </nav>

      <h1 className="text-2xl font-bold text-leka-navy mb-2">
        {collection?.title || slug}
      </h1>
      <p className="text-sm text-gray-500 mb-8">
        {products.length} products
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            brandSlug={brandSlug}
            showPrice={brand.hasPricing}
          />
        ))}
      </div>

      <div ref={sentinelRef} className="h-1" />

      {loading && (
        <div className="text-center py-8">
          <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
        </div>
      )}
    </main>
  )
}
