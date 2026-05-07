"use client"

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
  const activeStyle = {
    backgroundColor: "var(--brand-primary)",
    color: "var(--brand-paper, #fff)",
    borderColor: "var(--brand-primary)",
  } as React.CSSProperties

  return (
    <div className="flex flex-wrap gap-2 mb-6">
      <button
        className="badge"
        style={activeCollection === "" ? activeStyle : undefined}
        onClick={() => onSelect("")}
      >
        All
      </button>
      {collections.map((col) => {
        const isActive = activeCollection === col.id
        return (
          <button
            key={col.id}
            className={`badge ${isActive ? "" : "badge-outline"}`}
            style={isActive ? activeStyle : undefined}
            onClick={() => onSelect(col.id)}
          >
            {col.title}
          </button>
        )
      })}
    </div>
  )
}
