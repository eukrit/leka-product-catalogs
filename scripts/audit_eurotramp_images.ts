/**
 * Audit Eurotramp products' images in Medusa.
 *
 * Output: docs/reports/eurotramp-image-audit-<YYYY-MM-DD>.md
 *
 * Walks ALL Medusa products page-by-page (since /admin/products q= does not
 * search by handle reliably) and filters to anything where:
 *   - handle starts with "eurotramp-", OR
 *   - metadata.brand_slug === "eurotramp"
 *
 * Per product, records image count, filenames, thumbnail, whether
 * filenames match the catalogs storefront cert regex, and whether the
 * product has ZERO non-cert images (backfill target).
 *
 * Usage: npx tsx scripts/audit_eurotramp_images.ts
 */

import * as fs from "fs"
import * as path from "path"

const MEDUSA_URL =
  "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
const ADMIN_EMAIL = process.env.LEKA_MEDUSA_ADMIN_EMAIL || "admin@leka.studio"
const ADMIN_PASSWORD = process.env.LEKA_MEDUSA_ADMIN_PASSWORD
if (!ADMIN_PASSWORD) {
  console.error(
    "Missing LEKA_MEDUSA_ADMIN_PASSWORD. Fetch it from Secret Manager first, e.g.:\n" +
      "  PowerShell: $env:LEKA_MEDUSA_ADMIN_PASSWORD = (gcloud secrets versions access latest --secret=medusa-admin-password --project=ai-agents-go)\n" +
      "  bash:       export LEKA_MEDUSA_ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=medusa-admin-password --project=ai-agents-go)"
  )
  process.exit(1)
}

// Storefront cert regex as shipped in catalogs/v0.19.2 — `\b` falsely passes
// `tuev_*.jpg` because `_` is a word character. We keep it to report what the
// storefront actually sees today.
const CERT_RE_STOREFRONT =
  /\b(certificate|cert|tuv|tuev|t[uü]v|iso|ce[-_]?mark|gs[-_]?mark|compliance)\b/i

// Strict cert regex — uses `[a-z0-9]` lookarounds so `_`/`-`/`.` count as
// delimiters. This is the "ground truth" for whether a filename is a cert.
const CERT_RE_STRICT =
  /(?<![a-z0-9])(certificate|cert|tuv|tuev|tüv|iso|ce[-_]?mark|gs[-_]?mark|compliance)(?![a-z0-9])/i

function filenameFromUrl(url: string): string {
  try {
    return decodeURIComponent(path.basename(new URL(url).pathname))
  } catch {
    return path.basename(url)
  }
}

let authToken = ""

async function authenticate() {
  const res = await fetch(`${MEDUSA_URL}/auth/user/emailpass`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
  })
  if (!res.ok) throw new Error(`Auth failed: ${res.status}`)
  authToken = (await res.json()).token
}

async function admin<T = any>(endpoint: string): Promise<T> {
  const res = await fetch(`${MEDUSA_URL}${endpoint}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  })
  if (!res.ok) throw new Error(`${res.status} ${endpoint}: ${await res.text()}`)
  return res.json()
}

interface AuditRow {
  handle: string
  title: string
  thumbnail: string | null
  thumbnail_is_cert_strict: boolean
  thumbnail_is_cert_storefront: boolean
  image_count: number
  image_urls: string[]
  image_filenames: string[]
  cert_image_count_strict: number
  cert_image_count_storefront: number
  non_cert_image_count_strict: number
  is_backfill_target: boolean
  storefront_will_pick_cert: boolean
  vendor_url: string
  brand_slug: string
}

async function main() {
  console.log("Authenticating...")
  await authenticate()

  const PAGE = 200
  let offset = 0
  const rows: AuditRow[] = []
  let total = 0
  let scanned = 0

  while (true) {
    const fields = "id,handle,title,thumbnail,images.url,metadata"
    const url = `/admin/products?limit=${PAGE}&offset=${offset}&fields=${encodeURIComponent(
      fields
    )}`
    const data = await admin<{
      products: any[]
      count: number
      limit: number
      offset: number
    }>(url)
    total = data.count
    scanned += data.products.length
    console.log(
      `  Scanned ${scanned}/${data.count}  (eurotramp matches so far: ${rows.length})`
    )

    for (const p of data.products) {
      const meta = p.metadata || {}
      const brand = (meta.brand_slug || "").toString().toLowerCase()
      const isEurotramp =
        brand === "eurotramp" || (p.handle || "").startsWith("eurotramp-")
      if (!isEurotramp) continue

      const imgs: string[] = (p.images || []).map((i: any) => i.url)
      const filenames = imgs.map(filenameFromUrl)
      const certHitsStrict = filenames.filter((f) => CERT_RE_STRICT.test(f))
      const certHitsStorefront = filenames.filter((f) =>
        CERT_RE_STOREFRONT.test(f)
      )
      const nonCertCountStrict = filenames.length - certHitsStrict.length

      const thumbCertStrict = p.thumbnail
        ? CERT_RE_STRICT.test(filenameFromUrl(p.thumbnail))
        : false
      const thumbCertStorefront = p.thumbnail
        ? CERT_RE_STOREFRONT.test(filenameFromUrl(p.thumbnail))
        : false

      // Backfill target = ZERO genuine product photos in Medusa data.
      const isBackfillTarget = nonCertCountStrict === 0
      // Storefront will pick a cert as og:image when every URL it considers is
      // a strict-cert AND none of them trips the storefront regex.
      const allUrlsStorefrontMissed = imgs.every(
        (u) => !CERT_RE_STOREFRONT.test(u)
      )
      const storefrontWillPickCert =
        isBackfillTarget && imgs.length > 0 && allUrlsStorefrontMissed

      rows.push({
        handle: p.handle,
        title: p.title || "",
        thumbnail: p.thumbnail || null,
        thumbnail_is_cert_strict: thumbCertStrict,
        thumbnail_is_cert_storefront: thumbCertStorefront,
        image_count: filenames.length,
        image_urls: imgs,
        image_filenames: filenames,
        cert_image_count_strict: certHitsStrict.length,
        cert_image_count_storefront: certHitsStorefront.length,
        non_cert_image_count_strict: nonCertCountStrict,
        is_backfill_target: isBackfillTarget,
        storefront_will_pick_cert: storefrontWillPickCert,
        vendor_url: (meta.vendor_url || "").toString(),
        brand_slug: brand || "(none)",
      })
    }

    if (data.products.length < PAGE) break
    offset += PAGE
    if (scanned >= total) break
  }

  rows.sort((a, b) => a.handle.localeCompare(b.handle))

  const today = new Date().toISOString().slice(0, 10)
  const outDir = path.resolve(__dirname, "../docs/reports")
  fs.mkdirSync(outDir, { recursive: true })
  const outFile = path.join(outDir, `eurotramp-image-audit-${today}.md`)

  const targets = rows.filter((r) => r.is_backfill_target)
  const certOnly = rows.filter(
    (r) => r.image_count > 0 && r.non_cert_image_count_strict === 0
  )
  const noImages = rows.filter((r) => r.image_count === 0)
  const thumbCertStrict = rows.filter((r) => r.thumbnail_is_cert_strict)
  const storefrontBroken = rows.filter((r) => r.storefront_will_pick_cert)

  const lines: string[] = []
  lines.push(`# Eurotramp Image Audit — ${today}`)
  lines.push("")
  lines.push(`Source: live Medusa backend \`${MEDUSA_URL}\``)
  lines.push("")
  lines.push(`Storefront cert regex (catalogs/v0.19.2):`)
  lines.push("")
  lines.push(`    ${CERT_RE_STOREFRONT.source}`)
  lines.push("")
  lines.push(
    "Strict cert regex (this audit) — replaces `\\b` with `(?<![a-z0-9])`/`(?![a-z0-9])` so `_` counts as a delimiter and `tuev_1176_2021.jpg` is correctly classified:"
  )
  lines.push("")
  lines.push(`    ${CERT_RE_STRICT.source}`)
  lines.push("")
  lines.push("## Summary")
  lines.push("")
  lines.push(`- Total Medusa products scanned: **${total}**`)
  lines.push(`- Total Eurotramp products: **${rows.length}**`)
  lines.push(
    `- Products with **thumbnail = cert image** (strict): **${thumbCertStrict.length}**`
  )
  lines.push(
    `- Products with **zero non-cert images** (backfill targets): **${targets.length}**`
  )
  lines.push(`  - of which have **only cert images**: ${certOnly.length}`)
  lines.push(`  - of which have **no images at all**: ${noImages.length}`)
  lines.push(
    `- Products where **storefront will still pick a cert as og:image** (cert-only AND storefront regex misses the filename): **${storefrontBroken.length}** ← these are the visible OG-card failures the task is asking to fix`
  )
  lines.push(
    `- Products with at least one real photo: **${rows.length - targets.length}**`
  )
  lines.push("")

  lines.push(
    "## Storefront-visible failures (cert-only AND storefront regex misses it)"
  )
  lines.push("")
  lines.push(
    "These are the products where the live OG card today shows a TÜV/cert image. **First priority** — these break Slack/Canva/Miro/Discord OG previews."
  )
  lines.push("")
  lines.push(
    "| handle | title | images | thumb | storefront sees as cert? | vendor_url |"
  )
  lines.push("|---|---|---|---|---|---|")
  for (const r of storefrontBroken) {
    const thumb = r.thumbnail ? filenameFromUrl(r.thumbnail) : "—"
    const vurl = r.vendor_url ? `[link](${r.vendor_url})` : "—"
    lines.push(
      `| \`${r.handle}\` | ${r.title.replace(/\|/g, "\\|")} | ${r.image_count} | ${thumb.replace(/\|/g, "\\|")} | ${r.cert_image_count_storefront > 0 ? "yes" : "**no**"} | ${vurl} |`
    )
  }
  lines.push("")

  lines.push("## All backfill targets (zero real photos in Medusa)")
  lines.push("")
  lines.push(
    "Strict-regex view — every image is a cert (or there are no images at all). Even after fixing the storefront regex, these still need real photos."
  )
  lines.push("")
  lines.push(
    "| handle | title | images | cert (strict) | thumb | vendor_url |"
  )
  lines.push("|---|---|---|---|---|---|")
  for (const r of targets) {
    const thumb = r.thumbnail
      ? `${r.thumbnail_is_cert_strict ? "❌cert " : ""}${filenameFromUrl(r.thumbnail)}`
      : "—"
    const vurl = r.vendor_url ? `[link](${r.vendor_url})` : "—"
    lines.push(
      `| \`${r.handle}\` | ${r.title.replace(/\|/g, "\\|")} | ${r.image_count} | ${r.cert_image_count_strict} | ${thumb.replace(/\|/g, "\\|")} | ${vurl} |`
    )
  }
  lines.push("")

  lines.push(
    "## Products with cert-thumbnail but real photos available elsewhere"
  )
  lines.push("")
  lines.push(
    "Storefront `pickPrimaryImage()` correctly skips the cert thumbnail (after v0.19.2) and picks a real photo from `images[]`. Cosmetic fix: re-point `product.thumbnail` to the first real photo so admin/PDP doesn't show the cert."
  )
  lines.push("")
  lines.push("| handle | thumb (cert) | first non-cert available |")
  lines.push("|---|---|---|")
  for (const r of rows) {
    if (!r.thumbnail_is_cert_strict || r.is_backfill_target) continue
    const firstNonCert =
      r.image_filenames.find((f) => !CERT_RE_STRICT.test(f)) || "—"
    lines.push(
      `| \`${r.handle}\` | ${filenameFromUrl(r.thumbnail || "").replace(/\|/g, "\\|")} | ${firstNonCert.replace(/\|/g, "\\|")} |`
    )
  }
  lines.push("")

  lines.push("## Full audit (all Eurotramp products, sorted by handle)")
  lines.push("")
  lines.push(
    "| handle | brand_slug | images | cert (strict) | non-cert | thumb cert (strict)? | filenames |"
  )
  lines.push("|---|---|---|---|---|---|---|")
  for (const r of rows) {
    const fn = r.image_filenames.slice(0, 6).join("<br>") || "—"
    lines.push(
      `| \`${r.handle}\` | ${r.brand_slug} | ${r.image_count} | ${r.cert_image_count_strict} | ${r.non_cert_image_count_strict} | ${r.thumbnail_is_cert_strict ? "❌" : "✅"} | ${fn.replace(/\|/g, "\\|")} |`
    )
  }
  lines.push("")

  fs.writeFileSync(outFile, lines.join("\n"))

  fs.writeFileSync(
    outFile.replace(/\.md$/, ".json"),
    JSON.stringify(
      { generated_at: today, total_medusa_products: total, rows },
      null,
      2
    )
  )

  console.log("\n=== DONE ===")
  console.log(`Total Medusa products scanned: ${total}`)
  console.log(`Total Eurotramp products: ${rows.length}`)
  console.log(`Thumbnail = cert (strict): ${thumbCertStrict.length}`)
  console.log(`Backfill targets (zero real photos): ${targets.length}`)
  console.log(`  cert-only: ${certOnly.length}`)
  console.log(`  no-image:  ${noImages.length}`)
  console.log(`Storefront-visible failures: ${storefrontBroken.length}`)
  console.log(`Output: ${outFile}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
