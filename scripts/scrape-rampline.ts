/**
 * Scrape Rampline product catalog
 *
 * Usage: npx tsx scripts/scrape-rampline.ts [--limit N]
 *
 * Outputs:
 *   data/scraped/rampline/products.json
 *   data/scraped/rampline/images/
 *   data/scraped/rampline/downloads/
 *
 * Site: WordPress + WooCommerce, English at /en/
 * Product URL: /en/product/{slug}/
 * Sitemap: /en/product-sitemap.xml
 */

import * as cheerio from "cheerio"
import * as fs from "fs"
import * as path from "path"

const BASE_URL = "https://rampline.com"
const OUTPUT_DIR = path.resolve(__dirname, "../data/scraped/rampline")
const DELAY_MS = 800
const args = process.argv.slice(2)
const limitIdx = args.indexOf("--limit")
const LIMIT = limitIdx >= 0 ? parseInt(args[limitIdx + 1]) : Infinity

// ── Types ────────────────────────────────────────────────────────────────

interface ScrapedProduct {
  title: string
  handle: string
  description: string
  short_description: string
  sku: string
  vendor_url: string
  product_group: string
  category: string
  thumbnail_url: string
  image_urls: string[]
  dimensions: { height_cm: number; width_cm: number; depth_cm: number }
  weight_kg: number
  fall_height_cm: number
  safety_zone_cm: number
  age_group: string
  certifications: string[]
  materials: string[]
  installation: { foundation: string; time: string; persons: number }
  pricing: { amount_nok: number; currency: string }
  variants: { name: string; sku: string }[]
  downloads: { type: string; url: string; filename: string }[]
  colors: string[]
  ground_cover_options: string[]
  related_products: string[]
  raw_specs: Record<string, string>
  is_park: boolean
}

// ── Helpers ──────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

async function fetchPage(url: string): Promise<string> {
  await delay(DELAY_MS)
  console.log(`  GET ${url}`)
  const res = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (compatible; AredaCatalogBot/1.0; +https://catalogs.aredaatelier.com)",
      Accept: "text/html,application/xhtml+xml",
      "Accept-Language": "en-US,en;q=0.9",
    },
  })
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.text()
}

async function downloadAsset(url: string, destDir: string): Promise<string | null> {
  const filename = decodeURIComponent(path.basename(new URL(url).pathname)).replace(/[^a-zA-Z0-9._-]/g, "_")
  const dest = path.join(destDir, filename)
  if (fs.existsSync(dest)) return dest
  try {
    await delay(300)
    const res = await fetch(url)
    if (!res.ok) return null
    const buffer = Buffer.from(await res.arrayBuffer())
    fs.writeFileSync(dest, buffer)
    return dest
  } catch { return null }
}

// ── Discovery ────────────────────────────────────────────────────────────

async function discoverProductUrls(): Promise<string[]> {
  const urls: string[] = []

  // Try product sitemap
  for (const sitemapPath of [
    "/en/product-sitemap.xml",
    "/product-sitemap.xml",
    "/en/product-sitemap2.xml",
  ]) {
    try {
      const xml = await fetchPage(`${BASE_URL}${sitemapPath}`)
      const $ = cheerio.load(xml, { xmlMode: true })
      $("url > loc").each((_, el) => {
        const loc = $(el).text().trim()
        // Only English product URLs, skip category pages
        if (loc.includes("/en/product/") && !loc.includes("product-category")) {
          urls.push(loc)
        }
      })
    } catch {}
  }

  // Fallback: crawl product category pages
  if (urls.length === 0) {
    console.log("  Sitemaps empty, crawling category pages...")
    const categoryPaths = [
      "/en/product-category/products/",
      "/en/product-category/motor-skill-parks/",
      "/en/product-category/accessories/",
    ]
    for (const catPath of categoryPaths) {
      try {
        const html = await fetchPage(`${BASE_URL}${catPath}`)
        const $ = cheerio.load(html)
        $("a[href*='/en/product/']").each((_, el) => {
          const href = $(el).attr("href") || ""
          if (href.includes("/en/product/") && !href.includes("product-category")) {
            const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
            urls.push(fullUrl)
          }
        })
      } catch {}
    }
  }

  const unique = [...new Set(urls)].slice(0, LIMIT)
  console.log(`  Total unique product URLs: ${unique.length}`)
  return unique
}

// ── Extraction ───────────────────────────────────────────────────────────

async function scrapeProduct(url: string): Promise<ScrapedProduct> {
  const html = await fetchPage(url)
  const $ = cheerio.load(html)
  const slug = url.split("/product/")[1]?.replace(/\/$/, "") || ""
  const bodyText = $.root().text()

  // ── Title ──
  const title =
    $("h1").first().text().trim() ||
    $(".wp-block-heading.has-huge-font-size").first().text().trim() ||
    $(".product_title").first().text().trim() ||
    slug

  // ── JSON-LD structured data ──
  let jsonLd: any = {}
  $('script[type="application/ld+json"]').each((_, el) => {
    try {
      const data = JSON.parse($(el).html() || "{}")
      if (data["@type"] === "Product") jsonLd = data
      // Handle @graph arrays
      if (data["@graph"]) {
        for (const item of data["@graph"]) {
          if (item["@type"] === "Product") jsonLd = item
        }
      }
    } catch {}
  })

  const sku = jsonLd.sku || ""
  const short_description = jsonLd.description || ""

  // ── Description ──
  const descParts: string[] = []
  $(".wp-block-columns p, .entry-content p, article p").each((_, el) => {
    const text = $(el).text().trim()
    if (text.length > 30 && !descParts.includes(text) && !text.includes("cookie")) {
      descParts.push(text)
    }
  })
  const description = descParts.slice(0, 8).join("\n\n")

  // ── Category from breadcrumb JSON-LD ──
  let category = "playground-equipment"
  let productGroup = ""
  $('script[type="application/ld+json"]').each((_, el) => {
    try {
      const data = JSON.parse($(el).html() || "{}")
      if (data["@graph"]) {
        for (const item of data["@graph"]) {
          if (item["@type"] === "BreadcrumbList" && item.itemListElement) {
            const crumbs = item.itemListElement
            if (crumbs.length > 1) {
              productGroup = crumbs[crumbs.length - 2]?.name || ""
            }
          }
        }
      }
    } catch {}
  })

  const isPark = url.includes("park") || productGroup.toLowerCase().includes("park") || bodyText.includes("Motor Skills Park")

  if (isPark) category = "motor-skills-parks"
  else if (slug.includes("shockdeck")) category = "safety-surfaces"
  else category = "playground-equipment"

  // ── Images ──
  const imageUrls: string[] = []
  // WooCommerce gallery
  $(".woocommerce-product-gallery img, .wp-block-image img, .wp-lightbox-container img").each((_, el) => {
    const src = $(el).attr("data-large_image") || $(el).attr("data-src") || $(el).attr("src") || ""
    if (src && !src.includes("placeholder") && !imageUrls.includes(src)) {
      const fullUrl = src.startsWith("http") ? src : `${BASE_URL}${src}`
      imageUrls.push(fullUrl)
    }
  })
  // Also from JSON-LD
  if (jsonLd.image) {
    const imgs = Array.isArray(jsonLd.image) ? jsonLd.image : [jsonLd.image]
    for (const img of imgs) {
      const imgUrl = typeof img === "string" ? img : img?.url || img?.contentUrl || ""
      if (imgUrl && !imageUrls.includes(imgUrl)) imageUrls.push(imgUrl)
    }
  }

  // ── Pricing from JSON-LD ──
  let amount_nok = 0
  if (jsonLd.offers) {
    const offers = jsonLd.offers
    amount_nok = parseFloat(offers.price || offers.lowPrice || "0")
  }

  // ── Specifications ──
  // Rampline uses ul/li lists rather than tables for specs
  const rawSpecs: Record<string, string> = {}
  $("ul li, .wp-block-list li").each((_, el) => {
    const text = $(el).text().trim()
    const match = text.match(/^(.+?):\s*(.+)$/)
    if (match) rawSpecs[match[1].trim()] = match[2].trim()
  })

  const findSpec = (...keys: string[]): string => {
    for (const k of keys) {
      for (const [specKey, specVal] of Object.entries(rawSpecs)) {
        if (specKey.toLowerCase().includes(k.toLowerCase())) return specVal
      }
    }
    return ""
  }

  const heightText = findSpec("Height", "Høyde")
  const heightMatch = heightText.match(/([\d.]+)\s*cm/)
  const widthText = findSpec("Width", "Bredde")
  const widthMatch = widthText.match(/([\d.]+)\s*cm/)
  const depthText = findSpec("Depth", "Dybde")
  const depthMatch = depthText.match(/([\d.]+)\s*cm/)
  const dimensions = {
    height_cm: heightMatch ? parseFloat(heightMatch[1]) : 0,
    width_cm: widthMatch ? parseFloat(widthMatch[1]) : 0,
    depth_cm: depthMatch ? parseFloat(depthMatch[1]) : 0,
  }

  const weightText = findSpec("Weight", "Vekt")
  const weightMatch = weightText.match(/([\d.]+)\s*kg/)
  const weight_kg = weightMatch ? parseFloat(weightMatch[1]) : 0

  const fallText = findSpec("Fall height", "Fallhøyde")
  const fallMatch = fallText.match(/([\d.]+)\s*cm/)
  const fall_height_cm = fallMatch ? parseFloat(fallMatch[1]) : 0

  const safetyText = findSpec("Safety zone", "Clearance", "Sikkerhetssone")
  const safetyMatch = safetyText.match(/([\d.]+)\s*cm/)
  const safety_zone_cm = safetyMatch ? parseFloat(safetyMatch[1]) : 0

  const foundationText = findSpec("Foundation", "Fundament")
  const installTimeText = findSpec("Installation time", "Mounting time", "Montering")

  // ── Certifications ──
  const certifications: string[] = []
  if (bodyText.includes("EN 1176")) certifications.push("EN 1176")
  if (bodyText.includes("EN 1177")) certifications.push("EN 1177")
  if (bodyText.includes("EN 16630")) certifications.push("EN 16630")
  if (/\bTUV\b|TÜV/.test(bodyText)) certifications.push("TUV")

  // ── Materials ──
  const materials: string[] = []
  if (bodyText.toLowerCase().includes("stainless")) materials.push("stainless steel")
  if (bodyText.toLowerCase().includes("powder coat")) materials.push("powder coated steel")
  if (bodyText.toLowerCase().includes("epdm") || bodyText.toLowerCase().includes("rubber")) materials.push("EPDM rubber")
  if (bodyText.toLowerCase().includes("natural rubber")) materials.push("natural rubber")
  if (bodyText.toLowerCase().includes("recycled")) materials.push("recycled rubber")

  // ── Downloads ──
  const downloads: { type: string; url: string; filename: string }[] = []
  $("a[href$='.pdf'], a[href*='product-sheet'], a[href*='-oam'], a[href*='-mount']").each((_, el) => {
    const href = $(el).attr("href") || ""
    if (!href) return
    const text = $(el).text().trim().toLowerCase()
    const filename = decodeURIComponent(path.basename(href))
    let type = "other"
    if (text.includes("product sheet") || href.includes("product-sheet")) type = "datasheet"
    else if (text.includes("oam") || href.includes("-oam")) type = "manual"
    else if (text.includes("mount") || href.includes("-mount")) type = "manual"
    else if (href.endsWith(".dwg")) type = "dwg_2d"
    const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
    if (!downloads.find(d => d.url === fullUrl)) {
      downloads.push({ type, url: fullUrl, filename })
    }
  })

  // Check for Google Drive download links (DWG, BIM)
  $("a[href*='drive.google.com']").each((_, el) => {
    const href = $(el).attr("href") || ""
    const text = $(el).text().trim().toLowerCase()
    let type = "other"
    if (text.includes("2d") || text.includes("dwg")) type = "dwg_2d"
    else if (text.includes("3d")) type = "dwg_3d"
    else if (text.includes("bim") || text.includes("ifc")) type = "bim"
    downloads.push({ type, url: href, filename: `${slug}-${type}.zip` })
  })

  // ── Variants / Colors / Ground covers ──
  const variants: { name: string; sku: string }[] = []
  const colors: string[] = []
  const groundCovers: string[] = []

  // WooCommerce variation data
  $("form.variations_form").each((_, form) => {
    const variationsJson = $(form).attr("data-product_variations") || "[]"
    try {
      const variations = JSON.parse(variationsJson)
      for (const v of variations) {
        variants.push({
          name: Object.values(v.attributes || {}).join(" / "),
          sku: v.sku || "",
        })
      }
    } catch {}
  })

  // Ground cover from selects
  $("select option").each((_, el) => {
    const text = $(el).text().trim()
    if (text.includes("Grass") || text.includes("Wet pour") || text.includes("ShockDeck") || text.includes("artificial")) {
      if (!groundCovers.includes(text)) groundCovers.push(text)
    }
  })

  // ── Related products ──
  const relatedProducts: string[] = []
  $("a[href*='/en/product/']").each((_, el) => {
    const href = $(el).attr("href") || ""
    const relSlug = href.split("/product/")[1]?.replace(/\/$/, "")
    if (relSlug && relSlug !== slug && !relatedProducts.includes(relSlug)) {
      relatedProducts.push(relSlug)
    }
  })

  return {
    title: title.replace(/™|®/g, ""),
    handle: `rampline-${slug}`,
    description,
    short_description,
    sku,
    vendor_url: url,
    product_group: productGroup,
    category,
    thumbnail_url: imageUrls[0] || "",
    image_urls: imageUrls,
    dimensions,
    weight_kg,
    fall_height_cm,
    safety_zone_cm,
    age_group: bodyText.includes("kindergarten") ? "1+" : "3+",
    certifications,
    materials,
    installation: {
      foundation: foundationText,
      time: installTimeText,
      persons: installTimeText.match(/(\d+)\s*person/) ? parseInt(installTimeText.match(/(\d+)\s*person/)![1]) : 0,
    },
    pricing: { amount_nok, currency: "NOK" },
    variants,
    downloads,
    colors,
    ground_cover_options: groundCovers,
    related_products: relatedProducts.slice(0, 10),
    raw_specs: rawSpecs,
    is_park: isPark,
  }
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  for (const dir of ["images", "downloads"]) {
    fs.mkdirSync(path.join(OUTPUT_DIR, dir), { recursive: true })
  }

  console.log("=== RAMPLINE SCRAPER ===\n")
  console.log("Step 1: Discovering product URLs...")
  const urls = await discoverProductUrls()
  console.log(`Found ${urls.length} product URLs\n`)

  if (urls.length === 0) {
    console.error("No product URLs found.")
    process.exit(1)
  }

  fs.writeFileSync(path.join(OUTPUT_DIR, "product-urls.txt"), urls.join("\n"))

  console.log("Step 2: Scraping product details...")
  const products: ScrapedProduct[] = []
  const errors: { url: string; error: string }[] = []

  for (const [i, url] of urls.entries()) {
    console.log(`\n[${i + 1}/${urls.length}] ${url}`)
    try {
      const product = await scrapeProduct(url)
      products.push(product)
      console.log(`  OK: ${product.title} (SKU: ${product.sku})`)
    } catch (e: any) {
      console.error(`  FAILED: ${e.message}`)
      errors.push({ url, error: e.message })
    }
  }

  console.log("\nStep 3: Downloading assets...")
  let imgCount = 0, dlCount = 0

  for (const product of products) {
    for (const imgUrl of product.image_urls.slice(0, 5)) {
      const result = await downloadAsset(imgUrl, path.join(OUTPUT_DIR, "images"))
      if (result) imgCount++
    }
    for (const dl of product.downloads) {
      if (!dl.url.includes("drive.google.com")) { // Skip Google Drive links
        const result = await downloadAsset(dl.url, path.join(OUTPUT_DIR, "downloads"))
        if (result) dlCount++
      }
    }
  }

  fs.writeFileSync(path.join(OUTPUT_DIR, "products.json"), JSON.stringify(products, null, 2))
  fs.writeFileSync(path.join(OUTPUT_DIR, "errors.json"), JSON.stringify(errors, null, 2))

  console.log("\n=== SCRAPING COMPLETE ===")
  console.log(`Products scraped: ${products.length}`)
  console.log(`  Equipment: ${products.filter(p => !p.is_park).length}`)
  console.log(`  Motor Skills Parks: ${products.filter(p => p.is_park).length}`)
  console.log(`Errors: ${errors.length}`)
  console.log(`Images downloaded: ${imgCount}`)
  console.log(`Documents downloaded: ${dlCount}`)
  console.log(`Output: ${OUTPUT_DIR}/products.json`)
}

main().catch(console.error)
