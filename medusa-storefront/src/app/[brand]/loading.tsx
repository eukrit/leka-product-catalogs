export default function BrandLoading() {
  return (
    <main className="max-w-7xl mx-auto px-6 py-8">
      {/* Header skeleton */}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-64 bg-gray-100 rounded animate-pulse mt-2" />
        </div>
        <div className="flex gap-6">
          <div className="h-10 w-16 bg-gray-200 rounded animate-pulse" />
          <div className="h-10 w-16 bg-gray-200 rounded animate-pulse" />
        </div>
      </div>

      {/* Filter skeleton */}
      <div className="flex gap-3 mb-6">
        <div className="flex-1 h-10 bg-gray-200 rounded-button animate-pulse" />
        <div className="w-40 h-10 bg-gray-200 rounded-button animate-pulse" />
      </div>

      {/* Grid skeleton */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="card">
            <div className="aspect-square bg-gray-100 animate-pulse" />
            <div className="p-3 space-y-2">
              <div className="h-3 w-16 bg-gray-200 rounded animate-pulse" />
              <div className="h-4 w-full bg-gray-200 rounded animate-pulse" />
              <div className="h-3 w-24 bg-gray-100 rounded animate-pulse" />
            </div>
          </div>
        ))}
      </div>
    </main>
  )
}
