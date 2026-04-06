import type { Metadata } from "next"
import { getBrand } from "./medusa-client"

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://catalogs.leka.studio"

export function brandMetadata(brandSlug: string): Metadata {
  const brand = getBrand(brandSlug)
  if (!brand) return {}
  return {
    title: `${brand.name} — Leka Product Catalogs`,
    description: `Browse ${brand.description.toLowerCase()} from ${brand.name} (${brand.country}). Powered by Leka.`,
    openGraph: {
      title: `${brand.name} Product Catalog`,
      description: brand.description,
      type: "website",
      url: `${BASE_URL}/${brand.slug}`,
    },
  }
}

export function productMetadata(product: {
  title: string
  handle: string
  description: string | null
  images: Array<{ url: string }>
  variants: Array<{ sku: string; prices: Array<{ amount: number; currency_code: string }> }>
  metadata: Record<string, unknown>
}, brandSlug: string): Metadata {
  const brand = getBrand(brandSlug)
  const price = product.variants?.[0]?.prices?.find((p) => p.currency_code === "usd")
  const imageUrl = product.images?.[0]?.url

  return {
    title: `${product.title} — ${brand?.name || "Leka"}`,
    description: product.description || `${product.title} from ${brand?.name}`,
    openGraph: {
      title: product.title,
      description: product.description || undefined,
      type: "website",
      url: `${BASE_URL}/${brandSlug}/${product.handle}`,
      images: imageUrl ? [{ url: imageUrl, alt: product.title }] : undefined,
    },
  }
}

export function productJsonLd(product: {
  title: string
  handle: string
  description: string | null
  images: Array<{ url: string }>
  variants: Array<{ sku: string; prices: Array<{ amount: number; currency_code: string }> }>
}, brandSlug: string) {
  const price = product.variants?.[0]?.prices?.find((p) => p.currency_code === "usd")
  const imageUrl = product.images?.[0]?.url

  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.title,
    description: product.description,
    image: imageUrl,
    sku: product.variants?.[0]?.sku,
    url: `${BASE_URL}/${brandSlug}/${product.handle}`,
    ...(price
      ? {
          offers: {
            "@type": "Offer",
            price: (price.amount / 100).toFixed(2),
            priceCurrency: price.currency_code.toUpperCase(),
            availability: "https://schema.org/InStock",
          },
        }
      : {}),
  }
}
