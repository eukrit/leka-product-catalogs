import type { Metadata } from "next"
import { getBrand } from "@/lib/medusa-client"
import { brandMetadata } from "@/lib/seo"
import ProductDetailClient from "./product-detail"

interface Props {
  params: Promise<{ brand: string; handle: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { brand: brandSlug, handle } = await params
  const brand = getBrand(brandSlug)
  if (!brand) return {}

  // Format handle into a readable title for SEO
  const title = handle
    .replace(/^(berliner-|eurotramp-|rampline-|4soft-)/, "")
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")

  return {
    title: `${title} — ${brand.name} | Leka Catalogs`,
    description: `${title} from ${brand.name} (${brand.country}). View specifications, images, downloads, and pricing.`,
    openGraph: {
      title: `${title} — ${brand.name}`,
      description: `${title} from ${brand.name}`,
      type: "website",
    },
  }
}

export default async function ProductDetailPage({ params }: Props) {
  const { brand: brandSlug, handle } = await params
  return <ProductDetailClient brandSlug={brandSlug} handle={handle} />
}
