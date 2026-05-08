"use client"

import Link from "next/link"
import type { BrandConfig } from "@/lib/medusa-client"
import type { VendorTheme } from "@/lib/vendor-themes"
import { LocaleSwitcher } from "@/components/locale-switcher"

export function VendorHeader({
  brand,
  theme,
  onOpenCart,
}: {
  brand: BrandConfig
  theme: VendorTheme
  onOpenCart: () => void
}) {
  const { colors } = theme

  return (
    <header
      style={{
        backgroundColor: colors.headerBg,
        borderBottom: `3px solid ${colors.headerBorder}`,
      }}
      className="sticky top-0 z-40"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            style={{ color: colors.headerText, opacity: 0.45 }}
            className="text-xs uppercase tracking-widest hidden sm:inline hover:opacity-80 transition-opacity"
          >
            Leka
          </Link>
          <span
            style={{ color: colors.headerText, opacity: 0.25 }}
            className="hidden sm:inline text-xs"
          >
            /
          </span>
          <Link href={`/${brand.slug}`}>
            <VendorLogotype brand={brand} theme={theme} />
          </Link>
        </div>

        <nav className="flex items-center gap-3">
          <LocaleSwitcher />
          <button
            onClick={onOpenCart}
            className="text-sm px-4 py-2 rounded-lg font-semibold transition-opacity hover:opacity-85"
            style={{ backgroundColor: colors.accent, color: colors.accentContrast }}
          >
            Cart
          </button>
          <Link
            href={`/${brand.slug}/account`}
            className="text-sm hidden sm:inline transition-opacity hover:opacity-80"
            style={{ color: colors.headerText, opacity: 0.65 }}
          >
            Account
          </Link>
        </nav>
      </div>
    </header>
  )
}

function VendorLogotype({ brand, theme }: { brand: BrandConfig; theme: VendorTheme }) {
  const { colors } = theme

  switch (brand.slug) {
    case "berliner":
      return (
        <div className="flex flex-col leading-none select-none">
          <span
            style={{
              color: colors.accent,
              fontWeight: 800,
              fontSize: "10px",
              letterSpacing: "0.18em",
            }}
            className="uppercase"
          >
            Berliner
          </span>
          <span
            style={{
              color: colors.headerText,
              fontWeight: 700,
              fontSize: "14px",
              letterSpacing: "0.06em",
            }}
            className="uppercase"
          >
            Seilfabrik
          </span>
        </div>
      )

    case "eurotramp":
      return (
        <span
          style={{
            color: colors.accent,
            fontWeight: 900,
            fontSize: "18px",
            letterSpacing: "-0.03em",
          }}
          className="select-none"
        >
          eurotramp
        </span>
      )

    case "rampline":
      return (
        <div className="flex items-center gap-2 select-none">
          <div
            style={{
              width: 5,
              height: 18,
              backgroundColor: colors.accent,
              borderRadius: 2,
              flexShrink: 0,
            }}
          />
          <span
            style={{
              color: colors.headerText,
              fontWeight: 700,
              fontSize: "15px",
              letterSpacing: "0.08em",
            }}
            className="uppercase"
          >
            rampline
          </span>
        </div>
      )

    case "vortex":
      return (
        <span
          aria-label="Vortex"
          className="inline-flex items-center select-none"
          style={{ color: colors.headerText }}
        >
          <svg
            viewBox="0 0 192 41"
            role="img"
            aria-hidden="true"
            style={{ height: 22, width: "auto", display: "block" }}
          >
            <path
              fill="currentColor"
              fillRule="evenodd"
              d="M26.9 0c2.3 0 4.2 2 4.2 4.4 0 1.5-.7 2.9-1.9 3.6-.5.3-.7.8-.7 1.4 0 .8.5 1.4 1.2 1.6 5.4 1.3 9.5 6.3 9.5 12.3 0 2.5-.7 4.7-1.9 6.7-.2.3-.3.8-.3 1.2 0 1.2.9 2.2 2.1 2.2.2 0 .4 0 .6-.1.3-.1.6-.1.9-.1 2.1 0 3.7 1.7 3.7 3.8s-1.7 3.8-3.7 3.8c-2.1 0-3.7-1.7-3.7-3.8 0-.3 0-.6.1-.9v-.5c0-1.2-1-2.2-2.1-2.2-.4 0-.8.1-1.2.4-2 1.4-4.3 2.1-6.7 2.1-5.4 0-10-3.6-11.6-8.7-.3-1.1-1.3-1.9-2.5-1.9-.9 0-1.7.5-2.2 1.3-1 1.7-2.8 2.8-4.9 2.8-3.2 0-5.8-2.7-5.8-6s2.6-6 5.8-6c2 0 3.8 1.1 4.9 2.7.5.8 1.3 1.3 2.3 1.3 1.2 0 2.1-.8 2.5-1.9 1.3-4.1 4.7-7.4 8.8-8.4.7-.2 1.2-.8 1.2-1.6 0-.6-.3-1.1-.7-1.4-1.2-.8-1.9-2.2-1.9-3.6-.3-2.5 1.6-4.5 4-4.5zm159.7 11.6c.7-1 1.4-1.6 2.6-1.6 1.2 0 2.5 1 2.5 2.6 0 .8-.3 1.5-.8 2.2l-6.3 8 6.6 8.5c.4.6.8 1.3.8 2.1 0 1.6-1.1 2.8-2.7 2.8-1.2 0-1.8-.5-2.5-1.4l-5.8-7.9-5.7 7.7c-.7 1-1.4 1.6-2.6 1.6-1.2 0-2.5-1-2.5-2.6 0-.8.3-1.5.8-2.2l6.7-8.5-6.3-7.9c-.4-.6-.8-1.3-.8-2.1 0-1.6 1.1-2.8 2.7-2.8 1.2 0 1.8.5 2.5 1.4l5.4 7.5 5.4-7.4zm-118.1.3c.4-.9 1.3-1.8 2.6-1.8 1.5 0 2.7 1.2 2.7 2.7 0 .4-.1.9-.3 1.3l-8.1 20c-.6 1.4-1.6 2.3-3.2 2.3-1.7 0-2.7-.9-3.3-2.3l-8-19.8c-.2-.4-.3-.9-.3-1.4 0-1.6 1.2-2.8 2.7-2.8 1.4 0 2.3.9 2.8 2l6.1 16.5 6.3-16.7zm82.6-1.6h13.7c1.3 0 2.4 1.1 2.4 2.6 0 1.4-1.1 2.5-2.4 2.5h-11v5.2h9.4c1.3 0 2.4 1.1 2.4 2.6 0 1.4-1.1 2.5-2.4 2.5h-9.4V31H165c1.3 0 2.4 1.1 2.4 2.6 0 1.4-1.1 2.5-2.4 2.5h-13.9c-1.5 0-2.7-1.2-2.7-2.8v-20c0-1.7 1.2-3 2.7-3zm-23.6 0h15.9c1.4 0 2.5 1.2 2.5 2.6s-1.1 2.6-2.5 2.6h-5.2v17.7c0 1.6-1.2 2.8-2.7 2.8s-2.7-1.3-2.7-2.8V15.5h-5.2c-1.4 0-2.5-1.2-2.5-2.6-.1-1.4 1.1-2.6 2.4-2.6zM73.8 23.1c0-7.2 5.5-13.2 13.2-13.2 7.6 0 13.1 5.9 13.1 13.2s-5.5 13.3-13.2 13.3c-7.6 0-13.1-5.9-13.1-13.3zm5.7 0c0 4.4 3.1 8.1 7.5 8.1s7.4-3.5 7.4-8.1c0-4.3-3.1-8-7.5-8s-7.4 3.5-7.4 8zm26.2-12.8h8.6c3.1 0 5.6.9 7.2 2.6 1.4 1.4 2.1 3.4 2.1 5.8 0 4-1.9 6.6-4.9 7.9l3.8 4.7c.5.7.9 1.3.9 2.2 0 1.6-1.3 2.6-2.6 2.6-1.2 0-2-.6-2.7-1.5l-5.3-6.9h-4.3v5.6c0 1.6-1.2 2.8-2.7 2.8s-2.7-1.3-2.7-2.8V13.2c-.1-1.6 1.1-2.9 2.6-2.9zm2.7 5.1v7.3h5.5c2.6 0 4.2-1.5 4.2-3.6 0-2.5-1.6-3.6-4.3-3.6l-5.4-.1zM15.1 38.2c0-1.5 1.2-2.8 2.7-2.8 1.5 0 2.7 1.2 2.7 2.8 0 1.5-1.2 2.8-2.6 2.8-1.7-.1-2.8-1.3-2.8-2.8z"
            />
          </svg>
        </span>
      )

    case "4soft":
      return (
        <div className="flex items-center select-none">
          <span style={{ color: colors.accent, fontWeight: 900, fontSize: "20px" }}>4</span>
          <span style={{ color: colors.headerText, fontWeight: 700, fontSize: "20px" }}>soft</span>
        </div>
      )

    default:
      return (
        <span style={{ color: colors.headerText, fontWeight: 700, fontSize: "15px" }}>
          {brand.name}
        </span>
      )
  }
}
