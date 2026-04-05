import Link from "next/link"
import { notFound } from "next/navigation"
import { getBrand } from "@/lib/medusa-client"

export default async function BrandLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ brand: string }>
}) {
  const { brand: brandSlug } = await params
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Brand Header */}
      <header className="bg-white border-b border-gray-100 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-sm text-gray-400 hover:text-leka-purple">
              Leka
            </Link>
            <span className="text-gray-300">/</span>
            <Link href={`/${brand.slug}`} className="flex items-center gap-2">
              <div
                className="w-8 h-8 rounded-button flex items-center justify-center text-white font-bold text-sm"
                style={{ backgroundColor: brand.color }}
              >
                {brand.name.charAt(0)}
              </div>
              <span className="font-semibold text-leka-navy">
                {brand.name}
              </span>
            </Link>
          </div>
          <nav className="flex items-center gap-4">
            <Link
              href={`/${brand.slug}/cart`}
              className="btn-secondary text-sm px-4 py-2"
            >
              Cart
            </Link>
            <Link
              href={`/${brand.slug}/account`}
              className="text-sm text-gray-500 hover:text-leka-purple"
            >
              Account
            </Link>
          </nav>
        </div>
      </header>
      {children}
    </div>
  )
}
