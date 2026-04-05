import Medusa from "@medusajs/js-sdk"

const BACKEND_URL = process.env.NEXT_PUBLIC_MEDUSA_BACKEND_URL || "http://localhost:9000"

export const medusa = new Medusa({
  baseUrl: BACKEND_URL,
  debug: process.env.NODE_ENV === "development",
})

// Brand configuration — maps URL slugs to Sales Channel publishable keys
export const BRANDS: Record<string, BrandConfig> = {
  wisdom: {
    name: "Wisdom",
    slug: "wisdom",
    description: "Playground & Furniture Equipment",
    country: "China",
    color: "#8003FF",
    publishableKey: process.env.NEXT_PUBLIC_WISDOM_PUBLISHABLE_KEY || "",
    hasCollections: false,
    hasPricing: true,
  },
  vinciplay: {
    name: "Vinci Play",
    slug: "vinciplay",
    description: "Playground Equipment",
    country: "Poland",
    color: "#970260",
    publishableKey: process.env.NEXT_PUBLIC_VINCI_PUBLISHABLE_KEY || "",
    hasCollections: true,
    hasPricing: false,
  },
}

export interface BrandConfig {
  name: string
  slug: string
  description: string
  country: string
  color: string
  publishableKey: string
  hasCollections: boolean
  hasPricing: boolean
}

export function getBrand(slug: string): BrandConfig | undefined {
  return BRANDS[slug]
}
