/**
 * Seed Medusa v2 from Firestore JSON exports.
 *
 * Usage:
 *   1. Run scripts/export_firestore_to_json.py to generate migration/*.json
 *   2. npx medusa exec ./src/scripts/seed-from-firestore.ts
 *
 * Creates: Sales Channels, Categories, Collections, Tags, Products + Variants
 */
import * as fs from "fs"
import * as path from "path"
import {
  ExecArgs,
  IProductModuleService,
  ISalesChannelModuleService,
} from "@medusajs/framework/types"
import { Modules } from "@medusajs/framework/utils"

const MIGRATION_DIR = path.resolve(__dirname, "../../../migration")

interface FirestoreProduct {
  item_code: string
  brand: string
  name?: string
  description?: string
  description_cn?: string
  description_th?: string
  category?: string
  subcategory?: string
  series_slug?: string
  series_name?: string
  material?: string
  dimensions?: {
    raw?: string
    length_cm?: number
    width_cm?: number
    height_cm?: number
  }
  volume_cbm?: number
  weight_kg?: number
  pricing?: {
    fob_usd?: number
    currency?: string
    price_date?: string
  }
  specifications?: Record<string, unknown>
  images?: Array<{
    url: string
    alt_text?: string
    is_primary?: boolean
    source?: string
    view_type?: string
  }>
  downloads?: Array<{
    type: string
    format: string
    url: string
    label: string
  }>
  certifications?: string[]
  tags?: string[]
  source_url?: string
  status?: string
  catalog_page?: number
  catalog_source?: string
}

function loadJson<T>(filename: string): T[] {
  const filepath = path.join(MIGRATION_DIR, filename)
  if (!fs.existsSync(filepath)) {
    console.warn(`File not found: ${filepath} — skipping`)
    return []
  }
  return JSON.parse(fs.readFileSync(filepath, "utf-8"))
}

export default async function seedFromFirestore({ container }: ExecArgs) {
  const productService: IProductModuleService = container.resolve(Modules.PRODUCT)
  const salesChannelService: ISalesChannelModuleService = container.resolve(
    Modules.SALES_CHANNEL
  )

  console.log("=== Leka Product Catalogs — Medusa Seed ===\n")

  // --- Step 1: Sales Channels ---
  console.log("Step 1: Creating Sales Channels...")
  const wisdomChannel = await salesChannelService.createSalesChannels({
    name: "Wisdom",
    description: "Wisdom Playground Equipment — furniture, playground, outdoor",
    is_disabled: false,
  })
  const vinciChannel = await salesChannelService.createSalesChannels({
    name: "Vinci Play",
    description: "Vinci Play — playground equipment from Poland",
    is_disabled: false,
  })
  console.log(`  Created: Wisdom (${wisdomChannel.id}), Vinci Play (${vinciChannel.id})`)

  const channelMap: Record<string, string> = {
    wisdom: wisdomChannel.id,
    vinci: vinciChannel.id,
  }

  // --- Step 2: Product Categories ---
  console.log("\nStep 2: Creating Product Categories...")
  const allCategories = new Set<string>()
  const wisdomProducts = loadJson<FirestoreProduct>("wisdom_products.json")
  const vinciProducts = loadJson<FirestoreProduct>("vinci_products.json")

  for (const p of [...wisdomProducts, ...vinciProducts]) {
    if (p.category) allCategories.add(p.category)
  }

  const categoryMap: Record<string, string> = {}
  for (const catName of allCategories) {
    const displayName = catName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    const category = await productService.createProductCategories({
      name: displayName,
      handle: catName,
      is_active: true,
      is_internal: false,
    })
    categoryMap[catName] = category.id
    console.log(`  Category: ${displayName} (${category.id})`)
  }

  // --- Step 3: Product Collections (Vinci series) ---
  console.log("\nStep 3: Creating Product Collections (Vinci series)...")
  const seriesSlugs = new Set<string>()
  const seriesNames: Record<string, string> = {}
  for (const p of vinciProducts) {
    if (p.series_slug) {
      seriesSlugs.add(p.series_slug)
      if (p.series_name) seriesNames[p.series_slug] = p.series_name
    }
  }

  const collectionMap: Record<string, string> = {}
  for (const slug of seriesSlugs) {
    const name = seriesNames[slug] || slug.toUpperCase()
    const collection = await productService.createProductCollections({
      title: name,
      handle: slug,
    })
    collectionMap[slug] = collection.id
    console.log(`  Collection: ${name} (${collection.id})`)
  }

  // --- Step 4: Product Tags ---
  console.log("\nStep 4: Creating Product Tags...")
  const allTags = new Set<string>()
  for (const p of [...wisdomProducts, ...vinciProducts]) {
    for (const tag of p.tags || []) {
      allTags.add(tag)
    }
  }

  const tagMap: Record<string, string> = {}
  for (const tagName of allTags) {
    const tag = await productService.createProductTags({ value: tagName })
    tagMap[tagName] = tag.id
  }
  console.log(`  Created ${allTags.size} tags`)

  // --- Step 5: Import Products ---
  console.log("\nStep 5: Importing products...")

  async function importProduct(p: FirestoreProduct) {
    const handle = `${p.brand}-${p.item_code}`.toLowerCase().replace(/[^a-z0-9-]/g, "-")
    const status = p.status === "active" ? "published" : "draft"

    // Build metadata
    const metadata: Record<string, unknown> = {}
    if (p.description_cn) metadata.description_cn = p.description_cn
    if (p.description_th) metadata.description_th = p.description_th
    if (p.specifications) metadata.specifications = p.specifications
    if (p.downloads) metadata.downloads = p.downloads
    if (p.certifications) metadata.certifications = p.certifications
    if (p.source_url) metadata.source_url = p.source_url
    if (p.catalog_page) metadata.catalog_page = p.catalog_page
    if (p.catalog_source) metadata.catalog_source = p.catalog_source
    if (p.material) metadata.material = p.material
    if (p.volume_cbm) metadata.volume_cbm = p.volume_cbm
    if (p.series_slug) metadata.series_slug = p.series_slug
    if (p.series_name) metadata.series_name = p.series_name

    // Build images
    const images = (p.images || []).map((img) => ({
      url: img.url,
    }))

    // Build tags
    const tags = (p.tags || [])
      .filter((t) => tagMap[t])
      .map((t) => ({ id: tagMap[t] }))

    // Build variant
    const dims = p.dimensions || {}
    const variant = {
      title: "Default",
      sku: p.item_code,
      manage_inventory: false,
      length: dims.length_cm || undefined,
      width: dims.width_cm || undefined,
      height: dims.height_cm || undefined,
      weight: p.weight_kg || undefined,
      metadata: {
        volume_cbm: p.volume_cbm,
      },
      prices: [] as Array<{ amount: number; currency_code: string }>,
    }

    // Add pricing for Wisdom products
    if (p.pricing?.fob_usd) {
      variant.prices.push({
        amount: Math.round(p.pricing.fob_usd * 100),
        currency_code: "usd",
      })
    }

    const productData: Record<string, unknown> = {
      title: p.name || p.description || p.item_code,
      handle,
      description: p.description || "",
      status,
      metadata,
      images,
      tags,
      variants: [variant],
    }

    // Associate category
    if (p.category && categoryMap[p.category]) {
      productData.categories = [{ id: categoryMap[p.category] }]
    }

    // Associate collection (Vinci series)
    if (p.series_slug && collectionMap[p.series_slug]) {
      productData.collection_id = collectionMap[p.series_slug]
    }

    const product = await productService.createProducts(productData as any)
    return product.id
  }

  // Import Wisdom products
  console.log(`\n  Importing ${wisdomProducts.length} Wisdom products...`)
  let wisdomCount = 0
  for (const p of wisdomProducts) {
    try {
      await importProduct(p)
      wisdomCount++
      if (wisdomCount % 500 === 0) {
        console.log(`    ${wisdomCount} / ${wisdomProducts.length}`)
      }
    } catch (err: any) {
      console.error(`    Error importing ${p.item_code}: ${err.message}`)
    }
  }
  console.log(`  Done: ${wisdomCount} Wisdom products imported`)

  // Import Vinci products
  console.log(`\n  Importing ${vinciProducts.length} Vinci products...`)
  let vinciCount = 0
  for (const p of vinciProducts) {
    try {
      await importProduct(p)
      vinciCount++
      if (vinciCount % 200 === 0) {
        console.log(`    ${vinciCount} / ${vinciProducts.length}`)
      }
    } catch (err: any) {
      console.error(`    Error importing ${p.item_code}: ${err.message}`)
    }
  }
  console.log(`  Done: ${vinciCount} Vinci products imported`)

  // --- Step 6: Region, Fulfillment, Payment ---
  console.log("\nStep 6: Setting up Region, Fulfillment, and Payment...")

  const regionService = container.resolve(Modules.REGION)
  const fulfillmentService = container.resolve(Modules.FULFILLMENT)
  const paymentService = container.resolve(Modules.PAYMENT)

  // Create region for Asia-Pacific (THB + USD)
  const region = await (regionService as any).createRegions({
    name: "Asia-Pacific",
    currency_code: "usd",
    countries: ["th", "cn", "sg", "pl", "us"],
    payment_providers: ["pp_system_default"],
  })
  console.log(`  Region: Asia-Pacific (${region.id})`)

  // Create shipping option (manual fulfillment)
  try {
    const shippingProfile = await (fulfillmentService as any).createShippingProfiles({
      name: "Default",
      type: "default",
    })

    await (fulfillmentService as any).createShippingOptions({
      name: "Standard Shipping",
      price_type: "flat",
      service_zone_id: undefined,
      shipping_profile_id: shippingProfile.id,
      provider_id: "manual",
      type: { label: "Standard", description: "Standard shipping", code: "standard" },
      data: {},
      prices: [{ amount: 0, currency_code: "usd" }],
    })
    console.log("  Shipping: Standard Shipping (free)")
  } catch (err: any) {
    console.log(`  Shipping setup skipped: ${err.message}`)
  }

  // Create Publishable API Keys for each sales channel
  const apiKeyService = container.resolve(Modules.API_KEY)
  try {
    const wisdomKey = await (apiKeyService as any).createApiKeys({
      title: "Wisdom Storefront",
      type: "publishable",
    })
    const vinciKey = await (apiKeyService as any).createApiKeys({
      title: "Vinci Play Storefront",
      type: "publishable",
    })
    console.log(`  Publishable Keys:`)
    console.log(`    Wisdom: ${wisdomKey.token}`)
    console.log(`    Vinci:  ${vinciKey.token}`)
    console.log(`  >> Copy these keys to medusa-storefront/.env.local`)
  } catch (err: any) {
    console.log(`  API Key setup skipped: ${err.message}`)
  }

  // --- Summary ---
  console.log("\n=== Seed Complete ===")
  console.log(`  Sales Channels: 2 (Wisdom, Vinci Play)`)
  console.log(`  Categories: ${allCategories.size}`)
  console.log(`  Collections: ${seriesSlugs.size}`)
  console.log(`  Tags: ${allTags.size}`)
  console.log(`  Products: ${wisdomCount + vinciCount} (Wisdom: ${wisdomCount}, Vinci: ${vinciCount})`)
  console.log(`  Region: Asia-Pacific (USD, 5 countries)`)
}
