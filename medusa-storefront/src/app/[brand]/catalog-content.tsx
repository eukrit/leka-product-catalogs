"use client"

import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { notFound, useRouter, useSearchParams, usePathname } from "next/navigation"
import { medusa, getBrand, type BrandConfig } from "@/lib/medusa-client"
import { ProductCard } from "@/components/product-card"
import { FilterBar, type CategoryNode } from "@/components/filter-bar"
import { SeriesBadges } from "@/components/series-badges"
import { getBrandCI } from "@/lib/brand-ci"

const PAGE_SIZE = 48

// Material buckets used for the Wisdom material filter. The raw `metadata.material`
// strings are messy (e.g. "Wood   table topSize:..."), so we substring-match.
const MATERIAL_BUCKETS: Array<{ label: string; match: RegExp }> = [
  { label: "Wood", match: /wood/i },
  { label: "Rubber wood", match: /rubber\s*wood/i },
  { label: "Plastic", match: /plastic|pvc|pe\b|hdpe/i },
  { label: "Metal", match: /metal|steel|iron|aluminium|aluminum/i },
  { label: "Fabric", match: /fabric|cloth|cotton|polyester/i },
  { label: "Foam", match: /foam|epdm/i },
]

function bucketMaterial(raw: string | undefined): string | null {
  if (!raw) return null
  // Rubber wood is more specific than plain wood — check it first.
  for (const b of MATERIAL_BUCKETS) {
    if (b.match.test(raw)) return b.label
  }
  return null
}

interface MedusaProduct {
  id: string
  title: string
  handle: string
  description: string | null
  status: string
  thumbnail: string | null
  images: Array<{ url: string }>
  metadata: Record<string, unknown>
  categories: Array<{ id: string; name: string; handle: string; parent_category_id?: string | null }>
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

export default function CatalogPageClient({ brandSlug }: { brandSlug: string }) {
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  // Stub brands (no Sales Channel yet, productCount === 0) skip Medusa fetches
  // and render a "coming soon" placeholder using the brand's CI.
  if (brand.productCount === 0 && !brand.publishableKey) {
    const ci = getBrandCI(brandSlug)
    return (
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-16 sm:py-24 text-center">
        <h1
          className="text-3xl sm:text-4xl font-bold mb-4 font-heading"
          style={{ color: "var(--brand-primary)" }}
        >
          {brand.name}
        </h1>
        <p className="text-leka-navy text-base sm:text-lg mb-2">
          {ci?.tagline ?? brand.description}
        </p>
        <p className="text-gray-500 text-sm">
          Catalog coming soon — products are being onboarded into Leka.
        </p>
      </main>
    )
  }

  return <CatalogContent brand={brand} />
}

function CatalogContent({ brand }: { brand: BrandConfig }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [products, setProducts] = useState<MedusaProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState(searchParams.get("q") ?? "")
  const [categoryFilter, setCategoryFilter] = useState(searchParams.get("category") ?? "")
  const [subcategoryFilter, setSubcategoryFilter] = useState(searchParams.get("subcategory") ?? "")
  const [collectionFilter, setCollectionFilter] = useState("")
  const [ageFilter, setAgeFilter] = useState("")
  const [materialFilter, setMaterialFilter] = useState(searchParams.get("material") ?? "")
  const [minPrice, setMinPrice] = useState(searchParams.get("min_price") ?? "")
  const [maxPrice, setMaxPrice] = useState(searchParams.get("max_price") ?? "")
  const [totalCount, setTotalCount] = useState(0)
  const [categoryTree, setCategoryTree] = useState<CategoryNode[]>([])
  const [collections, setCollections] = useState<Array<{ id: string; title: string; handle: string }>>([])
  const sentinelRef = useRef<HTMLDivElement>(null)

  // Sync filter state -> URL (so deep links work and Reset clears the URL).
  useEffect(() => {
    const sp = new URLSearchParams()
    if (search) sp.set("q", search)
    if (categoryFilter) sp.set("category", categoryFilter)
    if (subcategoryFilter) sp.set("subcategory", subcategoryFilter)
    if (materialFilter) sp.set("material", materialFilter)
    if (minPrice) sp.set("min_price", minPrice)
    if (maxPrice) sp.set("max_price", maxPrice)
    const qs = sp.toString()
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
  }, [search, categoryFilter, subcategoryFilter, materialFilter, minPrice, maxPrice, pathname, router])

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
        // Subcategory wins over parent category — Medusa-side filter on the leaf id.
        if (subcategoryFilter) query.category_id = subcategoryFilter
        else if (categoryFilter) query.category_id = categoryFilter
        if (collectionFilter) query.collection_id = collectionFilter

        const { products: fetched, count } = await medusa.store.product.list(
          query,
          { "x-publishable-api-key": brand.publishableKey } as any
        ) as any

        let filtered: MedusaProduct[] = fetched
        // Client-side age filter (metadata field, not queryable via API)
        if (ageFilter) {
          filtered = filtered.filter((p: MedusaProduct) => {
            const specs = (p.metadata?.specifications || {}) as Record<string, unknown>
            const ageGroup = String(specs.age_group || "")
            return ageGroup.includes(ageFilter.replace("+", ""))
          })
        }
        // Material filter (Wisdom) — bucket the raw metadata.material string.
        if (materialFilter) {
          filtered = filtered.filter((p: MedusaProduct) => {
            const raw = String((p.metadata?.material as string) || "")
            return bucketMaterial(raw) === materialFilter
          })
        }
        // Price range filter (Wisdom) — first variant's first USD price, in cents.
        const minCents = minPrice ? Math.round(parseFloat(minPrice) * 100) : null
        const maxCents = maxPrice ? Math.round(parseFloat(maxPrice) * 100) : null
        if (minCents !== null || maxCents !== null) {
          filtered = filtered.filter((p: MedusaProduct) => {
            const cents = p.variants?.[0]?.prices?.[0]?.amount
            if (cents == null) return false
            if (minCents !== null && cents < minCents) return false
            if (maxCents !== null && cents > maxCents) return false
            return true
          })
        }

        if (reset) {
          setProducts(filtered)
          setOffset(PAGE_SIZE)
          setTotalCount(count)
        } else {
          setProducts((prev) => [...prev, ...filtered])
          setOffset(currentOffset + PAGE_SIZE)
        }
        setHasMore(currentOffset + PAGE_SIZE < count)
      } catch (err) {
        console.error("Failed to fetch products:", err)
      }
      setLoading(false)
    },
    [
      brand.publishableKey,
      offset,
      search,
      categoryFilter,
      subcategoryFilter,
      collectionFilter,
      ageFilter,
      materialFilter,
      minPrice,
      maxPrice,
    ]
  )

  // Load categories (with parent/child relationships) and collections.
  useEffect(() => {
    async function loadFilters() {
      try {
        const { product_categories } = await medusa.store.category.list(
          {
            limit: 200,
            fields: "id,name,handle,parent_category_id",
          } as any,
          { "x-publishable-api-key": brand.publishableKey } as any
        ) as any

        const all = (product_categories || []) as Array<{
          id: string
          name: string
          handle: string
          parent_category_id?: string | null
        }>
        const parents = all.filter((c) => !c.parent_category_id)
        const tree: CategoryNode[] = parents
          .map((p) => ({
            id: p.id,
            name: p.name,
            handle: p.handle,
            children: all
              .filter((c) => c.parent_category_id === p.id)
              .map((c) => ({ id: c.id, name: c.name, handle: c.handle }))
              .sort((a, b) => a.name.localeCompare(b.name)),
          }))
          .sort((a, b) => a.name.localeCompare(b.name))
        setCategoryTree(tree)

        if (brand.hasCollections) {
          const { collections: cols } = await medusa.store.collection.list(
            { limit: 100 },
            { "x-publishable-api-key": brand.publishableKey } as any
          ) as any
          // Filter to only this brand's collections.
          const OTHER_PREFIXES = ["berliner-", "4soft-", "vortex-"]
          const filtered = brand.collectionPrefix !== undefined
            ? (cols || []).filter((c: { handle: string }) => c.handle.startsWith(brand.collectionPrefix!))
            : (cols || []).filter((c: { handle: string }) => !OTHER_PREFIXES.some(p => c.handle.startsWith(p)))
          setCollections(filtered)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, categoryFilter, subcategoryFilter, collectionFilter, ageFilter, materialFilter, minPrice, maxPrice])

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

  // Materials list (Wisdom) — derived from currently-loaded products.
  const materialsAvailable = useMemo(() => {
    if (!brand.hasMaterialFilter) return []
    const set = new Set<string>()
    for (const p of products) {
      const b = bucketMaterial(String((p.metadata?.material as string) || ""))
      if (b) set.add(b)
    }
    return Array.from(set).sort()
  }, [products, brand.hasMaterialFilter])

  function resetAll() {
    setSearch("")
    setCategoryFilter("")
    setSubcategoryFilter("")
    setCollectionFilter("")
    setAgeFilter("")
    setMaterialFilter("")
    setMinPrice("")
    setMaxPrice("")
  }

  return (
    <main className="max-w-7xl mx-auto px-6 py-8">
      {/* Stats Header */}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-leka-navy">{brand.name}</h1>
          <p className="text-sm text-gray-500 mt-1">{brand.description}</p>
        </div>
        <div className="flex gap-6 text-right">
          <div>
            <div className="text-2xl font-bold text-leka-navy">
              {totalCount.toLocaleString()}
            </div>
            <div className="text-xs text-gray-400">Products</div>
          </div>
          {brand.hasCollections && (
            <div>
              <div className="text-2xl font-bold text-leka-navy">
                {collections.length}
              </div>
              <div className="text-xs text-gray-400">Series</div>
            </div>
          )}
        </div>
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
        categories={categoryTree}
        selectedCategory={categoryFilter}
        onCategoryChange={setCategoryFilter}
        selectedSubcategory={subcategoryFilter}
        onSubcategoryChange={setSubcategoryFilter}
        selectedAge={ageFilter}
        onAgeChange={setAgeFilter}
        showAgeFilter={brand.hasCollections}
        showMaterialFilter={!!brand.hasMaterialFilter}
        materials={materialsAvailable}
        selectedMaterial={materialFilter}
        onMaterialChange={setMaterialFilter}
        showPriceFilter={!!brand.hasMaterialFilter && brand.hasPricing}
        minPrice={minPrice}
        maxPrice={maxPrice}
        onPriceChange={(min, max) => {
          setMinPrice(min)
          setMaxPrice(max)
        }}
        onReset={resetAll}
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
