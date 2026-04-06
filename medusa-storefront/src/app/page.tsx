import type { Metadata } from "next"
import Link from "next/link"
import { BRANDS } from "@/lib/medusa-client"

export const metadata: Metadata = {
  title: "Leka Product Catalogs — Multi-Brand E-Commerce",
  description:
    "Browse playground equipment, furniture, and outdoor products from Wisdom and Vinci Play. Powered by GO Corporation Co., Ltd.",
  openGraph: {
    title: "Leka Product Catalogs",
    description: "Multi-brand product catalog and e-commerce platform",
    type: "website",
  },
}

export default function LandingPage() {
  const brands = Object.values(BRANDS)

  return (
    <div className="min-h-screen bg-leka-cream">
      {/* Header */}
      <header className="bg-white border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-leka-navy">
              Leka Product Catalogs
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              by GO Corporation Co., Ltd.
            </p>
          </div>
        </div>
      </header>

      {/* Brand Cards */}
      <main className="max-w-6xl mx-auto px-6 py-12">
        <h2 className="text-lg font-semibold text-leka-navy mb-8">
          Select a brand catalog
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {brands.map((brand) => (
            <Link
              key={brand.slug}
              href={`/${brand.slug}`}
              className="card group p-6 hover:ring-2 hover:ring-leka-purple/20"
            >
              <div
                className="w-12 h-12 rounded-card flex items-center justify-center text-white font-bold text-lg mb-4"
                style={{ backgroundColor: brand.color }}
              >
                {brand.name.charAt(0)}
              </div>
              <h3 className="text-xl font-bold text-leka-navy group-hover:text-leka-purple transition-colors">
                {brand.name}
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                {brand.description}
              </p>
              <div className="mt-4 flex items-center gap-2 text-xs text-gray-400">
                <span>{brand.country}</span>
              </div>
            </Link>
          ))}
        </div>
      </main>
    </div>
  )
}
