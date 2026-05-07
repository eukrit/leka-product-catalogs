"use client"

import { useEffect, useMemo, useRef } from "react"

export interface CategoryNode {
  id: string
  name: string
  handle: string
  children: Array<{ id: string; name: string; handle: string }>
}

interface FilterBarProps {
  search: string
  onSearchChange: (value: string) => void
  /** Top-level categories. Each may contain `children`. Brands without children render a flat list. */
  categories: CategoryNode[]
  selectedCategory: string
  onCategoryChange: (value: string) => void
  selectedSubcategory: string
  onSubcategoryChange: (value: string) => void
  selectedAge: string
  onAgeChange: (value: string) => void
  showAgeFilter: boolean
  /** Wisdom-style filters (price + material). */
  showMaterialFilter?: boolean
  materials?: string[]
  selectedMaterial?: string
  onMaterialChange?: (value: string) => void
  showPriceFilter?: boolean
  minPrice?: string
  maxPrice?: string
  onPriceChange?: (min: string, max: string) => void
  onReset: () => void
}

export function FilterBar({
  search,
  onSearchChange,
  categories,
  selectedCategory,
  onCategoryChange,
  selectedSubcategory,
  onSubcategoryChange,
  selectedAge,
  onAgeChange,
  showAgeFilter,
  showMaterialFilter = false,
  materials = [],
  selectedMaterial = "",
  onMaterialChange,
  showPriceFilter = false,
  minPrice = "",
  maxPrice = "",
  onPriceChange,
  onReset,
}: FilterBarProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null)

  function handleSearchInput(value: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => onSearchChange(value), 300)
  }

  useEffect(() => {
    const ref = debounceRef.current
    return () => {
      if (ref) clearTimeout(ref)
    }
  }, [])

  const selectedNode = useMemo(
    () => categories.find((c) => c.id === selectedCategory),
    [categories, selectedCategory]
  )
  const subcategories = selectedNode?.children ?? []
  const hasAnySubcategories = useMemo(
    () => categories.some((c) => c.children.length > 0),
    [categories]
  )

  return (
    <div className="flex flex-wrap items-center gap-3 mb-6">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <input
          type="text"
          placeholder="Search products by name, code, or description..."
          defaultValue={search}
          onChange={(e) => handleSearchInput(e.target.value)}
          className="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple focus:ring-1 focus:ring-leka-purple/20"
        />
      </div>

      {/* Category */}
      <select
        value={selectedCategory}
        onChange={(e) => {
          onCategoryChange(e.target.value)
          onSubcategoryChange("")
        }}
        className="px-4 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
      >
        <option value="">All Categories</option>
        {categories.map((cat) => (
          <option key={cat.id} value={cat.id}>
            {cat.name}
          </option>
        ))}
      </select>

      {/* Sub-category — only render when at least one parent has children */}
      {hasAnySubcategories && (
        <select
          value={selectedSubcategory}
          onChange={(e) => onSubcategoryChange(e.target.value)}
          disabled={!selectedNode || subcategories.length === 0}
          className="px-4 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple disabled:bg-gray-50 disabled:text-gray-400"
        >
          <option value="">
            {selectedNode && subcategories.length > 0
              ? "All Sub-categories"
              : "Sub-category (pick a category first)"}
          </option>
          {subcategories.map((sub) => (
            <option key={sub.id} value={sub.id}>
              {sub.name}
            </option>
          ))}
        </select>
      )}

      {/* Age Group (Vinci-specific) */}
      {showAgeFilter && (
        <select
          value={selectedAge}
          onChange={(e) => onAgeChange(e.target.value)}
          className="px-4 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
        >
          <option value="">All Ages</option>
          <option value="1+">1+ years</option>
          <option value="3+">3+ years</option>
          <option value="6+">6+ years</option>
          <option value="14+">14+ years</option>
        </select>
      )}

      {/* Material (Wisdom-specific) */}
      {showMaterialFilter && materials.length > 0 && (
        <select
          value={selectedMaterial}
          onChange={(e) => onMaterialChange?.(e.target.value)}
          className="px-4 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
        >
          <option value="">All Materials</option>
          {materials.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      )}

      {/* Price range (Wisdom-specific) */}
      {showPriceFilter && (
        <div className="flex items-center gap-1 text-sm">
          <span className="text-gray-400 mr-1">USD</span>
          <input
            type="number"
            inputMode="numeric"
            min="0"
            placeholder="Min"
            value={minPrice}
            onChange={(e) => onPriceChange?.(e.target.value, maxPrice)}
            className="w-24 px-3 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
          />
          <span className="text-gray-300">–</span>
          <input
            type="number"
            inputMode="numeric"
            min="0"
            placeholder="Max"
            value={maxPrice}
            onChange={(e) => onPriceChange?.(minPrice, e.target.value)}
            className="w-24 px-3 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
          />
        </div>
      )}

      {/* Reset */}
      <button
        onClick={onReset}
        className="px-4 py-2.5 text-sm text-gray-500 hover:text-leka-purple transition-colors"
      >
        Reset
      </button>
    </div>
  )
}
