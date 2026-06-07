/**
 * In-place migration from "brand = sales channel" to "brand = first-class
 * entity via the Brand module" (v2.49.0 → v2.52.0).
 *
 * What this script does
 * ----------------------
 * 1. Ensures a Brand record exists for each of the 11 live brands (Wisdom /
 *    Leka Project, Vinci Play, Berliner, Designpark, Vortex Aquatics, 4soft,
 *    Archimedes Water Play, Eurotramp, Rampline, WePlay, Gum-tech).
 * 2. Ensures a single shared "Leka Catalogs" sales channel + matching
 *    "Leka Catalogs Storefront" publishable API key exist. Adds the SC to
 *    the key so the storefront's single key resolves to the shared SC.
 * 3. Iterates every live Product:
 *    a. Infers the product's brand from its current sales-channel
 *       association (fallback: handle prefix).
 *    b. If no brand-product link exists, creates one.
 *    c. If the shared SC isn't yet on the product, adds it ALONGSIDE the
 *       existing per-brand SC. Per-brand SCs are NEVER removed by this
 *       script — that's a follow-up cleanup once the storefront is fully
 *       cut over.
 *
 * Safety
 * ------
 * - Fully idempotent. Re-running is a no-op (every step checks-then-creates).
 * - No deletions, no overwrites. Per-brand SCs + their publishable keys
 *   keep working through the transition.
 * - Dry-run via MIGRATION_DRY_RUN=1 — reads only, prints planned writes.
 * - MIGRATION_MAX=N caps how many products to touch (useful for a
 *   first-N smoke test against prod before a full run).
 *
 * Usage
 * -----
 *   # Dry run (no writes):
 *   MIGRATION_DRY_RUN=1 npx medusa exec ./src/scripts/migrate-to-brand-module.ts
 *
 *   # First-50 smoke test:
 *   MIGRATION_MAX=50 npx medusa exec ./src/scripts/migrate-to-brand-module.ts
 *
 *   # Full run:
 *   npx medusa exec ./src/scripts/migrate-to-brand-module.ts
 *
 * Recovery
 * --------
 * If anything looks wrong post-run: every link this script creates is
 * recorded in Medusa's link tables (brand_product, product_sales_channel)
 * and can be deleted via the admin API or a follow-up cleanup script.
 * No product, SC, brand record, or publishable key is mutated in a
 * destructive way.
 */
import {
  ExecArgs,
  IProductModuleService,
  ISalesChannelModuleService,
} from "@medusajs/framework/types"
import { ContainerRegistrationKeys, Modules } from "@medusajs/framework/utils"
import { BRAND_MODULE } from "../modules/brand"

const DRY_RUN = process.env.MIGRATION_DRY_RUN === "1"
const MAX_PRODUCTS = process.env.MIGRATION_MAX
  ? parseInt(process.env.MIGRATION_MAX, 10)
  : Infinity

const SHARED_SC_NAME = "Leka Catalogs"
const PUBLISHABLE_KEY_TITLE = "Leka Catalogs Storefront"

/**
 * Canonical Brand records. Handles are stable identifiers used by the
 * storefront's `?filters[brand][handle]=…` queries; names are human-facing.
 * Re-running this script with a new brand added here is safe — existing
 * brands are skipped, new ones get created.
 */
const BRAND_SPECS: Array<{
  handle: string
  name: string
  description: string
}> = [
  {
    handle: "wisdom",
    name: "Leka Project",
    description:
      "Leka Project (formerly Wisdom Playground) — playground, furniture, outdoor",
  },
  {
    handle: "vinci",
    name: "Vinci Play",
    description: "Vinci Play — playground equipment from Poland",
  },
  {
    handle: "berliner",
    name: "Berliner Seilfabrik",
    description: "Berliner Seilfabrik — climbing nets + rope structures",
  },
  {
    handle: "designpark",
    name: "Designpark",
    description: "Designpark playground equipment",
  },
  {
    handle: "vortex",
    name: "Vortex Aquatics",
    description: "Vortex Aquatics — splash-pad and water-play features",
  },
  {
    handle: "4soft",
    name: "4soft",
    description: "4soft EPDM safety surfacing + 2D graphics",
  },
  {
    handle: "archimedes-water-play",
    name: "Archimedes Water Play",
    description: "Archimedes Water Play — splash features",
  },
  {
    handle: "eurotramp",
    name: "Eurotramp",
    description: "Eurotramp trampolines",
  },
  {
    handle: "rampline",
    name: "Rampline",
    description: "Rampline outdoor active equipment",
  },
  {
    handle: "weplay",
    name: "WePlay",
    description: "WePlay inclusive play equipment",
  },
  {
    handle: "gumtech",
    name: "Gum-tech",
    description: "Gum-tech — EPDM rubber tiles + safety surfacing",
  },
  {
    handle: "lappset",
    name: "Lappset",
    description:
      "Lappset Group Oy — Finnish playground, outdoor sport, fitness, and "
      + "senior activity equipment. Catalogue heroes are normalized to clean "
      + "white at the vendors source (hero_white).",
  },
]

/**
 * Maps live Sales Channel names (as they exist in prod today) to brand
 * handles. Multiple SC name spellings can map to the same brand (the
 * sync script comments in scripts/sync_brand_prices_to_medusa.py show
 * Wisdom was renamed "Leka Project"; some brands have an "Aquatics" /
 * "Seilfabrik" suffix). Add aliases here freely.
 */
const SC_NAME_TO_BRAND: Record<string, string> = {
  "Leka Project": "wisdom",
  "Wisdom": "wisdom",
  "Wisdom Playground": "wisdom",
  "Vinci Play": "vinci",
  "Vinci": "vinci",
  "Berliner": "berliner",
  "Berliner Seilfabrik": "berliner",
  "Designpark": "designpark",
  "Design Park": "designpark",
  "Vortex Aquatics": "vortex",
  "Vortex": "vortex",
  "4soft": "4soft",
  "4soft EPDM": "4soft",
  "Archimedes Water Play": "archimedes-water-play",
  "Archimedes": "archimedes-water-play",
  "Eurotramp": "eurotramp",
  "Rampline": "rampline",
  "Weplay": "weplay",
  "WePlay": "weplay",
  "Gum-tech": "gumtech",
  "Gumtech": "gumtech",
  "Lappset": "lappset",
  // Legacy typo'd spellings — keep mapping to the corrected handle so an
  // in-flight prod SC named "Gum-tec" still resolves during/after the rename.
  "Gum-tec": "gumtech",
  "Gumtec": "gumtech",
}

export default async function migrateToBrandModule({ container }: ExecArgs) {
  console.log("=== In-place Brand-module migration ===")
  if (DRY_RUN) console.log("** DRY RUN ** — no writes")
  if (Number.isFinite(MAX_PRODUCTS)) console.log(`** MAX_PRODUCTS = ${MAX_PRODUCTS} **`)
  console.log()

  const productService: IProductModuleService = container.resolve(Modules.PRODUCT)
  const scService: ISalesChannelModuleService = container.resolve(Modules.SALES_CHANNEL)
  const brandService: any = container.resolve(BRAND_MODULE)
  const apiKeyService: any = container.resolve(Modules.API_KEY)
  const link: any = container.resolve(ContainerRegistrationKeys.LINK)
  const query: any = container.resolve(ContainerRegistrationKeys.QUERY)

  // ── Step 1: Ensure Brand records (idempotent) ──
  console.log("Step 1: Ensuring Brand records...")
  const brandMap: Record<string, string> = {}
  for (const spec of BRAND_SPECS) {
    const existing = await brandService.listBrands({ handle: spec.handle })
    if (existing.length > 0) {
      brandMap[spec.handle] = existing[0].id
      console.log(`  [exists]  ${spec.handle.padEnd(22)} → ${existing[0].id}`)
    } else if (!DRY_RUN) {
      const created = await brandService.createBrands({
        handle: spec.handle,
        name: spec.name,
        description: spec.description,
      })
      brandMap[spec.handle] = created.id
      console.log(`  [created] ${spec.handle.padEnd(22)} → ${created.id}`)
    } else {
      // Populate a placeholder so Steps 4 + 5 can still simulate the
      // brand → product linking they'd do in a real run. Without this,
      // every SC reports as `[unmapped]` and every product as `no-brand`
      // — misleading output that doesn't reflect what a real run would do.
      brandMap[spec.handle] = `brand_dryrun_${spec.handle}`
      console.log(`  [would]   ${spec.handle}`)
    }
  }

  // ── Step 2: Ensure shared "Leka Catalogs" SC ──
  console.log(`\nStep 2: Ensuring sales channel "${SHARED_SC_NAME}"...`)
  let sharedSc: any
  const matchingScs = await scService.listSalesChannels({ name: SHARED_SC_NAME })
  if (matchingScs.length > 0) {
    sharedSc = matchingScs[0]
    console.log(`  [exists]  ${sharedSc.id}`)
  } else if (!DRY_RUN) {
    sharedSc = await scService.createSalesChannels({
      name: SHARED_SC_NAME,
      description:
        "Shared storefront SC carrying all brands. Cart can mix products " +
        "across brands. Per-brand SCs remain for analytics + B2B use.",
      is_disabled: false,
    })
    console.log(`  [created] ${sharedSc.id}`)
  } else {
    console.log(`  [would create]`)
  }

  // ── Step 3: Ensure "Leka Catalogs Storefront" publishable key ──
  console.log(`\nStep 3: Ensuring publishable key "${PUBLISHABLE_KEY_TITLE}"...`)
  let pubKey: any
  const existingKeys = await apiKeyService.listApiKeys({
    type: "publishable",
    title: PUBLISHABLE_KEY_TITLE,
  })
  if (existingKeys.length > 0) {
    pubKey = existingKeys[0]
    console.log(`  [exists]  ${pubKey.id}`)
    if (pubKey.token) console.log(`            token=${pubKey.token}`)
  } else if (!DRY_RUN) {
    pubKey = await apiKeyService.createApiKeys({
      title: PUBLISHABLE_KEY_TITLE,
      type: "publishable",
      created_by: "migrate-to-brand-module",
    })
    console.log(`  [created] ${pubKey.id}`)
    console.log(`            token=${pubKey.token}`)
  } else {
    console.log(`  [would create]`)
  }

  // Link the key to the shared SC if not already linked.
  if (pubKey && sharedSc && !DRY_RUN) {
    try {
      await link.create({
        [Modules.API_KEY]: { publishable_key_id: pubKey.id },
        [Modules.SALES_CHANNEL]: { sales_channel_id: sharedSc.id },
      })
      console.log(`  [linked]  publishable key ↔ ${SHARED_SC_NAME}`)
    } catch (err: any) {
      // Link already exists — that's fine, idempotent.
      if (/already exists|duplicate/i.test(err?.message || "")) {
        console.log(`  [exists]  publishable key ↔ ${SHARED_SC_NAME}`)
      } else {
        console.log(`  [warn]    publishable-key SC link failed: ${err?.message}`)
      }
    }
  }

  // ── Step 4: Build the SC-id → brand-handle map ──
  console.log(`\nStep 4: Mapping existing sales channels to brand handles...`)
  const allScs = await scService.listSalesChannels({}, { take: 100 })
  const scIdToBrandHandle: Record<string, string> = {}
  for (const sc of allScs) {
    const handle = SC_NAME_TO_BRAND[sc.name]
    if (handle && brandMap[handle]) {
      scIdToBrandHandle[sc.id] = handle
      console.log(`  ${sc.name.padEnd(28)} (${sc.id}) → ${handle}`)
    } else if (sharedSc && sc.id === sharedSc.id) {
      // Shared SC — skip.
    } else {
      console.log(`  [unmapped]  ${sc.name.padEnd(28)} (${sc.id})`)
    }
  }

  // ── Step 5: Iterate products, link brand + add shared SC ──
  console.log(`\nStep 5: Linking products to brands + shared SC...`)
  const stats = {
    total: 0,
    linked_brand: 0,
    already_brand: 0,
    added_sc: 0,
    already_sc: 0,
    no_brand: 0,
  }
  const noBrandSamples: Array<string> = []

  let offset = 0
  const pageSize = 200
  outer: while (true) {
    const result = await query.graph({
      entity: "product",
      fields: [
        "id",
        "handle",
        "sales_channels.id",
        "sales_channels.name",
        "brand.id",
      ],
      pagination: { skip: offset, take: pageSize },
    })
    const products: Array<any> = result.data || []
    if (products.length === 0) break

    for (const p of products) {
      if (stats.total >= MAX_PRODUCTS) break outer
      stats.total++

      // (a) Infer brand handle
      let brandHandle: string | undefined
      for (const sc of p.sales_channels || []) {
        if (scIdToBrandHandle[sc.id]) {
          brandHandle = scIdToBrandHandle[sc.id]
          break
        }
      }
      if (!brandHandle) {
        // Fallback: handle prefix (wisdom-…, vinci-…, vortex-…, etc.)
        // Special case: Wisdom was rebranded to "Leka Project" — handles
        // are now `leka-project-XXX`. Map that to the `wisdom` brand.
        const lower = (p.handle || "").toLowerCase()
        if (lower.startsWith("leka-project-")) {
          brandHandle = "wisdom"
        } else {
          const prefix = lower.split("-")[0]
          if (brandMap[prefix]) brandHandle = prefix
        }
      }

      if (!brandHandle) {
        stats.no_brand++
        if (noBrandSamples.length < 10) {
          noBrandSamples.push(`${p.handle || "(no-handle)"} (${p.id})`)
        }
        continue
      }
      const brandId = brandMap[brandHandle]

      // (b) Brand link
      if (p.brand?.id) {
        stats.already_brand++
      } else if (!DRY_RUN) {
        try {
          await link.create({
            [BRAND_MODULE]: { brand_id: brandId },
            [Modules.PRODUCT]: { product_id: p.id },
          })
          stats.linked_brand++
        } catch (err: any) {
          if (/already exists|duplicate/i.test(err?.message || "")) {
            stats.already_brand++
          } else {
            console.log(`  [warn] brand-link failed for ${p.handle}: ${err?.message}`)
          }
        }
      } else {
        stats.linked_brand++
      }

      // (c) Add shared SC if not already present (per-brand SCs left alone)
      if (sharedSc) {
        const hasSharedSc = (p.sales_channels || []).some(
          (sc: any) => sc.id === sharedSc.id
        )
        if (hasSharedSc) {
          stats.already_sc++
        } else if (!DRY_RUN) {
          try {
            await link.create({
              [Modules.PRODUCT]: { product_id: p.id },
              [Modules.SALES_CHANNEL]: { sales_channel_id: sharedSc.id },
            })
            stats.added_sc++
          } catch (err: any) {
            if (/already exists|duplicate/i.test(err?.message || "")) {
              stats.already_sc++
            } else {
              console.log(`  [warn] sc-link failed for ${p.handle}: ${err?.message}`)
            }
          }
        } else {
          stats.added_sc++
        }
      }
    }

    offset += pageSize
    if (offset % 1000 === 0) {
      console.log(
        `  ${offset.toString().padStart(5)} processed | ` +
          `brand-linked: ${stats.linked_brand} | sc-added: ${stats.added_sc} | ` +
          `no-brand: ${stats.no_brand}`
      )
    }
  }

  // ── Summary ──
  console.log("\n=== Migration Complete ===")
  console.log(`  Products processed: ${stats.total}`)
  console.log(
    `  Brand links — created: ${stats.linked_brand}, already: ${stats.already_brand}, no-brand: ${stats.no_brand}`
  )
  console.log(
    `  Shared SC   — added:   ${stats.added_sc}, already: ${stats.already_sc}`
  )
  if (stats.no_brand > 0) {
    console.log(`\n  Products with no inferable brand (first ${noBrandSamples.length}):`)
    for (const s of noBrandSamples) console.log(`    - ${s}`)
    console.log(`  → Add an SC-name alias to SC_NAME_TO_BRAND or a handle-prefix rule, then re-run.`)
  }
  if (pubKey?.token) {
    console.log(`\n  Storefront key for leka-website/catalogs/.env.local:`)
    console.log(`    NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY=${pubKey.token}`)
  }
}
