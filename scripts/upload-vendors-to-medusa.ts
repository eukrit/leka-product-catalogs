/**
 * Upload scraped vendor products to Leka Medusa
 *
 * Usage:
 *   npx tsx scripts/upload-vendors-to-medusa.ts --vendor berliner [--dry-run] [--limit N]
 *   npx tsx scripts/upload-vendors-to-medusa.ts --vendor eurotramp
 *   npx tsx scripts/upload-vendors-to-medusa.ts --vendor rampline
 *   npx tsx scripts/upload-vendors-to-medusa.ts --vendor 4soft
 *   npx tsx scripts/upload-vendors-to-medusa.ts --vendor all
 *
 * Leka Medusa has NO Brand module — brand info goes into product.metadata
 */

import * as fs from "fs"
import * as path from "path"

// ── Leka Medusa Config ───────────────────────────────────────────────────
const MEDUSA_URL = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
const ADMIN_EMAIL = "admin@leka.studio"
const ADMIN_PASSWORD = "LekaAdmin2026"

// Leka sales channels — playground equipment goes to a new dedicated channel
// or to the Wisdom channel for now
const SALES_CHANNEL_WISDOM = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
const SALES_CHANNEL_VINCI = "sc_01KNKTHC77716EPCE3E2BKAMQP"

const DATA_DIR = path.resolve(__dirname, "../data/scraped")

const args = process.argv.slice(2)
const DRY_RUN = args.includes("--dry-run")
const RETRY_ERRORS = args.includes("--retry-errors")
const vendorIdx = args.indexOf("--vendor")
const VENDOR = vendorIdx >= 0 ? args[vendorIdx + 1] : null
const limitIdx = args.indexOf("--limit")
const LIMIT = limitIdx >= 0 ? parseInt(args[limitIdx + 1]) : Infinity

if (!VENDOR) {
  console.error("Usage: npx tsx scripts/upload-vendors-to-medusa.ts --vendor <berliner|eurotramp|rampline|4soft|all>")
  process.exit(1)
}

// ── Vendor Configs ───────────────────────────────────────────────────────

interface VendorConfig {
  slug: string
  name: string
  country: string
  description: string
  inputFile: string
  salesChannel: string
  buildPayload: (p: any, catMap: Record<string, string>, collMap: Record<string, string>) => any
}

const VENDORS: Record<string, VendorConfig> = {
  berliner: {
    slug: "berliner",
    name: "Berliner Seilfabrik",
    country: "Germany",
    description: "World leader in rope play equipment since 1865",
    inputFile: path.join(DATA_DIR, "berliner/products.json"),
    salesChannel: SALES_CHANNEL_WISDOM,
    buildPayload: buildBerlinerPayload,
  },
  eurotramp: {
    slug: "eurotramp",
    name: "Eurotramp",
    country: "Germany",
    description: "Premium trampoline manufacturer, Olympic supplier",
    inputFile: path.join(DATA_DIR, "eurotramp/products.json"),
    salesChannel: SALES_CHANNEL_WISDOM,
    buildPayload: buildEurotrampPayload,
  },
  rampline: {
    slug: "rampline",
    name: "Rampline",
    country: "Norway",
    description: "Innovative motor skill playground equipment",
    inputFile: path.join(DATA_DIR, "rampline/products.json"),
    salesChannel: SALES_CHANNEL_WISDOM,
    buildPayload: buildRamplinePayload,
  },
  "4soft": {
    slug: "4soft",
    name: "4soft",
    country: "Czech Republic",
    description: "EPDM playground surfaces, 3D elements, tunnels, furniture",
    inputFile: path.join(DATA_DIR, "4soft/products.json"),
    salesChannel: SALES_CHANNEL_WISDOM,
    buildPayload: build4softPayload,
  },
}

// ── Handle & SKU Helpers ────────────────────────────────────────────────

/** Sanitize handle: collapse multiple hyphens, trim leading/trailing hyphens */
function sanitizeHandle(handle: string): string {
  return handle.replace(/-{2,}/g, "-").replace(/^-|-$/g, "")
}

/** Track used SKUs to deduplicate within a vendor upload */
const usedSkus = new Set<string>()

/** Make a SKU unique — if already used, append the product handle */
function uniqueSku(sku: string, handle: string): string {
  if (!usedSkus.has(sku)) {
    usedSkus.add(sku)
    return sku
  }
  const deduped = `${sku}-${handle}`
  usedSkus.add(deduped)
  return deduped
}

// ── API Helpers ──────────────────────────────────────────────────────────

let authToken = ""

async function authenticate() {
  const res = await fetch(`${MEDUSA_URL}/auth/user/emailpass`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
  })
  if (!res.ok) throw new Error(`Auth failed: ${res.status}`)
  const data = await res.json()
  authToken = data.token
}

async function medusaFetch(endpoint: string, options: RequestInit = {}) {
  const res = await fetch(`${MEDUSA_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
      ...(options.headers as Record<string, string> || {}),
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json()
}

// ── Shared: Categories & Collections ─────────────────────────────────────

async function ensureCategories(handles: string[]): Promise<Record<string, string>> {
  const map: Record<string, string> = {}
  for (const handle of [...new Set(handles)]) {
    if (!handle) continue
    const displayName = handle.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    try {
      const res = await medusaFetch("/admin/product-categories", {
        method: "POST",
        body: JSON.stringify({ name: displayName, handle, is_active: true, is_internal: false }),
      })
      map[handle] = res.product_category.id
      console.log(`  Created category: ${displayName}`)
    } catch {
      try {
        const existing = await medusaFetch(`/admin/product-categories?handle=${handle}`)
        if (existing.product_categories?.length) {
          map[handle] = existing.product_categories[0].id
        }
      } catch {}
    }
  }
  return map
}

async function ensureCollections(names: string[]): Promise<Record<string, string>> {
  const map: Record<string, string> = {}
  for (const name of [...new Set(names)]) {
    if (!name) continue
    const handle = name.toLowerCase().replace(/[^a-z0-9]+/g, "-")
    try {
      const res = await medusaFetch("/admin/collections", {
        method: "POST",
        body: JSON.stringify({ title: name, handle }),
      })
      map[name] = res.collection.id
      console.log(`  Created collection: ${name}`)
    } catch {
      try {
        const existing = await medusaFetch(`/admin/collections?handle=${handle}`)
        if (existing.collections?.length) map[name] = existing.collections[0].id
      } catch {}
    }
  }
  return map
}

// ── Payload Builders (brand in metadata, not module) ─────────────────────

function buildBerlinerPayload(p: any, catMap: Record<string, string>, collMap: Record<string, string>) {
  const metadata = {
    brand_slug: "berliner",
    brand_name: "Berliner Seilfabrik",
    brand_country: "Germany",
    vendor_sku: p.sku || "",
    vendor_url: p.vendor_url || "",
    product_group: p.product_group || "",
    length_cm: p.dimensions?.length_cm || 0,
    width_cm: p.dimensions?.width_cm || 0,
    height_cm: p.dimensions?.height_cm || 0,
    fall_height_cm: p.fall_height_cm || 0,
    safety_zone_en: p.safety_zone_en || {},
    safety_zone_astm: p.safety_zone_astm || {},
    max_users: p.max_users || 0,
    age_group: p.age_group || "3+",
    certifications: p.certifications || [],
    materials: ["rope", "steel", "aluminum"],
    downloads: (p.downloads || []).map((d: any) => ({ type: d.type, filename: d.filename, original_url: d.url })),
    related_products: p.related_products || [],
    taxonomies: p.taxonomies || {},
    vendor_data: p.raw_specs || {},
  }

  const collName = p.product_group ? `Berliner ${p.product_group}` : ""

  return {
    title: p.title,
    handle: p.handle,
    status: "draft",
    description: p.description || "",
    thumbnail: p.thumbnail_url || undefined,
    images: (p.image_urls || []).map((url: string) => ({ url })),
    metadata,
    options: [{ title: "Default", values: ["Default"] }],
    variants: [{
      title: "Default",
      sku: uniqueSku(String(p.sku || p.handle), p.handle),
      manage_inventory: false,
      prices: [{ amount: 0, currency_code: "usd" }],
      options: { Default: "Default" },
      metadata: { vendor_sku: p.sku, dimensions: p.dimensions },
    }],
    ...(p.category && catMap[p.category] ? { categories: [{ id: catMap[p.category] }] } : {}),
    ...(collName && collMap[collName] ? { collection_id: collMap[collName] } : {}),
  }
}

function buildEurotrampPayload(p: any, catMap: Record<string, string>, collMap: Record<string, string>) {
  const metadata = {
    brand_slug: "eurotramp",
    brand_name: "Eurotramp",
    brand_country: "Germany",
    vendor_sku: p.sku || "",
    vendor_url: p.vendor_url || "",
    product_group: p.product_group || "",
    length_cm: p.dimensions?.length_cm || 0,
    width_cm: p.dimensions?.width_cm || 0,
    height_cm: p.dimensions?.height_cm || 0,
    weight_kg: p.weight_kg || 0,
    certifications: p.certifications || [],
    standards: p.standards || [],
    article_numbers: p.article_numbers || [],
    made_in: "Germany",
    is_discontinued: p.is_discontinued || false,
    downloads: (p.downloads || []).map((d: any) => ({ type: d.type, filename: d.filename, original_url: d.url })),
    faq: p.faq || [],
    vendor_data: p.raw_specs || {},
  }

  // Avoid multi-variant SKU conflicts — use handle-suffixed SKUs
  const articleNumbers = (p.article_numbers as string[]) || []
  const hasMulti = articleNumbers.length > 1

  return {
    title: p.title,
    handle: p.handle,
    status: "draft",
    description: p.description || "",
    thumbnail: p.thumbnail_url || undefined,
    images: (p.image_urls || []).map((url: string) => ({ url })),
    metadata,
    options: [{ title: "Default", values: ["Default"] }],
    variants: [{
      title: "Default",
      sku: uniqueSku(String(p.sku ? `ET-${p.sku}` : p.handle), p.handle),
      manage_inventory: false,
      prices: [{ amount: 0, currency_code: "usd" }],
      options: { Default: "Default" },
      metadata: { article_numbers: articleNumbers, weight_kg: p.weight_kg },
    }],
    ...(p.category && catMap[p.category] ? { categories: [{ id: catMap[p.category] }] } : {}),
  }
}

function buildRamplinePayload(p: any, catMap: Record<string, string>, collMap: Record<string, string>) {
  const metadata = {
    brand_slug: "rampline",
    brand_name: "Rampline",
    brand_country: "Norway",
    vendor_sku: String(p.sku || ""),
    vendor_url: p.vendor_url || "",
    product_group: p.product_group || "",
    height_cm: p.dimensions?.height_cm || 0,
    width_cm: p.dimensions?.width_cm || 0,
    depth_cm: p.dimensions?.depth_cm || 0,
    weight_kg: p.weight_kg || 0,
    fall_height_cm: p.fall_height_cm || 0,
    safety_zone_cm: p.safety_zone_cm || 0,
    certifications: p.certifications || [],
    materials: p.materials || [],
    installation: p.installation || {},
    is_park: p.is_park || false,
    ground_cover_options: p.ground_cover_options || [],
    downloads: (p.downloads || []).map((d: any) => ({ type: d.type, filename: d.filename, original_url: d.url })),
    vendor_data: p.raw_specs || {},
  }

  const prices: { amount: number; currency_code: string }[] = []
  if (p.pricing?.amount_nok > 0) {
    prices.push({ amount: Math.round(p.pricing.amount_nok * 100), currency_code: "nok" })
  } else {
    prices.push({ amount: 0, currency_code: "usd" })
  }

  return {
    title: p.title,
    handle: p.handle,
    status: "draft",
    description: p.description || p.short_description || "",
    thumbnail: p.thumbnail_url || undefined,
    images: (p.image_urls || []).map((url: string) => ({ url })),
    metadata,
    options: [{ title: "Default", values: ["Default"] }],
    variants: [{
      title: "Default",
      sku: String(p.sku || p.handle),
      manage_inventory: false,
      prices,
      options: { Default: "Default" },
      metadata: { vendor_sku: String(p.sku) },
    }],
    ...(p.category && catMap[p.category] ? { categories: [{ id: catMap[p.category] }] } : {}),
  }
}

function build4softPayload(p: any, catMap: Record<string, string>, collMap: Record<string, string>) {
  const TYPE_COLL: Record<string, string> = {
    "2D": "4soft 2D Graphics",
    "3D": "4soft 3D Elements",
    "ostatni": "4soft Tunnels & Furniture",
  }
  const collName = TYPE_COLL[p.product_type] || ""

  const metadata = {
    brand_slug: "4soft",
    brand_name: "4soft",
    brand_country: "Czech Republic",
    vendor_sku: p.sku || "",
    vendor_url: p.vendor_url || "",
    product_type: p.product_type || "",
    category_cz: p.category || "",
    subcategory_cz: p.subcategory || "",
    title_en: p.title_en || "",
    height_cm: p.dimensions?.height_cm || 0,
    width_cm: p.dimensions?.width_cm || 0,
    length_cm: p.dimensions?.length_cm || 0,
    area_m2: p.dimensions?.area_m2 || 0,
    weight_kg: p.weight_kg || 0,
    color_count: p.color_count || 0,
    colors: p.colors || [],
    is_bestseller: p.is_bestseller || false,
    is_new: p.is_new || false,
    vendor_data: p.raw || {},
  }

  const catHandle = p.subcategory || (p.product_type === "2D" ? "epdm-2d-graphics" : p.product_type === "3D" ? "epdm-3d-elements" : "epdm-accessories")

  return {
    title: p.title_en ? `${p.title} (${p.title_en})` : p.title,
    handle: p.handle,
    status: "draft",
    description: p.description || "",
    thumbnail: p.thumbnail_url || p.detail_image_url || undefined,
    images: (p.image_urls || []).map((url: string) => ({ url })),
    metadata,
    options: [{ title: "Default", values: ["Default"] }],
    variants: [{
      title: "Default",
      sku: String(p.sku || p.handle),
      manage_inventory: false,
      prices: [{ amount: 0, currency_code: "usd" }],
      options: { Default: "Default" },
      metadata: { vendor_sku: p.sku, weight_kg: p.weight_kg },
    }],
    ...(catHandle && catMap[catHandle] ? { categories: [{ id: catMap[catHandle] }] } : {}),
    ...(collName && collMap[collName] ? { collection_id: collMap[collName] } : {}),
  }
}

// ── Upload Logic ─────────────────────────────────────────────────────────

async function uploadVendor(config: VendorConfig) {
  if (!fs.existsSync(config.inputFile)) {
    console.error(`  File not found: ${config.inputFile}`)
    return { created: 0, exists: 0, errors: 0 }
  }

  let products = JSON.parse(fs.readFileSync(config.inputFile, "utf-8")).slice(0, LIMIT)

  // If --retry-errors, only process products that previously failed
  if (RETRY_ERRORS) {
    const logFile = path.join(DATA_DIR, config.slug, "leka-import-log.json")
    if (fs.existsSync(logFile)) {
      const prevLog = JSON.parse(fs.readFileSync(logFile, "utf-8"))
      const errorHandles = new Set(prevLog.filter((l: any) => l.status === "error").map((l: any) => l.handle))
      // Also pre-populate usedSkus from successfully created products to avoid new conflicts
      for (const entry of prevLog) {
        if (entry.status === "created" || entry.status === "exists") {
          const prod = products.find((p: any) => p.handle === entry.handle)
          if (prod) {
            const sku = String(prod.sku || prod.handle)
            usedSkus.add(config.slug === "eurotramp" && prod.sku ? `ET-${sku}` : sku)
          }
        }
      }
      products = products.filter((p: any) => errorHandles.has(p.handle))
      console.log(`Retrying ${products.length} previously failed products`)
    }
  }

  // Sanitize handles — skip products with empty handles after sanitization
  for (const p of products) {
    p.handle = sanitizeHandle(p.handle || "")
  }
  const vendorPrefix = `${config.slug.replace(/\./g, "")}`
  products = products.filter((p: any) => {
    if (!p.handle || p.handle === vendorPrefix || p.handle === `eurotramp`) return false
    return true
  })

  console.log(`\n=== ${config.name.toUpperCase()} → LEKA MEDUSA ===`)
  console.log(`Products: ${products.length} | Dry run: ${DRY_RUN} | Retry: ${RETRY_ERRORS}\n`)

  // Ensure categories
  const catHandles = [...new Set(products.map((p: any) => p.category).filter(Boolean))]
  // For 4soft, also add subcategory handles
  if (config.slug === "4soft") {
    const subHandles = [...new Set(products.map((p: any) => p.subcategory).filter(Boolean))]
    catHandles.push(...subHandles)
    catHandles.push("epdm-2d-graphics", "epdm-3d-elements", "epdm-accessories")
  }
  const catMap = DRY_RUN ? {} : await ensureCategories(catHandles)

  // Ensure collections
  const collNames: string[] = []
  if (config.slug === "berliner") {
    const groups = [...new Set(products.map((p: any) => p.product_group).filter(Boolean))]
    collNames.push(...groups.map(g => `Berliner ${g}`))
  } else if (config.slug === "4soft") {
    collNames.push("4soft 2D Graphics", "4soft 3D Elements", "4soft Tunnels & Furniture")
  }
  const collMap = DRY_RUN ? {} : await ensureCollections(collNames)

  // Upload
  const log: any[] = []
  for (const [i, p] of products.entries()) {
    console.log(`[${i + 1}/${products.length}] ${p.title} (${p.handle})`)
    if (DRY_RUN) { log.push({ handle: p.handle, status: "dry-run" }); continue }

    try {
      const existing = await medusaFetch(`/admin/products?handle=${p.handle}`)
      if (existing.products?.length) {
        log.push({ handle: p.handle, id: existing.products[0].id, status: "exists" })
        continue
      }

      const payload = config.buildPayload(p, catMap, collMap)
      const result = await medusaFetch("/admin/products", { method: "POST", body: JSON.stringify(payload) })
      const id = result.product.id

      // Assign to sales channel
      try {
        await medusaFetch(`/admin/sales-channels/${config.salesChannel}/products`, {
          method: "POST",
          body: JSON.stringify({ add: [id] }),
        })
      } catch {}

      log.push({ handle: p.handle, id, status: "created" })
      console.log(`  Created: ${id}`)
    } catch (e: any) {
      console.error(`  FAILED: ${e.message}`)
      log.push({ handle: p.handle, status: "error", error: e.message })
    }
  }

  // Save log — merge with previous log when retrying
  const logFile = path.join(DATA_DIR, config.slug, "leka-import-log.json")
  if (RETRY_ERRORS && fs.existsSync(logFile)) {
    const prevLog = JSON.parse(fs.readFileSync(logFile, "utf-8"))
    const retryHandles = new Set(log.map((l: any) => l.handle))
    const merged = prevLog.filter((l: any) => !retryHandles.has(l.handle)).concat(log)
    fs.writeFileSync(logFile, JSON.stringify(merged, null, 2))
  } else {
    fs.writeFileSync(logFile, JSON.stringify(log, null, 2))
  }

  const created = log.filter(l => l.status === "created").length
  const exists = log.filter(l => l.status === "exists").length
  const errors = log.filter(l => l.status === "error").length
  console.log(`\n  Created: ${created} | Existed: ${exists} | Errors: ${errors}`)
  return { created, exists, errors }
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  console.log("=== VENDOR UPLOAD TO LEKA MEDUSA ===")
  console.log(`Target: ${MEDUSA_URL}`)
  console.log(`Dry run: ${DRY_RUN}\n`)

  if (!DRY_RUN) {
    console.log("Authenticating...")
    await authenticate()
    console.log("OK\n")
  }

  const vendorKeys = VENDOR === "all" ? Object.keys(VENDORS) : [VENDOR!]
  const totals = { created: 0, exists: 0, errors: 0 }

  for (const key of vendorKeys) {
    const config = VENDORS[key]
    if (!config) {
      console.error(`Unknown vendor: ${key}`)
      continue
    }
    const result = await uploadVendor(config)
    totals.created += result.created
    totals.exists += result.exists
    totals.errors += result.errors
  }

  console.log("\n=== ALL DONE ===")
  console.log(`Total created: ${totals.created}`)
  console.log(`Total existed: ${totals.exists}`)
  console.log(`Total errors: ${totals.errors}`)
}

main().catch(console.error)
