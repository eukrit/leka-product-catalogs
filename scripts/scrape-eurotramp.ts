/**
 * Scrape Eurotramp product catalog
 *
 * Usage: npx tsx scripts/scrape-eurotramp.ts [--limit N] [--include-accessories]
 *
 * Outputs:
 *   data/scraped/eurotramp/products.json
 *   data/scraped/eurotramp/images/
 *   data/scraped/eurotramp/downloads/
 */

import * as cheerio from "cheerio"
import * as fs from "fs"
import * as path from "path"

const BASE_URL = "https://www.eurotramp.com"
const OUTPUT_DIR = path.resolve(__dirname, "../data/scraped/eurotramp")
const DELAY_MS = 800
const args = process.argv.slice(2)
const limitIdx = args.indexOf("--limit")
const LIMIT = limitIdx >= 0 ? parseInt(args[limitIdx + 1]) : Infinity
const INCLUDE_ACCESSORIES = args.includes("--include-accessories")

// ── Types ────────────────────────────────────────────────────────────────

interface ScrapedProduct {
  title: string
  subtitle: string
  handle: string
  description: string
  sku: string
  article_numbers: string[]
  vendor_url: string
  product_group: string
  category: string
  thumbnail_url: string
  image_urls: string[]
  dimensions: { length_cm: number; width_cm: number; height_cm: number }
  stowed_dimensions: { length_cm: number; width_cm: number; height_cm: number }
  weight_kg: number
  certifications: string[]
  standards: string[]
  downloads: { type: string; url: string; filename: string }[]
  accessories: { title: string; url: string; article_numbers: string[] }[]
  spare_part_categories: string[]
  faq: { question: string; answer: string }[]
  variants: {
    name: string
    options: string[]
  }[]
  raw_specs: Record<string, string>
  is_accessory: boolean
  is_discontinued: boolean
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

function parseDimensions(text: string): {
  length_cm: number
  width_cm: number
  height_cm: number
} {
  const nums =
    text.match(/[\d,.]+/g)?.map((n) => parseFloat(n.replace(",", "."))) || []
  return {
    length_cm: Math.round(nums[0] || 0),
    width_cm: Math.round(nums[1] || 0),
    height_cm: Math.round(nums[2] || 0),
  }
}

// ── Discovery ────────────────────────────────────────────────────────────

const CATEGORY_SLUGS = [
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
]

async function discoverProductUrls(): Promise<
  { url: string; category: string; isAccessory: boolean }[]
> {
  const found: { url: string; category: string; isAccessory: boolean }[] = []
  const seen = new Set<string>()

  // Main product categories
  for (const catSlug of CATEGORY_SLUGS) {
    console.log(`  Crawling category: ${catSlug}`)
    try {
      const html = await fetchPage(
        `${BASE_URL}/en/product-categories/${catSlug}/`
      )
      const $ = cheerio.load(html)

      $("a[href*='/en/products/']").each((_, el) => {
        const href = $(el).attr("href") || ""
        const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
        // Normalize: remove trailing hash/tab paths, keep base product URL
        const baseUrl = fullUrl.split("/details/")[0].split("/accessories/")[0].split("/downloads/")[0].split("/faq/")[0].split("/spare-parts/")[0].split("/dealers/")[0]
        const normalized = baseUrl.endsWith("/") ? baseUrl : baseUrl + "/"

        if (!seen.has(normalized) && normalized.includes("/en/products/")) {
          seen.add(normalized)
          found.push({
            url: normalized,
            category: catSlug,
            isAccessory: false,
          })
        }
      })
    } catch (e: any) {
      console.log(`  Category ${catSlug} failed: ${e.message}`)
    }
  }

  // Accessories
  if (INCLUDE_ACCESSORIES) {
    console.log("  Crawling accessories...")
    try {
      const html = await fetchPage(`${BASE_URL}/en/accessories/`)
      const $ = cheerio.load(html)
      $("a[href*='/en/products/']").each((_, el) => {
        const href = $(el).attr("href") || ""
        const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
        const baseUrl = fullUrl.split("/details/")[0].split("/accessories/")[0]
        const normalized = baseUrl.endsWith("/") ? baseUrl : baseUrl + "/"
        if (!seen.has(normalized)) {
          seen.add(normalized)
          found.push({
            url: normalized,
            category: "accessories",
            isAccessory: true,
          })
        }
      })
    } catch (e: any) {
      console.log(`  Accessories page failed: ${e.message}`)
    }
  }

  return found.slice(0, LIMIT)
}

// ── Extraction ───────────────────────────────────────────────────────────

async function scrapeProduct(
  url: string,
  category: string,
  isAccessory: boolean
): Promise<ScrapedProduct> {
  const html = await fetchPage(url)
  const $ = cheerio.load(html)

  const title = $("h1").first().text().trim()
  const subtitle =
    $("h2, .product-subtitle, .tagline").first().text().trim() || ""
  const slug =
    url
      .split("/products/")[1]
      ?.replace(/\/$/, "")
      .split("/")[0] || ""

  const bodyText = $.root().text()

  // Article numbers (5-digit or alphanumeric like E26410)
  const articleNumbers: string[] = []
  // Look for labeled article numbers first
  const artMatch = bodyText.match(
    /(?:Article\s*(?:No\.?|number)|Art\.\s*No\.?)[:\s]*([\w\d,\s]+)/i
  )
  if (artMatch) {
    const nums = artMatch[1].match(/\b[\dA-Z]{4,8}\b/g) || []
    for (const n of nums) {
      if (!articleNumbers.includes(n)) articleNumbers.push(n)
    }
  }
  // Fallback: find 5-digit numbers in product context
  if (articleNumbers.length === 0) {
    const fiveDigit = bodyText.match(/\b0\d{4}\b/g) || []
    for (const n of fiveDigit) {
      if (!articleNumbers.includes(n)) articleNumbers.push(n)
    }
  }
  const primarySku = articleNumbers[0] || ""

  // Description
  const descParts: string[] = []
  $("article p, .product-content p, .product-description p, main p").each(
    (_, el) => {
      const text = $(el).text().trim()
      if (
        text.length > 30 &&
        !text.match(/^\d/) &&
        !descParts.includes(text) &&
        !text.includes("cookie")
      ) {
        descParts.push(text)
      }
    }
  )
  const description = descParts.slice(0, 8).join("\n\n")

  // Specifications table
  const rawSpecs: Record<string, string> = {}
  $("table tr").each((_, el) => {
    const cells = $(el).find("td, th")
    if (cells.length >= 2) {
      const key = $(cells[0]).text().trim()
      const val = $(cells[1]).text().trim()
      if (key && val && key.length < 100) rawSpecs[key] = val
    }
  })
  $("dl dt").each((_, dt) => {
    const key = $(dt).text().trim()
    const dd = $(dt).next("dd")
    if (dd.length) rawSpecs[key] = dd.text().trim()
  })

  // Helper to find spec by partial key match
  const findSpec = (...keys: string[]): string => {
    for (const k of keys) {
      for (const [specKey, specVal] of Object.entries(rawSpecs)) {
        if (specKey.toLowerCase().includes(k.toLowerCase())) return specVal
      }
    }
    return ""
  }

  // Parse dimensions
  const dimText = findSpec("Installation dimensions", "Dimensions", "Size")
  const dimensions = parseDimensions(dimText)

  const stowedText = findSpec("Stowed", "Folded", "Storage")
  const stowedDimensions = parseDimensions(stowedText)

  // Weight
  const weightText = findSpec("Weight", "Gewicht")
  const weightMatch = weightText.match(/([\d,.]+)\s*kg/i)
  const weight_kg = weightMatch
    ? parseFloat(weightMatch[1].replace(",", "."))
    : 0

  // Images
  const imageUrls: string[] = []
  $("img").each((_, el) => {
    const src =
      $(el).attr("data-src") || $(el).attr("src") || ""
    if (
      src &&
      (src.includes("/_resources.d/images.d/") ||
        src.includes("/images.d/")) &&
      !src.includes("icon") &&
      !src.includes("logo") &&
      !imageUrls.includes(src)
    ) {
      const fullUrl = src.startsWith("http") ? src : `${BASE_URL}${src}`
      imageUrls.push(fullUrl)
    }
  })

  // Certifications
  const certifications: string[] = []
  const standards: string[] = []
  if (bodyText.includes("EN 13219")) {
    certifications.push("EN 13219")
    standards.push("EN 13219")
  }
  if (bodyText.includes("EN 1176") || bodyText.includes("DIN EN 1176")) {
    certifications.push("EN 1176")
    standards.push("DIN EN 1176")
  }
  if (/\bFIG\b/.test(bodyText)) certifications.push("FIG")
  if (/\bTUV\b|TÜV/.test(bodyText)) certifications.push("TUV")
  if (/\bGS\s*mark\b/i.test(bodyText)) certifications.push("GS")

  // Discontinued check
  const is_discontinued =
    bodyText.toLowerCase().includes("discontinued") ||
    url.includes("discontinued")

  // Downloads tab
  const downloads: { type: string; url: string; filename: string }[] = []
  try {
    const dlHtml = await fetchPage(`${url}downloads/`)
    const $dl = cheerio.load(dlHtml)
    $dl("a[href$='.pdf']").each((_, el) => {
      const href = $dl(el).attr("href") || ""
      const text = $dl(el).text().trim().toLowerCase()
      const filename = decodeURIComponent(path.basename(href))
      let type = "other"
      if (text.includes("tuv") || text.includes("tüv") || text.includes("certificate"))
        type = "certificate"
      else if (text.includes("fig")) type = "certificate"
      else if (text.includes("factsheet") || text.includes("fact sheet"))
        type = "datasheet"
      else if (text.includes("flyer") || text.includes("brochure"))
        type = "brochure"
      else if (
        text.includes("installation") ||
        text.includes("assembly") ||
        text.includes("setup")
      )
        type = "manual"
      else if (text.includes("maintenance") || text.includes("care"))
        type = "manual"
      else if (text.includes("competition")) type = "guide"

      const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
      if (!downloads.find((d) => d.url === fullUrl)) {
        downloads.push({ type, url: fullUrl, filename })
      }
    })
  } catch {}

  // Accessories tab
  const accessories: { title: string; url: string; article_numbers: string[] }[] = []
  try {
    const accHtml = await fetchPage(`${url}accessories/`)
    const $acc = cheerio.load(accHtml)
    $acc("a[href*='/en/products/']").each((_, el) => {
      const href = $acc(el).attr("href") || ""
      const accTitle = $acc(el).text().trim()
      const fullUrl = href.startsWith("http") ? href : `${BASE_URL}${href}`
      // Extract article numbers from link text/context
      const accNums = accTitle.match(/\b\d{5}\b/g) || []
      if (accTitle && fullUrl !== url) {
        accessories.push({
          title: accTitle,
          url: fullUrl,
          article_numbers: accNums,
        })
      }
    })
  } catch {}

  // FAQ tab
  const faq: { question: string; answer: string }[] = []
  try {
    const faqHtml = await fetchPage(`${url}faq/`)
    const $faq = cheerio.load(faqHtml)
    // FAQ typically uses accordion or dl/dt/dd
    $faq(".faq-question, .accordion-title, dt, h3").each((_, el) => {
      const question = $faq(el).text().trim()
      const answer =
        $faq(el).next(".faq-answer, .accordion-content, dd, p").text().trim() ||
        ""
      if (question && answer && question.length < 200) {
        faq.push({ question, answer })
      }
    })
  } catch {}

  // Variant options (jumping bed types, frame pads, etc.)
  const variants: { name: string; options: string[] }[] = []

  // Look for option selectors or labeled lists
  $("select, .option-group").each((_, el) => {
    const label =
      $(el).attr("name") ||
      $(el).prev("label").text().trim() ||
      $(el).attr("data-label") ||
      ""
    if (label) {
      const options = $(el)
        .find("option")
        .map((_, opt) => $(opt).text().trim())
        .get()
        .filter((o) => o && o !== "---")
      if (options.length > 1) {
        variants.push({ name: label, options })
      }
    }
  })

  // Spare part categories
  const sparePartCategories: string[] = []
  try {
    const spHtml = await fetchPage(`${url}spare-parts/`)
    const $sp = cheerio.load(spHtml)
    $sp("a[href*='spare-part-categories'], .spare-part-category, h3, h4").each(
      (_, el) => {
        const text = $sp(el).text().trim()
        if (text && text.length < 80 && !sparePartCategories.includes(text)) {
          sparePartCategories.push(text)
        }
      }
    )
  } catch {}

  // Map category
  const categoryHandle = category
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")

  return {
    title,
    subtitle,
    handle: `eurotramp-${slug}`,
    description: subtitle
      ? `${subtitle}\n\n${description}`
      : description,
    sku: primarySku,
    article_numbers: articleNumbers,
    vendor_url: url,
    product_group: category,
    category: categoryHandle,
    thumbnail_url: imageUrls[0] || "",
    image_urls: imageUrls,
    dimensions,
    stowed_dimensions: stowedDimensions,
    weight_kg,
    certifications,
    standards,
    downloads,
    accessories,
    spare_part_categories: sparePartCategories,
    faq,
    variants,
    raw_specs: rawSpecs,
    is_accessory: isAccessory,
    is_discontinued,
  }
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  for (const dir of ["images", "downloads"]) {
    fs.mkdirSync(path.join(OUTPUT_DIR, dir), { recursive: true })
  }

  console.log("=== EUROTRAMP SCRAPER ===\n")
  console.log("Step 1: Discovering product URLs...")
  const entries = await discoverProductUrls()
  console.log(`Found ${entries.length} product URLs\n`)

  if (entries.length === 0) {
    console.error("No product URLs found.")
    process.exit(1)
  }

  fs.writeFileSync(
    path.join(OUTPUT_DIR, "product-urls.txt"),
    entries.map((e) => `${e.url}\t${e.category}\t${e.isAccessory}`).join("\n")
  )

  // Step 2: Extract
  console.log("Step 2: Scraping product details (including tabs)...")
  const products: ScrapedProduct[] = []
  const errors: { url: string; error: string }[] = []

  for (const [i, entry] of entries.entries()) {
    console.log(
      `\n[${i + 1}/${entries.length}] ${entry.url} (${entry.category})`
    )
    try {
      const product = await scrapeProduct(
        entry.url,
        entry.category,
        entry.isAccessory
      )
      products.push(product)
      console.log(
        `  OK: ${product.title} (SKU: ${product.sku}, ${product.downloads.length} downloads, ${product.accessories.length} accessories)`
      )
    } catch (e: any) {
      console.error(`  FAILED: ${e.message}`)
      errors.push({ url: entry.url, error: e.message })
    }
  }

  // Step 3: Download assets
  console.log("\nStep 3: Downloading assets...")
  let imgCount = 0
  let dlCount = 0

  for (const product of products) {
    for (const imgUrl of product.image_urls.slice(0, 5)) {
      const result = await downloadAsset(
        imgUrl,
        path.join(OUTPUT_DIR, "images")
      )
      if (result) imgCount++
    }
    for (const dl of product.downloads) {
      const result = await downloadAsset(
        dl.url,
        path.join(OUTPUT_DIR, "downloads")
      )
      if (result) dlCount++
    }
  }

  // Save
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
  console.log(
    `  Main products: ${products.filter((p) => !p.is_accessory).length}`
  )
  console.log(
    `  Accessories: ${products.filter((p) => p.is_accessory).length}`
  )
  console.log(
    `  Discontinued: ${products.filter((p) => p.is_discontinued).length}`
  )
  console.log(`Errors: ${errors.length}`)
  console.log(`Images downloaded: ${imgCount}`)
  console.log(`Documents downloaded: ${dlCount}`)
  console.log(
    `Total downloads across products: ${products.reduce((s, p) => s + p.downloads.length, 0)}`
  )
  console.log(`Output: ${OUTPUT_DIR}/products.json`)
}

main().catch(console.error)
