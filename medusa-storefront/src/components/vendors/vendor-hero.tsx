import type { BrandConfig } from "@/lib/medusa-client"
import type { VendorTheme } from "@/lib/vendor-themes"

export function VendorHero({
  brand,
  theme,
  totalCount,
}: {
  brand: BrandConfig
  theme: VendorTheme
  totalCount: number
}) {
  const { hero, colors } = theme

  return (
    <div style={{ background: hero.bg }} className="py-10 sm:py-14 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-end justify-between gap-8">
          <div className="min-w-0">
            <div
              style={{
                color: hero.accentColor,
                fontSize: "10px",
                fontWeight: 700,
                letterSpacing: "0.22em",
              }}
              className="uppercase mb-3"
            >
              {theme.origin}
            </div>
            <h1
              style={{
                color: hero.textColor,
                fontWeight: 900,
                lineHeight: 1.05,
                letterSpacing: "-0.025em",
              }}
              className="text-3xl sm:text-4xl md:text-5xl"
            >
              {brand.name}
            </h1>
            <p
              style={{ color: hero.textColor, opacity: 0.65 }}
              className="mt-3 text-sm sm:text-base"
            >
              {theme.tagline}
            </p>
            <div
              style={{
                width: 36,
                height: 3,
                backgroundColor: hero.accentColor,
                borderRadius: 2,
                marginTop: 20,
              }}
            />
          </div>

          {totalCount > 0 && (
            <div className="text-right flex-shrink-0 hidden sm:block">
              <div
                style={{
                  color: hero.textColor,
                  fontWeight: 800,
                  fontSize: "42px",
                  lineHeight: 1,
                  letterSpacing: "-0.03em",
                }}
              >
                {totalCount.toLocaleString()}
              </div>
              <div
                style={{
                  color: hero.textColor,
                  opacity: 0.45,
                  fontSize: "10px",
                  letterSpacing: "0.15em",
                }}
                className="uppercase mt-1"
              >
                Products
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
