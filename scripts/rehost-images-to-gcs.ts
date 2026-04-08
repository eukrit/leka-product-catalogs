/**
 * Re-host vendor product images from CDN URLs to GCS
 *
 * Usage:
 *   npx tsx scripts/rehost-images-to-gcs.ts --vendor berliner [--dry-run] [--limit N]
 *   npx tsx scripts/rehost-images-to-gcs.ts --vendor all
 *
 * Flow:
 *   1. Load products.json for vendor
 *   2. For each image URL, check if already in local images/ folder
 *   3. If not local, download from vendor CDN
 *   4. Upload to GCS: gs://ai-agents-go-documents/product-images/{vendor}/{handle}/{filename}
 *   5. Update Medusa product with new GCS URLs
 */

import * as fs from "fs"
import * as path from "path"
import { Storage } from "@google-cloud/storage"

// ── Config ──────────────────────────────────────────────────────────────

const MEDUSA_URL = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
const ADMIN_EMAIL = "admin@leka.studio"
const ADMIN_PASSWORD = "LekaAdmin2026"
const GCS_BUCKET = "ai-agents-go-documents"
const GCS_PREFIX = "product-images"
const GCS_PUBLIC_BASE = `https://storage.googleapis.com/${GCS_BUCKET}`
const CRED_PATH = path.resolve("C:/Users/Eukrit/OneDrive/Documents/Claude Code/Credentials Claude Code/ai-agents-go-4c81b70995db.json")
const DATA_DIR = path.resolve(__dirname, "../data/scraped")

const args = process.argv.slice(2)
const DRY_RUN = args.includes("--dry-run")
const vendorIdx = args.indexOf("--vendor")
const VENDOR = vendorIdx >= 0 ? args[vendorIdx + 1] : null
const limitIdx = args.indexOf("--limit")
const LIMIT = limitIdx >= 0 ? parseInt(args[limitIdx + 1]) : Infinity

if (!VENDOR) {
  console.error("Usage: npx tsx scripts/rehost-images-to-gcs.ts --vendor <berliner|eurotramp|rampline|4soft|all>")
  process.exit(1)
}

const VENDORS = ["berliner", "eurotramp", "rampline", "4soft"]

// ── GCS Client ──────────────────────────────────────────────────────────

const storage = new Storage({ keyFilename: CRED_PATH })
const bucket = storage.bucket(GCS_BUCKET)

// ── Medusa Auth ─────────────────────────────────────────────────────────

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
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 300)}`)
  }
  return res.json()
}

// ── Helpers ─────────────────────────────────────────────────────────────

function filenameFromUrl(url: string): string {
  try {
    const u = new URL(url)
    const base = path.basename(u.pathname)
    // Clean up query strings from filename
    return base.replace(/[?#].*$/, "") || "image.jpg"
  } catch {
    return "image.jpg"
  }
}

async function fileExistsInGcs(gcsPath: string): Promise<boolean> {
  try {
    const [exists] = await bucket.file(gcsPath).exists()
    return exists
  } catch {
    return false
  }
}

async function uploadBufferToGcs(buffer: Buffer, gcsPath: string, contentType: string): Promise<string> {
  const file = bucket.file(gcsPath)
  await file.save(buffer, { contentType, resumable: false })
  return `${GCS_PUBLIC_BASE}/${gcsPath}`
}

async function downloadUrl(url: string): Promise<{ buffer: Buffer; contentType: string } | null> {
  // Use curl as a subprocess — Node fetch/https fails on some CDNs (timeouts, TLS)
  try {
    const { execSync } = require("child_process")
    const tmpFile = path.join(require("os").tmpdir(), `rehost-${Date.now()}-${Math.random().toString(36).slice(2)}`)
    execSync(`curl -sL -o "${tmpFile}" --max-time 30 "${url}"`, { timeout: 35000 })
    if (!fs.existsSync(tmpFile)) return null
    const buffer = fs.readFileSync(tmpFile)
    fs.unlinkSync(tmpFile)
    if (buffer.length < 100) return null // too small, likely an error page
    const ext = path.extname(new URL(url).pathname).toLowerCase()
    const contentType = getContentType(ext ? `file${ext}` : "file.jpg")
    return { buffer, contentType }
  } catch {
    return null
  }
}

function getContentType(filename: string): string {
  const ext = path.extname(filename).toLowerCase()
  const types: Record<string, string> = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".pdf": "application/pdf", ".dwg": "application/acad",
    ".dxf": "application/dxf", ".zip": "application/zip",
  }
  return types[ext] || "application/octet-stream"
}

// ── Per-Vendor Processing ───────────────────────────────────────────────

async function rehostVendor(vendor: string) {
  const productsFile = path.join(DATA_DIR, vendor, "products.json")
  const imagesDir = path.join(DATA_DIR, vendor, "images")
  const downloadsDir = path.join(DATA_DIR, vendor, "downloads")

  if (!fs.existsSync(productsFile)) {
    console.error(`  No products.json for ${vendor}`)
    return
  }

  const products = JSON.parse(fs.readFileSync(productsFile, "utf-8")).slice(0, LIMIT)
  console.log(`\n=== RE-HOST: ${vendor.toUpperCase()} (${products.length} products) ===\n`)

  // Build local file index for fast lookup
  const localImages = new Map<string, string>()
  if (fs.existsSync(imagesDir)) {
    for (const f of fs.readdirSync(imagesDir)) {
      localImages.set(f.toLowerCase(), path.join(imagesDir, f))
    }
  }
  const localDownloads = new Map<string, string>()
  if (fs.existsSync(downloadsDir)) {
    for (const f of fs.readdirSync(downloadsDir)) {
      localDownloads.set(f.toLowerCase(), path.join(downloadsDir, f))
    }
  }

  let uploaded = 0, skipped = 0, failed = 0, medusaUpdated = 0

  for (const [i, p] of products.entries()) {
    const handle = p.handle || ""
    if (!handle) continue

    const allUrls: string[] = []
    if (p.thumbnail_url) allUrls.push(p.thumbnail_url)
    for (const u of (p.image_urls || [])) allUrls.push(u)
    for (const d of (p.downloads || [])) if (d.url) allUrls.push(d.url)

    if (allUrls.length === 0) continue

    const urlMap: Record<string, string> = {} // original URL → GCS URL

    for (const url of allUrls) {
      const filename = filenameFromUrl(url)
      const gcsPath = `${GCS_PREFIX}/${vendor}/${handle}/${filename}`
      const gcsUrl = `${GCS_PUBLIC_BASE}/${gcsPath}`

      // Check if already uploaded
      if (await fileExistsInGcs(gcsPath)) {
        urlMap[url] = gcsUrl
        skipped++
        continue
      }

      if (DRY_RUN) {
        urlMap[url] = gcsUrl
        skipped++
        continue
      }

      // Try local file first
      const localKey = filename.toLowerCase()
      let buffer: Buffer | null = null
      let contentType = getContentType(filename)

      if (localImages.has(localKey)) {
        buffer = fs.readFileSync(localImages.get(localKey)!)
      } else if (localDownloads.has(localKey)) {
        buffer = fs.readFileSync(localDownloads.get(localKey)!)
      }

      // If not local, download from CDN
      if (!buffer) {
        const dl = await downloadUrl(url)
        if (dl) {
          buffer = dl.buffer
          contentType = dl.contentType
        }
      }

      if (buffer) {
        try {
          const newUrl = await uploadBufferToGcs(buffer, gcsPath, contentType)
          urlMap[url] = newUrl
          uploaded++
        } catch (e: any) {
          console.error(`  FAIL upload ${filename}: ${e.message}`)
          failed++
        }
      } else {
        console.error(`  FAIL download ${url.slice(0, 80)}`)
        failed++
      }
    }

    // Update Medusa product with new URLs
    if (!DRY_RUN && Object.keys(urlMap).length > 0) {
      try {
        // Find product in Medusa by handle
        const search = await medusaFetch(`/admin/products?handle=${handle}&fields=id,thumbnail,images`)
        if (search.products?.length) {
          const prod = search.products[0]
          const update: any = {}

          // Update thumbnail
          if (p.thumbnail_url && urlMap[p.thumbnail_url]) {
            update.thumbnail = urlMap[p.thumbnail_url]
          }

          // Update images
          const newImages = (p.image_urls || [])
            .map((u: string) => urlMap[u] || u)
            .map((url: string) => ({ url }))
          if (newImages.length > 0) {
            update.images = newImages
          }

          // Update downloads in metadata
          if (p.downloads?.length) {
            const newDownloads = p.downloads.map((d: any) => ({
              type: d.type,
              filename: d.filename,
              original_url: d.url,
              gcs_url: urlMap[d.url] || d.url,
            }))
            update.metadata = { ...prod.metadata, downloads: newDownloads }
          }

          if (Object.keys(update).length > 0) {
            await medusaFetch(`/admin/products/${prod.id}`, {
              method: "POST",
              body: JSON.stringify(update),
            })
            medusaUpdated++
          }
        }
      } catch (e: any) {
        console.error(`  FAIL medusa update ${handle}: ${e.message.slice(0, 100)}`)
      }
    }

    if ((i + 1) % 50 === 0) {
      console.log(`  [${i + 1}/${products.length}] uploaded=${uploaded} skipped=${skipped} failed=${failed} medusa=${medusaUpdated}`)
    }
  }

  console.log(`\n  ${vendor} done: uploaded=${uploaded} skipped=${skipped} failed=${failed} medusaUpdated=${medusaUpdated}`)
  return { uploaded, skipped, failed, medusaUpdated }
}

// ── Main ────────────────────────────────────────────────────────────────

async function main() {
  console.log("=== RE-HOST IMAGES TO GCS ===")
  console.log(`Bucket: gs://${GCS_BUCKET}/${GCS_PREFIX}/`)
  console.log(`Dry run: ${DRY_RUN}\n`)

  if (!DRY_RUN) {
    console.log("Authenticating with Medusa...")
    await authenticate()
    console.log("OK\n")
  }

  const vendorKeys = VENDOR === "all" ? VENDORS : [VENDOR!]
  const totals = { uploaded: 0, skipped: 0, failed: 0, medusaUpdated: 0 }

  for (const v of vendorKeys) {
    const result = await rehostVendor(v)
    if (result) {
      totals.uploaded += result.uploaded
      totals.skipped += result.skipped
      totals.failed += result.failed
      totals.medusaUpdated += result.medusaUpdated
    }
  }

  console.log("\n=== ALL DONE ===")
  console.log(`Uploaded: ${totals.uploaded}`)
  console.log(`Skipped (already in GCS): ${totals.skipped}`)
  console.log(`Failed: ${totals.failed}`)
  console.log(`Medusa products updated: ${totals.medusaUpdated}`)
}

main().catch(console.error)
