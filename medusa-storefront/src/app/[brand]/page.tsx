import type { Metadata } from "next"
import { getBrand } from "@/lib/medusa-client"
import CatalogPageClient from "./catalog-content"

interface Props {
  params: Promise<{ brand: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { brand: brandSlug } = await params
  const brand = getBrand(brandSlug)
  if (!brand) return {}

  return {
    title: `${brand.name} — Leka Product Catalogs`,
    description: `Browse ${brand.description.toLowerCase()} from ${brand.name} (${brand.country}). Powered by Leka.`,
    openGraph: {
      title: `${brand.name} Product Catalog`,
      description: `${brand.description} from ${brand.country}`,
      type: "website",
    },
  }
}

export default async function CatalogPage({ params }: Props) {
  const { brand: brandSlug } = await params
  return <CatalogPageClient brandSlug={brandSlug} />
}
