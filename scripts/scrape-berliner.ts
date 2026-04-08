/**
 * Scrape Berliner Seilfabrik product catalog
 *
 * Usage: npx tsx scripts/scrape-berliner.ts [--limit N]
 *
 * Outputs:
 *   data/scraped/berliner/products.json
 *   data/scraped/berliner/images/
 *   data/scraped/berliner/downloads/
 */

import * as cheerio from "cheerio"
import * as fs from "fs"
import * as path from "path"

const BASE_URL = "https://www.berliner-seilfabrik.com"
const OUTPUT_DIR = path.resolve(__dirname, "../data/scraped/berliner")
const DELAY_MS = 800
const args = process.argv.slice(2)
const limitIdx = args.indexOf("--limit")
const LIMIT = limitIdx >= 0 ? parseInt(args[limitIdx + 1]) : Infinity

// ── Types ────────────────────────────────────────────────────────────────

interface ScrapedProduct {
  title: string
  handle: string
  description: string
  sku: string
  vendor_url: string
  product_group: string
  category: string
  thumbnail_url: string
  image_urls: string[]
  dimensions: { length_cm: number; width_cm: number; height_cm: number }
  safety_zone_en: { length_cm: number; width_cm: number }
  safety_zone_astm: { length_cm: number; width_cm: number }
  fall_height_cm: number
  max_users: number
  age_group: string
  certifications: string[]
  downloads: { type: string; url: string; filename: string }[]
  related_products: string[]
  taxonomies: {
    equipment_type: string[]
    target_group: string[]
    play_function: string[]
  }
  raw_specs: Record<string, string>
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

async function downloadAsset(
  url: string,
  destDir: string
): Promise<string | null> {
  const filename = decodeURIComponent(
    path.basename(new URL(url).pathname)
  ).replace(/[^a-zA-Z0-9._-]/g, "_")
  const dest = path.join(destDir, filename)
  if (fs.existsSync(dest)) return dest

  try {
    await delay(300)
    const res = await fetch(url)
    if (!res.ok) return null
    const buffer = Buffer.from(await res.arrayBuffer())
    fs.writeFileSync(dest, buffer)
    return dest
  } catch {
    return null
  }
}

function parseDimensions(text: string): { length_cm: number; width_cm: number; height_cm: number } {
  // Handle formats: "1234 x 567 x 890 cm", "12.3 m x 5.6 m x 8.9 m", etc.
  const nums = text.match(/[\d,.]+/g)?.map((n) => parseFloat(n.replace(",", "."))) || []
  const isMeters = text.toLowerCase().includes(" m") && !text.toLowerCase().includes(" mm")
  const factor = isMeters ? 100 : 1
  return {
    length_cm: Math.round((nums[0] || 0) * factor),
    width_cm: Math.round((nums[1] || 0) * factor),
    height_cm: Math.round((nums[2] || 0) * factor),
  }
}

// ── Discovery ────────────────────────────────────────────────────────────

function isProductUrl(url: string): boolean {
  // Must have a slug after /products/ or /produkte/ — exclude listing pages
  const match = url.match(/\/(?:products|produkte)\/([^/?#]+)/)
  return !!match && match[1].length > 0
}

async function discoverProductUrls(): Promise<string[]> {
  const urls: string[] = []

  // Try sitemap index first, then individual sitemaps
  const sitemapPaths = [
    "/de/produkte-sitemap.xml",
    "/de/produkte-sitemap2.xml",
    "/de/produkte-sitemap3.xml",
    "/de/produkte-sitemap4.xml",
    "/de/produkte-sitemap5.xml",
  ]

  for (const sitemapPath of sitemapPaths) {
    try {
      const xml = await fetchPage(`${BASE_URL}${sitemapPath}`)
      const $ = cheerio.load(xml, { xmlMode: true })
      $("url > loc").each((_, el) => {
        const loc = $(el).text().trim()
        if (loc.includes("/de/produkte/") && isProductUrl(loc)) {
          // Convert /de/produkte/{slug}/ → /en/products/{slug}/
          const enUrl = loc
            .replace("berliner-seilfabrik.com/de/produkte/", "berliner-seilfabrik.com/en/products/")
            .replace(/([^/])$/, "$1/") // ensure trailing slash
          urls.push(enUrl)
        }
      })
    } catch (e: any) {
      // Silently skip missing sitemaps (e.g. sitemap3-5 may not exist)
      if (!e.message.includes("404")) {
        console.log(`  Sitemap ${sitemapPath} failed: ${e.message}`)
      }
    }
  }

  // Fallback: crawl product listing page and extract product links
  if (urls.length === 0) {
    console.log("  Sitemaps empty, crawling product listings...")
    try {
      const html = await fetchPage(`${BASE_URL}/en/products/`)
      const $ = cheerio.load(html)
      $("a[href*='/en/products/']").each((_, el) => {
        const href = $(el).attr("href") || ""
        if (isProductUrl(href)) {
          const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
          urls.push(fullUrl)
        }
      })
    } catch (e: any) {
      console.log(`  Product listing crawl failed: ${e.message}`)
    }

    // Also try product group pages
    const groupSlugs = [
      "univers", "greenville", "villago", "levelup", "woodville",
      "polygodes", "twist-shout", "terranos-terranova", "hodgepodge",
      "geos", "ufos", "combination", "waggawagga", "spooky-rookies",
    ]
    for (const groupSlug of groupSlugs) {
      try {
        const html = await fetchPage(`${BASE_URL}/en/productgroup/${groupSlug}/`)
        const $ = cheerio.load(html)
        $("a[href*='/en/products/']").each((_, el) => {
          const href = $(el).attr("href") || ""
          if (isProductUrl(href)) {
            const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
            urls.push(fullUrl)
          }
        })
        console.log(`  Group ${groupSlug}: found products`)
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
  const slug = url.split("/products/")[1]?.replace(/\/$/, "") || ""

  // ── Title ──
  // Berliner uses <div class="title typo-h1"> not <h1>
  const title =
    $("div.title.typo-h1").first().text().trim() ||
    $("h1").first().text().trim() ||
    $("table.bsf-specs-table thead th").first().text().trim() ||
    slug

  // ── Description ──
  const description =
    $(".produktgruppen-header-content-long-description").first().text().trim() ||
    $(".entry-content p").first().text().trim() ||
    ""

  // ── Breadcrumb → product group ──
  const breadcrumbs = $("div.breadcrumbs a.text-turquoise")
    .map((_, el) => $(el).text().trim())
    .get()
    .filter((b) => b && b !== "Homepage" && b !== "Product groups" && b !== "Products")
  const productGroup = breadcrumbs[breadcrumbs.length - 1] || ""

  // ── Article number from specs table ──
  // First tbody row has the SKU in <span class="px-5">
  const skuFromTable = $("table.bsf-specs-table tbody tr")
    .first()
    .find("span.px-5")
    .text()
    .trim()
  // Fallback: regex match XX.XXX.XXX anywhere
  const bodyText = $.root().text()
  const skuMatch = bodyText.match(/(\d{2}\.\d{3}\.\d{3})/)
  const sku = skuFromTable || (skuMatch ? skuMatch[1] : "")

  // ── Images ──
  const imageUrls: string[] = []

  // 1. Feature/main image
  $(".produktgruppen-header-image img").each((_, el) => {
    const src = $(el).attr("src") || ""
    if (src && src.includes("berlinerzone")) imageUrls.push(src)
    // Get highest-res from srcset
    const srcset = $(el).attr("srcset") || ""
    const biggest = srcset
      .split(",")
      .map((s) => s.trim().split(/\s+/))
      .sort((a, b) => parseInt(b[1] || "0") - parseInt(a[1] || "0"))
    if (biggest.length && biggest[0][0]) {
      const hiRes = biggest[0][0]
      if (!imageUrls.includes(hiRes)) imageUrls.unshift(hiRes)
    }
  })

  // 2. Thumbnail gallery — full-res URL in parent's data-full-image attribute
  $(".produktgruppen-header-content-image[data-full-image]").each((_, el) => {
    const fullImg = $(el).attr("data-full-image") || ""
    if (fullImg && !imageUrls.includes(fullImg)) imageUrls.push(fullImg)
  })

  // 3. Any other product images in the page body (not nav/footer icons)
  $("article.produkte img, .entry-content.produkte-detailpage img").each((_, el) => {
    const src = $(el).attr("src") || ""
    if (
      src &&
      src.includes("berlinerzone.b-cdn.net") &&
      !src.includes(".svg") &&
      !src.includes("bsf-specs") &&
      !src.includes("icon") &&
      !src.includes("logo") &&
      !imageUrls.includes(src)
    ) {
      imageUrls.push(src)
    }
  })

  // ── Specifications table ──
  // Structure: 3-column rows → icon | label (with unit) | value
  const rawSpecs: Record<string, string> = {}
  const specRows = $("table.bsf-specs-table tbody tr").toArray()

  for (const row of specRows) {
    const cells = $(row).find("td")
    if (cells.length < 3) continue

    // Icon determines the spec type
    const icon = $(cells[0]).find("img").attr("src") || ""
    const label = $(cells[1]).text().trim()
    const value = $(cells[2]).text().trim()

    if (!value) continue

    if (icon.includes("bsf-specs-01")) {
      rawSpecs["Dimensions"] = value
    } else if (icon.includes("bsf-specs-02")) {
      rawSpecs["EN 1176 Safety Zone"] = value
    } else if (icon.includes("bsf-specs-03")) {
      rawSpecs["Fall Height"] = value
    } else if (icon.includes("bsf-specs-04")) {
      rawSpecs["Min Age"] = value
    } else if (label) {
      rawSpecs[label] = value
    }
  }

  // Also extract ASTM safety zone if present (sometimes separate row)
  const astmRow = specRows.find((row) => {
    const text = $(row).text()
    return text.includes("ASTM") || text.includes("CSA")
  })
  if (astmRow) {
    const cells = $(astmRow).find("td")
    if (cells.length >= 3) {
      rawSpecs["ASTM Safety Zone"] = $(cells[2]).text().trim()
    }
  }

  // ── Parse structured specs ──
  // Dimensions format: "8,3 x 11,0 x 6,0\n23-6 x 36-0 x 19-8" (meters with comma decimal, then imperial)
  // The values are in meters — parseDimensions handles conversion with the "m" flag
  const dimText = rawSpecs["Dimensions"] || ""
  // Extract just the metric numbers (comma-decimal, before any imperial line)
  const metricNums = dimText.match(/[\d,]+/g)?.slice(0, 3).map(n => parseFloat(n.replace(",", "."))) || []
  const dimensions = {
    length_cm: Math.round((metricNums[0] || 0) * 100),
    width_cm: Math.round((metricNums[1] || 0) * 100),
    height_cm: Math.round((metricNums[2] || 0) * 100),
  }

  const safetyEnText = rawSpecs["EN 1176 Safety Zone"] || ""
  const safetyEnNums = safetyEnText.match(/[\d,]+/g)?.slice(0, 3).map(n => parseFloat(n.replace(",", "."))) || []
  const safetyZoneEn = {
    length_cm: Math.round((safetyEnNums[0] || 0) * 100),
    width_cm: Math.round((safetyEnNums[1] || 0) * 100),
  }

  const safetyAstmText = rawSpecs["ASTM Safety Zone"] || ""
  const safetyAstmNums = safetyAstmText.match(/[\d,]+/g)?.slice(0, 3).map(n => parseFloat(n.replace(",", "."))) || []
  const safetyZoneAstm = {
    length_cm: Math.round((safetyAstmNums[0] || 0) * 100),
    width_cm: Math.round((safetyAstmNums[1] || 0) * 100),
  }

  // Fall height: "2,6\n8-6" (first value is meters)
  const fallText = rawSpecs["Fall Height"] || ""
  const fallNums = fallText.match(/[\d,]+/g)
  const fall_height_cm = fallNums
    ? Math.round(parseFloat(fallNums[0].replace(",", ".")) * 100)
    : 0

  // Age: "5+\n..." (first value before newline)
  const ageText = rawSpecs["Min Age"] || ""
  const ageClean = ageText.replace(/\s+/g, " ").trim().split(/\s/)[0] || ""
  const age_group = ageClean || "3+"

  // Max users — look in body text
  const maxUsersMatch = bodyText.match(/(?:max\.?\s*(?:simultaneous\s*)?users?|capacity)[:\s]*(\d+)/i)
  const max_users = maxUsersMatch ? parseInt(maxUsersMatch[1]) : 0

  // ── Downloads ──
  const downloads: { type: string; url: string; filename: string }[] = []
  $(".downloads-buttons a[download], a[download][href$='.pdf'], a[download][href$='.dwg']").each(
    (_, el) => {
      const href = $(el).attr("href") || ""
      if (!href) return
      const text = $(el).text().trim().toLowerCase()
      const spanText = $(el).find("span").text().trim().toLowerCase()
      const linkText = spanText || text
      const filename = decodeURIComponent(path.basename(href))

      let type = "other"
      if (linkText.includes("certificate") || linkText.includes("tüv") || linkText.includes("tuv"))
        type = "certificate"
      else if (linkText.includes("specification") || linkText.includes("spec"))
        type = "datasheet"
      else if (href.toLowerCase().endsWith(".dwg") || linkText.includes("2d"))
        type = "dwg_2d"
      else if (linkText.includes("color") || linkText.includes("colour") || linkText.includes("palette"))
        type = "color_palette"

      const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
      if (!downloads.find((d) => d.url === fullUrl)) {
        downloads.push({ type, url: fullUrl, filename })
      }
    }
  )

  // ── Related products ──
  const relatedProducts: string[] = []
  $("a[href*='/en/products/']").each((_, el) => {
    const href = $(el).attr("href") || ""
    if (href.includes("?")) return // skip filter links
    const relSlug = href.split("/products/")[1]?.replace(/\/$/, "")
    if (relSlug && relSlug !== slug && relSlug.length > 0 && !relatedProducts.includes(relSlug)) {
      relatedProducts.push(relSlug)
    }
  })

  // ── Taxonomies from <article> class names ──
  const articleClasses = $("article.produkte").attr("class") || ""
  const taxonomies = {
    equipment_type: [] as string[],
    target_group: [] as string[],
    play_function: [] as string[],
  }
  // Extract from classes like "produkte-geraetetyp-net-climber-2"
  const typeMatches = articleClasses.match(/produkte-geraetetyp-([a-z0-9-]+)/g) || []
  for (const m of typeMatches) {
    const name = m
      .replace("produkte-geraetetyp-", "")
      .replace(/-\d+$/, "")
      .replace(/-/g, " ")
    if (!taxonomies.equipment_type.includes(name)) taxonomies.equipment_type.push(name)
  }
  const groupMatches = articleClasses.match(/produkte-produktgruppe-([a-z0-9-]+)/g) || []
  for (const m of groupMatches) {
    const name = m
      .replace("produkte-produktgruppe-", "")
      .replace(/-\d+$/, "")
      .replace(/-/g, " ")
    if (!taxonomies.play_function.includes(name)) taxonomies.play_function.push(name)
  }

  // ── Category mapping ──
  const categoryMap: Record<string, string> = {
    classics: "rope-play-structures",
    univers: "rope-play-structures",
    greenville: "nature-play",
    villago: "themed-play",
    levelup: "climbing-structures",
    woodville: "timber-play",
    polygodes: "geometric-play",
    "twist & shout": "spinning-play",
    "twist shout": "spinning-play",
    terranos: "low-rope-courses",
    terranova: "low-rope-courses",
    combination: "combination-play",
    "custom-made": "custom-play",
    "custom made": "custom-play",
    ufos: "single-play-elements",
    geos: "geometric-play",
    hodgepodge: "mixed-play",
    "spooky rookies": "themed-play",
    waggawagga: "low-rope-courses",
  }

  const categoryHandle =
    categoryMap[productGroup.toLowerCase()] ||
    productGroup.toLowerCase().replace(/[^a-z0-9]+/g, "-") ||
    "rope-play-equipment"

  return {
    title,
    handle: `berliner-${slug}`,
    description,
    sku,
    vendor_url: url,
    product_group: productGroup,
    category: categoryHandle,
    thumbnail_url: imageUrls[0] || "",
    image_urls: imageUrls,
    dimensions,
    safety_zone_en: { length_cm: safetyZoneEn.length_cm, width_cm: safetyZoneEn.width_cm },
    safety_zone_astm: { length_cm: safetyZoneAstm.length_cm, width_cm: safetyZoneAstm.width_cm },
    fall_height_cm,
    max_users,
    age_group,
    certifications: ["EN 1176", "ASTM/CSA", "TUV"],
    downloads,
    related_products: relatedProducts.slice(0, 10),
    taxonomies,
    raw_specs: rawSpecs,
  }
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  // Ensure output dirs
  for (const dir of ["images", "downloads"]) {
    fs.mkdirSync(path.join(OUTPUT_DIR, dir), { recursive: true })
  }

  // Step 1: Discover
  console.log("=== BERLINER SEILFABRIK SCRAPER ===\n")
  console.log("Step 1: Discovering product URLs...")
  const urls = await discoverProductUrls()
  console.log(`Found ${urls.length} product URLs\n`)

  if (urls.length === 0) {
    console.error("No product URLs found. Check sitemap access or crawl logic.")
    process.exit(1)
  }

  // Save URL list
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "product-urls.txt"),
    urls.join("\n")
  )

  // Step 2: Extract product data
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

  // Step 3: Download assets
  console.log("\nStep 3: Downloading assets...")
  let imgCount = 0
  let dlCount = 0

  for (const product of products) {
    // Download images (limit to first 5 per product)
    for (const imgUrl of product.image_urls.slice(0, 5)) {
      const result = await downloadAsset(imgUrl, path.join(OUTPUT_DIR, "images"))
      if (result) imgCount++
    }
    // Download PDFs and DWGs
    for (const dl of product.downloads) {
      const result = await downloadAsset(dl.url, path.join(OUTPUT_DIR, "downloads"))
      if (result) dlCount++
    }
  }

  // Save results
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "products.json"),
    JSON.stringify(products, null, 2)
  )
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "errors.json"),
    JSON.stringify(errors, null, 2)
  )

  // Summary
  console.log("\n=== SCRAPING COMPLETE ===")
  console.log(`Products scraped: ${products.length}`)
  console.log(`Errors: ${errors.length}`)
  console.log(`Images downloaded: ${imgCount}`)
  console.log(`Documents downloaded: ${dlCount}`)
  console.log(`Output: ${OUTPUT_DIR}/products.json`)
}

main().catch(console.error)
