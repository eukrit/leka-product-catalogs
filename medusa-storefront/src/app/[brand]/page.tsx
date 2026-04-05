"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { notFound } from "next/navigation"
import { use } from "react"
import { medusa, getBrand, type BrandConfig } from "@/lib/medusa-client"
import { ProductCard } from "@/components/product-card"
import { FilterBar } from "@/components/filter-bar"
import { SeriesBadges } from "@/components/series-badges"

const PAGE_SIZE = 48

interface MedusaProduct {
  id: string
  title: string
  handle: string
  description: string | null
  status: string
  thumbnail: string | null
  images: Array<{ url: string }>
  metadata: Record<string, unknown>
  categories: Array<{ id: string; name: string; handle: string }>
  collection: { id: string; title: string; handle: string } | null
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

export default function CatalogPage({
  params,
}: {
  params: Promise<{ brand: string }>
}) {
  const { brand: brandSlug } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  return <CatalogContent brand={brand} />
}

function CatalogContent({ brand }: { brand: BrandConfig }) {
  const [products, setProducts] = useState<MedusaProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("")
  const [collectionFilter, setCollectionFilter] = useState("")
  const [categories, setCategories] = useState<Array<{ id: string; name: string; handle: string }>>([])
  const [collections, setCollections] = useState<Array<{ id: string; title: string; handle: string }>>([])
  const sentinelRef = useRef<HTMLDivElement>(null)

  const fetchProducts = useCallback(
    async (reset = false) => {
      setLoading(true)
      const currentOffset = reset ? 0 : offset

      try {
        const query: Record<string, unknown> = {
          limit: PAGE_SIZE,
          offset: currentOffset,
          fields: "+metadata,+categories,+collection,+tags,+variants,+variants.prices,+images",
        }

        if (search) query.q = search
        if (categoryFilter) query.category_id = categoryFilter
        if (collectionFilter) query.collection_id = collectionFilter

        const { products: fetched, count } = await medusa.store.product.list(
          query,
          { "x-publishable-api-key": brand.publishableKey } as any
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
    [brand.publishableKey, offset, search, categoryFilter, collectionFilter]
  )

  // Load categories and collections
  useEffect(() => {
    async function loadFilters() {
      try {
        const { product_categories } = await medusa.store.category.list(
          { limit: 100 },
          { "x-publishable-api-key": brand.publishableKey } as any
        ) as any
        setCategories(product_categories || [])

        if (brand.hasCollections) {
          const { collections: cols } = await medusa.store.collection.list(
            { limit: 100 },
            { "x-publishable-api-key": brand.publishableKey } as any
          ) as any
          setCollections(cols || [])
        }
      } catch (err) {
        console.error("Failed to load filters:", err)
      }
    }
    loadFilters()
  }, [brand])

  // Initial load and filter changes
  useEffect(() => {
    fetchProducts(true)
  }, [search, categoryFilter, collectionFilter])

  // Infinite scroll observer
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
      {/* Stats */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-leka-navy">{brand.name}</h1>
        <p className="text-sm text-gray-500 mt-1">{brand.description}</p>
      </div>

      {/* Series Badges (Vinci) */}
      {brand.hasCollections && collections.length > 0 && (
        <SeriesBadges
          collections={collections}
          activeCollection={collectionFilter}
          onSelect={(id) => setCollectionFilter(id === collectionFilter ? "" : id)}
          brandColor={brand.color}
        />
      )}

      {/* Filters */}
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        categories={categories}
        selectedCategory={categoryFilter}
        onCategoryChange={setCategoryFilter}
        onReset={() => {
          setSearch("")
          setCategoryFilter("")
          setCollectionFilter("")
        }}
      />

      {/* Product Grid */}
      {products.length === 0 && !loading ? (
        <div className="text-center py-16">
          <h3 className="text-lg font-semibold text-gray-400">
            No products found
          </h3>
          <p className="text-sm text-gray-400 mt-1">
            Try adjusting your filters or search query.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {products.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              brandSlug={brand.slug}
              showPrice={brand.hasPricing}
            />
          ))}
        </div>
      )}

      {/* Infinite scroll sentinel */}
      <div ref={sentinelRef} className="h-1" />

      {loading && (
        <div className="text-center py-8">
          <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
        </div>
      )}
    </main>
  )
}
