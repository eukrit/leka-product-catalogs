/**
 * Seed Medusa v2 from Firestore JSON exports.
 *
 * Usage:
 *   1. Run scripts/export_firestore_to_json.py to generate migration/*.json
 *      (wisdom_products.json, vinci_products.json, optional vortex_products.json)
 *   2. npx medusa exec ./src/scripts/seed-from-firestore.ts
 *
 * Creates:
 *   - ONE Sales Channel "Leka Catalogs" (shared across brands so the cart
 *     is no longer brand-scoped — a customer can put Wisdom + Vinci + Vortex
 *     items in the same cart and send one combined proposal).
 *   - Three Brand records (Wisdom, Vinci Play, Vortex Aquatics) via the
 *     custom brand module (src/modules/brand/).
 *   - Product Categories + Collections + Tags from the Firestore exports.
 *   - All products published to "Leka Catalogs" AND linked to their Brand
 *     via the brand-product module link (src/links/brand-product.ts).
 *   - ONE publishable API key "Leka Catalogs Storefront" used by all
 *     per-brand landing pages in eukrit/leka-website/catalogs/.
 *
 * Idempotency note: this seed creates fresh resources on every run. Re-running
 * against a non-empty DB will produce duplicate categories/tags. Wipe the DB
 * (npx medusa db:reset) before re-seeding — the wipe+reseed migration path is
 * documented in CHANGELOG.md under v2.49.0.
 */
import * as fs from "fs"
import * as path from "path"
import {
  ExecArgs,
  IProductModuleService,
  ISalesChannelModuleService,
} from "@medusajs/framework/types"
import { ContainerRegistrationKeys, Modules } from "@medusajs/framework/utils"
import { BRAND_MODULE } from "../modules/brand"

const MIGRATION_DIR = path.resolve(__dirname, "../../../migration")

const BRAND_DEFINITIONS: Array<{
  handle: string
  name: string
  description: string
}> = [
  {
    handle: "wisdom",
    name: "Wisdom",
    description: "Wisdom Playground Equipment — furniture, playground, outdoor",
  },
  {
    handle: "vinci",
    name: "Vinci Play",
    description: "Vinci Play — playground equipment from Poland",
  },
  {
    handle: "vortex",
    name: "Vortex Aquatics",
    description: "Vortex Aquatics — splash-pad and water-play features",
  },
]

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
  const brandService: any = container.resolve(BRAND_MODULE)
  const link = container.resolve(ContainerRegistrationKeys.LINK)

  console.log("=== Leka Product Catalogs — Medusa Seed ===\n")

  // --- Step 1: Sales Channel ---
  // ONE shared sales channel for all brands. Brand is no longer a cart-
  // scoping construct — it's a product attribute (see Step 1b). This is
  // what lets a single cart carry products from Wisdom + Vinci + Vortex
  // at the same time.
  console.log("Step 1: Creating Sales Channel 'Leka Catalogs'...")
  const lekaChannel = await salesChannelService.createSalesChannels({
    name: "Leka Catalogs",
    description:
      "Public storefront for all Leka catalog brands (Wisdom, Vinci Play, Vortex). " +
      "Single SC so the cart can mix products across brands.",
    is_disabled: false,
  })
  console.log(`  Created: Leka Catalogs (${lekaChannel.id})`)

  // --- Step 1b: Brand records ---
  // Each brand becomes a Brand entity linked to its products via the
  // brand-product module link. Replaces the previous "one SC per brand"
  // pattern. Idempotent: if a brand already exists by handle, reuse it
  // (this lets us re-run the seed without unique-constraint errors).
  console.log("\nStep 1b: Creating Brand records...")
  const brandMap: Record<string, string> = {}
  for (const def of BRAND_DEFINITIONS) {
    const [existing] = await brandService.listBrands({ handle: def.handle })
    let brand = existing
    if (!brand) {
      brand = await brandService.createBrands({
        handle: def.handle,
        name: def.name,
        description: def.description,
      })
    }
    brandMap[def.handle] = brand.id
    console.log(`  Brand: ${def.name} (${brand.id}) [handle: ${def.handle}]`)
  }

  // --- Step 2: Product Categories ---
  console.log("\nStep 2: Creating Product Categories...")
  const allCategories = new Set<string>()
  const wisdomProducts = loadJson<FirestoreProduct>("wisdom_products.json")
  const vinciProducts = loadJson<FirestoreProduct>("vinci_products.json")
  // Vortex is optional — seed still completes if the JSON isn't generated yet
  // (the Brand record + /vortex landing page will exist regardless so the
  // storefront can render "Coming soon" without 404ing).
  const vortexProducts = loadJson<FirestoreProduct>("vortex_products.json")

  for (const p of [...wisdomProducts, ...vinciProducts, ...vortexProducts]) {
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
  for (const p of [...wisdomProducts, ...vinciProducts, ...vortexProducts]) {
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
      // Publish to the single shared sales channel so the cart accepts
      // this product regardless of brand.
      sales_channels: [{ id: lekaChannel.id }],
    }

    // Associate category
    if (p.category && categoryMap[p.category]) {
      productData.categories = [{ id: categoryMap[p.category] }]
    }

    // Associate collection (Vinci series)
    if (p.series_slug && collectionMap[p.series_slug]) {
      productData.collection_id = collectionMap[p.series_slug]
    }

    const product = await productService.createProducts(productData as any) as any
    const productId = Array.isArray(product) ? product[0]?.id : product.id

    // Link the product to its Brand via the brand-product module link.
    // This is what powers the storefront brand filter (Medusa query
    // graph: `GET /store/products?fields=+brand.*&filters[brand][handle]=wisdom`)
    // and the admin "Brand" column on the Products list.
    const brandId = brandMap[p.brand]
    if (productId && brandId) {
      await link.create({
        [BRAND_MODULE]: { brand_id: brandId },
        [Modules.PRODUCT]: { product_id: productId },
      })
    } else if (!brandId) {
      console.warn(`    No brand mapping for "${p.brand}" on ${p.item_code} — skipped brand link`)
    }

    return productId
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

  // Import Vortex products (optional — skipped if vortex_products.json absent)
  let vortexCount = 0
  if (vortexProducts.length > 0) {
    console.log(`\n  Importing ${vortexProducts.length} Vortex products...`)
    for (const p of vortexProducts) {
      try {
        await importProduct(p)
        vortexCount++
        if (vortexCount % 100 === 0) {
          console.log(`    ${vortexCount} / ${vortexProducts.length}`)
        }
      } catch (err: any) {
        console.error(`    Error importing ${p.item_code}: ${err.message}`)
      }
    }
    console.log(`  Done: ${vortexCount} Vortex products imported`)
  } else {
    console.log(`\n  Skipping Vortex (vortex_products.json not found)`)
  }

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

  // Create ONE publishable API key for the shared Leka Catalogs storefront.
  // Replaces the previous per-brand keys — the storefront now uses a single
  // key across /wisdom, /vinci, /vortex landing pages so the cart cookie is
  // shared and items from any brand can sit in the same cart.
  const apiKeyService = container.resolve(Modules.API_KEY)
  try {
    const storefrontKey = await (apiKeyService as any).createApiKeys({
      title: "Leka Catalogs Storefront",
      type: "publishable",
    })
    console.log(`  Publishable Key:`)
    console.log(`    Leka Catalogs Storefront: ${storefrontKey.token}`)
    console.log(`  >> Copy this key to eukrit/leka-website/catalogs/.env.local`)
    console.log(`     as NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY (single key for all brands)`)
  } catch (err: any) {
    console.log(`  API Key setup skipped: ${err.message}`)
  }

  // --- Step 7: B2B Customer Groups ---
  console.log("\nStep 7: Creating B2B Customer Groups...")
  const customerService = container.resolve(Modules.CUSTOMER)
  try {
    const groups = [
      { name: "Dealer", metadata: { discount_pct: 15 } },
      { name: "Distributor", metadata: { discount_pct: 25 } },
      { name: "Retail", metadata: { discount_pct: 0 } },
    ]
    for (const g of groups) {
      await (customerService as any).createCustomerGroups({
        name: g.name,
        metadata: g.metadata,
      })
      console.log(`  Group: ${g.name} (${g.metadata.discount_pct}% discount)`)
    }
  } catch (err: any) {
    console.log(`  Customer groups skipped: ${err.message}`)
  }

  // --- Summary ---
  const totalProducts = wisdomCount + vinciCount + vortexCount
  console.log("\n=== Seed Complete ===")
  console.log(`  Sales Channels: 1 (Leka Catalogs — shared across all brands)`)
  console.log(`  Brands: ${Object.keys(brandMap).length} (${BRAND_DEFINITIONS.map((b) => b.name).join(", ")})`)
  console.log(`  Categories: ${allCategories.size}`)
  console.log(`  Collections: ${seriesSlugs.size}`)
  console.log(`  Tags: ${allTags.size}`)
  console.log(
    `  Products: ${totalProducts} ` +
      `(Wisdom: ${wisdomCount}, Vinci: ${vinciCount}, Vortex: ${vortexCount})`
  )
  console.log(`  Region: Asia-Pacific (USD, 5 countries)`)
  console.log(`  Customer Groups: 3 (Dealer, Distributor, Retail)`)
  console.log(
    `\n  NOTE: cart is now multi-brand by design. The storefront's single ` +
      `publishable key + shared cart cookie lets customers add Wisdom + Vinci ` +
      `+ Vortex products to the same cart and send one combined proposal.`
  )
}
