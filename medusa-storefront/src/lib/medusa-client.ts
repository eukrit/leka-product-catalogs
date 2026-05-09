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
    hasMaterialFilter: true,
    productCount: 5062,
  },
  vinci: {
    name: "Vinci Play",
    slug: "vinci",
    description: "Playground Equipment",
    country: "Poland",
    color: "#970260",
    publishableKey: process.env.NEXT_PUBLIC_VINCI_PUBLISHABLE_KEY || "",
    hasCollections: true,
    hasPricing: false,
    productCount: 1096,
    // Vinci collections have no vendor prefix — filter out all other vendors' prefixed handles
    collectionPrefix: undefined,
  },
  berliner: {
    name: "Berliner Seilfabrik",
    slug: "berliner",
    description: "Rope Play Equipment",
    country: "Germany",
    color: "#182557",
    publishableKey: process.env.NEXT_PUBLIC_BERLINER_PUBLISHABLE_KEY || "",
    hasCollections: true,
    hasPricing: false,
    productCount: 466,
    collectionPrefix: "berliner-",
  },
  eurotramp: {
    name: "Eurotramp",
    slug: "eurotramp",
    description: "Premium Trampolines",
    country: "Germany",
    color: "#E54822",
    publishableKey: process.env.NEXT_PUBLIC_EUROTRAMP_PUBLISHABLE_KEY || "",
    hasCollections: false,
    hasPricing: false,
    productCount: 80,
  },
  rampline: {
    name: "Rampline",
    slug: "rampline",
    description: "Motor Skill Playground Equipment",
    country: "Norway",
    color: "#970260",
    publishableKey: process.env.NEXT_PUBLIC_RAMPLINE_PUBLISHABLE_KEY || "",
    hasCollections: false,
    hasPricing: true,
    productCount: 54,
  },
  "4soft": {
    name: "4soft",
    slug: "4soft",
    description: "EPDM Playground Surfaces & 3D Elements",
    country: "Czech Republic",
    color: "#FFA900",
    publishableKey: process.env.NEXT_PUBLIC_4SOFT_PUBLISHABLE_KEY || "",
    hasCollections: true,
    hasPricing: false,
    productCount: 391,
    collectionPrefix: "4soft-",
  },
  vortex: {
    name: "Vortex Aquatics",
    slug: "vortex",
    description: "Splashpads, Waterslides & Aquatic Play Structures",
    country: "Canada",
    color: "#153cba",
    publishableKey: process.env.NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY || "",
    hasCollections: true,
    hasPricing: false,
    productCount: 521,
    collectionPrefix: "vortex-",
  },
  weplay: {
    name: "Weplay",
    slug: "weplay",
    description: "Sensory & Educational Play Equipment",
    country: "Taiwan",
    color: "#C7161E",
    publishableKey: process.env.NEXT_PUBLIC_WEPLAY_PUBLISHABLE_KEY || "",
    hasCollections: true,
    hasPricing: false,
    productCount: 0,
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
  /** Show price-range + material filters in the catalog filter bar (Wisdom only today). */
  hasMaterialFilter?: boolean
  productCount?: number
  // Prefix used to filter Medusa collections to this brand's own series.
  // undefined = show all unprefixed collections (i.e. Vinci — no vendor prefix).
  // "" = show nothing (hasCollections: false brands never reach this).
  // "berliner-" / "4soft-" / "vortex-" = strict prefix match.
  collectionPrefix?: string
}

export function getBrand(slug: string): BrandConfig | undefined {
  return BRANDS[slug]
}
