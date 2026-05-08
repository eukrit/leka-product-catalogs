"use client"

import { useState, useCallback } from "react"
import { use } from "react"
import Link from "next/link"
import Image from "next/image"
import { notFound } from "next/navigation"
import { getBrand } from "@/lib/medusa-client"
import { getBrandCI } from "@/lib/brand-ci"
import { getCartId } from "@/lib/cart"
import { CartDrawer } from "@/components/cart-drawer"
import { LocaleSwitcher } from "@/components/locale-switcher"

export default function BrandLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ brand: string }>
}) {
  const { brand: brandSlug } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()
  const ci = getBrandCI(brandSlug)

  const [cartOpen, setCartOpen] = useState(false)
  const [cartVersion, setCartVersion] = useState(0)

  const openCart = useCallback(() => setCartOpen(true), [])
  const closeCart = useCallback(() => setCartOpen(false), [])
  const onCartUpdate = useCallback(() => setCartVersion((v) => v + 1), [])

  const cartId = typeof window !== "undefined" ? getCartId(brandSlug) : null

  const brandStyle = {
    "--brand-primary": ci?.palette.primary ?? brand.color,
    "--brand-secondary": ci?.palette.secondary ?? brand.color,
    "--brand-ink": ci?.palette.ink ?? "#182557",
    "--brand-paper": ci?.palette.paper ?? "#FFFFFF",
    "--brand-heading": ci?.fonts.headingVar
      ? `var(${ci.fonts.headingVar})`
      : "Manrope",
  } as React.CSSProperties

  return (
    <div className="min-h-screen bg-gray-50" style={brandStyle}>
      {/* Brand Header */}
      <header className="bg-white border-b border-gray-100 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 sm:py-4 flex items-center justify-between">
          <div className="flex items-center gap-2 sm:gap-4">
            <Link href="/" className="text-sm text-gray-400 hover:text-leka-purple hidden sm:inline">
              Leka
            </Link>
            <span className="text-gray-300 hidden sm:inline">/</span>
            <Link href={`/${brand.slug}`} className="flex items-center gap-2">
              {ci?.logo ? (
                <span
                  className="inline-flex items-center justify-center rounded-button overflow-hidden h-8 px-2"
                  style={{
                    backgroundColor: ci.logoBg ?? "transparent",
                  }}
                >
                  <Image
                    src={ci.logo}
                    alt={brand.name}
                    width={120}
                    height={32}
                    className="h-6 w-auto object-contain"
                    priority
                    unoptimized
                  />
                </span>
              ) : (
                <span
                  className="w-8 h-8 rounded-button flex items-center justify-center text-white font-bold text-sm"
                  style={{ backgroundColor: ci?.palette.primary ?? brand.color }}
                >
                  {brand.name.charAt(0)}
                </span>
              )}
              <span className="font-semibold text-leka-navy text-sm sm:text-base font-heading">
                {brand.name}
              </span>
            </Link>
          </div>
          <nav className="flex items-center gap-2 sm:gap-4">
            <LocaleSwitcher />
            <button
              onClick={openCart}
              className="btn-secondary text-sm px-3 sm:px-4 py-2 relative"
            >
              Cart
            </button>
            <Link
              href={`/${brand.slug}/account`}
              className="text-sm text-gray-500 hover:text-leka-purple hidden sm:inline"
            >
              Account
            </Link>
          </nav>
        </div>
      </header>

      {children}

      {/* Cart Drawer */}
      <CartDrawer
        brandSlug={brandSlug}
        isOpen={cartOpen}
        onClose={closeCart}
        cartId={cartId}
        onCartUpdate={onCartUpdate}
      />
    </div>
  )
}
