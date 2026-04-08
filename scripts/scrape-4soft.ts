/**
 * Scrape 4soft.cz product catalog via internal API
 *
 * Usage: npx tsx scripts/scrape-4soft.ts [--limit N] [--type 2D|3D|ostatni]
 *
 * Outputs:
 *   data/scraped/4soft/products.json
 *   data/scraped/4soft/images/
 *
 * Site: Vue.js SPA with Laravel API backend
 * API: GET /getGraphicsPage, POST /getGraphicsByCategoryPage/{cat}
 * Product detail: GET /getGraphicDetailPage/{cat}/{sub}/{id}
 */

import * as fs from "fs"
import * as path from "path"

const BASE_URL = "https://4soft.cz"
const OUTPUT_DIR = path.resolve(__dirname, "../data/scraped/4soft")
const DELAY_MS = 500
const args = process.argv.slice(2)
const limitIdx = args.indexOf("--limit")
const LIMIT = limitIdx >= 0 ? parseInt(args[limitIdx + 1]) : Infinity
const typeIdx = args.indexOf("--type")
const TYPE_FILTER = typeIdx >= 0 ? args[typeIdx + 1] : null
const ITEMS_PER_PAGE = 50

// ── Types ────────────────────────────────────────────────────────────────

interface ScrapedProduct {
  title: string
  title_en: string
  handle: string
  description: string
  sku: string
  vendor_url: string
  product_type: string
  category: string
  subcategory: string
  subcategory2: string
  thumbnail_url: string
  detail_image_url: string
  image_urls: string[]
  dimensions: {
    height_cm: number
    width_cm: number
    length_cm: number
    diameter_cm: number
    area_m2: number
  }
  weight_kg: number
  colors: { name: string; hex: string }[]
  color_count: number
  is_bestseller: boolean
  is_new: boolean
  raw: Record<string, any>
}

// ── Helpers ──────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

// Session state for CSRF
let csrfToken = ""
let cookies = ""

async function initSession() {
  console.log("  Initializing session (CSRF + cookies)...")
  const res = await fetch(BASE_URL, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; AredaCatalogBot/1.0)" },
    redirect: "follow",
  })
  const setCookies = res.headers.getSetCookie?.() || []
  const cookieParts: string[] = []
  for (const sc of setCookies) {
    const name = sc.split("=")[0]
    const value = sc.split(";")[0]
    cookieParts.push(value)
    if (name === "XSRF-TOKEN") {
      csrfToken = decodeURIComponent(value.split("=")[1])
    }
  }
  cookies = cookieParts.join("; ")
  console.log(`  CSRF token: ${csrfToken.slice(0, 20)}...`)
  console.log(`  Cookies: ${cookies.slice(0, 60)}...`)
}

async function apiGet(endpoint: string): Promise<any> {
  await delay(DELAY_MS)
  const url = `${BASE_URL}${endpoint}`
  console.log(`  GET ${url}`)
  const res = await fetch(url, {
    headers: {
      "Accept": "application/json",
      "User-Agent": "Mozilla/5.0 (compatible; AredaCatalogBot/1.0)",
      "Cookie": cookies,
    },
  })
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.json()
}

async function apiPost(endpoint: string, body: any): Promise<any> {
  await delay(DELAY_MS)
  const url = `${BASE_URL}${endpoint}`
  console.log(`  POST ${url}`)
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": csrfToken,
      "User-Agent": "Mozilla/5.0 (compatible; AredaCatalogBot/1.0)",
      "Cookie": cookies,
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${url}: ${text.slice(0, 200)}`)
  }
  return res.json()
}

async function downloadAsset(url: string, destDir: string): Promise<string | null> {
  const filename = decodeURIComponent(path.basename(new URL(url).pathname)).replace(/[^a-zA-Z0-9._-]/g, "_")
  const dest = path.join(destDir, filename)
  if (fs.existsSync(dest)) return dest
  try {
    await delay(200)
    const res = await fetch(url)
    if (!res.ok) return null
    const buffer = Buffer.from(await res.arrayBuffer())
    fs.writeFileSync(dest, buffer)
    return dest
  } catch { return null }
}

function buildImageUrl(image: any): string {
  if (!image || !image.path || !image.name) return ""
  return `${BASE_URL}/storage/${image.path}/${encodeURIComponent(image.name)}`
}

// ── Discovery & Extraction ───────────────────────────────────────────────

async function scrapeCategory(categoryAlias: string): Promise<ScrapedProduct[]> {
  const products: ScrapedProduct[] = []
  let page = 1
  let total = 0

  do {
    const body = {
      page,
      numItemsPerPage: ITEMS_PER_PAGE,
      subcategories2: [],
      colors: [],
      order: "P",
      search: "",
      searchBy: "name",
    }

    const data = await apiPost(`/getGraphicsByCategoryPage/${categoryAlias}`, body)
    total = data.totalGraphics || 0
    const graphics = data.graphics || []

    if (graphics.length === 0) break

    console.log(`  Page ${page}: ${graphics.length} products (total: ${total})`)

    for (const g of graphics) {
      const product = parseGraphic(g, categoryAlias)
      products.push(product)
      if (products.length >= LIMIT) return products
    }

    page++
  } while (products.length < total && products.length < LIMIT)

  return products
}

async function scrapeSubcategory(categoryAlias: string, subcategoryAlias: string): Promise<ScrapedProduct[]> {
  const products: ScrapedProduct[] = []
  let page = 1
  let total = 0

  do {
    const body = {
      page,
      numItemsPerPage: ITEMS_PER_PAGE,
      subcategories2: [],
      colors: [],
      order: "P",
      search: "",
      searchBy: "name",
    }

    const data = await apiPost(`/getGraphicsByCategoryPage/${categoryAlias}/${subcategoryAlias}`, body)
    total = data.totalGraphics || 0
    const graphics = data.graphics || []

    if (graphics.length === 0) break

    for (const g of graphics) {
      const product = parseGraphic(g, categoryAlias)
      products.push(product)
      if (products.length >= LIMIT) return products
    }

    page++
  } while (products.length < total && products.length < LIMIT)

  return products
}

function parseGraphic(g: any, categoryAlias: string): ScrapedProduct {
  const code = g.code || ""
  const name = g.name || ""
  const nameVariant = g.name_variant || ""

  // Build English name from image name if available
  const img = g.image || {}
  const imgName = img.name || ""
  const enMatch = imgName.match(/[A-Z]\d+-[\dA-Z]+-[\dA-Za-z]+\s+(.+?)_WEB/)
  const title_en = enMatch ? enMatch[1].replace(/_/g, " ").trim() : ""

  // Build URLs
  const thumbnailUrl = buildImageUrl(img)
  // Detail image: replace _PREHLED with _DETAIL
  const detailName = imgName.replace("_WEB_PREHLED", "_WEB_DETAIL").replace(".png", ".jpg")
  const detailUrl = img.path ? `${BASE_URL}/storage/${img.path}/${encodeURIComponent(detailName)}` : ""

  const catAlias = g.categoryAlias || categoryAlias
  const subAlias = g.subcategoryAlias || ""
  const sub2Alias = g.subcategory2Alias || ""
  const graphicAlias = g.alias || g.id?.toString() || ""

  // Build vendor URL
  const vendorUrl = sub2Alias
    ? `${BASE_URL}/grafika/${catAlias}/${subAlias}/${sub2Alias}/${graphicAlias}`
    : subAlias
    ? `${BASE_URL}/grafika/${catAlias}/${subAlias}/${graphicAlias}`
    : `${BASE_URL}/grafika/${catAlias}/${graphicAlias}`

  // Colors
  const colors = (g.colors || []).map((c: any) => ({
    name: c.name || "",
    hex: c.hex || c.color || "",
  }))

  return {
    title: nameVariant ? `${name} (${nameVariant})` : name,
    title_en,
    handle: `4soft-${code.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    description: g.description || "",
    sku: code,
    vendor_url: vendorUrl,
    product_type: catAlias,
    category: subAlias,
    subcategory: sub2Alias,
    subcategory2: "",
    thumbnail_url: thumbnailUrl,
    detail_image_url: detailUrl,
    image_urls: [thumbnailUrl, detailUrl].filter(Boolean),
    dimensions: {
      height_cm: parseFloat(g.height) || 0,
      width_cm: parseFloat(g.width) || 0,
      length_cm: parseFloat(g.length) || 0,
      diameter_cm: 0,
      area_m2: parseFloat(g.surface) || 0,
    },
    weight_kg: parseFloat(g.weight) || 0,
    colors,
    color_count: colors.length,
    is_bestseller: !!g.is_bestseller,
    is_new: !!g.is_new,
    raw: {
      id: g.id,
      name_color: g.name_color,
      categoryAlias: catAlias,
      subcategoryAlias: subAlias,
      subcategory2Alias: sub2Alias,
    },
  }
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  for (const dir of ["images"]) {
    fs.mkdirSync(path.join(OUTPUT_DIR, dir), { recursive: true })
  }

  console.log("=== 4SOFT.CZ API SCRAPER ===\n")
  if (TYPE_FILTER) console.log(`Filtering to type: ${TYPE_FILTER}\n`)

  // Initialize session for CSRF
  await initSession()

  // Get category overview
  console.log("\nStep 1: Discovering categories...")
  const categoriesData = await apiGet("/getGraphicsPage")
  const allCategories = categoriesData.graphicCategories || []
  console.log(`Found ${allCategories.length} top-level categories`)

  for (const cat of allCategories) {
    console.log(`  ${cat.name} → ${cat.buttonLink || cat.alias || "?"}`)
  }

  // Determine which categories to scrape
  const types = TYPE_FILTER ? [TYPE_FILTER] : ["2D", "3D", "ostatni"]

  console.log("\nStep 2: Scraping products by category...")
  const allProducts: ScrapedProduct[] = []
  const errors: { category: string; error: string }[] = []

  for (const type of types) {
    if (allProducts.length >= LIMIT) break

    console.log(`\n--- Category: ${type} ---`)
    try {
      const products = await scrapeCategory(type)
      allProducts.push(...products)
      console.log(`  Total from ${type}: ${products.length}`)
    } catch (e: any) {
      console.error(`  FAILED: ${e.message}`)
      errors.push({ category: type, error: e.message })
    }
  }

  // Deduplicate by SKU
  const seen = new Set<string>()
  const deduped = allProducts.filter(p => {
    if (!p.sku || seen.has(p.sku)) return false
    seen.add(p.sku)
    return true
  })

  console.log(`\nStep 3: Downloading images (thumbnails)...`)
  let imgCount = 0
  for (const product of deduped) {
    if (product.thumbnail_url) {
      const result = await downloadAsset(product.thumbnail_url, path.join(OUTPUT_DIR, "images"))
      if (result) imgCount++
    }
  }

  // Save
  fs.writeFileSync(path.join(OUTPUT_DIR, "products.json"), JSON.stringify(deduped, null, 2))
  fs.writeFileSync(path.join(OUTPUT_DIR, "errors.json"), JSON.stringify(errors, null, 2))

  console.log("\n=== SCRAPING COMPLETE ===")
  console.log(`Products scraped: ${deduped.length} (${allProducts.length} before dedup)`)
  console.log(`  2D: ${deduped.filter(p => p.product_type === "2D").length}`)
  console.log(`  3D: ${deduped.filter(p => p.product_type === "3D").length}`)
  console.log(`  Other: ${deduped.filter(p => p.product_type === "ostatni").length}`)
  console.log(`Errors: ${errors.length}`)
  console.log(`Images downloaded: ${imgCount}`)
  console.log(`Output: ${OUTPUT_DIR}/products.json`)
}

main().catch(console.error)
