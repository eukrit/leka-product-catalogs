"use client"

const BADGE_COLORS = [
  "badge-purple",
  "badge-navy",
  "badge-amber",
  "badge-magenta",
  "badge-red-orange",
]

interface SeriesBadgesProps {
  collections: Array<{ id: string; title: string; handle: string }>
  activeCollection: string
  onSelect: (id: string) => void
  brandColor: string
}

export function SeriesBadges({
  collections,
  activeCollection,
  onSelect,
}: SeriesBadgesProps) {
  return (
    <div className="flex flex-wrap gap-2 mb-6">
      <button
        className={`badge ${activeCollection === "" ? "badge-purple" : "badge-outline"}`}
        onClick={() => onSelect("")}
      >
        All
      </button>
      {collections.map((col, i) => (
        <button
          key={col.id}
          className={`badge ${activeCollection === col.id ? BADGE_COLORS[i % BADGE_COLORS.length] : "badge-outline"}`}
          onClick={() => onSelect(col.id)}
        >
          {col.title}
        </button>
      ))}
    </div>
  )
}
