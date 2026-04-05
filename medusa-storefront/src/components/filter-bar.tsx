"use client"

import { useEffect, useRef } from "react"

interface FilterBarProps {
  search: string
  onSearchChange: (value: string) => void
  categories: Array<{ id: string; name: string; handle: string }>
  selectedCategory: string
  onCategoryChange: (value: string) => void
  onReset: () => void
}

export function FilterBar({
  search,
  onSearchChange,
  categories,
  selectedCategory,
  onCategoryChange,
  onReset,
}: FilterBarProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  function handleSearchInput(value: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => onSearchChange(value), 300)
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  return (
    <div className="flex flex-wrap items-center gap-3 mb-6">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <input
          type="text"
          placeholder="Search products..."
          defaultValue={search}
          onChange={(e) => handleSearchInput(e.target.value)}
          className="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple focus:ring-1 focus:ring-leka-purple/20"
        />
      </div>

      {/* Category */}
      <select
        value={selectedCategory}
        onChange={(e) => onCategoryChange(e.target.value)}
        className="px-4 py-2.5 bg-white border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
      >
        <option value="">All Categories</option>
        {categories.map((cat) => (
          <option key={cat.id} value={cat.id}>
            {cat.name}
          </option>
        ))}
      </select>

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
