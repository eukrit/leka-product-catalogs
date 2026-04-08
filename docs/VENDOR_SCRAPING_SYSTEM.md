# Vendor Product Scraping System

## Overview

A systematic framework for scraping product data from playground equipment vendor websites and importing into the Areda Medusa e-commerce backend. This document covers:

1. **Medusa Target Schema** — what fields we need to populate
2. **Generic Scraping Architecture** — reusable system design
3. **Berliner Seilfabrik Instructions** — vendor-specific scraping + import
4. **Eurotramp Instructions** — vendor-specific scraping + import

---

## 1. Medusa Target Schema

### Product (core fields via Medusa Admin API)

| Field | Type | Required | Source Mapping |
|---|---|---|---|
| `title` | string | Yes | Product name from vendor |
| `handle` | string | Yes | URL-safe slug (auto-generated from title or SKU) |
| `status` | `"published"` / `"draft"` | Yes | Default `"draft"` until reviewed |
| `description` | string | No | Marketing description from vendor |
| `subtitle` | string | No | Tagline or short description |
| `thumbnail` | string (URL) | No | Primary product image URL |
| `images` | `{url: string}[]` | No | All product images |
| `metadata` | JSON object | No | All vendor-specific fields (see below) |
| `categories` | `{id: string}[]` | No | Mapped to Medusa category IDs |
| `collection_id` | string | No | Mapped to Medusa collection ID |
| `tags` | `{id: string}[]` | No | Pre-created tag IDs |
| `options` | `{title, values}[]` | Yes | Product configuration axes |
| `variants` | array | Yes | At least one variant |

### Variant (per product)

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | Yes | SKU or descriptive name |
| `sku` | string | No | Article number from vendor |
| `manage_inventory` | boolean | Yes | `false` for catalog-only products |
| `prices` | `{amount, currency_code}[]` | No | Amount in cents; omit if B2B/no public price |
| `options` | object | Yes | Must match product options |
| `metadata` | JSON | No | Variant-specific specs |

### Brand (custom module: `/admin/brands`)

| Field | Type | Required |
|---|---|---|
| `slug` | string | Yes |
| `name` | string | Yes |
| `brand_code` | string | Yes |
| `description` | string | No |
| `country` | string | No |
| `logo_url` | string | No |
| `product_count` | number | No |
| `collections` | string[] | No |
| `categories` | string[] | No |
| `metadata` | JSON | No |

### Product Metadata Schema (stored in `product.metadata`)

These fields go into the flexible JSON metadata, standardized across all vendors:

```typescript
interface VendorProductMetadata {
  // Identity
  manufacturer_slug: string         // "berliner" | "eurotramp" | "vinci-play"
  vendor_sku: string                // Original article/SKU number
  vendor_url: string                // Source product page URL
  product_group: string             // Vendor's product line/series

  // Dimensions (all in cm)
  length_cm: number
  width_cm: number
  height_cm: number

  // Safety
  fall_height_cm: number
  safety_zone_length_cm: number
  safety_zone_width_cm: number
  safety_zone_area_m2: number
  max_users: number
  age_group: string                 // "3+" | "5+" | "1-8" etc.

  // Certifications
  certifications: string[]          // ["EN 1176", "ASTM", "TUV", "FIG"]
  en_standard: string               // "EN 1176-1:2017" etc.

  // Materials & Construction
  materials: string[]               // ["steel", "rope", "HDPE"]
  installation_type: string         // "surface-mount" | "in-ground" | "pit"
  installation_time_hours: number

  // Logistics
  weight_kg: number
  heaviest_part_kg: number

  // Downloads (stored as URLs to our GCS bucket after download)
  downloads: {
    type: string                    // "datasheet" | "dwg_2d" | "dwg_3d" | "certificate" | "manual"
    filename: string
    url: string                     // GCS URL after upload
    original_url: string            // Vendor source URL
  }[]

  // Vendor-specific (catch-all)
  vendor_data: Record<string, any>
}
```

---

## 2. Generic Scraping Architecture

### System Components

```
┌─────────────────────────────────────────────────────┐
│                   SCRAPING PIPELINE                   │
│                                                       │
│  1. DISCOVER    → Sitemap/catalog crawl               │
│  2. EXTRACT     → Product detail page parsing         │
│  3. DOWNLOAD    → Images + PDFs + DWG files           │
│  4. TRANSFORM   → Normalize to Medusa schema          │
│  5. UPLOAD      → Push to Medusa Admin API            │
│  6. VERIFY      → Validate imported data              │
└─────────────────────────────────────────────────────┘
```

### Directory Structure

```
scripts/
  scrape-{vendor}.ts           # Main scraping script
  upload-{vendor}-to-medusa.ts # Medusa import script

data/
  scraped/
    {vendor}/
      products.json            # Raw scraped product data
      images/                  # Downloaded product images
      downloads/               # PDFs, DWGs, certificates
      import-log.json          # Import results + ID mapping
```

### Technology Stack

| Component | Tool | Why |
|---|---|---|
| HTTP fetching | `node-fetch` or built-in `fetch` | Native to Node 20 |
| HTML parsing | `cheerio` | Fast, jQuery-like selector API |
| Rate limiting | Custom delay (500ms–1s between requests) | Respect vendor servers |
| Image download | `fetch` + `fs.writeFile` | Stream to disk |
| PDF/DWG download | `fetch` + `fs.writeFile` | Binary file handling |
| Cloud upload | `@google-cloud/storage` | GCS bucket for assets |
| Medusa API | `fetch` with admin auth | Same pattern as existing scripts |

### Scraping Script Template

```typescript
// scripts/scrape-{vendor}.ts
import * as cheerio from "cheerio"
import * as fs from "fs"
import * as path from "path"

const VENDOR_SLUG = "{vendor}"
const BASE_URL = "https://www.{vendor}.com"
const OUTPUT_DIR = path.resolve(__dirname, `../data/scraped/${VENDOR_SLUG}`)
const DELAY_MS = 800 // Rate limit: max ~1.25 req/sec

interface ScrapedProduct {
  // Standard fields
  title: string
  handle: string
  description: string
  sku: string
  vendor_url: string
  product_group: string
  category: string

  // Images
  thumbnail_url: string
  image_urls: string[]

  // Specs
  dimensions: { length_cm: number; width_cm: number; height_cm: number }
  safety_zone: { length_cm: number; width_cm: number; area_m2: number }
  fall_height_cm: number
  max_users: number
  age_group: string

  // Certifications
  certifications: string[]

  // Downloads
  downloads: { type: string; url: string; filename: string }[]

  // Raw vendor data
  raw: Record<string, any>
}

async function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

async function fetchPage(url: string): Promise<string> {
  await delay(DELAY_MS)
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.text()
}

async function discoverProductUrls(): Promise<string[]> {
  // Override per vendor: parse sitemap.xml or crawl catalog pages
  throw new Error("Implement per vendor")
}

async function scrapeProduct(url: string): Promise<ScrapedProduct> {
  // Override per vendor: parse product detail page
  throw new Error("Implement per vendor")
}

async function downloadAsset(url: string, destDir: string): Promise<string> {
  const filename = path.basename(new URL(url).pathname)
  const dest = path.join(destDir, filename)
  if (fs.existsSync(dest)) return dest

  const res = await fetch(url)
  if (!res.ok) throw new Error(`Download failed: ${res.status} ${url}`)
  const buffer = Buffer.from(await res.arrayBuffer())
  fs.writeFileSync(dest, buffer)
  return dest
}

async function main() {
  // Ensure output dirs
  for (const dir of ["images", "downloads"]) {
    fs.mkdirSync(path.join(OUTPUT_DIR, dir), { recursive: true })
  }

  // Step 1: Discover
  console.log("Discovering product URLs...")
  const urls = await discoverProductUrls()
  console.log(`Found ${urls.length} products`)

  // Step 2: Extract
  const products: ScrapedProduct[] = []
  for (const [i, url] of urls.entries()) {
    console.log(`[${i + 1}/${urls.length}] Scraping ${url}`)
    try {
      const product = await scrapeProduct(url)
      products.push(product)
    } catch (e: any) {
      console.error(`  FAILED: ${e.message}`)
    }
  }

  // Step 3: Download assets
  for (const product of products) {
    // Download images
    for (const imgUrl of product.image_urls) {
      try {
        await downloadAsset(imgUrl, path.join(OUTPUT_DIR, "images"))
      } catch (e: any) {
        console.error(`  Image download failed: ${imgUrl}`)
      }
    }
    // Download PDFs/DWGs
    for (const dl of product.downloads) {
      try {
        await downloadAsset(dl.url, path.join(OUTPUT_DIR, "downloads"))
      } catch (e: any) {
        console.error(`  Download failed: ${dl.url}`)
      }
    }
  }

  // Save raw data
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "products.json"),
    JSON.stringify(products, null, 2)
  )
  console.log(`\nSaved ${products.length} products to ${OUTPUT_DIR}/products.json`)
}

main().catch(console.error)
```

### Upload Script Template

```typescript
// scripts/upload-{vendor}-to-medusa.ts
import * as fs from "fs"
import * as path from "path"

const MEDUSA_URL = process.env.MEDUSA_BACKEND_URL || "http://localhost:9000"
const API_KEY = process.env.MEDUSA_API_KEY || ""
const VENDOR_SLUG = "{vendor}"
const INPUT_FILE = path.resolve(__dirname, `../data/scraped/${VENDOR_SLUG}/products.json`)

async function medusaFetch(endpoint: string, options: RequestInit = {}) {
  const url = `${MEDUSA_URL}${endpoint}`
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  }
  if (API_KEY) headers["Authorization"] = `Bearer ${API_KEY}`
  const res = await fetch(url, { ...options, headers })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json()
}

async function ensureBrand() {
  // Create brand if not exists — see vendor-specific instructions
}

async function ensureCategories(categories: string[]): Promise<Record<string, string>> {
  const map: Record<string, string> = {}
  for (const cat of categories) {
    const handle = cat.toLowerCase().replace(/[^a-z0-9]+/g, "-")
    const displayName = cat.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    try {
      const res = await medusaFetch("/admin/product-categories", {
        method: "POST",
        body: JSON.stringify({ name: displayName, handle, is_active: true, is_internal: false }),
      })
      map[cat] = res.product_category.id
    } catch {
      const existing = await medusaFetch(`/admin/product-categories?handle=${handle}`)
      if (existing.product_categories?.length) map[cat] = existing.product_categories[0].id
    }
  }
  return map
}

async function ensureCollections(names: string[]): Promise<Record<string, string>> {
  const map: Record<string, string> = {}
  for (const name of names) {
    const handle = name.toLowerCase().replace(/[^a-z0-9]+/g, "-")
    try {
      const res = await medusaFetch("/admin/collections", {
        method: "POST",
        body: JSON.stringify({ title: name, handle }),
      })
      map[name] = res.collection.id
    } catch {
      const existing = await medusaFetch(`/admin/collections?handle=${handle}`)
      if (existing.collections?.length) map[name] = existing.collections[0].id
    }
  }
  return map
}

async function uploadProducts(products: any[], categoryMap: Record<string, string>, collectionMap: Record<string, string>) {
  const log: any[] = []
  for (const [i, p] of products.entries()) {
    console.log(`[${i + 1}/${products.length}] Uploading: ${p.title}`)
    try {
      // Check if exists
      const existing = await medusaFetch(`/admin/products?handle=${p.handle}`)
      if (existing.products?.length) {
        console.log(`  Already exists: ${existing.products[0].id}`)
        log.push({ handle: p.handle, id: existing.products[0].id, status: "exists" })
        continue
      }

      // Build payload — see vendor-specific section
      const payload = buildPayload(p, categoryMap, collectionMap)
      const result = await medusaFetch("/admin/products", { method: "POST", body: JSON.stringify(payload) })
      console.log(`  Created: ${result.product.id}`)
      log.push({ handle: p.handle, id: result.product.id, status: "created" })

      // Assign to sales channel
      await medusaFetch(`/admin/sales-channels/sc_01KN8ZHPHQEHVJ9DMGG9RSQW2S/products`, {
        method: "POST",
        body: JSON.stringify({ product_ids: [result.product.id] }),
      })
    } catch (e: any) {
      console.error(`  FAILED: ${e.message}`)
      log.push({ handle: p.handle, status: "error", error: e.message })
    }
  }
  return log
}

function buildPayload(p: any, categoryMap: Record<string, string>, collectionMap: Record<string, string>) {
  // Override per vendor — see sections 3 and 4
  throw new Error("Implement per vendor")
}

async function main() {
  const products = JSON.parse(fs.readFileSync(INPUT_FILE, "utf-8"))
  console.log(`Loaded ${products.length} products from ${INPUT_FILE}`)

  await ensureBrand()
  const categories = [...new Set(products.map((p: any) => p.category))]
  const collections = [...new Set(products.map((p: any) => p.product_group).filter(Boolean))]
  const categoryMap = await ensureCategories(categories)
  const collectionMap = await ensureCollections(collections)

  const log = await uploadProducts(products, categoryMap, collectionMap)
  fs.writeFileSync(
    path.resolve(__dirname, `../data/scraped/${VENDOR_SLUG}/import-log.json`),
    JSON.stringify(log, null, 2)
  )
  console.log(`\nImport complete. ${log.filter(l => l.status === "created").length} created, ${log.filter(l => l.status === "exists").length} existing, ${log.filter(l => l.status === "error").length} errors.`)
}

main().catch(console.error)
```

---

## 3. Berliner Seilfabrik — Scraping & Import Instructions

### Vendor Profile

| Field | Value |
|---|---|
| Website | https://www.berliner-seilfabrik.com |
| Language | English at `/en/`, German at `/de/` |
| Platform | WordPress + Yoast SEO |
| CDN | berlinerzone.b-cdn.net |
| Product count | ~600 products |
| Pricing | Not public (B2B) |
| Sitemaps | `/de/sitemap_index.xml` → `/de/produkte-sitemap.xml`, `/de/produkte-sitemap2.xml` |

### Step 1: Discovery

```typescript
// In scripts/scrape-berliner.ts
const BASE_URL = "https://www.berliner-seilfabrik.com"
const SITEMAP_URLS = [
  `${BASE_URL}/de/produkte-sitemap.xml`,
  `${BASE_URL}/de/produkte-sitemap2.xml`,
]

async function discoverProductUrls(): Promise<string[]> {
  const urls: string[] = []
  for (const sitemapUrl of SITEMAP_URLS) {
    const xml = await fetchPage(sitemapUrl)
    const $ = cheerio.load(xml, { xmlMode: true })
    $("url > loc").each((_, el) => {
      const loc = $(el).text()
      // Convert German URLs to English: /de/produkte/ → /en/products/
      if (loc.includes("/de/produkte/")) {
        const enUrl = loc.replace("/de/produkte/", "/en/products/")
        urls.push(enUrl)
      }
    })
  }
  // Deduplicate
  return [...new Set(urls)]
}
```

### Step 2: Product Page Extraction

**URL pattern:** `https://www.berliner-seilfabrik.com/en/products/{slug}/`

**Fields to extract with CSS selectors:**

| Field | Selector / Method | Notes |
|---|---|---|
| Product name | `h1` or `.product-title` | e.g., "DNA Tower L.04.01" |
| Article number | Look for text pattern matching `\d{2}\.\d{3}\.\d{3}` | e.g., "90.295.019" |
| Description | `.product-description` or main content area | HTML → plain text |
| Product group | Breadcrumb or taxonomy link | e.g., "Univers", "Greenville" |
| Equipment dimensions | Table/spec rows with "Equipment footprint" or dimensions label | Parse L x W x H |
| EN 1176 safety zone | Row labeled "EN 1176" + dimensions | Parse L x W |
| ASTM safety zone | Row labeled "ASTM/CSA" + dimensions | Parse L x W |
| Fall height | Row labeled "Fall height" | Parse number in cm/m |
| Max users | Row labeled "Max. simultaneous users" | Integer |
| Main image | Primary `<img>` in product hero | Full-res URL from CDN |
| Technical drawings | Top-view / isometric images | URLs from CDN |
| Download links | Links to `.pdf` and `.dwg` files | Spec sheets, certificates, DWG |
| Related products | Related products section | Product slugs |
| Filter taxonomies | Equipment type, target group, play function | From page or filter params |

```typescript
async function scrapeProduct(url: string): Promise<ScrapedProduct> {
  const html = await fetchPage(url)
  const $ = cheerio.load(html)

  const title = $("h1").first().text().trim()
  const slug = url.split("/products/")[1]?.replace(/\/$/, "") || ""

  // Extract article number (pattern: XX.XXX.XXX)
  const skuMatch = $("body").text().match(/(\d{2}\.\d{3}\.\d{3})/)
  const sku = skuMatch ? skuMatch[1] : ""

  // Description
  const description = $(".product-description, .entry-content p").first().text().trim()

  // Product group from breadcrumb
  const breadcrumbs = $(".breadcrumb a, .wpseo-bc a").map((_, el) => $(el).text().trim()).get()
  const productGroup = breadcrumbs.length > 2 ? breadcrumbs[breadcrumbs.length - 2] : ""

  // Images from CDN
  const imageUrls: string[] = []
  $("img[src*='berlinerzone.b-cdn.net']").each((_, el) => {
    const src = $(el).attr("src") || $(el).attr("data-src") || ""
    if (src && !imageUrls.includes(src)) imageUrls.push(src)
  })

  // Specifications table - parse dimension rows
  const specs: Record<string, string> = {}
  $("table tr, .spec-row, .product-specs dt, .product-specs dd").each((_, el) => {
    const text = $(el).text().trim()
    // Parse key-value pairs from spec rows
    const match = text.match(/^(.+?):\s*(.+)$/)
    if (match) specs[match[1].trim()] = match[2].trim()
  })

  // Downloads
  const downloads: { type: string; url: string; filename: string }[] = []
  $("a[href$='.pdf'], a[href$='.dwg']").each((_, el) => {
    const href = $(el).attr("href") || ""
    const text = $(el).text().trim().toLowerCase()
    const filename = path.basename(href)
    let type = "other"
    if (text.includes("certificate") || text.includes("tuv")) type = "certificate"
    else if (text.includes("specification") || text.includes("spec")) type = "datasheet"
    else if (href.endsWith(".dwg")) type = "dwg_2d"
    else if (text.includes("drawing")) type = "dwg_2d"
    downloads.push({ type, url: href.startsWith("http") ? href : `${BASE_URL}${href}`, filename })
  })

  // Parse dimensions from specs
  const parseDimensions = (text: string) => {
    const nums = text.match(/[\d.]+/g)?.map(Number) || []
    return { length_cm: nums[0] || 0, width_cm: nums[1] || 0, height_cm: nums[2] || 0 }
  }

  const dimText = specs["Equipment footprint"] || specs["Dimensions"] || ""
  const dimensions = parseDimensions(dimText)

  const safetyText = specs["EN 1176 safety zone"] || specs["Safety zone EN 1176"] || ""
  const safetyDims = parseDimensions(safetyText)

  const fallHeightText = specs["Fall height"] || specs["Fall height EN 1176"] || ""
  const fallHeightMatch = fallHeightText.match(/([\d.]+)\s*(cm|m)/)
  const fall_height_cm = fallHeightMatch
    ? parseFloat(fallHeightMatch[1]) * (fallHeightMatch[2] === "m" ? 100 : 1)
    : 0

  const maxUsersText = specs["Max. simultaneous users"] || specs["Max. users"] || ""
  const max_users = parseInt(maxUsersText) || 0

  return {
    title,
    handle: `berliner-${slug}`,
    description,
    sku,
    vendor_url: url,
    product_group: productGroup,
    category: "rope-play-equipment", // Refine based on taxonomy
    thumbnail_url: imageUrls[0] || "",
    image_urls: imageUrls,
    dimensions,
    safety_zone: { length_cm: safetyDims.length_cm, width_cm: safetyDims.width_cm, area_m2: 0 },
    fall_height_cm,
    max_users,
    age_group: "3+", // Default, refine from page data
    certifications: ["EN 1176", "ASTM/CSA"], // Standard for Berliner
    downloads,
    raw: specs,
  }
}
```

### Step 3: Category Mapping

| Berliner Product Group | Medusa Category Handle | Medusa Collection |
|---|---|---|
| Univers | `rope-play-structures` | Berliner Univers |
| Greenville | `nature-play` | Berliner Greenville |
| Villago | `themed-play` | Berliner Villago |
| LevelUp | `climbing-structures` | Berliner LevelUp |
| Woodville | `timber-play` | Berliner Woodville |
| Polygodes | `geometric-play` | Berliner Polygodes |
| Twist & Shout | `spinning-play` | Berliner Twist & Shout |
| Terranos & Terranova | `low-rope-courses` | Berliner Terranos |
| CombiNation | `combination-play` | Berliner CombiNation |
| Custom-made | `custom-play` | Berliner Custom |
| UFOs | `single-play-elements` | Berliner UFOs |
| Geos | `geometric-play` | Berliner Geos |
| HodgePodge | `mixed-play` | Berliner HodgePodge |
| Spooky Rookies | `themed-play` | Berliner Spooky Rookies |
| WaggaWagga | `low-rope-courses` | Berliner WaggaWagga |

### Step 4: Medusa Upload — `buildPayload` for Berliner

```typescript
function buildPayload(p: ScrapedProduct, categoryMap: Record<string, string>, collectionMap: Record<string, string>) {
  const metadata = {
    manufacturer_slug: "berliner",
    vendor_sku: p.sku,
    vendor_url: p.vendor_url,
    product_group: p.product_group,
    length_cm: p.dimensions.length_cm,
    width_cm: p.dimensions.width_cm,
    height_cm: p.dimensions.height_cm,
    fall_height_cm: p.fall_height_cm,
    safety_zone_length_cm: p.safety_zone.length_cm,
    safety_zone_width_cm: p.safety_zone.width_cm,
    max_users: p.max_users,
    age_group: p.age_group,
    certifications: p.certifications,
    materials: ["rope", "steel", "aluminum"], // Standard for Berliner
    downloads: p.downloads,
    vendor_data: p.raw,
  }

  const payload: Record<string, any> = {
    title: p.title,
    handle: p.handle,
    status: "draft", // Review before publishing
    description: p.description,
    thumbnail: p.thumbnail_url,
    images: p.image_urls.map(url => ({ url })),
    metadata,
    options: [{ title: "Default", values: ["Default"] }],
    variants: [{
      title: "Default",
      sku: p.sku,
      manage_inventory: false,
      options: { Default: "Default" },
      metadata: {
        vendor_sku: p.sku,
        dimensions: p.dimensions,
        fall_height_cm: p.fall_height_cm,
        max_users: p.max_users,
      },
    }],
  }

  if (p.category && categoryMap[p.category]) {
    payload.categories = [{ id: categoryMap[p.category] }]
  }
  if (p.product_group && collectionMap[p.product_group]) {
    payload.collection_id = collectionMap[p.product_group]
  }

  return payload
}
```

### Step 5: Brand Setup for Berliner

```typescript
async function ensureBrand() {
  try {
    await medusaFetch("/admin/brands", {
      method: "POST",
      body: JSON.stringify({
        slug: "berliner",
        name: "Berliner Seilfabrik",
        brand_code: "BERLINER",
        description: "World leader in rope play equipment and play structures since 1865. Known for innovative 3D net climbing structures, rope play systems, and themed playgrounds.",
        country: "Germany",
        logo_url: "", // Add after downloading logo
        metadata: {
          website: "https://www.berliner-seilfabrik.com",
          founded: 1865,
          headquarters: "Berlin, Germany",
          specialties: ["rope play", "climbing structures", "3D nets", "themed playgrounds"],
        },
      }),
    })
    console.log("Created brand: Berliner Seilfabrik")
  } catch {
    console.log("Brand Berliner may already exist")
  }
}
```

### Full Execution Sequence (Berliner)

```bash
# 1. Install dependencies
cd areda-product-catalogs
npm install cheerio

# 2. Scrape all products
npx tsx scripts/scrape-berliner.ts

# 3. Review scraped data
# Check data/scraped/berliner/products.json — verify field extraction quality

# 4. Upload to Medusa
export MEDUSA_BACKEND_URL=https://areda-medusa-538978391890.asia-southeast1.run.app
export MEDUSA_API_KEY=<your-admin-api-key>
npx tsx scripts/upload-berliner-to-medusa.ts

# 5. Assign to sales channel (done in script)
# 6. Verify in Medusa Admin UI
```

---

## 4. Eurotramp — Scraping & Import Instructions

### Vendor Profile

| Field | Value |
|---|---|
| Website | https://www.eurotramp.com |
| Language | English at `/en/`, German at `/de/` |
| Platform | Custom CMS |
| Product count | ~51 main products + ~25 accessories + spare parts |
| Pricing | Not public (B2B through dealers) |
| Image pattern | `/_resources.d/images.d/{article}-{name}_{hash}_{WxH}.jpg` |
| Product URL | `/en/products/{slug}/` |
| Category URL | `/en/product-categories/{slug}/` |

### Step 1: Discovery

```typescript
// In scripts/scrape-eurotramp.ts
const BASE_URL = "https://www.eurotramp.com"

async function discoverProductUrls(): Promise<string[]> {
  const urls: string[] = []

  // Eurotramp has 14 categories — crawl each
  const categorySlugs = [
    "competition-trampolines",
    "school-popular-sports-trampolines",
    "double-minitramp",
    "minitramps",
    "booster-board",
    "trampoline-tracks",
    "playground-kindergarten",
    "outdoor-trampolines",
    "underwater-trampoline",
    "trampoline-sets",
    "freestyle-trampolines",
    "arenas-parks",
    "customized-trampoline-fabrications",
    // Skip "discontinued-models" unless you want archive
  ]

  for (const catSlug of categorySlugs) {
    const html = await fetchPage(`${BASE_URL}/en/product-categories/${catSlug}/`)
    const $ = cheerio.load(html)

    // Extract product links from category listing
    $("a[href*='/en/products/']").each((_, el) => {
      const href = $(el).attr("href") || ""
      const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
      if (fullUrl.includes("/en/products/") && !urls.includes(fullUrl)) {
        urls.push(fullUrl.replace(/\/$/, "/"))
      }
    })
  }

  // Also scrape accessories
  const accHtml = await fetchPage(`${BASE_URL}/en/accessories/`)
  const $acc = cheerio.load(accHtml)
  $acc("a[href*='/en/products/']").each((_, el) => {
    const href = $(el).attr("href") || ""
    const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
    if (!urls.includes(fullUrl)) urls.push(fullUrl.replace(/\/$/, "/"))
  })

  return [...new Set(urls)]
}
```

### Step 2: Product Page Extraction

**URL pattern:** `https://www.eurotramp.com/en/products/{slug}/`

**Tab pages to scrape per product (6 tabs):**
- `/en/products/{slug}/` — Main details + specs
- `/en/products/{slug}/accessories/#info` — Linked accessories
- `/en/products/{slug}/spare-parts/#info` — Linked spare parts
- `/en/products/{slug}/downloads/#info` — PDFs (certificates, factsheets, manuals)
- `/en/products/{slug}/faq/#info` — FAQ content

| Field | Selector / Method | Notes |
|---|---|---|
| Product name | `h1` | e.g., "Ultimate" |
| Subtitle | `h2` or `.subtitle` | e.g., "FIG certified competition trampoline..." |
| Article numbers | Text matching `\d{5}` patterns or labeled "Article No." | Multiple per product |
| Description | Main content paragraphs | Marketing text |
| Category | Breadcrumb | "Competition Trampolines" etc. |
| Specs table | Specification rows | Dimensions, weight, springs, etc. |
| Images | `img[src*='/_resources.d/images.d/']` | Product photos |
| Downloads | Links on downloads tab | PDF certificates, factsheets, manuals |
| Accessories | Product links on accessories tab | Article numbers of linked accessories |
| Spare parts | Product links on spare-parts tab | Linked replacement parts |
| FAQ | Q&A pairs on FAQ tab | Useful for product descriptions |

```typescript
async function scrapeProduct(url: string): Promise<ScrapedProduct> {
  const html = await fetchPage(url)
  const $ = cheerio.load(html)

  const title = $("h1").first().text().trim()
  const subtitle = $("h2, .product-subtitle").first().text().trim()
  const slug = url.split("/products/")[1]?.replace(/\/$/, "").split("/")[0] || ""

  // Article numbers
  const articleNumbers: string[] = []
  const bodyText = $("body").text()
  const skuMatches = bodyText.match(/\b\d{5}\b/g) || []
  // Filter for valid article numbers (typically 5-digit)
  for (const m of skuMatches) {
    if (!articleNumbers.includes(m)) articleNumbers.push(m)
  }
  const primarySku = articleNumbers[0] || ""

  // Description
  const descParagraphs: string[] = []
  $(".product-content p, .entry-content p, main p").each((_, el) => {
    const text = $(el).text().trim()
    if (text.length > 20) descParagraphs.push(text)
  })
  const description = descParagraphs.join("\n\n")

  // Category from breadcrumb
  const breadcrumbs = $(".breadcrumb a, nav a").map((_, el) => $(el).text().trim()).get()
  const category = breadcrumbs.find(b =>
    b.includes("Trampoline") || b.includes("Minitramp") || b.includes("Playground")
  ) || "trampolines"

  // Specifications
  const specs: Record<string, string> = {}
  $("table tr, .spec-row, dl dt, dl dd").each((_, el) => {
    const text = $(el).text().trim()
    const match = text.match(/^(.+?):\s*(.+)$/)
    if (match) specs[match[1].trim()] = match[2].trim()
  })

  // Images
  const imageUrls: string[] = []
  $("img[src*='/_resources.d/images.d/'], img[src*='images.d']").each((_, el) => {
    const src = $(el).attr("src") || ""
    const fullUrl = src.startsWith("http") ? src : `${BASE_URL}${src}`
    if (!imageUrls.includes(fullUrl)) imageUrls.push(fullUrl)
  })

  // Downloads (fetch downloads tab)
  const downloads: { type: string; url: string; filename: string }[] = []
  try {
    const dlHtml = await fetchPage(`${url}downloads/#info`)
    const $dl = cheerio.load(dlHtml)
    $dl("a[href$='.pdf']").each((_, el) => {
      const href = $(el).attr("href") || ""
      const text = $(el).text().trim().toLowerCase()
      const filename = path.basename(href)
      let type = "other"
      if (text.includes("tuv") || text.includes("certificate")) type = "certificate"
      else if (text.includes("fig")) type = "certificate"
      else if (text.includes("factsheet") || text.includes("fact sheet")) type = "datasheet"
      else if (text.includes("flyer") || text.includes("brochure")) type = "brochure"
      else if (text.includes("installation") || text.includes("assembly")) type = "manual"
      else if (text.includes("maintenance")) type = "manual"
      downloads.push({ type, url: href.startsWith("http") ? href : `${BASE_URL}${href}`, filename })
    })
  } catch {}

  // Accessories (fetch accessories tab)
  const accessoryLinks: string[] = []
  try {
    const accHtml = await fetchPage(`${url}accessories/#info`)
    const $acc = cheerio.load(accHtml)
    $acc("a[href*='/en/products/']").each((_, el) => {
      const href = $(el).attr("href") || ""
      accessoryLinks.push(href.startsWith("http") ? href : `${BASE_URL}${href}`)
    })
  } catch {}

  // Parse dimensions
  const parseDimensions = (text: string) => {
    const nums = text.match(/[\d.]+/g)?.map(Number) || []
    return { length_cm: nums[0] || 0, width_cm: nums[1] || 0, height_cm: nums[2] || 0 }
  }

  const dimText = specs["Installation dimensions"] || specs["Dimensions"] || ""
  const dimensions = parseDimensions(dimText)

  const weightText = specs["Weight"] || specs["Net weight"] || ""
  const weightMatch = weightText.match(/([\d.]+)\s*kg/)

  // Certifications
  const certifications: string[] = []
  if (bodyText.includes("EN 13219")) certifications.push("EN 13219")
  if (bodyText.includes("EN 1176") || bodyText.includes("DIN EN 1176")) certifications.push("EN 1176")
  if (bodyText.includes("FIG")) certifications.push("FIG")
  if (bodyText.includes("TUV") || bodyText.includes("TÜV")) certifications.push("TUV")
  if (bodyText.includes("GS mark") || bodyText.includes("GS-mark")) certifications.push("GS")

  // Map category
  const categoryHandle = category
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")

  return {
    title,
    handle: `eurotramp-${slug}`,
    description: subtitle ? `${subtitle}\n\n${description}` : description,
    sku: primarySku,
    vendor_url: url,
    product_group: categoryHandle,
    category: categoryHandle,
    thumbnail_url: imageUrls[0] || "",
    image_urls: imageUrls,
    dimensions,
    safety_zone: { length_cm: 0, width_cm: 0, area_m2: 0 },
    fall_height_cm: 0,
    max_users: 0,
    age_group: "",
    certifications,
    downloads,
    raw: {
      ...specs,
      subtitle,
      article_numbers: articleNumbers,
      accessory_links: accessoryLinks,
      weight_kg: weightMatch ? parseFloat(weightMatch[1]) : 0,
    },
  }
}
```

### Step 3: Category Mapping

| Eurotramp Category | Medusa Category Handle | Medusa Collection |
|---|---|---|
| Competition Trampolines | `competition-trampolines` | Eurotramp Competition |
| School/Popular Sports | `school-trampolines` | Eurotramp School & Sports |
| Double-Minitramp | `double-minitramp` | Eurotramp Minitramps |
| Minitramps | `minitramps` | Eurotramp Minitramps |
| Booster Board | `booster-board` | Eurotramp Accessories |
| Trampoline Tracks | `trampoline-tracks` | Eurotramp Tracks |
| Playground & Kindergarten | `playground-trampolines` | Eurotramp Playground |
| Outdoor Trampolines | `outdoor-trampolines` | Eurotramp Outdoor |
| Underwater Trampoline | `underwater-trampolines` | Eurotramp Specialty |
| Trampoline Sets | `trampoline-sets` | Eurotramp Sets |
| Freestyle Trampolines | `freestyle-trampolines` | Eurotramp Freestyle |
| Arenas & Parks | `trampoline-parks` | Eurotramp Parks |
| Accessories | `trampoline-accessories` | Eurotramp Accessories |

### Step 4: Variant Handling for Eurotramp

Eurotramp products often have multiple configuration axes. Map these to Medusa options:

```typescript
// Eurotramp products can have multiple variants based on:
// - Frame size (e.g., 300x200, 464x281, 524x311)
// - Jumping bed type (4x4mm, 5x4mm, 6x4mm, 6x6mm, 13mm)
// - Frame pad thickness (32mm, 50mm, 80mm SAFETY PLUS)

function buildEurotrampPayload(p: ScrapedProduct, categoryMap: Record<string, string>, collectionMap: Record<string, string>) {
  const metadata = {
    manufacturer_slug: "eurotramp",
    vendor_sku: p.sku,
    vendor_url: p.vendor_url,
    product_group: p.product_group,
    length_cm: p.dimensions.length_cm,
    width_cm: p.dimensions.width_cm,
    height_cm: p.dimensions.height_cm,
    certifications: p.certifications,
    weight_kg: p.raw.weight_kg || 0,
    article_numbers: p.raw.article_numbers || [],
    accessory_links: p.raw.accessory_links || [],
    downloads: p.downloads,
    made_in: "Germany",
    vendor_data: p.raw,
  }

  // For products with multiple article numbers, create variants
  const articleNumbers = (p.raw.article_numbers as string[]) || [p.sku]
  const hasMultipleVariants = articleNumbers.length > 1

  const options = hasMultipleVariants
    ? [{ title: "Configuration", values: articleNumbers }]
    : [{ title: "Default", values: ["Default"] }]

  const variants = hasMultipleVariants
    ? articleNumbers.map(artNo => ({
        title: `${p.title} - ${artNo}`,
        sku: artNo,
        manage_inventory: false,
        options: { Configuration: artNo },
        metadata: { article_number: artNo },
      }))
    : [{
        title: "Default",
        sku: p.sku,
        manage_inventory: false,
        options: { Default: "Default" },
        metadata: { article_number: p.sku },
      }]

  const payload: Record<string, any> = {
    title: p.title,
    handle: p.handle,
    status: "draft",
    description: p.description,
    thumbnail: p.thumbnail_url,
    images: p.image_urls.map(url => ({ url })),
    metadata,
    options,
    variants,
  }

  if (p.category && categoryMap[p.category]) {
    payload.categories = [{ id: categoryMap[p.category] }]
  }
  if (p.product_group && collectionMap[p.product_group]) {
    payload.collection_id = collectionMap[p.product_group]
  }

  return payload
}
```

### Step 5: Brand Setup for Eurotramp

```typescript
async function ensureBrand() {
  try {
    await medusaFetch("/admin/brands", {
      method: "POST",
      body: JSON.stringify({
        slug: "eurotramp",
        name: "Eurotramp",
        brand_code: "EUROTRAMP",
        description: "Premium trampoline manufacturer from Germany. Official supplier for Olympic Games, World Championships, and international competitions. Products include competition, school, playground, and freestyle trampolines.",
        country: "Germany",
        logo_url: "",
        metadata: {
          website: "https://www.eurotramp.com",
          headquarters: "Weilheim/Teck, Germany",
          specialties: ["competition trampolines", "school trampolines", "playground trampolines", "FIG certified"],
          olympic_supplier: true,
        },
      }),
    })
    console.log("Created brand: Eurotramp")
  } catch {
    console.log("Brand Eurotramp may already exist")
  }
}
```

### Full Execution Sequence (Eurotramp)

```bash
# 1. Install dependencies
cd areda-product-catalogs
npm install cheerio

# 2. Scrape all products
npx tsx scripts/scrape-eurotramp.ts

# 3. Review scraped data
# Check data/scraped/eurotramp/products.json

# 4. Upload to Medusa
export MEDUSA_BACKEND_URL=https://areda-medusa-538978391890.asia-southeast1.run.app
export MEDUSA_API_KEY=<your-admin-api-key>
npx tsx scripts/upload-eurotramp-to-medusa.ts

# 5. Verify in Medusa Admin UI
```

---

## 5. Vinci Play Reference Schema

For reference, here is the data schema observed on vinci-play.com (correct domain: www.vinci-play.com):

### Product Fields Available

| Field | Example | Type |
|---|---|---|
| Product Code | ST0519-1, RB1907 | String (series-prefixed) |
| Series | ROBINIA, CASTILLO, RECYCLED | String (28 series) |
| Length/Width/Height | 2090 / 1270 / 1040 cm | Numbers |
| Platform Heights | 90, 120, 150... cm | Number[] |
| Age Group | 1+, 1-8, 3-14, 6+ | String |
| Capacity (users) | 1-76 | Number |
| Safety Zone Area | 10.1-264.6 m2 | Number |
| Free Fall Height | <60-270 cm | Number |
| Heaviest Part | 17-31 kg | Number |
| Installation Time | 1-4 hours | Number |
| EN Standard | EN 1176-1:2017+A1:2023 | String |
| Color Options | 12+ colors | String[] |
| Downloads | PDF datasheet, 2D DWG, 3D DWG, TUV cert | File[] |
| Pricing | Not public (B2B login required) | N/A |

---

## 6. Post-Import Checklist

After importing products from any vendor:

- [ ] Verify product count matches expected (`/admin/products?manufacturer_slug={vendor}`)
- [ ] Spot-check 5-10 products for correct field mapping in Medusa Admin
- [ ] Verify images load correctly (check thumbnail URLs)
- [ ] Confirm categories and collections are properly assigned
- [ ] Assign all products to sales channel `sc_01KN8ZHPHQEHVJ9DMGG9RSQW2S`
- [ ] Link products to brand via `/admin/brands` module
- [ ] Download and re-host images/PDFs to GCS bucket if vendor CDN is unreliable
- [ ] Change status from `"draft"` to `"published"` after review
- [ ] Update storefront search index
- [ ] Test storefront product display at https://catalogs.aredaatelier.com

---

## 7. Adding New Vendors

To add a new vendor, follow this checklist:

1. **Research** the vendor website: URL patterns, sitemap, product page structure
2. **Copy** `scripts/scrape-{vendor}.ts` template and customize `discoverProductUrls()` + `scrapeProduct()`
3. **Map** vendor categories to Medusa categories (reuse existing where possible)
4. **Create** brand entry via Admin API
5. **Run** scrape → review JSON → upload → verify
6. **Add** vendor section to this document

---

*Document created: 2026-04-07*
*Last updated: 2026-04-07*
