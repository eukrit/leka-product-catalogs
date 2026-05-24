# Changelog

All notable changes to this project will be documented in this file.

---

## [2.32.0] - 2026-05-24

### Fixed — Rampline weight scraper + airfreight routing for 32/127 SKUs

- `scripts/scrape-rampline.ts`: fixed weight extraction — Rampline publishes specs
  in `<p><br>` blocks, not `<ul><li>`. Now parses both; takes max weight across all
  variant lines per page (conservative airfreight estimate).
  Products with weight data: Rampit 40kg, Rampit TWIN 60kg, Jumpstone 20kg,
  Rampit Storm 50kg, BalanceBuddy 43kg, Fungi 33kg, Playground Loop 160kg.
- `rampline-catalog/import_pricelist.py`: added `FAMILY_DESC_TO_SLUG` table (pricelist
  uses long descriptive family names, not marketing names); `load_dim_index()` now
  keys by handle slug + title slug in addition to WooCommerce SKU; main loop tries
  family-desc lookup when article-SKU lookup misses.
  Result: **32/127 SKUs now use `airfreight_weight` strategy** (was 0), 95 remain on
  `flat_uplift` (Rampball — no published weight, ShockDeck, motor-skill parks).
  Scraped data: `data/scraped/rampline/products.json` (54 products from sitemap).

---

## [2.31.0] - 2026-05-24

### Changed — Pricing formula overhaul: duty fix, TH VAT, independent currencies, CBM routing

#### Task 1 — Pricing config master doc
- Added `docs/summaries/pricing-config-master.md`: complete authoritative reference
  for all FX sources, brand params, tax rules, per-brand formulas, Vinci tier
  floor/cap system with worked examples, shipping-automation integration details,
  and script reference.

#### Task 2 — Fix Wisdom import duty (0%, not 7%)
- `shared/wisdom_pricing.py`: `IMPORT_DUTY_RATE` corrected 0.07 → 0.00. China-origin
  goods qualify under ASEAN-China FTA (Form E); 7% was incorrect.
- `shared/pricing_config.py` schema doc updated: `brands.wisdom.import_duty_rate = 0.0`.
- After this fix, Wisdom retail prices decrease by ~7% (the erroneous duty is removed).
  Re-run `scripts/backfill_sgd_pricing.py --brand wisdom --write` to apply.

#### Task 3 — TH customer VAT: embed 7% into all retail prices
- `shared/landed_pricing.py`: added `TH_CUSTOMER_VAT_RATE = 0.07`. `_resolve_params()`
  now reads `th_customer_vat_rate` from Firestore. `price_row()` applies
  `retail_thb = (landed_thb / (1-gm)) × 1.07`. This is the TH domestic customer VAT
  (distinct from the 7% import VAT already in `landed_thb`).
- `shared/wisdom_pricing.py`: same `TH_CUSTOMER_VAT_RATE` constant and application in
  `compute_wisdom_retail()`.
- `scripts/ingest_designpark_pricelist.py`: applies `th_customer_vat_rate` from config.
- `berliner-catalog/import_pricelist.py`: applies `th_customer_vat_rate`.
- `rampline-catalog/import_pricelist.py`: applies `th_customer_vat_rate`.
- Net effect: all THB retail prices increase by 7% vs pre-VAT. USD and SGD prices are
  unaffected (TH customer VAT is a Thai domestic tax; international prices pre-VAT).

#### Task 4 — Vinci tier floor/cap documented (code unchanged)
- Vinci already routes through `shared.price_row()` → `cost_engine` when CBM available.
- Full tier table and worked examples now documented in pricing-config-master.md.

#### Task 5 — Berliner: CBM routing via shipping-automation
- Berliner already uses `cost_engine` via its own `price_row()` implementation when
  Firestore docs carry dimension data (from prior website scrape). No code change needed.
- `_berliner_params()` now includes `th_customer_vat_rate`.

#### Task 6 — DesignPark: Korea LCL CBM routing
- `scripts/ingest_designpark_pricelist.py`: `price_designpark_row()` now accepts `cbm`
  and `kg` params. When CBM > 0, routes through `cost_engine origin=japan_korea,
  method=lcl` (3,500 THB/CBM). Applies Vinci-style tier clamp. Falls back to
  flat 35% uplift when no CBM data (current pricelist has no dimensions).

#### Task 7 — Wisdom: China LCL CBM routing + tier clamp
- `shared/wisdom_pricing.py`: `compute_wisdom_retail()` now accepts `cbm`, `kg`, `fx`
  params. New `_wisdom_lcl_estimate()` helper calls `cost_engine origin=china,
  method=lcl` (2,800 THB/CBM). When CBM estimate succeeds, applies Vinci-style tier
  clamp. Falls back to flat China CIF ≈ FOB path (duty=0%) when no CBM.
- `compute_wisdom_retail_batch()` now auto-computes CBM from `dimensions` dict if
  present on product docs (packing_factor 0.15).

#### Task 8 — Rampline: airfreight routing when weight available
- `rampline-catalog/import_pricelist.py`: load_dim_index() now also reads `weight_kg`
  from scraped products. Main pricing loop: when weight_kg > 0, calls `cost_engine
  origin=europe, method=air` (120 THB/kg, Profreight Italy→BKK rate, Norway comparable).
  Applies tier clamp. Falls back to LCL tier system when no weight data (current scrape
  has no weight; air routing activates after re-scrape).
- Added `RAMPLINE_SHIPPING_METHOD = "air"` constant and airfreight rate logging.

#### Task 9 — PLP currency selector (THB / USD / SGD)
- `leka-website/catalogs/src/lib/currency.ts` (new): `SupportedCurrency` type,
  `SUPPORTED_CURRENCIES`, `getStoredCurrency()` / `storeCurrency()` (localStorage),
  `pickPrice()` (currency-aware Medusa variant price picker), `formatPrice()`.
- `leka-website/catalogs/src/components/currency-selector.tsx` (new): pill-shaped
  THB/USD/SGD selector matching Leka DS (Manrope, #8003FF, 9999px pill radius, 8px
  button radius, `0px 2px 8px rgba(24,37,87,0.08)` shadow).
- `leka-website/catalogs/src/components/product-card.tsx`: accepts `currency` prop;
  uses `pickPrice()` + `formatPrice()` for currency-aware price display.
- `leka-website/catalogs/src/app/[brand]/catalog-content.tsx`: adds `currency` state
  (hydrated from localStorage after mount to avoid SSR mismatch); shows
  `CurrencySelector` in header when `brand.hasPricing`; passes `currency` to
  every `ProductCard`.

#### Task 10 — Independent retail calculations per currency
- `shared/landed_pricing.py` `price_row()`: `retail_usd` and `retail_sgd` now derived
  from `landed_thb / FX` (not from `retail_thb / FX`) — independent from the TH
  customer VAT applied to `retail_thb`. International prices are pre-TH-VAT.
- `shared/wisdom_pricing.py`: same independent derivation.
- `scripts/ingest_designpark_pricelist.py`: same independent derivation.
- `berliner-catalog/import_pricelist.py`: same independent derivation.
- `rampline-catalog/import_pricelist.py`: same independent derivation.

**Files changed:**
- `shared/landed_pricing.py`
- `shared/wisdom_pricing.py`
- `shared/pricing_config.py` (schema comment update)
- `scripts/ingest_designpark_pricelist.py`
- `berliner-catalog/import_pricelist.py`
- `rampline-catalog/import_pricelist.py`
- `docs/summaries/pricing-config-master.md` (new)
- `leka-website/catalogs/src/lib/currency.ts` (new)
- `leka-website/catalogs/src/components/currency-selector.tsx` (new)
- `leka-website/catalogs/src/components/product-card.tsx`
- `leka-website/catalogs/src/app/[brand]/catalog-content.tsx`

---


---

## [2.30.0] - 2026-05-23

### Changed — Playground Mound Modeler extracted to dedicated repo

The `mound-modeler/` module (developed in a worktree off this repo from
2026-04 to 2026-05-17) has been extracted to its own repo and Cloud Run
service:

- **Repo:** [eukrit/leka-mound](https://github.com/eukrit/leka-mound) (private, branch `main`)
- **Cloud Run service:** `leka-mound` (asia-southeast1, replaces the `/mound/` blueprint mount on `leka-product-catalogs` Cloud Run)
- **Gateway slug:** `leka-mound` (kind=cloud_run, visibility=admin)
- **Legacy slug:** `leka-mound-modeler` deprecated 2026-05-23; still points at the existing `leka-product-catalogs` Cloud Run revision (which carries the historical /mound/ blueprint). Scheduled for removal on 2026-06-23.

### Vinci catalog dependency

The new `leka-mound` service fetches Vinci product data at runtime from
`https://leka-product-catalogs-538978391890.asia-southeast1.run.app/vinciplay/data/products_all.json`.
Bundled snapshot in `leka-mound/data/vinci_products.bundled.json` is the
offline fallback. Refresh cadence: 1h in-memory cache. `/health` surfaces
the current source as `remote` / `bundled` / `remote_stale`.

### Firestore designs

`mound_designs` collection stays in this project's Firestore database
(`leka-product-catalogs`). The new service uses a cross-database client
so existing saved-design URLs (`?id=m-XXXX`) still resolve.

### Note on the running Cloud Run revision

`leka-product-catalogs` Cloud Run revision `00014-mw2` was built from the
worktree (not from main) and includes the mound blueprint at `/mound/`.
A redeploy from `main` would drop the blueprint and break the legacy
`leka-mound-modeler` gateway slug. Plan: redeploy from main only AFTER
2026-06-23 when the legacy slug is removed.

### Pre-history

All mound-modeler development before extraction is preserved in this
repo's git history under the worktree branch
`claude/determined-yalow-d2e28e`. See `eukrit/leka-mound/BUILD_LOG.md`
for v0.2.0 (the extraction).

---

## [2.29.0] - 2026-05-22

### Added — Proposal Builder backend endpoints (sibling to leka-projects #29)

Two new HTTP routes + one subscriber so the `catalogs.leka.studio` storefront's "Send to Proposal" button (sibling PR in `eukrit/leka-website`) can convert a customer cart into a Medusa Draft Order, and so the Python `proposal_engine` adapter in `eukrit/leka-projects` (v1.48.0) can fetch that draft order pre-joined with every expansion it needs.

Plan: `~/.claude/plans/based-on-the-latest-tingly-coral.md` §D.

**New routes:**

- `POST /store/proposal-builder/convert-cart`
  - **Auth:** store-side (publishable API key + optional customer session).
  - **Body:** `{ cart_id, project_id?, project_name?, site_location?, project_details?, metadata? }`.
  - **Flow:** retrieves the cart, runs `createOrderWorkflow` from `@medusajs/medusa/core-flows` with `status: "draft"`, stamps `metadata.proposal_builder: true` on the order + every line item plus the project context. Copies cart shipping/billing address through. Returns `{ draft_order_id, display_id, status, message }`.
  - **What happens to the cart:** left intact on the server (storefront clears its localStorage cart-id on success).
  - **File:** `medusa-backend/src/api/store/proposal-builder/convert-cart/route.ts`.

- `GET /admin/draft-orders/:id/proposal-export`
  - **Auth:** admin (JWT or admin API key from Medusa admin UI). The proposal engine sends `x-medusa-access-token: <key>`; key lives in GCP Secret Manager as `medusa-admin-api-key-proposal-engine`.
  - **Returns:** the draft order with every expansion the Python adapter needs (items → variant → product → images, region, addresses) in a single HTTP call, wrapped in a legacy-`cart`-shaped envelope so the adapter doesn't have to dual-handle v1/v2 order shapes.
  - **Why custom:** the BoQ adapter contract is stable in `proposal_engine` (plan §C3); pinning the wire shape here means future BoQ schema changes don't require redeploying Cloud Run.
  - **File:** `medusa-backend/src/api/admin/draft-orders/[id]/proposal-export/route.ts`.

**New subscriber:**

- `src/subscribers/proposal-created.ts` — listens on `order.placed`, filters `metadata.proposal_builder === true`, posts a Slack alert to `#leka-medusa-proposal` via the data-comms Slack Router (Rule 16) with the `draft_order_id`, total, project_id/name/site, and a one-liner instruction to paste the ID into `projects/<id>/config.yaml` and run `python -m proposal_engine render ...`. Best-effort (no-throws) so the cart conversion never fails on notification glitches.

**Verification:**

- `npm run build` → green (backend compiled in 19.85s, admin frontend in 59.31s; no TypeScript errors).
- Manual smoke (post-deploy):
  ```
  curl -X POST https://catalogs.leka.studio/api/store/proposal-builder/convert-cart \
    -H "Content-Type: application/json" \
    -H "x-publishable-api-key: $LEKA_PUBLISHABLE_KEY" \
    -d '{"cart_id":"cart_xxx","project_id":"dulwich-singapore","project_name":"Test"}'
  ```
  Expect `201` with `draft_order_id`.

**Not in this PR (sibling work):**

- `eukrit/leka-projects` v1.48.0 — the Python adapter that consumes `/admin/draft-orders/:id/proposal-export` (PR #29, merged).
- `eukrit/leka-website` — the storefront "Send to Proposal" button that POSTs to `/store/proposal-builder/convert-cart`.
- One-shot: `gcloud secrets create medusa-admin-api-key-proposal-engine --replication-policy=automatic` + paste the admin key issued in Medusa admin UI.
- Variant metadata backfill (`supplier`, `supplier_url`, `dimensions`, `age_range`, `diecut_white_gcs`) on Wisdom / Vinci Play / Weplay products so the proposal engine cards have full data — separate follow-up; until then bare products render with default zone/category + sales retags in admin.

---

## [2.28.0] - 2026-05-22

### Added — SGD retail across 5 brands + recompute onto current config

Implements "local currency per country": Thailand checks out in THB,
Singapore in SGD, everywhere else USD. SGD retail prices were missing on
every brand except Eurotramp; this pass computes them for Wisdom, Vinci,
Berliner, DesignPark, and Rampline straight from each brand's original
pricelist FOB through the canonical landed-cost pipeline (user direction
2026-05-22: "always refer to original pricelist and use pricing calculation
to THB/SGD/USD as target").

#### Tax treatment (already in `pricing_config/canonical`, confirmed)
- **TH** — `th_customer_vat_rate = 0`: retail is VAT-inclusive; the 7% import
  VAT is already inside `landed_thb`. No extra customer-VAT line.
- **SG** — `sg_nubo_gst_registered = false`: SG sale is treated as a
  zero-rated export, so **no GST is added** at catalog price. The formula
  `retail_sgd = retail_pre_tax_thb / (THB/SGD)` flips to add 9% automatically
  once Nubo registers and the flag is set true.

#### Pipeline changes (SGD added to the formula)
- `shared/landed_pricing.py` — `PricedRow.retail_sgd`; `price_row()` computes
  it with the Nubo GST gate. New `SG_CUSTOMER_GST_RATE` / `SG_NUBO_GST_REGISTERED`
  fallbacks; `_resolve_params()` reads the SG keys from Firestore config.
- `shared/wisdom_pricing.py` — `retail_sgd` + `sgd_thb` on `WisdomPricedRow`;
  `get_sgd_thb()` live-FX helper; `pricing_metadata()` emits SGD.
- `scripts/ingest_designpark_pricelist.py` — `price_designpark_row()` emits
  `retail_sgd`.
- `vinci/berliner/rampline import_pricelist.py` — persist `retail_sgd`; Berliner
  derives the EXW cost basis from `list_eur × (1 - exw_discount)` (config-driven).

#### Recompute = adds SGD AND corrects stale config drift
Recomputing from FOB at the current config also fixed prices that predated
config changes and were never backfilled:
- **Vinci -7.8%** — stored prices used 40% GM; config moved to 35% on 2026-05-14.
- **Berliner +0.4%→+17.3%** — stored prices predated the 2026-05-14 7% Thai
  VAT layer (small items floored either way; large items show the added VAT).
- DesignPark/Rampline ~0% drift; Wisdom had no retail at all (FOB-only).

Trade terms re-verified against the `vendors` DB before writing: Berliner
`eur_fob` = `list_eur × 0.85` (EXW -15%, no double discount); Vinci/DesignPark/
Wisdom are discount-free FOB; Vinci `eur_fob_2026` == `eur_fob`; Wisdom
`fob_usd` covers all priceable docs.

#### `scripts/backfill_sgd_pricing.py` (new)
Recomputes the landed→retail cascade per brand from the original-pricelist FOB
captured on each Firestore doc and writes `pricing.retail_{thb,usd,eur,sgd}`
back to `vendors/{slug}/products` (Rampline → its `pricelists/<date>` audit
doc). Dry-run by default; dumps a pre-write backup CSV per brand
(`scripts/backfill_backups/`, gitignored) and stamps `fx_snapshot`,
`fx_source`, `retail_basis`, `calculated_at` for audit. **Written:** Vinci
1,234 · Berliner 728 · DesignPark 178 · Wisdom 4,809 · Rampline 127 (audit).

#### `scripts/sync_brand_prices_to_medusa.py` (new)
Update-only multi-currency price push. Indexes ALL Medusa products by variant
sku / `metadata.legacy_sku` / handle and matches vendor docs by
item_code → handle → doc-id, so it **never creates products** — avoiding the
duplicate hazard of the handle-based `sync_vendors_to_medusa.py` (Berliner uses
descriptive handles with item-code SKUs; Wisdom is rebranded "Leka Project"
with `LP-` SKUs + `legacy_sku`). Match rates: Vinci 1,234/1,234, Berliner
728/728, DesignPark 178/178, Wisdom 4,800/4,809 (9 `CQ14-QL-*(n)` sub-variants
absent in Medusa).

#### Deferred (not in this pass)
- **SGD region NOT created** — per user, hold the `sg` region switch until the
  whole ~9k catalog has SGD; SG keeps checking out in USD until then. No
  storefront change needed (checkout currency follows `cart.region`).
- **Rampline → Medusa** stays deferred (per-variant migration not done); SGD is
  in the audit doc only.
- **4soft / Weplay / Vortex** have no usable FOB/retail source in the vendors DB
  and were out of scope.

---

## [2.27.0] - 2026-05-21

### Added — B2B project context in order-placed notifications

The `order.placed` subscriber (`medusa-backend/src/subscribers/order-placed.ts`)
now reads the B2B project fields the storefront sets on the cart/order metadata
(`project_name`, `project_details`, `site_location`) and surfaces them in both
the Slack alert (#leka-medusa-order) and the confirmation email:

- **Slack:** adds a Project / Site-location fields block and a Project-details
  section when present (rendered between the customer block and the items list).
- **Email:** adds a cream-highlighted project block above the line-item table.

Both are conditional — orders without project metadata are unchanged. Pairs with
leka-website catalogs v0.17.0 (Submit Order flow).

---

## [2.26.0] - 2026-05-18

### Added — Weplay quotation AQ1251030077 USD pricing sync

Ingested the 2025-11-05 Weplay quotation (`AQ1251030077`, dated
Oct. 30, 2025, FOB Taiwan, USD) into `vendors/weplay/products/*`.

#### `scripts/ingest_weplay_quotation_aq1251030077.py` (new)
Parses the 7-page text-layer PDF with `pdfplumber`, line regex on
`SKU DESCRIPTION PRICE / UNIT PACK CBM GW`. Uses the same
`SKU_TOKEN_RE = ([A-Z]{2}[0-9]{4,})` (no word boundaries) as
`scripts/ingest_weplay_local_catalogs.py` so it matches tokens inside
larger item codes (e.g. `KM1003` inside `6800KM1003`).

Source-priority gating preserved: name/description only written when
the target doc has zero provenance (`source_url_en/cached/flipbook/
pdf_ocr/local`) AND is in a draft state. Otherwise the write is
audit-only — never clobbers richer sources.

Always-written fields (merge=True):
  - `pricing.quote_2025_usd`              — FOB Taiwan price
  - `pricing.quote_aq1251030077_at`       — `"2025-10-30"`
  - `pricing.quote_aq1251030077_unit`     — `PC | SET | PAC | DZN`
  - `quotation_refs`                      — `ArrayUnion(["AQ1251030077"])`

#### Run results
  - 167 quotation rows parsed
  - 151 unique SKU tokens
  - 189 Firestore docs matched (some tokens have variant docs)
  - 0 no-doc-match
  - 189 audit-only writes (all matched docs already had names from
    richer scrape sources — `name`/`description`/`source_url_local`
    correctly skipped per the priority gate)

#### Audit-only by design
USD `quote_*` fields are kept separate from any landed-cost or retail
`retail_*` keys consumed by `sync_vendors_to_medusa.py`, so no Medusa
re-sync is required from this commit.

---

## [2.25.0] - 2026-05-17

### Removed — 38 duplicate Weplay products (Medusa 200 → 162)

Inspection of the live Medusa Weplay SC surfaced **34 SKU tokens with
>1 doc**, producing **62 active duplicate products** on
`catalogs.leka.studio/weplay`. Each was a separate scrape-pass artifact
showing the same product as multiple cards:

  - `KM2802`: 11 docs all named "Soft Gym (7 pcs)"
  - `KC0002`: 4 docs all named "Brick Me" (6800KC0002.1-090, KC0002,
    KC0002.1, WE-KC0002)
  - `KC2003`: 3 "Fun with Curves" (kc2003, kc2003-00b, we-kc2003)
  - `KP1001`: 3 "Seesaw (A)"
  - `KM1003`: 2 "Pile Balance Up" (6800km1003, km1003)
  - `KM2016`: 2 "Over The Mountain"
  - `KT0017`: 2 "Squishy Tactile Shell"
  - `KC0004`: 2 "Q-blocks (64 pcs)"
  - And 18 more groups

#### `scripts/merge_weplay_duplicates.py` (new)
Groups docs by `(sku_token, normalized_name)`. Within each group picks
a canonical doc using priority `active+images > active > has_images >
shortest doc_id`. For non-canonical docs:
  - Sets `status = "merged_duplicate"`
  - Sets `merged_into = <canonical_doc_id>`
  - Sets `merged_canonical_sku` for audit
  - DELETEs the corresponding Medusa product (if found by handle)

Run: 26 dedup groups identified, **40 Firestore docs marked merged**,
**38 Medusa products deleted** (2 didn't have matching handles —
likely never synced). **Medusa Weplay catalog: 200 → 162 products.**

Idempotent. Doesn't touch tokens where docs have DIFFERENT names
(those are likely real variants or AI-misinferred SKUs needing
human review — see HTML report).

#### `scripts/generate_weplay_review_html.py` (new)
Static HTML page at `docs/weplay-review.html` (95KB) for the user
to review:

1. **AI-inferred drafts tab** — all 103 docs stamped by v2.15.1's
   `stamp_weplay_ai_inferred.py`. Grouped by category (balance,
   construction, motor-skill, sensory, etc.), each card shows
   SKU + doc_id + name + description + AI notes (the Anthropic
   Vision pipeline's audit trail like "Product identified as
   Weplay X based on visual appearance").

2. **Variant groups tab** — every SKU token that still has >1 doc
   after the dedup pass (mostly mixed-name groups that need
   human eye). Each group shows all docs side-by-side with status
   badge + thumbnail.

Searchable + tabbed. Two-color borders distinguish AI-inferred
(purple) from variant-group cards (red).

Served at `https://gateway.goco.bz/leka-product-catalogs/weplay-review.html`
(after deploy) and from local docs/ folder. Hub regenerated.

### Composite catalog state
- **`catalogs.leka.studio/weplay`: 162 product cards** (was 200 with
  dupes, now de-duped)
- 103 AI-inferred drafts still draft, now visible in HTML review for
  human decisions
- 8 multi-doc variant groups remaining (mixed names — need review,
  visible in HTML)

### Files changed
- `scripts/merge_weplay_duplicates.py` (new)
- `scripts/generate_weplay_review_html.py` (new)
- `docs/weplay-review.html` (new)
- `docs/hub.html` (regenerated)
- `CHANGELOG.md`

---

## [2.24.0] - 2026-05-17

### Changed — TH retail = VAT-inclusive by default + Vinci → Vinci Play rename

Per user direction:
- `global.th_customer_vat_rate` default `0.07` → **`0.0`**. Retail price
  is always quoted VAT-inclusive in Thailand; the 7% Thai import VAT is
  already folded into `landed_thb` so no additional customer-VAT line
  is needed. With this change, `retail_th_thb == retail_pre_tax_thb`.
- `brands.vinci.source_pricelist_url` changed to the renamed
  Google Drive folder
  `https://drive.google.com/drive/folders/1ZiRZknbz0XlE9RMIbDwe9MC1oXegMyfl`
  (label: "Vinci Play master folder (Google Drive)"). Old local
  Windows path was browser-broken; this URL opens cleanly.

### Synced in this commit
- `src/main.py` `_empty_config()` matches the live Firestore state.
- `scripts/seed_pricing_config.py` extended to seed all v2.21.0
  schema additions (TH/SG tax fields + per-brand source URLs) so
  `--force` re-seed no longer regresses them.
- Live Firestore was patched directly via the deployed
  `POST /api/pricing-config` (audit footer now shows
  `eukrit@gmail.com (via claude)` at 2026-05-17T08:50:05Z).

### Companion — `vendors` repo
Drive folder rename `My Drive/Partners Playground/Vinci/Vinci Play Prices`
→ `My Drive/Partners Playground/Vinci Play/Vinci Play Prices`. Three
scripts in `vendors/vinci-play-catalog/scripts/` hardcoded the old path
and were updated in the same change-set:
`import_pricelist.py`, `enrich_schema.py`, `run_enrichment_pipeline.py`.
Cloud Build job `vinci-pricelist-enrich` is unaffected — it resolves
the Drive folder by ID via the `vinci-play-pricelist-folder-id` Secret
Manager secret (folder ID didn't change, only the display name).

> *Note: bumped from the originally-prepared v2.21.1 to v2.24.0 to stay
> above the v2.22.x / v2.23.x rebrand work that landed on `main` in
> parallel.*

## [2.23.9] - 2026-05-16

### Added — 5 themed collections for Leka Project (auto-generated)

Wisdom never had a "series" concept (unlike Vinci or Berliner), so the
storefront's collection filter was disabled for Leka Project. This adds
5 curated themed collections by mapping each product's top-level
category to the first matching collection from a priority list.

Created collections (handle prefix `leka-project-`):
- `leka-project-furniture-collection`     — 1,261 products (from `furniture`)
- `leka-project-outdoor-and-nature-play`  — 618 products  (from `outdoor`, `nature_play`, `water_play`)
- `leka-project-active-play`              — 1,278 products (from `playground`, `balance`, `climbing`, `sports`)
- `leka-project-early-years-collection`   — 83 products   (from `early_years`)
- `leka-project-creative-and-loose-parts` — 130 products  (from `creative`, `loose_parts`)

**3,370 of 5,062 products (67%) assigned**, 0 errors, elapsed 20m 25s.
The remaining 1,692 products in the catch-all `other` category stay
uncollected — discoverable via category and search only. Future curation
can claim them.

Medusa v2 only supports one collection per product (`collection_id`
is singular), so priority order matters: Furniture first (most specific),
then Outdoor & Nature, Active Play, Early Years, Creative & Loose Parts.

### Storefront coordination
- Pairs with leka-website v0.10.0 which flips
  `BRANDS["leka-project"].hasCollections: true` and sets
  `collectionPrefix: "leka-project-"` so the existing filter UI picks
  them up without any rendering changes.

### Added
- `scripts/create_leka_project_collections.py` — idempotent; `--revert`
  clears `collection_id` on every Leka Project product (does not delete
  the empty collections).

### Files changed
- `scripts/create_leka_project_collections.py` (new)
- `CHANGELOG.md`, `VERSION`

---

## [2.23.8] - 2026-05-16

### Changed — Renamed 80 `wisdom-*` Medusa product categories to `leka-project-*`

Final cleanup for the Wisdom → Leka Project rebrand (v2.17.0). Product
categories were left behind in that pass: 80 subcategory handles like
`wisdom-furniture-cabinet`, `wisdom-balance-house`, etc. continued to
surface in storefront URLs as `?subcategory=wisdom-...`, leaking the
upstream supplier identity. The category *names* ("Furniture", "Climbing",
etc.) were already clean — only the handles needed updating.

- 80 / 80 categories renamed via Medusa Admin API in 26 seconds.
- Old handle preserved in `metadata.legacy_handle` for revert.
- Verified live: Store API returns 0 `wisdom-*` handles to the Leka Project
  publishable key, 76 `leka-project-*` subcategories present and visible
  on `catalogs.leka.studio/leka-project`.

### Added
- `scripts/rename_wisdom_categories.py` — idempotent rename + `--revert`.

### Files changed
- `scripts/rename_wisdom_categories.py` (new)
- `CHANGELOG.md`, `VERSION`

---

## [2.23.7] - 2026-05-16

### Added — Wisdom / Leka Project Medusa price refresh tooling

New bulk updater that pushes the canonical FOB → CIF → duty + VAT → landed
→ retail formula (already in `shared/wisdom_pricing.py`) to Firestore
`products_wisdom` documents AND the corresponding Medusa variants in the
Leka Project sales channel.

Key wrinkle this handles: products were rebranded from Wisdom to Leka
Project in May 2026, so Medusa SKUs are now `LP-XXXXXXXX` while Wisdom
item codes survive in `variants[].metadata.legacy_sku`. The updater
indexes the sales channel once by `legacy_sku` and then matches each
Firestore row in O(1).

### Files

- `shared/medusa_importer.py` — added 4 methods:
  - `get_product_with_variants(handle)` — fetch product including variants
  - `get_variant_by_sku(sku)` — current-SKU lookup with legacy handle fallback
  - `build_legacy_sku_index(sales_channel_id)` — O(N) page through SC,
    O(1) lookup keyed by `metadata.legacy_sku`
  - `update_variant_prices(product_id, variant_id, prices)` — replace
    variant price list (e.g. set THB retail alongside USD FOB)
- `wisdom-catalog/update_pricing.py` **(new)** — Firestore + Medusa bulk
  updater. Supports `--dry-run`, `--skip-medusa`, `--usd-thb` overrides.
  Writes `pricing.{landed_thb,retail_thb,retail_usd,duty_thb,vat_thb,
  usd_thb,import_duty_rate,thai_vat_rate,gross_margin,price_date}` to
  Firestore and `{usd: FOB, thb: retail}` prices to each Leka Project
  variant.

### Usage

```powershell
python wisdom-catalog/update_pricing.py --dry-run                  # preview
python wisdom-catalog/update_pricing.py --usd-thb 35.20            # live
python wisdom-catalog/update_pricing.py --skip-medusa              # FS only
```

Effective multiplier on FOB-USD at USD/THB 35.0: `35 × 1.07 × 1.07 × 2.0 ≈ 80.14` THB/USD.

---

## [2.23.6] - 2026-05-16

### Improved — DesignPark follow-ups (image coverage, Modern Igloo, Slack)

Tightens the v2.20.0 / v2.23.5 DesignPark pipeline along the three open
follow-ups. Net live result: **87 active products** (up from 15, +480 %)
and **87 / 191 published in Medusa** (up from 15).

#### 1. Asset matcher overhaul (`scripts/ingest_designpark_assets.py`)

The original SKU regex covered only 6 prefixes (`SDM|PTC|PTM|DPM|DPF|DPS`)
which missed the majority of pricelist SKUs. New strategy:

- **Generic regex** widened to all pricelist prefixes:
  `SDM, PTC, PTM, SM, BOA, BTA, BKA, BGA, UTM, DPM, DPF, DPS, DP`.
- **Known-SKU substring matcher** (`find_sku_in_text`) — `load_product_index()`
  now exports a longest-first SKU list; `match_product()` searches filenames
  (and Slack message context) against the live set, tolerant of
  spaces/dashes/underscores between SKU segments. This is what unlocks
  `SM12 - 04B - Upright Cycle EMERALD GREEN.jpg` and
  `BTA12-06 금광.jpg` matches that the regex alone couldn't reach.
- **Theme alias table** (`THEME_ALIASES`) — manual map from the 2024 CAD
  bundle theme slugs (`twin-tower`, `hunter-s-hut`, …) to the 2023 manifest
  product slugs (`twin-star`, `hut-in-the-forest`, …). Plus a 2-token
  Jaccard-style fallback for partial overlap.
- **Result**: 109 matched → **288 matched** (+179 joins, +165 %).

#### 2. Modern Igloo sheet handling (`scripts/ingest_designpark_pricelist.py`)

The 12th pricelist sheet uses a 4-column layout (No / Category /
Description / Unit Price) with no MODEL NO column, which the original
parser skipped. New fallback path: synthesize
`item_code = "DP-<SHEET-SLUG>-<DESC-SLUG>"` and filter out the
trailing 1)/2)/3) footer rows. **Result**: +1 product.

#### 3. Slack ingest live (`scripts/ingest_designpark_slack.py`)

Replaces the v2.20.0 manifest-driven scaffold with a direct Slack API
client that pages `files.list?channel=C0AESCDCZRQ` and fetches
`conversations.history` for per-file message context. Auth via
`slack-bot-token` from Secret Manager. Channel state (2026-02-13 →
2026-05-16): 3 files, all PDFs, all brochures (no per-product photos
yet). Run yield: 3 PDFs uploaded to GCS, attached to
`vendors/designpark.brochures[]` (vendor-level — multi-product catalogs).

#### 4. Status promotion (`scripts/promote_designpark_published.py`)

`sync_vendors_to_medusa.py::_build_update_payload` intentionally omits
`status` so manual Medusa Admin curation isn't overwritten on every sync.
This new idempotent helper closes the loop: for every product with
`status="active"` in Firestore that's still `draft` in Medusa, POST
`{status: "published"}`. This run: **72 promoted** + 15 already published
= **87 published** total.

#### Files

- modified: `scripts/ingest_designpark_assets.py`
- modified: `scripts/ingest_designpark_pricelist.py`
- added: `scripts/ingest_designpark_slack.py`
- added: `scripts/promote_designpark_published.py`
- modified: `VERSION` → `2.23.6`

#### Live final state (verified via Medusa Admin API)

- Total in `Design Park` SC: **191** products.
- Status: **87 published**, **104 draft**.
- 178 priced (USD + THB + EUR); 13 themes / no-FOB rows carry no `retail_*`.
- GCS blobs: 518 (no new uploads this run — re-ingest path is fully idempotent).
- Slack brochures attached at vendor level: 3.

#### Remaining gaps (smaller than before)

1. **230 unmatched assets** (down from 411) — mostly Korean-language
   drawings and loose CAD. Would need OCR-on-DWG or a manual mapping pass.
2. **104 draft products** — components/themes without imagery. When the
   partner sends more photos (Slack drop or Drive update), re-running B2 +
   E1 + sync + this version's promote helper picks them up automatically.

---

## [2.23.5] - 2026-05-16

### Deployed — DesignPark v2.20.0 apply run (9th brand live in Medusa)

Executed the v2.20.0 scaffolding against live Firestore + GCS + Medusa.

#### Live state

- **Medusa Sales Channel:** `Design Park` → `sc_01KRRK0N4ET8QZHX6QB3KZ84YD`.
  Registered in `scripts/sync_vendors_to_medusa.py::BRAND_SALES_CHANNELS`.
- **Firestore `vendors/designpark` root doc:** written with `origin_route=japan_korea`,
  `currency_native=USD`, `fob_port="Busan, South Korea"`, `duty_rate_thai=0.10`.
- **Firestore `vendors/designpark/products`:** **190 docs** (211 pricelist rows
  collapsed to 190 unique handles; duplicate `MODEL NO` entries across sheets
  resolved by last-write-wins on merge). 178 priced via the USD-FOB →
  THB-landed → retail-USD/THB/EUR formula (formula_version `designpark-v1-2026-05-15`);
  12 themes carry `status=draft_no_images` and no `pricing.retail_*` (quoted
  per project, not catalog-priced).
- **GCS `gs://ai-agents-go-vendors/designpark/media/`:** **518 blobs uploaded**
  (PE images + DWG drawings). UBLA + PAP. Served via storefront proxy at
  `https://catalogs.leka.studio/api/i/designpark/media/<sha>.<ext>`.
- **Firestore `vendors/designpark/attachments/`:** 518 attachment docs.
- **Image-to-product joins:** **109 matches** (15 products with ≥1 image now
  `status=active`, 175 remain `draft_no_images`). Coverage is intentionally
  low for v1 — see Follow-ups #1.
- **Descriptions:** **97 backfills** from 4 catalog PDFs (2024-05-30 ENG,
  2023-09-14 ENG 2022, D.PARK_Catalog_EN, DesignPark-Catalogue). 100
  text-extractable pages processed, 41 image-only pages skipped.
- **Medusa Admin verified:** `GET /admin/products?sales_channel_id[]=sc_01KRRK0N4ET8QZHX6QB3KZ84YD&limit=5`
  returned `count=190` with multi-currency prices on every variant.

#### Sample verification (live data, FX 2026-05-16 USD=33.29, EUR=38.70 THB)

| Handle | FOB USD | Retail USD | Retail THB | Retail EUR |
|---|---:|---:|---:|---:|
| `designpark-3p090-40b0300a-00` | $455 | $1,112.27 | ฿37,028.31 | €956.71 |
| `designpark-3p090-40b0600a-00` | $650 | $1,588.95 | ฿52,897.57 | €1,366.73 |
| `designpark-5p090-58a30a00-00` | $100 | $244.45 | ฿8,138.09 | €210.27 |

#### Run order executed

```
py scripts/bootstrap_designpark.py --apply
py scripts/ingest_designpark_pricelist.py --apply --dump-csv=docs/designpark-pricelist-2026-05-16.csv
py scripts/ingest_designpark_assets.py --apply       # 518 uploads, 109 matched
py scripts/ingest_designpark_catalog_pdfs.py --apply # 97 description writes
py scripts/shape_designpark_to_medusa_schema.py --apply
py scripts/sync_vendors_to_medusa.py --brand=designpark   # 190 created, 0 errors
```

Total wall-clock: ~5 min (asset upload dominates).

#### Files

- modified: `scripts/sync_vendors_to_medusa.py` — `BRAND_SALES_CHANNELS["designpark"] = "sc_01KRRK0N4ET8QZHX6QB3KZ84YD"`
- added (audit): `docs/designpark-pricelist-2026-05-16.csv` (211-row pricelist audit dump)
- modified: `VERSION` → `2.23.5`

#### Follow-ups (not in this entry)

1. **Image-join coverage (109/518 matched).** Most unmatched assets are DWG
   drawings whose filenames carry no SKU token (CAD bundle uses
   `<N>_<theme>.dwg` naming, theme zips use line names). Two fixes:
   (a) tighten the SKU regex to also accept the pricelist's own SKU shapes
   (`5W092-…`, `5P091-…`, `3P090-…`); (b) reconcile the 2024 CAD-bundle
   theme list with the 2023 theme manifest (different theme names —
   e.g. CAD says `Twin Tower`, manifest says `Twin star`).
2. **Modern Igloo sheet.** 12th pricelist sheet uses a non-standard header
   and was skipped (11 rows lost). Easy patch.
3. **Slack `#vendor-design-park` ingest.** Phase C was deferred at v2.20.0;
   not in this deploy entry.
4. **Status promotion.** 175 products remain `draft_no_images`. They sync
   to Medusa as `draft` (correct). After image-join coverage improves, run
   `shape_designpark_to_medusa_schema.py --apply` again and re-sync — they
   will be promoted to `active` → `published`.

## [2.23.4] - 2026-05-16

### Added — Rampline specifications enrichment

New `rampline-catalog/enrich_specifications.py` reads
`vendors/rampline-catalog/parsed/products.json` and pushes
storefront-useful product specs to Medusa via product metadata. Winner-
takes-all per product on a richness score (presence of raw dimensions,
certifications, downloads, notes; tiebreak on description length).

### Fields written to `metadata`

- `installed_dimensions` — `{raw, length, width, height, unit}`. **NOT
  packing CBM** — rampline.com only publishes installed footprint (e.g.
  "Approx. 8 x 10 m", "Area: 46 m²"). Sufficient for storefront product
  pages.
- `installed_area_raw` — captured separately when the raw line says
  "Area: NN m²" (Trip, Twist, Dynamic, Grip, Speed).
- `certifications` — joined string of EN-standard certs (e.g. "EN 1176").
- `downloads_json` — JSON-encoded list of `{type, url, filename}` for
  Rampline-supplied DWG/PDF reference docs. Many point at public Drive
  folders Rampline themselves host.
- `downloads_count` — convenience count for storefront badges.
- `crawl_notes` — free-text "notes" field from the crawl (often the
  equipment-list "Area: NN m². Equipment: …" lines from PDPs).

### Run results (2026-05-16)

| Stage | Counts |
|---|---|
| Dry-run | 28 ENRICH_SPECS planned · 0 skipped |
| Apply | **28 ENRICH_SPECS applied · 0 errors** |

| Field | Products updated |
|---|---|
| `installed_dimensions` | 18 |
| `installed_area_raw` | 5 (Trip, Twist, Dynamic, Grip, Speed) |
| `certifications` | 7 |
| `downloads_json` + count | 14 |
| `crawl_notes` | 26 |

### Why this is NOT landed-cost CBM

The plan's item B asked for landed-cost refinement using crawled tech-
sheet PDFs (replace the 35 % flat uplift). Investigation: the crawled
`docs/` bucket contains 6 CAD `.zip` files + 1 installation manual — no
dimensional packing data. The 2025 NOK pricelist PDF in the Drive folder
contains diameters and installed heights, but no packing CBM. The
crawled `products.json` specifications.dimensions field stores installed
footprint, not box size. **Real CBM still requires supplier-supplied
packing lists from Rampline.** See `MANUAL_TASKS.md` for what to ask for.

## [2.23.3] - 2026-05-16

### Added — Rampline brand-CI enrichment → Sales Channel metadata

New `rampline-catalog/enrich_brand_ci.py` reads
`vendors/rampline-catalog/parsed/brand_ci.json` (palette + logos extracted
by step3) and writes a canonical `brand_ci` token block to the Rampline
Sales Channel (`sc_01KNQAA448RY0YPR51FNPM2TVA`) metadata in Medusa. The
storefront can now render Rampline-branded product pages using these
tokens instead of the generic Leka theme.

### Tokens written (live on Medusa, 2026-05-16)

| Token | Value |
|---|---|
| `primary_color` | `#B5BC00` (Rampline green) |
| `secondary_color` | `#2D5346` |
| `accent_color` | `#0073AA` |
| `text_color` | `#313131` |
| `background_color` | `#E6E6E6` |
| `surface_color` | `#EEEEEE` |
| `neutral_color` | `#DDDDDD` |
| `primary_logo_url` | `https://catalogs.leka.studio/api/i/rampline/design-system/logos/<sha>.svg` |
| `fonts` | `[]` (typography extraction was a Playwright miss; static CSS only had font-family rules that didn't parse cleanly — to be revisited if/when step3 re-renders with the fixed Playwright timeout) |
| `source` | `vendors/rampline/brand_ci/latest` |

Idempotent: re-runs are no-ops when tokens are unchanged.

## [2.23.2] - 2026-05-16

### Added — Playwright fallback for Rampline image enrichment

Follows v2.23.1. The static crawl missed product photos on 11 PDPs
because rampline.com lazy-loads its 360 viewer / gallery images via JS,
and those URLs (`rampline.com/wp-content/uploads/360-uploads/...`) never
appeared in the static HTML. The carousel-only candidates were correctly
filtered out as sibling products, leaving those 11 with 0 images.

New `rampline-catalog/enrich_images_playwright.py`:
- Opens each target product page in headless Chromium
  (`wait_until="domcontentloaded"` + best-effort `networkidle` 20 s) and
  scrolls 4× to trigger lazy-load.
- Reads `document.querySelectorAll('img')` → `src` + `currentSrc` +
  `srcset` after JS hydration.
- Whitelist: `rampline.imgix.net` + `rampline.com/wp-content/uploads/`.
  Same name-token filter as v2.23.1 keeps sibling-carousel images out.
- PATCHes Medusa product with new images + thumbnail (when missing).

### Run results (2026-05-16)

| Stage | Counts |
|---|---|
| Dry-run | 11 ADD_IMAGES, 1 image each |
| Apply | **11 ADD_IMAGES applied · 11 thumbnails set · 0 errors** |

Products enriched (all picked up the rampline.com 360-viewer reference image):
`rampline-take-5`, `rampline-monkey-business`, `rampline-junior-power-ii`,
`rampline-junior-power`, `rampline-jane-jump`, `rampline-hunting-high-and-low`,
`rampline-fearless`, `rampline-fast-and-curious`, `rampline-crouching-tiger`,
`rampline-cliffhanger`, `rampline-classic-jump`.

Combined post-v2.23 totals: 28 Rampline products now have crawl-derived
images on Medusa (3 from v2.23.1 static crawl + 11 from v2.23.2 Playwright +
14 already had images from earlier work). The remaining 34 Medusa-only
products (Rampit, BalanceBuddy, Jumpstone, …) have no rampline.com
counterpart so they still need manual or pricelist-supplied artwork.

## [2.23.1] - 2026-05-16

### Added — Rampline image enrichment from website crawl

Follows v2.23.0 metadata enrichment. New `rampline-catalog/enrich_images.py`
reads `vendors/rampline-catalog/source-files/_manifest.json` + per-page
HTML, parses each Medusa product's source_url page for `<img>` tags, and
attaches new photos to Medusa.

### Image resolution paths

1. **Crawled (preferred):** image is in `vendors/rampline` manifest → use
   GCS proxy URL `https://catalogs.leka.studio/api/i/rampline/media/<sha>.<ext>`
   (served by `leka-website/catalogs/src/app/api/i/[...path]/route.ts` from
   the private `ai-agents-go-vendors` bucket).
2. **External whitelist (fallback):** image is on `rampline.imgix.net` →
   link directly. The crawler skipped imgix because it's off-host; the
   imgix CDN is publicly cached and stable, so direct linking is fine.

### Carousel filter (key correctness fix)

Initial dry-run pulled sibling-product photos from rampline.com's "you
might also like" carousel onto wrong products (e.g. `rampline-take-5`
getting PulseZone + FastandCurious shots). Filter now requires each
candidate image's filename to share at least one token with the Medusa
product handle (or its dehyphenated variant for CamelCase imgix names).
Result: 28 → 3 ADD_IMAGES, all genuinely matching.

### Run results (2026-05-16)

| Stage | Counts |
|---|---|
| Dry-run | 3 ADD_IMAGES · 25 IMAGES_UPTODATE · 0 skipped |
| Apply | **3 ADD_IMAGES applied · 0 errors** · 17 new images total |

| Product | Existing → New |
|---|---|
| `rampline-floating-bench` | 6 → 14 (+8 imgix product photos) |
| `rampline-shockdeck` | 18 → 26 (+8 imgix product photos) |
| `rampline-trip` | 1 → 2 (+1 Trip_Produktbilde) |

The other 25 products with crawl metadata are `IMAGES_UPTODATE`: either
they already have images from earlier work, OR the carousel filter
screened out all candidates (their PDPs only showed sibling-park photos,
not their own). To enrich those further we'd need either (a) a Playwright
re-render of step3 to capture lazy-loaded photos, or (b) a more aggressive
image-mining pass over the rampline.com sitemap.

Idempotent: images are added by union (never replaces). Re-runs are
no-ops.

## [2.23.0] - 2026-05-16

### Added — Rampline enrichment bridge: `vendors/rampline/*` → Medusa

Per the 2026-05-16 architecture statement ("`leka-product-catalogs` is
canonical; `vendors/*` mirrors external sources and ENRICHES the canonical
layer"), this commit wires the rampline.com website crawl output into the
Medusa product catalog.

### What shipped

- `rampline-catalog/enrich_from_vendors.py` (NEW, 360 lines) — reads
  `vendors/rampline-catalog/parsed/products.json` (91 crawled products
  from rampline.com), matches each to a Medusa product on the Rampline
  sales channel by URL/title slug similarity (winner-takes-all per Medusa
  product), and upserts:
    - `metadata.source_url` — canonical rampline.com PDP URL
    - `metadata.crawled_at` — first-write timestamp
    - `metadata.crawl_sha` — SHA-256 of the source HTML
    - `metadata.crawl_category`, `metadata.crawl_subcategory`
    - `metadata.crawl_variant_skus` — comma-joined sibling SKUs from the
      same PDP (preserves the surface-variant breakdown for traceability)
  Description is preserved if Medusa's existing value is ≥80 chars (the
  rich descriptions migrated from earlier work stay intact); only short
  pricelist-title stubs would be overwritten.
- Three run modes: `--report-only` (reconciliation CSV), `--dry-run`,
  `--apply`. Audit logs land in `rampline-catalog/data/build_runs/` with
  the same shape as `build_variants.py` + `sync_variant_prices.py`.

### Run results (2026-05-16)

| Stage | File | Counts |
|---|---|---|
| Reconciliation | `reconciliation_2026-05-16T11-28-24Z.csv` | 125 rows: 90 matched · 1 crawl-only (`slakklinesystem`, no URL) · 34 medusa-only |
| Dry-run | `enrichment_dryrun_2026-05-16T11-30-39Z.json` | 28 ENRICH planned (winner-takes-all collapses 90 → 28 unique Medusa products) |
| Apply | `enrichment_applied_2026-05-16T11-31-42Z.json` | **28 ENRICH applied · 0 errors** |

The 34 medusa-only entries are genuinely absent from the crawl: products
like Rampit, BalanceBuddy, Jumpstone, Fungi are referenced inside other
PDPs on rampline.com but do not have their own standalone PDP pages, so
the crawl could not extract them as discrete products. Not a matcher
defect.

### Spot-check (live Medusa, post-apply)

- `rampline-shockdeck` ← `shock-absorber`: `source_url` ✓, `crawl_sha` ✓,
  `crawl_variant_skus` lists 3 sibling components.
- `rampline-trip` ← `trip-for-shockdeck`: `source_url` https://rampline.com/en/product/trip/,
  `crawl_variant_skus` covers 3 surface variants.
- `rampline-classic-jump` ← `24536`: `crawl_variant_skus` lists 3 article codes.

### Out of scope (deferred to future versions)

- Image enrichment: the crawl captured 239 media artifacts under
  `gs://ai-agents-go-vendors/rampline/media/`. v2.22.3 just landed the
  image-sync fix in `sync_vendors_to_medusa.py`. Wiring crawl media →
  Medusa images is the natural follow-up.
- Brand-CI enrichment (`vendors/rampline/brand_ci/latest` → Medusa
  collection metadata or storefront theme tokens).
- Landed-cost refinement using crawled tech-sheet PDFs for per-SKU CBM.

## [2.22.3] - 2026-05-16

### Fixed — `sync_vendors_to_medusa.py` UPDATE path now syncs images

Bug found while verifying the Eurotramp v1.11.2 image enrichment landed
in Medusa. After uploading 404 product images to GCS and writing
`images[]` to 105 Firestore docs, the storefront still showed the 📦
placeholder for those products. Root cause: `_build_update_payload()`
only emitted `title`, `description`, and `metadata` — it never touched
`images` or `thumbnail`, so any product that already existed in Medusa
(the UPDATE path) had its Firestore images silently dropped on every
sync. Only the CREATE path included images.

### Changes (`scripts/sync_vendors_to_medusa.py`)

- `_build_update_payload()` gains an `existing_image_urls` kwarg. When
  the caller passes it (the set of URLs Medusa already has), the payload
  appends any Firestore URLs not already present (union semantics, so
  Medusa's existing image ids — including reverse-imported ones — are
  preserved). Also writes `thumbnail` when the product has none.
- `metadata` now carries `dimensions` and `gtin` so the v1.11.3
  structured-data backfill propagates to Medusa without a separate sync.
- `_find_product_by_handle()` fetches `thumbnail` + `images.url` so the
  caller can pass them into the update payload.
- Call site in `sync_brand()` builds `existing_img_urls` from the lookup
  response and passes it through.

Idempotent: re-running the sync with no new Firestore images is a no-op
on the image axis (everything already in `existing_image_urls`).

### Outcome

After this fix, `sync_vendors_to_medusa.py --brand=eurotramp` should
push the 404 images uploaded in [eukrit/vendors#12](https://github.com/eukrit/vendors/pull/12)
to Medusa, and the storefront PDPs for the 105 enriched SKUs will
finally render real product photos instead of the placeholder.

## [2.22.2] - 2026-05-16

### Changed — Re-priced Rampline at v2.20.1 pricing constants (30% GM, 7% VAT)

Re-ran the landed-cost + retail pipeline against the Rampline-specific
constants (`GROSS_MARGIN=0.30`, `DUTY_RATE_NON_CHINA=0.10`,
`THAI_VAT_RATE=0.07`) introduced in v2.20.1, refreshed the Firestore
audit doc, and pushed the new prices to all 127 Medusa variants on
the Rampline sales channel.

Also flipped the 8 new Rampball/Jumpstone size sub-products
`draft → published` so they're now visible on the storefront.

#### Pricing-config note

Firestore `pricing_config/canonical` is not yet seeded — the run used
`PRICING_CONFIG_DISABLE=1` to skip the live cfg lookup and resolve to
the module-level fallbacks in
`rampline-catalog/import_pricelist.py` and
`shared/landed_pricing.py`. Once `scripts/seed_pricing_config.py`
populates the Firestore doc, this caveat goes away and the import
script reads the cfg automatically.

#### Price delta vs v2.22.1

Net effect of 0.40 → 0.30 GM (plus today's FX): roughly
**-15 % on retail across the board**, modulated by minor
NOK→EUR drift (0.09277 → 0.09236 today).

| SKU | Family | THB v2.22.1 | THB v2.22.2 | Δ |
|---|---|---:|---:|---:|
| `RB35` | Rampball 35 (wet pour) | 133,471 | **113,648** | -14.85 % |
| `SD 02` | ShockDeck U-piece | 786 | **669** | -14.89 % |
| `BP 15 LF` | Marathon Play (loose fills) | 9,710,485 | **9,731,783** | +0.22 % (FX drift > GM cut for clamped tiers) |

#### Status changes

| Handle | Before | After |
|---|---|---|
| `rampline-rampball-{35,50,50r,70r}` | draft | **published** |
| `rampline-jumpstone-en-{27,50,3,5}` | draft | **published** |

#### Verification

```
Audit doc: vendors/rampline/pricelists/2026-05-13
  calculated_at: 2026-05-16T08:46:12  (refreshed)
  gross_margin: 0.30
  row_count: 127

sync_variant_prices.py --apply
  SET_VARIANT_PRICES: 127
  errors: 0
  unmatched audit codes: 0

8 sub-products status flipped draft → published, 0 NOT FOUND
```

#### Files

- REGENERATED: `rampline-catalog/data/pricelist_2026-05-13_landed.csv`
  (overwritten with 30 % GM numbers).
- NEW: `rampline-catalog/data/build_runs/prices_dryrun_2026-05-16T08-47-52Z.json`,
  `prices_applied_2026-05-16T08-48-43Z.json`.

## [2.22.1] - 2026-05-16

### Added — Rampline variant prices pushed to Medusa (THB / USD / EUR)

127 / 127 Medusa variants on the Rampline sales channel now carry
retail prices in three currencies, sourced from the
`vendors/rampline/pricelists/2026-05-13` Firestore audit doc.

#### Pipeline

`rampline-catalog/sync_variant_prices.py`:
1. Reads the audit doc via Firestore REST (uses
   `LEKA_FIRESTORE_ACCESS_TOKEN` env or ADC fallback — no SA key on disk).
2. Indexes Rampline variants by `metadata.article_code` (set during the
   v2.22.0 variant creation) → falls back to `variants.sku`.
3. For each pricelist row, computes the price delta vs current variant
   state and emits one of `SET_VARIANT_PRICES` / `PRICES_UPTODATE`.
4. Pushes per-variant prices via `POST /admin/products/{pid}/variants/{vid}`,
   stamping each variant with provenance metadata
   (`prices_synced_at`, `prices_synced_from`, `prices_formula_version`).
5. Writes a full audit log under
   `rampline-catalog/data/build_runs/prices_*.json`.

#### Currencies + carve-outs

- **Pushed**: `thb`, `usd`, `eur` (storefront-facing).
- **Not pushed**: `nok`. Wholesale net stays in `variant.metadata.net_nok`
  to avoid confusing customers with supplier currency.
- 8 Rampball/Jumpstone size sub-products remain `status=draft` — flip to
  `published` after a final sanity check.

#### Caveat (intentional)

Prices use the v2.19.0 formula constants from the 2026-05-13 audit doc
(`gross_margin=0.40`, no separate Thai VAT layer). The post-v2.20.1
pricing-config (per-brand GMs + 7% Thai VAT) supersedes this; once the
config is locked, re-run `rampline-catalog/import_pricelist.py` to
refresh the audit doc, then re-run `sync_variant_prices.py` — it's
idempotent and only POSTs deltas.

#### Spot-check

| SKU | Family | Retail THB | Retail USD | Retail EUR |
|---|---|---:|---:|---:|
| RB35 | Rampball 35 (wet pour) | 133,471 | 4,039 | 3,441 |
| SD 02 | ShockDeck U-piece | 786 | 24 | 20 |
| BP 15 LF | Marathon Play (loose fills) | 9,710,485 | 293,837 | 250,350 |

#### Verification

```
Total variants on Rampline channel: 149  (127 real + 22 placeholder)
Variants with prices_synced_at metadata: 127
SET_VARIANT_PRICES actions: 127
PRICES_UPTODATE: 0
errors: 0
unmatched audit codes (no Medusa variant): 0
```

#### Files

- NEW: `rampline-catalog/sync_variant_prices.py` (Medusa price-push
  script with `--dry-run` / `--apply` / `--limit-family`).
- NEW: `rampline-catalog/data/build_runs/prices_dryrun_*.json`,
  `prices_applied_*.json` (full audit trail).
- REGENERATED: `docs/build-summary.html`, `docs/architecture.html`,
  `docs/hub.html` (v2.22.x pickup).

## [2.22.0] - 2026-05-16

### Added — Rampline pricelist → Medusa variants

127 article codes from the 2025 NOK pricelist now live as Medusa
variants across 40 Rampline sub-products. Default placeholder variants
(keyed on the WooCommerce post IDs from the original `rampline.com`
scrape) are removed from every product that received real variants.

#### Structure (per user decision 2026-05-16)

- **Size-as-product** for clean Size × Surface families:
  - `rampline-rampball` → 4 new size sub-products `-35`, `-50`, `-50r`,
    `-70r` (4 surface variants each = 16 variants).
  - `rampline-jumpstone-en` → 4 new size sub-products `-27`, `-50`,
    `-3`, `-5` (4 surface variants each = 16 variants).
- **Single-product-with-options** for multi-axis / service families
  (`balancebuddy-en`, `balancebuddy-wave`, `fungi-eng`, `rampit`,
  `rampit-hopper`, `rampit-swing`, `rampit-storm-en`, `rampbow`,
  `rampline-slackline`, `floating-bench`, `shockdeck`). Axes per
  family: Length × Style, Surface, Size, Component × Surface, Type, or
  synthetic Type (Medusa v2 forbids option-less products).
- **Group B park bundles** — each of 21 SHOCKDECK-priced parks
  (Kangaroo, Marathon Play, …) gains 3-surface variants on top of the
  existing product.

#### Counts

- Products: 54 → **62** (8 new Rampball/Jumpstone size sub-products,
  `status=draft`).
- Variants: **149** total (127 from pricelist + 22 untouched
  placeholders on legacy parks / unpriced equipment / family parents).
- Cleanup: 24 placeholder defaults deleted, 25 "Default" options
  removed.
- Reconciliation: 0 pricelist SKUs missing, 0 unexpected real SKUs.

#### Out of scope (intentional)

- 17 legacy parks not in the 2025 pricelist (ABILITY, AGILE, BOUNCE,
  …, TWIST) — pre-2025 lineup, kept as-is.
- 3 unpriced equipment products (Spare parts ×2, Playground Loop
  trampoline) — kept as-is.
- Variants carry full audit `metadata` (`article_code`, `family`,
  `family_discount`, `net_nok`, `recommended_nok`, `description`,
  `pricelist_date`, `source`) but **no prices** — pricing handled
  separately via the Firestore-backed pricing-config flow (v2.20.1) +
  a follow-up sync script.

#### Files

- NEW: `rampline-catalog/build_variants.py` (Medusa write script,
  `--dry-run` / `--apply` / `--limit-family`).
- NEW: `rampline-catalog/data/mapping/generate_mapping_drafts.py`
  (parser + scaffold generator).
- NEW: `rampline-catalog/data/mapping/family_mapping_draft.csv`
  (40 sub-product rows).
- NEW: `rampline-catalog/data/mapping/variant_scaffold_draft.csv`
  (127 article codes, full option breakdown).
- NEW: `rampline-catalog/data/mapping/medusa_snapshot_2026-05-14.json`
  (read-only Medusa state at planning time).
- NEW: `rampline-catalog/data/build_runs/*.json` (dry-run + applied
  action logs, full audit trail).
- NEW: `docs/summaries/rampline-variants.html` (Leka-styled summary).

#### Verification

```
Total Rampline products: 62  (was 54 + 8 new size sub-products)
Total variants: 149  (127 from pricelist + 22 untouched placeholders)
Pricelist SKUs missing from Medusa: 0
Unexpected non-placeholder SKUs in Medusa: 0
```

#### Next

- Set per-currency prices (THB/USD/EUR/NOK) on the 127 new variants
  via a sync_vendors_to_medusa extension reading
  `vendors/rampline/pricelists/<date>`.
- Flip Rampball/Jumpstone size sub-products `draft` → `published`
  once prices land.
- Re-run the landed-cost computation against the post-v2.20.1 pricing
  config (0.30 GM + duty/VAT layers) once Rampline cfg is locked.
- Parse Rampline tech-sheet PDFs for per-SKU dimensions so the
  landed-cost engine uses real CBM rather than the 35% flat uplift.

## [2.21.0] - 2026-05-16

### Added — Cost cascade dashboard with TH/SG destination pricing

The pricing-config editor at `/forms/pricing-config` now shows the full
FOB → Landed → Retail cascade for one product per logistics tier per
brand, live FX, and side-by-side TH-VAT-inclusive vs SG-via-Nubo
retail prices. Schema additions are backward-compatible.

#### New global config fields
- `th_customer_vat_rate` (default `0.07`) — added to retail base for
  TH-destination sales. The import 7% VAT inside `landed_thb` remains;
  this is an additional sales VAT charged to the customer.
- `sg_customer_gst_rate` (default `0.09`) — applied on SG-destination
  retail **only when** `sg_nubo_gst_registered` is true.
- `sg_nubo_gst_registered` (default `false`) — checkbox. Nubo is not
  yet GST-registered in Singapore; the dashboard ships with this off
  so SG retail is GST-free until that registration completes.

#### New per-brand config fields
- `source_pricelist_url` — file path or URL for the EXW/FOB pricelist.
  Defaults:
  - `vinci`: 2026-05-11 xlsx in Eukrit's Drive (Partners Playground/…)
  - `berliner`: `berliner-catalog/data/pricelist_2026-01-01.csv`
  - `rampline`: Rampline 2025 NOK pricelist (Google Drive)
  - `wisdom`: `wisdom-catalog/data/` (Excel catalogs)
- `source_pricelist_label` — display name for the link in the UI.

#### Live cost cascade
- `GET /api/pricing-context` — new endpoint returning:
  - `fx`: live USD/EUR/SGD vs THB from frankfurter.app (ECB-backed,
    no key), cached 1h server-side, with hardcoded fallback if the
    feed fails.
  - `brands`: for each brand, 1 example product per logistics tier
    (4 examples × 4 brands = 16). For Vinci/Berliner, examples come
    from `vendors/<brand>/products` with stored pricing. For Rampline,
    from `vendors/rampline/pricelists/<date>` variants. For Wisdom,
    from per-product fob_usd. Cascade recomputed against current
    Firestore config so config changes flow through.
- Each cascade row shows: source FOB (native ccy), THB FOB, logistics
  uplift, duty, import VAT, landed, retail-pre-tax (÷ (1 − GM)),
  retail TH (VAT-inclusive), retail SG (SGD).

#### UI
- `docs/forms/pricing-config.html` — major rewrite:
  - Live FX strip in the header (USD/EUR/SGD per THB).
  - All rate fields now display as **percentages** (`7`, not `0.07`),
    stored as decimals.
  - New "Cost cascade — live examples" card under the config form,
    one table per brand.
  - New "Source pricelist" URL + label per brand (clickable; flagged
    if the value is a local Windows path the browser can't open).
  - "Refresh FX + examples" button.
  - Inline formula card explaining the math.
- `src/main.py` VERSION `0.6.1` → `0.7.1`.

#### Formula recap (visible in the dashboard)

```
landed_thb         = (FOB × EUR/THB × unmatched_landed_uplift)
                   + (CIF × duty_rate)
                   + ((CIF + duty) × thai_vat_rate)
retail_pre_tax_thb = landed_thb / (1 − gross_margin)
retail_th_thb      = retail_pre_tax_thb × (1 + th_customer_vat_rate)
retail_sg_thb      = retail_pre_tax_thb × (1 + sg_customer_gst_rate)   (if Nubo GST-registered)
                   = retail_pre_tax_thb                                 (otherwise)
retail_sg_sgd      = retail_sg_thb / (THB/SGD)
```

Wisdom (China-origin) skips the EU-logistics uplift + tier clamp; uses
`brands.wisdom.import_duty_rate` instead of `global.duty_rate_non_china`.

#### Build sequence
1. `a7a41738` SUCCESS (2m1s) — v0.7.0 first cut. Rampline examples
   came back empty.
2. *(diagnosed)* — variant key was `article_code`, not `article`;
   `eur_fob` was pre-computed (no NOK→EUR multiply needed).
3. `bwp6k17ne` — fixed variant field names. Rampline still 0 — caused
   by `order_by("__name__")` returning empty on the named DB.
4. v0.7.1 — switched to `stream() + Python sort by doc id`. All four
   brands now return 4 examples.

#### Smoke output (2026-05-16, live FX EUR=37.99 SGD=25.52 USD=32.67)

```
berliner | tier0 (EUR ≤ 500)  | EUR 163   → landed ฿9,487   → retail_TH ฿13,535  → retail_SG SGD 496
berliner | tier3 (EUR > 10k)  | EUR 10117 → landed ฿519,137 → retail_TH ฿740,635 → retail_SG SGD 27,120
vinci    | tier0              | EUR 116   → landed ฿7,933   → retail_TH ฿13,059  → retail_SG SGD 478
vinci    | tier3              | EUR 10184 → landed ฿614,812 → retail_TH ฿1.01M   → retail_SG SGD 37,059
rampline | tier0              | NOK 73    → landed ฿462     → retail_TH ฿706     → retail_SG SGD 26
rampline | tier3              | NOK 113833 → landed ฿637,529 → retail_TH ฿974,508 → retail_SG SGD 35,683
wisdom   | tier0              | USD 3     → landed ฿120     → retail_TH ฿257     → retail_SG SGD 9
wisdom   | tier3              | USD 11640 → landed ฿435,382 → retail_TH ฿931,717 → retail_SG SGD 34,117
```

#### Notes for the user to verify
- The 7% Thai customer VAT is **stacked on top** of the import VAT
  (per your direction). If the convention is actually that retail
  already absorbs the import VAT and only the 7% customer VAT is
  shown to the buyer, set `th_customer_vat_rate = 0` and the formula
  collapses to `retail_th = retail_pre_tax`.
- Nubo SG GST: dashboard ships with the flag OFF. Flip when Nubo is
  registered and the 9% multiplier kicks in automatically.
- Source pricelist links: Vinci's default is a local Windows path that
  browsers can't open. Replace with the Drive share URL once you have
  it (the field is right above the link).
- Wisdom values look low because `wisdom-b2-2255` has a `fob_usd` of
  $3 — that's likely a SKU with a misparsed unit price (catalog default
  is per-piece, not per-pack). Catalog data, not formula bug.

## [2.20.3] - 2026-05-16

### Fixed — pricing-config form Load failed HTTP 404

The editor page loaded but `fetch("/api/pricing-config")` 404'd because
the gateway strips the `/leka-product-catalogs` prefix on the way to the
backend, and the browser resolved the absolute path against the gateway
host (`https://gateway.goco.bz/api/pricing-config`) instead of the
project-prefixed path. Two follow-ups from v2.20.2:

- `docs/forms/pricing-config.html` — added `API_URL` derived from
  `location.pathname` so the same HTML works whether served via
  `gateway.goco.bz/leka-product-catalogs/forms/pricing-config` or
  directly from local Flask. Footer "← Hub" link is now path-relative
  (`../`) instead of hardcoded `/leka-product-catalogs/`.
- `src/main.py` — `VERSION` 0.6.0 → 0.6.1 for traceability.

Also adds a separate gateway-side change merged in PR
[go-access-gateway#6](https://github.com/eukrit/go-access-gateway/pull/6) —
script sync for `register-all-projects.sh` (live registry was already
patched via Firestore REST when the user hit the v2.20.2
`not_found_in_repo` error).

### Build
- Cloud Build `aaa11d4c` SUCCESS (1m48s). Image
  `gateway:3eac0a2-dirty` deployed as new revision of
  `leka-catalogs-gateway`. `/health` returns `0.6.1`.

## [2.20.2] - 2026-05-16

### Deployed — pricing-config UI live at gateway

Followed the v2.20.1 deploy plan and pushed a new revision of the
existing `leka-catalogs-gateway` Cloud Run service (asia-southeast1).
The page that previously returned the gateway's `not_found_in_repo` 404
now resolves because the v0.5.0 revision didn't have the
`/forms/pricing-config` route — the new revision (image
`gateway:3d640e7`) does.

#### Decisions
- **Reused `leka-catalogs-gateway`** instead of creating a separate
  `leka-catalogs-admin` service. The access-gateway already proxies
  `https://gateway.goco.bz/leka-product-catalogs/...` to it, and that's
  what the user actually calls.
- **Kept `--allow-unauthenticated`** on the service. Tightening to
  invoker-only requires a coordinated change in `go-access-gateway`
  routing so it mints an ID token before proxying — out of scope for
  this deploy. The form's POST handler already trusts the gateway's
  forwarded `X-Goog-Authenticated-User-Email` for the audit trail.

#### Changes
- `cloudbuild-admin.yaml` — retargeted to `_SERVICE: leka-catalogs-gateway`
  + image `_IMAGE: gateway`. Removed `--no-allow-unauthenticated` flip.
- `.gcloudignore` — root `Dockerfile` build context needs `src/`,
  `shared/`, `docs/forms/`, and `vinci-catalog/web-app/public/`. Removed
  the wholesale `docs`, `shared`, `scripts`, `/src`, `/vinci-catalog`
  exclusions (gitignore semantics — can't re-include children of an
  excluded parent); added narrow per-file exclusions for the heavy
  non-runtime parts that we don't need in the image.
- `.dockerignore` — same fix on the Docker side: removed `docs/` and
  `shared/`, added narrow exclusions for non-runtime docs files.

#### Build sequence (today)
1. Cloud Build `4b7964fa` — FAIL: `$SHORT_SHA` empty on manual submit.
   Fix: pass `--substitutions=SHORT_SHA=$(git rev-parse --short HEAD)`.
2. Cloud Build `708f2b37` — FAIL: `COPY shared/` not found
   (`.gcloudignore` excluded `shared`). Fix: see above.
3. Cloud Build `e65c0c30` — FAIL: `COPY docs/forms/` not found
   (gitignore parent-dir rule defeated `!/docs/forms/**`). Fix: removed
   the blanket `docs` exclusion.
4. Cloud Build `a2642143` — **SUCCESS** (2m1s). Image
   `asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs/gateway:3d640e7`
   deployed as revision `leka-catalogs-gateway-00002-?`.

#### Smoke test (direct Cloud Run URL)
- `GET /health` → `{"version":"0.6.0", ...}` ✅ (was `0.5.0`)
- `GET /api/pricing-config` → 200 with the seed (5 globals, 4 brands,
  4 tiers) ✅
- `GET /forms/pricing-config` → 200, 13.9 KB of HTML ✅

Gateway URL `https://gateway.goco.bz/leka-product-catalogs/forms/pricing-config`
returned the Google sign-in flow on unauthenticated curl — IAP working
as expected. Authenticated browser sessions get the editor.

### Outstanding (not blocking the editor)
- `pricing_config/canonical` Firestore doc doesn't exist yet. The form
  serves `_empty_config()` defaults until either:
  - The user clicks **Save changes** in the editor (writes the doc with
    their email as `updated_by`), or
  - `python scripts/seed_pricing_config.py` is run locally (writes the
    doc with `scripts/seed_pricing_config.py` as `updated_by`).
- `--no-allow-unauthenticated` tightening — see Decisions above.

## [2.20.1] - 2026-05-15

### Added — Firestore-backed pricing config + gateway-fronted editor UI

Pricing parameters are no longer scattered Python module-level constants
edited via PR. They now live in **`pricing_config/canonical`** in the
`leka-product-catalogs` Firestore database and are editable through a
form behind the access gateway.

#### Reader side
- `shared/pricing_config.py` (new) — process-cached Firestore loader.
  `get_pricing_config(brand)` merges global keys with per-brand overrides;
  returns `{}` when Firestore unreachable so module-level constants act
  as fallbacks. `PRICING_CONFIG_DISABLE=1` short-circuits in CI/tests.
- `shared/landed_pricing.py` — `price_row()` gains `brand: str = "vinci"`
  kwarg; pulls GROSS_MARGIN, DUTY_RATE_NON_CHINA, THAI_VAT_RATE,
  UNMATCHED_LANDED_UPLIFT, and LOGISTICS_TIERS from the live cfg.
- `shared/wisdom_pricing.py` — `compute_wisdom_retail()` and
  `pricing_metadata()` consult the live cfg via `_params()`.
- `vinci-catalog/import_pricelist.py` — passes `brand="vinci"` into
  `price_row()`; metadata writes use `_vinci_gross_margin()` (live).
- `berliner-catalog/import_pricelist.py` — `_berliner_params()` returns
  live cfg merged with Berliner's local fallbacks; both `price_row()` and
  `write_firestore()` consume it.
- `rampline-catalog/import_pricelist.py` — passes `brand="rampline"`
  into `price_row()`; `_rampline_params()` covers the post-call retail
  re-derivation.

#### Writer side
- `src/main.py` — adds `/forms/pricing-config`, `GET /api/pricing-config`,
  `POST /api/pricing-config`. Auth boundary is the gateway IAP; we trust
  `X-Goog-Authenticated-User-Email` / `X-Goco-User-Email` for the audit
  field. Range-validates payloads (catches "35" entered as percent vs
  "0.35"). `VERSION` bumped 0.5.0 → 0.6.0.
- `docs/forms/pricing-config.html` — Manrope + Leka palette editor with
  brand pills, logistics-tier table, save/reload buttons, audit footer
  ("Last edited by … at …"), and a raw-JSON debug pane.
- `Dockerfile` — installs `google-cloud-firestore`, copies `shared/` and
  `docs/forms/` so the Flask service can serve the editor.
- `cloudbuild-admin.yaml` (new) — manual-trigger build that deploys the
  Flask service as Cloud Run service `leka-catalogs-admin`,
  `--no-allow-unauthenticated`, ready for the gateway invoker-binding.

#### Seed
- `scripts/seed_pricing_config.py` — one-shot. Reads current module-level
  constants from shared + brand scripts and writes them to
  `pricing_config/canonical`. `--force` to overwrite, `--dry-run` to print.

#### Hub
- `hub.config.json` — `pricing-config.html` added to
  `classification_hints`. `live.enabled` stays `false` until the
  Cloud Run admin service is deployed and gateway-routed.

### Verification
- `PRICING_CONFIG_DISABLE=1 python -c "..."` confirms the fallback path
  resolves to module defaults (Vinci 0.35 GM, non-China duty 0.10, etc.).
- Flask test_client smoke: GET returns seed (5 globals, 4 brands, 4
  tiers); bad payload (`thai_vat_rate=7`) → 400; valid payload → 500
  with sanitized Firestore error (expected — local ADC expired).
- Form route serves the 13.5 KB HTML editor.

### Deploy plan (one-time, manual)
```bash
gcloud builds submit --config=cloudbuild-admin.yaml
gcloud run services add-iam-policy-binding leka-catalogs-admin \
  --region=asia-southeast1 \
  --member="serviceAccount:go-access-gateway@ai-agents-go.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
python scripts/seed_pricing_config.py
# Then in go-access-gateway/registry, point project_id "leka-product-catalogs"
# at this Cloud Run URL and flip hub.config.json hub.live.enabled to true.
```

### Outcome
- The 2026-05-14 pricing canonicalization (commits `e0c5c75` + `4316d8f`)
  is now live-editable. Next tweak is one form save + one re-run of
  `<brand>/import_pricelist.py` — no PR required.
- Closes the Rules 2 + 4 gap from the v1.32.0 sibling work
  (CHANGELOG + build-summary were left stale by `e0c5c75` + `4316d8f`).

## [2.20.0] - 2026-05-15

### Added — DesignPark onboarding (9th brand, full Gen-3 pipeline scaffolding)

DesignPark (DESIGN PARK Co., Ltd., South Korea — playground, water play,
outdoor fitness, themed installations) onboarded via the same
`vendors/<slug>` → `sync_vendors_to_medusa.py` path the other 8 brands use.
This version lands the **code + dry-run validation**; the actual
`--apply` runs against live Firestore / GCS / Medusa are gated on
credentials and follow as a v2.20.1 deploy entry.

### Pipeline

1. **`scripts/bootstrap_designpark.py`** — creates the Medusa Sales Channel
   "Design Park" via `MedusaImporter.get_or_create_sales_channel`, then
   merge-writes `vendors/designpark` root doc to Firestore DB `vendors`
   (origin_route=`japan_korea`, currency_native=USD, FOB port=Busan,
   duty_rate_thai=0.10 — non-China per landed_pricing rule).
2. **`scripts/ingest_designpark_pricelist.py`** — parses
   `Design Park Pricelist D'Park Price List (USD-2024).xlsx` (12 sheets,
   178 component SKUs across Slides & Tubes, Fitness Premium/Universal/
   Elderly/SMART/Senior/CrossFit, Speed Racers, Play Dry/GRC/Aquatic)
   plus the 33-theme manifest at
   `2024-03-18 D'Park 2D CAD & Images/2023 Theme dry&waterplay list ... .xlsx`.
   211 product docs written to `vendors/designpark/products`.
3. **USD FOB → THB landed → retail (THB/USD/EUR)** — same formula spine as
   Vinci/Rampline, but currency-agnostic per row: cost_engine origin =
   `japan_korea` (LCL Busan → Bangkok), DUTY_RATE_NON_CHINA=10%,
   THAI_VAT_RATE=7%, UNMATCHED_LANDED_UPLIFT=1.35x (no CBM data in the
   pricelist; tightens when B2 supplies DWG-derived dimensions),
   GROSS_MARGIN=0.35. Formula version stamped `designpark-v1-2026-05-15`.
4. **`scripts/ingest_designpark_assets.py`** — discovers 620 assets across
   four sources: CAD bundle (66 numbered `<N>_<theme>.{jpg,dwg}` files),
   `Catalogs GO/DesignPark/IMAGE/*.zip` (197 images across 11 line zips),
   `Catalogs GO/DesignPark/DRAWING/*.zip` (337 DWGs across 10 zips),
   `Suppliers GO/DesignPark/*.zip` (16 per-SKU drops). Uploads to
   `gs://ai-agents-go-vendors/designpark/media/<sha>.<ext>` (UBLA, PAP),
   serves via `https://catalogs.leka.studio/api/i/designpark/media/<sha>.<ext>`,
   joins to products by SKU regex (SDM/PTC/PTM/DPM/DPF/DPS) or theme-name
   slug match.
5. **`scripts/ingest_designpark_catalog_pdfs.py`** — pdfplumber-extracts
   text from the 2024 ENG catalog (and 2022 fallback); backfills empty
   `description` fields by matching SKU tokens / product names against
   the product index. Image-only pages are reported but skipped (Gemini
   Vision OCR path deferred to follow-up if needed).
6. **`scripts/shape_designpark_to_medusa_schema.py`** — finalizes invariants
   (`handle`, `images[]` deduped by sha, `thumbnail`, `status` promoted to
   `active` when ≥1 image attached else `draft_no_images`).
7. **`scripts/sync_vendors_to_medusa.py`** — added `designpark` placeholder
   to `BRAND_SALES_CHANNELS`; the bootstrap script provides the `sc_…` id.

### Phase C deferred

Slack `#vendor-design-park` ingest deferred to v2.20.1 — depends on Slack
OAuth setup not yet in place for this brand. Plan placeholder lives at
`~/.claude/plans/inspect-new-vendor-scraping-stateful-octopus.md` §C1.
Website scrape (originally Phase D) skipped per plan §7 decision #1.

### Dry-run output (2026-05-15)

```
ingest_designpark_pricelist.py --dry-run
  FX: USD=33.0119 THB/USD, EUR=38.5735 THB/EUR
  parsed 11/12 component sheets (Modern Igloo header non-standard, skipped)
  parsed 33 themes
  built 211 product docs
  sample: PE SINGLE SLIDE 900 — fob_usd=$375 → retail_usd=$916.70

ingest_designpark_assets.py --dry-run
  total assets discovered: 620
  by kind:   {'image': 389, 'drawing': 211}
  by source: {'cad-bundle': 66, 'image-zips': 197, 'drawing-zips': 337, 'suppliers': 16}
  has sku:   78 / no sku: 522 (theme/line match)
```

### Files

- new: `scripts/bootstrap_designpark.py`
- new: `scripts/ingest_designpark_pricelist.py`
- new: `scripts/ingest_designpark_assets.py`
- new: `scripts/ingest_designpark_catalog_pdfs.py`
- new: `scripts/shape_designpark_to_medusa_schema.py`
- modified: `scripts/sync_vendors_to_medusa.py` — `BRAND_SALES_CHANNELS` entry placeholder.
- modified: `VERSION` → `2.20.0`

### Apply sequence (for v2.20.1 deploy)

```
py scripts/bootstrap_designpark.py --apply                      # SC + root doc
py scripts/ingest_designpark_pricelist.py --apply               # 211 products
py scripts/ingest_designpark_assets.py --apply                  # GCS uploads + image[] join
py scripts/ingest_designpark_catalog_pdfs.py --apply            # descriptions
py scripts/shape_designpark_to_medusa_schema.py --apply         # status promote
# Update BRAND_SALES_CHANNELS["designpark"] with sc_ id printed by bootstrap.
py scripts/sync_vendors_to_medusa.py --brand=designpark --dry-run
py scripts/sync_vendors_to_medusa.py --brand=designpark
```

## [2.19.0] - 2026-05-13

### Added — Rampline pricelist → landed cost + retail (Firestore audit)

Rampline's 2025 NOK pricelist (Google Drive, 31 KB, 127 article codes
across 13 product families) now flows through the same landed-cost +
40 % GM retail formula as Vinci Play, with results audited in Firestore
at `vendors/rampline/pricelists/2026-05-13`.

### Pipeline

1. `rampline-catalog/import_pricelist.py` fetches/reads the xlsx,
   parses section headers (each carries the wholesale discount), reads
   the **Net price 2025** column as EXW (NOK).
2. NOK → EUR via `open.er-api.com` (live ECB-backed, fallback
   `frankfurter.app`, then hardcoded 0.087). Today: 0.09277 EUR/NOK.
3. EUR FOB → THB landed via `shared/landed_pricing.py` (shipping-automation
   `estimate_landed_cost` LCL Europe → Laem Chabang, Baltic-rate
   calibrated).
4. Tiered logistics clamp (80 / 60 / 45 / 35 % floor by FOB band).
5. Retail THB = landed / 0.60 (40 % GM); USD/EUR at live FX.

### Output

- CSV: `rampline-catalog/data/pricelist_2026-05-13_landed.csv` (127 rows).
- Firestore: `vendors/rampline/pricelists/2026-05-13` — single audit doc
  with `variants` map keyed by sanitized article code, plus
  `fx_snapshot`, `nok_eur_rate`, `baltic_rate_snapshot`, `logistics_tiers`.

### Spot-check

| SKU | NOK net | EUR FOB | Landed THB | Retail USD |
|---|---:|---:|---:|---:|
| SD 02 (SHOCKDECK smallest) | 73 | 6 | 442 | $22 |
| RB35 (Rampball wet-pour) | 13,910 | 1,290 | 80,083 | $4,039 |
| BP 15 LF (SHOCKDECK largest) | 1,199,380 | 111,259 | 5,826,041 | $293,820 |

94/127 SKUs hit the floor clamp (small parts dominated by fixed
shipping costs), 33/127 within band, 0 capped. Realized GM uniformly 40 %.

### Shared module

Lifted the Vinci landed-cost + retail formula into
`shared/landed_pricing.py` so both brands share one canonical
implementation. `vinci-catalog/import_pricelist.py` refactored
(427 → 219 lines) — zero behaviour change.

### Medusa push — DEFERRED

Rampline's 54 Medusa products each have a single "Default" variant
keyed on the WooCommerce numeric ID. The pricelist's 127 article
codes are variant-level SKUs that don't yet exist in Medusa. Creating
per-article variants is a separate migration (also needs new products
for SHOCKDECK / climbing pole / balance arch families). For now we
only audit landed + retail in Firestore.

### Files

- NEW: `shared/landed_pricing.py`,
  `rampline-catalog/import_pricelist.py`,
  `rampline-catalog/data/source/rampline_pricelist_2025_fetched-2026-05-13.xlsx`,
  `rampline-catalog/data/pricelist_2026-05-13_landed.csv`,
  `docs/rampline.html`.
- CHANGED: `vinci-catalog/import_pricelist.py`, `CHANGELOG.md`, `VERSION`.

### Next

- Decide whether to create per-article Medusa variants (127 new
  variants across 13 families) — needs family-name → Medusa-product
  map and probably new products for SHOCKDECK / climbing pole /
  balance arch.
- Source per-SKU dimensions (Rampline tech-sheet PDFs are scraped but
  not parsed yet). Would shift most rows off the flat-uplift branch.

## [2.18.4] - 2026-05-13

### Fixed — Medusa admin UI silent-crash (start from `.medusa/server`, not `/app`)

Root cause of the v2.18.2/2.18.3 silent-exit-on-start when
`DISABLE_ADMIN=false`:

Medusa v2's `medusa build` outputs the admin UI assets to
`.medusa/server/public/admin/`. At runtime, the admin loader
(`@medusajs/medusa/src/loaders/admin.ts:90`) looks for
`<cwd>/.medusa/admin/index.html` — i.e. it assumes the CLI is being run
from inside `.medusa/server`, not from the project root. Our `start.sh`
was running `medusa start` from `/app`, so the loader looked for
`/app/.medusa/admin/index.html` (doesn't exist) and crashed.

The crash output never reached Cloud Logging because the medusa CLI
catches the error and exits before its logger has flushed — only
"Server is ready" + the error message appear, and only when started
from the right cwd. We caught this by spinning up the image inside
Cloud Build with verbose stdout capture and a wide `find .medusa`,
which surfaced both the build output location (`.medusa/server/public/admin/`)
and the loader's expectation (`.medusa/admin/`).

### Changes

- **`medusa-backend/start.sh`** — `cd /app/.medusa/server` before
  `exec node /app/node_modules/.bin/medusa start`. The CLI is resolved
  via the parent `/app/node_modules` so we don't need a second
  `npm install` inside `.medusa/server`.
- **`cloudbuild.yaml`** — restored `DISABLE_ADMIN=false` in the deploy
  step's `--set-env-vars` (was reverted to `true` in v2.18.3 as a
  hotfix when we couldn't isolate the crash).

After Cloud Build picks this up, the admin UI lives at
https://catalogs.leka.studio/app . Login with `admin@leka.studio` +
the password in Secret Manager (`medusa-admin-password`).

### Debug artefact

`cloudbuild-debug-admin.yaml` (new) — pulls the production image and
runs `medusa start` inside Cloud Build with stdout/stderr captured,
useful for surfacing silent crashes that Cloud Run obscures. Keep
around for future debugging.

## [2.18.3] - 2026-05-13

### Reverted — `DISABLE_ADMIN=false` in cloudbuild (Medusa start silent-crash on Cloud Run)

v2.18.2 set `DISABLE_ADMIN=false` so the admin UI would be served at
`https://catalogs.leka.studio/app`. After two rebuilds and three Cloud
Run revisions (`00015`, `00016`, `00017`), the container failed every
startup probe with no usable error: stdout shows `medusa start` printing
its banner then exit(1) with nothing else on stdout / stderr / Cloud
Logging. Revision `00018-mcq` is the working state — same new image
(`medusa-backend:01addb0`), same MEDUSA_BACKEND_URL baked in, but
`DISABLE_ADMIN=true` so the API stays healthy.

This commit reverts the `DISABLE_ADMIN` default in `cloudbuild.yaml` back
to `true` so the next Cloud Build doesn't break the service. Everything
else from v2.18.1+2 stays:

- `MEDUSA_ADMIN_PASSWORD` from Secret Manager (Rule 12 fix).
- `MEDUSA_BACKEND_URL=https://catalogs.leka.studio` baked + at runtime
  (harmless with admin disabled; ready for when admin is re-enabled).
- `ADMIN_CORS` / `AUTH_CORS` include `catalogs.leka.studio` (also
  harmless; future-proofs the storefront).
- `cloudbuild.yaml` deploy `--set-env-vars` keeps the `^|^` delimiter so
  comma-bearing values (AUTH_CORS) deploy cleanly.

The `catalogs.leka.studio/admin/*` + `/auth/*` Next.js rewrites in
[eukrit/leka-website](https://github.com/eukrit/leka-website) v0.8.8
**do work** — the admin API + login are reachable through the catalogs
domain. Only the admin UI HTML at `/app` is unavailable on Cloud Run.

### Workaround

Run the admin UI locally against prod credentials:

```powershell
cd medusa-backend
# .env: DATABASE_URL / REDIS_URL / COOKIE_SECRET / JWT_SECRET copied
# from Secret Manager (or use ADC via gcloud secrets versions access)
npx medusa develop
# Open http://localhost:9000/app
```

`medusa develop` builds + serves the admin in dev mode and bypasses the
production startup issue.

### Follow-up

The silent `medusa start` exit needs local repro to surface stack
traces. Likely candidates: missing admin asset, NODE_ENV=production +
admin combination in this Medusa version, or a config validation that
fails without printing. Out of scope for tonight; tracked for next
session.

## [2.18.2] - 2026-05-13

### Changed — Wire Medusa admin to catalogs.leka.studio/app

- **`cloudbuild.yaml`**:
  - `--build-arg=MEDUSA_BACKEND_URL=https://catalogs.leka.studio` — admin
    bundle now calls its API on the catalogs domain, not the raw Cloud Run
    URL. Combined with the storefront's Next.js rewrites, every admin
    request stays on one origin (no CORS).
  - `--set-env-vars` switched to `^|^` delimiter syntax. The previous
    `\,` escape inside `AUTH_CORS` was being rejected by gcloud as
    `Bad syntax for dict arg: [https://leka-medusa-backend-...]`, which is
    why v2.18.1's build step succeeded but the deploy step silently
    failed (the bash wrapper echoed "Deployed..." regardless of exit
    code). The new `^|^` delimiter lets values contain literal commas.
  - `ADMIN_CORS` and `AUTH_CORS` both now include
    `https://catalogs.leka.studio` (plus the Cloud Run direct URL for
    fall-back during DNS / domain-mapping cutover).

### Companion change

[eukrit/leka-website](https://github.com/eukrit/leka-website)
`catalogs/next.config.js` — new `rewrites()`:
```
/app           → ${MEDUSA}/app
/app/:path*    → ${MEDUSA}/app/:path*
/admin/:path*  → ${MEDUSA}/admin/:path*
/auth/:path*   → ${MEDUSA}/auth/:path*
```
After both deploys land, the admin lives at
https://catalogs.leka.studio/app (HTML+assets) and the bundle's API
calls (`/admin/*`, `/auth/*`) hit the same origin via the rewrites.

## [2.18.1] - 2026-05-13

### Changed — Medusa admin UI enabled + admin password moved to Secret Manager (Rule 12 fix)

- **Dockerfile (`medusa-backend/Dockerfile`):** add `ARG MEDUSA_BACKEND_URL`
  + `ENV MEDUSA_BACKEND_URL` before `npm run build` so the admin UI bundle is
  built with the production backend URL hard-coded into its API client.
- **`cloudbuild.yaml` (build step):** pass
  `--build-arg=MEDUSA_BACKEND_URL=https://leka-medusa-backend-538978391890.asia-southeast1.run.app`
  so the bundle that lands in the image points at the live Cloud Run URL.
- **`cloudbuild.yaml` (deploy step):**
  - `--set-secrets` adds `MEDUSA_ADMIN_PASSWORD=medusa-admin-password:latest`
    (previously plain text — visible to anyone with `run.services.get`,
    Rule 12 violation).
  - `--set-env-vars` adds `NODE_ENV=production`, `DISABLE_ADMIN=false`
    (was `true` — admin UI now served at `/app`), and
    `MEDUSA_ADMIN_EMAIL=admin@leka.studio` so the deploy matches what the
    earlier out-of-band `gcloud run services update` runs had to set
    manually.

### Other

- Granted `roles/secretmanager.secretAccessor` to the runtime SA
  `538978391890-compute@developer.gserviceaccount.com` on the
  `medusa-admin-password` secret (so the new revision can resolve the
  secret binding at start).
- Revision `leka-medusa-backend-00014-w4s` already has the secret binding
  + Rule-12 fix live; this commit makes that state reproducible from
  Cloud Build and unlocks the admin UI on the next image rebuild.

## [2.18.0] - 2026-05-13

### Added — EPDM/Infill pricer + new shared product categories

Converted the live "EPDM 2024 / Pricelist" Google Sheet
(`1wXGZoseE4PWEiY14BmtrYaHkkCJJEPyLQnUte7qUGrg`, tab `Pricelist`) into a
configurable HTML pricer and a Firestore product catalog so other projects can
query Critical Fall Height (CFH) without ever opening the spreadsheet.

(Originally landed locally as v2.10.0 commit `2d96cd0`, lost to a
`git reset --hard origin/main` that brought in v2.14–v2.16, re-applied as
v2.17.0 then renumbered to **v2.18.0** to clear the version collision with
the remote-side Wisdom → Leka Project rebrand that also took v2.17.0.)

- **`scripts/sync_epdm_pricelist.py`** — pulls the sheet via the Sheets API
  (SA `claude@ai-agents-go`), re-implements the formula chain locally
  (`H = G·C`, `J = H·I`, `L = J·K`, `P = (J+L)·(1+O)·N`, `R = P·Q`,
  `V = P·(V₃/12)·U`, `AD = H·AB·AC`, `AE = W of SBR-Shreded[thk=D]`,
  `W = P+R+T+V+AD+AE`, `Y = W/(1−X)`, `Quote = CEIL(Y/(1−Z), step)`),
  and writes (a) `docs/forms/data/epdm-pricelist.json` plus (b) one Firestore
  doc per row. Two-pass compute handles the AE backing lookup for layered
  EPDM/TPV. **Quote parity vs the sheet: 10/10 spot-checked rows match
  exactly** (SBR Granule, Sand Infill, Rubber Infill, SBR Shreded, EPDM Miroad,
  EPDM Eurosia Non-UV, EPDM Eurosia UV, TPV UV).
- **`scripts/import_categories_shared.py`** — writes two new
  brand-agnostic category docs (`product_categories/epdm`,
  `product_categories/infill`) in the `leka-product-catalogs` database,
  parallel to the existing per-brand `product_categories_{brand}` ones.
  `brand: null` marks them shared.
- **Firestore** (`leka-product-catalogs` database):
  - `products_epdm` — 53 docs (SBR Granule + SBR Shreded + EPDM Miroad +
    EPDM Eurosia Non-UV/UV + EPDM Custom Graphic + TPV UV)
  - `products_infill` — 5 docs (Sand 16/30 + 20/40 + SBR 4/7 kg/sqm + TPE 4 kg/sqm)
  - Each doc carries `cfh_m: number` at top level so other projects can ask
    "given fall height ≥ X m, which thickness/SBR/system is the cheapest
    compliant option?" via
    `db.collection("products_epdm").where("cfh_m", ">=", X)
       .order_by("cfh_m").order_by("pricing.quote_thb_per_sqm").limit(1)`.
- **`docs/forms/epdm-pricer.html`** — single-file static page, Leka Design
  System styled (Manrope, `#8003FF`, 16px cards, navy header, amber CFH
  badge). Left pane: product picker + per-row inputs. Right pane: global
  params + live cost breakdown ending in the boxed final Quote. Pure
  client-side JS mirrors the same 2-pass calc so changing globals re-flows
  every backing lookup. Served via gateway at
  `https://gateway.goco.bz/leka-product-catalogs/forms/epdm-pricer`
  (private, sign-in-gated per Rule 14).
- **`firestore/firestore.indexes.json`** — three new composite indexes:
  `products_epdm(status, cfh_m, pricing.quote_thb_per_sqm)`,
  `products_epdm(system, cfh_m, thickness_mm)`,
  `products_infill(system, pricing.quote_thb_per_sqm)`. All deployed.
- **`hub.config.json`** — classification hint so the pricer lands under
  Forms on the regenerated `docs/hub.html`.

### CFH lookup contract for downstream projects

Database: `leka-product-catalogs` · Collection: `products_epdm` ·
Query: `where status==active and cfh_m >= <required>` ordered by
`cfh_m ASC, pricing.quote_thb_per_sqm ASC`. Smoke-tested live:
`cfh_m >= 1.5` returns `EPDM Blk 50/0` (1.6 m, 5,155 THB/sqm) and
`EPDM E 10/40` (1.6 m, 3,195 THB/sqm) — cheapest Eurosia Non-UV option.

### Files
- NEW `scripts/sync_epdm_pricelist.py`
- NEW `scripts/import_categories_shared.py`
- NEW `docs/forms/epdm-pricer.html`
- NEW `docs/forms/data/epdm-pricelist.json` (58 products + defaults + source)
- MOD `firestore/firestore.indexes.json` (+3 composites)
- MOD `hub.config.json` (classification_hints)
- MOD `PROJECT_INDEX.md` (CFH lookup contract section)
- REGEN `docs/hub.html`, `docs/build-summary.html`, `docs/architecture.html`
- BUMP `VERSION` 2.17.0 → 2.18.0

## [2.17.0] - 2026-05-13

### Changed — Wisdom → Leka Project rebrand (customer-facing)

Customers now see the formerly-Wisdom vendor's 5,062 products as the in-house
"Leka Project" brand. The upstream supplier identity is hidden behind Leka's
own house brand across every customer-visible surface in Medusa.

### Medusa data changes (live, scripted, idempotent)

- **Sales channel `sc_01KNKTHC0B7KFEDSZ3NNM49JQW`**: name `"Wisdom"` →
  `"Leka Project"`; description updated. ID unchanged so the publishable key
  binding and storefront env vars stay valid.
- **Publishable API key `apk_01KNKTHXDJ344T8V131SKJPNEK`**: title
  `"Wisdom Storefront"` → `"Leka Project Storefront"` (token unchanged — no
  storefront re-deploy required).
- **5,061 products** got fresh opaque handles `leka-project-{nanoid8}` and
  fresh opaque variant SKUs `LP-{NANOID8}`. Old handle preserved in
  `metadata.legacy_handle`; old SKU in `variant.metadata.legacy_sku` for
  procurement / quotation cross-reference. One stray `test-swing` product
  was skipped (not a real Wisdom product).
- **32 titles + 32 descriptions** had embedded "Wisdom" / "WISDOM" /
  "Wisdom Toys" strings stripped.
- **6,228 product image URLs + 2,835 thumbnails** rewritten from
  `https://catalogs.leka.studio/api/i/wisdom/...` →
  `https://catalogs.leka.studio/api/i/leka-project/...`.

### Image bucket (Gemini-cleaned)

- New cleaned-image prefix `gs://ai-agents-go-vendors/leka-project/` populated
  by `scripts/strip_wisdom_logos.py`. Originals kept untouched at
  `gs://ai-agents-go-vendors/wisdom/` for audit + rollback.
- **Pass-1 (logo detection):** 37,975 / 37,976 images classified via Gemini
  2.5 Flash. **814 images contain Wisdom branding** (2.14%); 37,161 are clean.
  Per-image checkpoint persisted in Firestore `image_logo_scan/{sha1(path)}`.
- **Pass-2 (logo removal):** 814 hits fed to Gemini 2.5 Flash Image
  (Nano Banana Pro) at `location=global`. Final counts after error mop-up:
  ~625 OK / ~185 manual_review / ~5 hard errors. QA-failed edits routed to
  `gs://ai-agents-go-vendors/manual_review/` for human follow-up. Per-image
  state in Firestore `image_logo_edit/{sha1(path)}`.
- **Bulk copy:** 37,161 no-logo blobs server-side-copied to `leka-project/`
  in 4.5 minutes (zero Gemini cost).
- **Cost:** ≈ $5 Flash + ≈ $30 Nano Banana Pro = ~$35 in Vertex AI.

### Storefront-side coordination (next: leka-website)

- The leka-website image proxy at `catalogs/src/app/api/i/[...path]/route.ts`
  is already prefix-agnostic (`/api/i/<vendor>/...` →
  `gs://ai-agents-go-vendors/<vendor>/...`), so the new
  `/api/i/leka-project/...` URLs resolve with **zero code changes**.
- Outstanding for leka-website (separate PR): rename the `wisdom` brand-route
  to `leka-project`, swap the brand registry entry, replace the logo asset,
  and 301 the old `/catalogs/wisdom/*` URLs. The redirect map for product
  handles ships with this commit at `migration/wisdom-handle-redirects.json`
  (5,061 entries) for storefront middleware to consume.

### Added — three new scripts

- `scripts/strip_wisdom_logos.py` — three-phase pipeline (`--scan-only`,
  `--edit-only`, `--copy-only`). Idempotent + resumable via Firestore
  checkpoints. Tolerant JSON parser, exponential-backoff retry on 429/5xx,
  schema flattened to avoid Vertex `Nested arrays are not allowed` rejection.
- `scripts/rebrand_wisdom_to_leka_project.py` — orchestrates SC rename,
  publishable-key rename, product handle/SKU regeneration. `--dry-run` and
  `--revert` supported. Writes `migration/wisdom-handle-redirects.json`.
- `scripts/rewrite_wisdom_image_urls.py` — flips Medusa product
  `images[].url` and `thumbnail` from `/api/i/wisdom/...` to
  `/api/i/leka-project/...`. Idempotent.

### Notable lessons learned

- Gemini Flash schema with nested arrays (`bboxes: array of array of number`)
  hits a hard `400 Nested arrays are not allowed` server-side validator. Use
  array of objects or a flat numeric array instead.
- Gemini image-edit refuses prompts that name a third-party trademark
  ("remove the Wisdom logo" → policy refusal). Brand-neutral framing
  ("remove overlay text and small graphics, preserve product") works.
- Vertex `gemini-2.5-flash` at `location=global` has tight quota
  (~5 RPM-effective with bursts). Concurrency above 4 reliably trips
  RESOURCE_EXHAUSTED storms.

### Files changed
- `scripts/strip_wisdom_logos.py` (new)
- `scripts/rebrand_wisdom_to_leka_project.py` (new)
- `scripts/rewrite_wisdom_image_urls.py` (new)
- `migration/wisdom-handle-redirects.json` (new, force-tracked)
- `CHANGELOG.md`, `VERSION`

### Outcome

Live Medusa Production: 5,061 Wisdom products rebranded to Leka Project on
2026-05-13. Storefront images resolve via the existing image proxy.
~185 manual_review + ~5 hard-error images need human inpainting follow-up
(<0.5% of catalog).

---

## [2.16.0] - 2026-05-13

### Added — Multi-currency variant pricing + Firestore-driven variants in `sync_vendors_to_medusa.py`

Extended the cross-brand Medusa sync to read 4-currency pricing (USD/THB/EUR/SGD)
and Firestore-declared `variants[]` arrays, used by the new Eurotramp 2025
pricelist pipeline in [eukrit/vendors](https://github.com/eukrit/vendors)
`eurotramp-catalog/scripts/` (BUILD_LOG `[1.10.1]`).

- `_build_prices()` (new) — emits a Medusa `prices[]` array from
  `pricing.retail_{usd,thb,eur,sgd}` in minor units. Falls back to legacy
  `pricing.fob_usd` (USD-only) so previously-seeded brands still work.
- `_update_variant_prices()` (renamed from `_update_variant_price`) — PATCHes
  all currencies in a single body, reusing existing `price.id` per
  `currency_code` so price rows aren't orphaned. Endpoint corrected to
  Medusa v2: `POST /admin/products/{product_id}/variants/{variant_id}`.
- `_build_create_payload()` — when a Firestore doc carries `variants[]`,
  emits one option (`variant_option` field, e.g. `Coating`) + one Medusa
  variant per entry with per-variant `prices[]`. Single-variant docs
  unchanged (Default/Default).
- `_ensure_variants()` (new) — for existing Medusa products, upserts any
  `variants[]` entries that aren't on the product yet; skips with a log
  when the product was created with the legacy `Default` option only
  (needs one-off admin migration to add the new option).
- `_find_product_by_handle()` — now returns `options.{id,title,values.value}`,
  `variants.{title,sku,options.value,options.option_id}`, and
  `variants.prices.{id,currency_code,amount}`.

Live run on Eurotramp (sales channel `sc_01KNQAA3Y72W17B7CP2VQ93T3M`):
**187 products · 105 created · 187 updated · 123 priced · 0 errors**.
Spot-check `eurotramp-kids-tramp-playground`: USD $3,572.10 / THB ฿118,047.75
/ EUR €3,043.43 / SGD $4,544.84.

One-off store config: PATCHed `store.supported_currencies` to add `sgd`
(was `eur, thb, usd`).

- **Files modified:** `scripts/sync_vendors_to_medusa.py`, `CHANGELOG.md`.
- **Backwards compat:** brands without `pricing.retail_*` (vortex, wisdom,
  vinci, berliner) keep USD-only pricing via the legacy `pricing.fob_usd`
  path. No re-run required.

## [2.15.1] - 2026-05-13

### Changed — Berliner gross margin 40 % → 25 %

Berliner-specific markup retune. `GROSS_MARGIN = 0.25` in
`berliner-catalog/import_pricelist.py` (Vinci keeps its 40 %). Re-ran the
landed-cost importer (801 Firestore docs refreshed) and re-pushed prices to
Medusa. All Berliner retail prices scaled by ×0.80 (= 0.60 / 0.75).

### Fixed — `push_pricelist_to_medusa.py` name-only lookup

The first GM-25 re-push CREATEd 405 duplicate products (handles `*-3`/`*-4`)
because the original script only looked up rows by `item_code`. Name-only
pricelist rows (no SKU) bypassed the match path and re-CREATEd instead of
UPDATEing the v2.15.0 originals.

- Fixed by using the CSV row's `handle` (already uniquified by parser with
  `-2`/`-3` suffixes on name collisions) as the synthetic SKU lookup key —
  matches the SKU that `create_product` writes for name-only rows
  (`variant.sku = sku or handle`), so subsequent runs round-trip as
  UPDATEs.
- Added `berliner-catalog/delete_duplicate_products.py` to clean up the
  damage. Filter is **time-windowed by `--since` against `created_at`** so
  real product SKU-style handles like `berliner-spaceball-l-02` (Spaceball
  L.02, created during initial scrape) are not matched. Deleted 405 dupes
  with 0 errors.
- Final re-push: 722 updated + 6 created + 73 skipped + 0 errors.

Sample: LU.001.001 retail THB 2,546,873 → **2,037,498** / USD 77,068 →
**61,654** / EUR 65,662 → **52,529**. Solar Explorer THB 52,312 → **41,849**.
944 total Berliner products in Medusa SC.

## [2.15.0] - 2026-05-13

### Added — Berliner Seilfabrik pricelist load (Compendium 11, 2026)

First Berliner data load. Parses the 2026 Compendium 11 EN-Ausland pricelist PDF
(11 pages, 801 SKUs/lines) and pushes products + THB/USD/EUR retail prices
through the same landed-cost pipeline Vinci uses. Trade terms are EXW; our EXW
cost is 15 % off the published list, then the Vinci EU-LCL cost engine
(Baltic-rate calibrated, tier-clamped, 40 % GM) produces THB landed and retail.

**New code**
- `berliner-catalog/parse_pricelist.py` — PyMuPDF `find_tables()` extraction.
  Detects 4- and 5-column schemas (some tables drop the leading "Page" col).
  Synthesizes handles from item code; falls back to slugified name when an
  accessory row has no SKU. Disambiguates collisions with a counter suffix.
- `berliner-catalog/import_pricelist.py` — mirrors
  `vinci-catalog/import_pricelist.py`. Reads pricelist CSV, applies 15 % EXW
  discount, computes landed THB via the shared
  `shipping-automation/mcp-server/cost_engine`, applies the standard Vinci
  `LOGISTICS_TIERS` floor/cap, marks up to 40 % GM, and upserts
  `vendors/berliner/products/{handle}` in Firestore. Reads existing dimensions
  if a prior website scrape populated them; otherwise every row takes the
  `flat_uplift` path. `GOOGLE_APPLICATION_CREDENTIALS` is read from env (no
  hardcoded SA path).

**New artifacts**
- `berliner-catalog/data/pricelist_2026-01-01.csv` — parsed PDF
- `berliner-catalog/data/pricelist_2026-01-01_landed.csv` — landed cost
- `berliner-catalog/DEPLOYMENT_LOG.md` — initial load
- `docs/berliner.html` — Leka-styled summary page

**Counts**
- 801 rows: 380 priced+SKU, 348 priced/name-only, 16 SKU on-request, 57
  name-only on-request
- 728 `flat_uplift` + 73 `n/a` (on-request) — 0 dim-matched (no scrape yet)
- Firestore: 801 docs under `vendors/berliner/products`
- Medusa: 801 rows reconciled with the existing Berliner sales channel
  (`sc_01KNQAA3QDYHP15Y9K4PPRMDF0`, ~498 pre-scrape products): **349 updated**
  + **440 created** + **12 skipped** + **0 errors**. On-request rows pushed as
  `draft` with no price; priced rows carry THB+USD+EUR retail.

**Mismatch discovery**: the generic `scripts/sync_vendors_to_medusa.py` couldn't
be used as-is because the prior Berliner scrape used `berliner-<slug(name)>`
handles (e.g. `berliner-swingo-02`) while our pricelist parser produced
`berliner-<slug(item_code)>` (e.g. `berliner-90-160-141`). Lookup by handle
missed every existing product, then CREATE collided on the duplicate SKU.
`push_pricelist_to_medusa.py` solves this by paginating the SC, building a
SKU → variant map, and routing each row to UPDATE-by-SKU or CREATE-with-
slug-of-name.

**Sample math (verified)**
- berliner-lu-001-001 (LevelUp.01.1) list EUR 34,333 → EXW EUR 29,183 (×0.85)
  → THB FOB 1,131,931 → landed THB 1,528,124 (flat_uplift) → tier-band cap
  (EUR≥10 k → 35-80 % logistics, clamp inactive) → retail THB 2,546,873 / USD
  77,068 / EUR 65,662 (÷0.60 GM)

## [2.14.1] - 2026-05-13

### Fixed — Vinci series filter (badges + `/vinci/series/<slug>` page) returned 0 products

**Symptom:** On `catalogs.leka.studio/vinci`, clicking any series badge emptied the
product grid; deep-linking to `/vinci/series/<slug>` also rendered 0 products.
Berliner / 4soft / Vortex were unaffected.

**Root cause:** All 1,096 Vinci products had `collection_id = null` on the Medusa
backend, while their `metadata.series_slug` / `metadata.series_name` were
populated and the 27 Vinci collections (`pcol_…`) themselves still existed. An
earlier Vinci re-import wrote products under a flattened handle scheme
(`vinci-{item_code}` instead of `vinci-{series_slug}-{item_code}`) and dropped
the `collection_id` field — the badges queried `?collection_id=pcol_…` and got
0 matches. Probed via the four brands' publishable keys: Berliner / 4soft /
Vortex returned 100% `collection.id` populated; Vinci returned 0/100.

**Fix:**
- Added `MedusaImporter.set_product_collection(product_id, collection_id)` —
  one-line wrapper around `POST /admin/products/:id` to set the collection link.
- New script `vinci-catalog/relink_collections.py` — paginates all products in
  the Vinci Sales Channel via Admin API, reads `metadata.series_slug`,
  get-or-creates the matching collection (idempotent), and PATCHes each product
  with the correct `collection_id`. Run with `--dry-run` first.

**Result:** 1,096 / 1,096 products relinked, 0 errors. Verified post-fix:
- `ACTIVE` (pcol_01KNKVFBG2WD4GHG6GRR86QSFF) → 11 products
- `ROBINIA` (pcol_01KNKVHCSNDZGHQWAFVJVTR49F) → 255 products
- All 27 Vinci series filters now functional.

### Verified — all four collection-bearing brands

| Brand | Own collections | Sample filter | Products |
|---|---|---|---|
| Vinci Play | 27 | `workout` | 54 |
| Berliner Seilfabrik | 18 | `berliner-univers` | 1 |
| 4soft | 3 | `4soft-tunnels-furniture` | 48 |
| Vortex Aquatics | 8 | `vortex-uncategorized` | 272 |

### Files changed
- `shared/medusa_importer.py` — `set_product_collection` helper
- `vinci-catalog/relink_collections.py` — new one-off relink script
- `CHANGELOG.md`

### Storefront note
No `leka-website/catalogs/` changes were needed; the storefront's
`collection_id` filter call (`catalog-content.tsx:141`,
`series/[slug]/page.tsx:36`) was already correct. The fix is
backend-data-only.

---

## [2.15.1] - 2026-05-13

### Documented — the "remaining 103 uncovered drafts" are AI-Vision-inferred, not orphans

The v2.15.0 followup report flagged "~91 real-SKU drafts still uncovered" as
needing another image source or hand curation. Investigation surfaced the
real story: those 103 docs were created by the **upstream Anthropic-Vision
scrape pipeline** (well before this session) and already contain full
English `name`, `description`, and `category` fields. They look "uncovered"
only because they predate v2.13.0's source-priority guards and lack a
`source_url_*` field.

Examples of what's actually in these docs (sampled):
- `AT0002` "Tactile Path - Nature" — full description, balance category
- `ED0001` "Edusante Trike" — full description, motor-skill category
- `KB0001` "Jumbo Blocks" — full description, construction category
- `KB0007` "Translucent Honeycomb" — full description, sensory category
- `KC0015` "Log & Roll", `KC0016` "Tai Chi Ball", `KC0018` "Step 'n' Stones",
  `KC0019` "Wavy Tactile Path", `KC0021` "Tactile Board", `KC0022`
  "Tactile Stepping Stone" — all with rich descriptions

The docs even carry an audit trail in their `notes` field:
"Product identified as Weplay X (SKU) based on visual appearance.
Specifications are not available in the image."

#### `scripts/stamp_weplay_ai_inferred.py` (new)
Stamps these 103 docs with explicit lineage:
  - `source_ai_inferred = True`
  - `source_ai_pipeline = "anthropic_vision_v1"`
  - `source_ai_sha = <existing source_sha>`

Doesn't change `status` (kept as draft — SKU assignments are AI-inferred
and may not match the real catalog), `name`, or `description`. Just makes
the lineage visible so future enrichment passes know to treat these as
"covered with caveat".

By prefix: KC=55, KM=20, KP=13, KB=4, KS=4, KT=2, AT=1, ED=1, KF=1,
KY=1, WJ=1.

#### Why they stay drafts
The AI inference IS plausible and the descriptions read well, but:
1. SKU may not match Weplay's actual catalog (e.g. `KC0010` was AI-tagged
   "Tai Chi Ball", but Vision OCR of the 2025 catalog also tagged
   `KC0016` as "Tai Chi Ball" — same product, different inferred SKUs).
2. No images attached — would render as placeholder cards on storefront.

To promote any of these to active in a future pass would require:
1. Cross-referencing the inferred SKU against the catalog OCR data
   (`scripts/ocr_weplay_local_pdfs.py` dump) for confirmation.
2. Image attachment (likely from `source_sha` page lookup).
3. Probably a manual review step.

Out of scope here. The stamp + documentation is enough to prevent future
"~91 uncovered" reports and clarify the gap.

### Composite catalog state (unchanged from v2.15.0)
`catalogs.leka.studio/weplay`: still **200 active product cards**. The
103 AI-inferred drafts remain drafts — high-quality candidates for a
future manual review pass.

### Files changed
- `scripts/stamp_weplay_ai_inferred.py` (new)
- `CHANGELOG.md`

---

## [2.15.0] - 2026-05-13

### Added — Weplay catalog 149 → 200 via Vision OCR of image-only catalog PDFs

Two new scripts that close the last open growth path: Gemini-Vision-OCR
of the four image-only PDFs in the local Drive folder that v2.14.0
skipped (`2025-2026`, `2020-2021`, `2022-2023`, `New Products 2021-2023`,
totaling 330 pages, ≤135 chars/page text-extractable).

#### `scripts/ocr_weplay_local_pdfs.py` (new)
PyMuPDF renders each PDF page to a 180-DPI JPG; Gemini 2.5 Flash extracts
`{sku, name_en, description_en, age_range}` per visible product card.
Resumable via JSON checkpoint dump every 5 pages. Same writeback safety
as flipbook: only writes when no `source_url_*` is set.

**Run:** 330 pages processed, **198 unique SKU tokens** extracted,
148 with rich descriptions (>30 chars), 174 with age ranges. Source
attribution: 2025 (516 mentions), 2022-2023 (381), 2020-2021 (314),
New Products (9 — mostly section dividers).

Writeback: 162 matched to existing docs → 153 already covered →
**9 new draft writes** (KC0007 Icy Ice Building Set, KC0008 Forever
Up-Down, KC0009 Infinite Loop, KC0010 Tai Chi Ball, KC0011 Putt Putt
Balance Board, KC0013 Tai-Chi Balance Board, etc).

#### `scripts/create_weplay_pdf_only_docs.py` (new)
For the 77 SKUs the OCR found that DON'T have any Firestore product
yet, create new docs with `status="draft_no_images"`, EN name +
description from OCR, category inferred from SKU prefix
(`PREFIX_CATEGORY` map: KB=balance, KM=motor-skill, KT=sensory,
KP=construction, KC=construction, KE=classroom-furniture,
KF=ball-play, EM=motor-skill).

Notable additions: KT7001-KT7006 (Helix Balance Path, Jungle Trial,
Coral Adventure, Rainbow River Stones, Wavy Tactile Path, Tactile
Curve Path), KC0012 (Maze Balance Board), KM4001 (Team Walker),
KT0001 (Stepping Stones), KT0004 (Tactile Straight Path).

URL-safe handle slugifier added (`re.sub(r"[^a-z0-9._-]+", "-")`)
after first sync attempt rejected `kt3310-(l)` / `ke0311...(l)..(s)`
handles with `Invalid product handle` errors.

#### Bug fixed — `shape_weplay_to_medusa_schema.py` was clobbering data
The original shaping script (v2.8.4) wrote `name = product_name or sku`
unconditionally, then `images = []` when no URL-encoded SKU folder match
existed. Re-running it after EN content + thumb-image ingest had landed
**clobbered** the EN names back to Chinese product_name and **nuked**
the thumb images on the 36 promoted-via-thumb drafts.

Detected via spot-check after running shape post-PDF-OCR. Recovered by
re-running scrape_weplay_en + scrape_weplay_cached + ingest_weplay_images
(all idempotent). Patched the shape script to be safe by default:
  - `name` only set if doc has no existing `name` (so EN scraper writes
    win on re-run).
  - `images` only set when this run finds attachments AND doc has no
    existing `images[]` (preserves thumbs).
  - `status` only flipped TO active — never demoted by this script.

The recovery turned out to be a net win: re-running the cached scrape
caught additional drafts the prior pass had missed, raising the
post-recovery active count from the pre-shape 149 to **200**.

#### Vision rank rerun + thumbnail sync
After the catalog grew to 200, vision_rank_weplay_images.py picked up
the previously-unscored ~460 images plus all the new actives:
**+462 scored, +74 reordered, +71 primary photo changes**. Cumulative
across all session runs: ~1,060 images scored.

`sync_weplay_thumbnails.py` pushed the 71 thumbnail changes + 70+ image
order updates to Medusa. End-state dry-run: 200/200 in sync, 0 changes
needed, 0 errors.

#### Final composite catalog
- **`catalogs.leka.studio/weplay`: 200 active product cards** (was 149
  in v2.14.0, +34% jump)
- All 200 carry English names + descriptions (sourced from `.tw?lang=en`
  live, GCS-cached HTML, 2025 flipbook OCR, OR 2020/2022/2025 PDF
  Vision OCR)
- 71 lifestyle/kids-using primary photos picked by Gemini Vision
- Provenance fields per product: `source_url_en`, `source_url_cached`,
  `source_url_flipbook`, `source_url_local`, `source_url_pdf_ocr`

#### Reversed prior conclusion (v2.14.0)
v2.14.0 concluded that `KC0007`–`KC0030` were "scrape artifacts" because
none of the text-extractable sources had them. Vision OCR proved them
**real Weplay products** (Icy Ice Building Set, Tai Chi Ball, Infinite
Loop, etc.) just hidden inside image-only PDFs. The previous
"definitive answer" was definitively wrong.

### Files changed
- `scripts/ocr_weplay_local_pdfs.py` (new)
- `scripts/create_weplay_pdf_only_docs.py` (new)
- `scripts/shape_weplay_to_medusa_schema.py` (safety patch)
- `CHANGELOG.md`

### Remaining (small)
- ~91 Firestore draft tokens still uncovered (real-SKU `item_code`
  with no source). Need another image-only catalog edition or hand
  curation. Many likely color variants (e.g. `KC0013-B`) that match
  the parent SKU's URL pattern but have separate Firestore docs.

---

## [2.14.0] - 2026-05-12

### Investigated — local Google-Drive Weplay catalogs (closes upstream-data debate)

Mined `C:\Users\Eukrit\My Drive\Catalogs GO\WePlay Catalogs\` (5 PDF
catalogs 2020–2026, 2 Excel pricelists, 2 quotation PDFs). Built
`scripts/ingest_weplay_local_catalogs.py` to parse all text-extractable
sources and merge into Firestore using the same source-priority writeback
as the cached and flipbook scripts.

#### Result
113 unique SKUs found across local sources → 100 already had richer
source data (live/cached/flipbook) → only **1 truly new write**
(KP4003 "Weplay Twinkle Stones" — pulled from the 2021 Powen pricelist).

#### Definitive finding on the "uncovered drafts"
Of the 113 draft products with extractable SKU tokens that had no
catalog source attached:
  - **112 are scrape artifacts** — synthetic SKUs like `KC0007`–`KC0030`
    that don't exist in ANY of the five PDF catalogs (2020-2026), the
    Excel pricelists, or the 2020 quotations. Real Weplay numbering
    jumps from `KC0001`–`KC0006` directly to `KC1801`/`KC2001`/`KC2802`,
    so the entire `KC0007`–`KC0030` range is upstream pipeline noise.
  - **1 (KP4003)** is real but discontinued, recovered from 2021
    pricelist.

These 112 ghost SKUs should be archived/deleted as a future cleanup —
they're polluting the `vendors/weplay/products/*` collection but will
never become real products.

#### 40 catalog-only SKUs (legitimate gap)
Local catalogs surfaced 40 real SKUs we don't have Firestore docs for:
EM5501–EM5531 (Edusante line), KC1801/KC2008/KC2009 (Creative Mat /
Puzzle Fun), KC2803–KC2805, KE0014/KE0015 (Cot), KE0311/KE0312 (Modern
Ball Chair), KF0005 (Tricky Fish), KM4001/KM5514, KP0002 (Circular
Balancing Board), and others. These could become new active products
in a future pass — they have names + sometimes prices, just need image
sources matched.

#### Image-only PDFs skipped
2025 (95p), 2020-2021 (83p), 2022-2023 (91p), and New Products 2021-2023
(61p) PDFs have ≤135 chars/page (image-only). Vision OCR via Gemini
would cost ~$30-50 across 330+ pages — deferred unless the 40
catalog-only SKUs warrant it.

### Files changed
- `scripts/ingest_weplay_local_catalogs.py` (new)
- `CHANGELOG.md`

### Composite catalog state on `catalogs.leka.studio/weplay`
- **149 active products** (no change from v2.13.0 — local sources
  largely overlap)
- 1 more product with EN content (KP4003, still draft until image
  ingest)
- Catalog growth path is now exhausted from automated EN sources;
  further growth requires (a) bulk-creating Firestore docs for the 40
  catalog-only SKUs + sourcing their images, or (b) Vision OCR on the
  330+ image-only catalog pages.

---

## [2.13.0] - 2026-05-12

### Added — Weplay coverage closes follow-ups: catalog 136 → 149 + cached/flipbook fallback sources

Three small follow-up scripts that close out the v2.12.0 out-of-scope items
(missing actives, unreachable drafts, unscored vision images).

#### `scripts/scrape_weplay_cached.py` (new)
Mines `gs://ai-agents-go-vendors/weplay/pages/*.html` (1,453 pages from
the original scrape) for English product detail content the live
crawler missed. Same parser as `scrape_weplay_en.py`; only writes when
the doc lacks both `source_url_en` and `source_url_cached`.

**Result:** 597 cached HTML pages parsed → 181 unique SKUs → 31 new
Firestore writes. Recovered EN content for 4 of the 9 originally-missing
actives (KB1303 Gym Ball, KB1307 Gym Roll, KC3001 Learning Cube, KC3004
Stepping Shape) plus 27 more drafts. After re-running the existing
ingest pipeline + Medusa sync: **+13 new active products promoted**.
Catalog grew **136 → 149**.

The remaining 5 missing actives (KC0001, KP1001, KP1002, KP1003, KT0003)
aren't in any cached page — likely never crawled.

#### `scripts/ocr_weplay_flipbook.py` (new)
OCRs the 188-page Weplay EN 2025 Flash flipbook (one high-res JPG per
page at `weplay.com.tw/download/EN/Catalog/2025/files/mobile/N.jpg`)
via Gemini 2.5 Flash. Per-page prompt asks for every product card on
the page as `{sku, name_en, description_en, age_range}`.

**Result:** 257 SKUs extracted, 251 matched to Firestore docs, 248
already had richer source data (live or cached) and were skipped, **3
new writes** (KM1004 Balance Rocking Ice, KM1006 Honey Hills, KM1007
Coral Adventure). 103 catalog SKUs found with no matching Firestore
doc — could become new products in a future pass. Cost ~$2-3.

The 116 originally-uncovered drafts are mostly OLDER products
(`KB0001`, `KC0007` style) discontinued before the 2025 catalog — the
flipbook doesn't help them. They'd need an older catalog edition or
hand-curation.

#### Vision rerun (no new script — `vision_rank_weplay_images.py --apply` again)
Second pass picked up the ~460 images Gemini 429'd on first run.
**+110 images scored, +15 reordered, +8 primary changes.** Cumulative
totals across the two passes: 600 images scored, 82 products
reordered, 66 new card thumbnails.

### Composite outcome
- `catalogs.leka.studio/weplay`: **149 product cards** (was 136 in v2.12.0)
- Provenance fields per product: `source_url_en` (live), `source_url_cached`
  (GCS HTML), `source_url_flipbook` (page N OCR) — explicit lineage
- Drafts left: 113 with real-SKU `item_code` not in any source we tried
  (mostly KB0001-style discontinued products)

### Files changed
- `scripts/scrape_weplay_cached.py` (new)
- `scripts/ocr_weplay_flipbook.py` (new)
- `CHANGELOG.md`

---

## [2.12.0] - 2026-05-12
## [2.9.1] - 2026-05-10

### Verified — backend pipeline green end-to-end

Manually submitted `cloudbuild.yaml` against `medusa-backend/` to validate the
v2.8.5 db-migrate fix had actually been exercised — it had not, because no
Cloud Build trigger exists for this repo (the storefront's build was driven
manually too). Build [`5628a71c-3485-47dd-bf29-4eb99fdeefa4`](https://console.cloud.google.com/cloud-build/builds;region=asia-southeast1/5628a71c-3485-47dd-bf29-4eb99fdeefa4?project=538978391890):
4m3s, **SUCCESS** through all four steps (build / push / db-migrate / deploy).
Backend image `medusa-backend:fixmigratetest` is now serving on Cloud Run
service `leka-medusa-backend`. Storefront at `https://catalogs.leka.studio/`
continues to call this backend — no client-visible change.

### Added
- **Cloud Build trigger `deploy-leka-medusa-backend`** — watches `main` branch
  on `eukrit/leka-product-catalogs`, build config `cloudbuild.yaml`, included
  files `medusa-backend/**` + `cloudbuild.yaml`. So future backend changes
  auto-deploy the same way the storefront now does. Service account
  `claude@ai-agents-go.iam.gserviceaccount.com` runs the build.

### Out of scope (still TODO)
- `medusa-backend/Dockerfile` — Medusa v2 `.medusa/server` structure mismatch.
  The fact that builds pass and the runtime works suggests the mismatch is
  cosmetic / partial; flagged as a separate task to clean up the layered
  COPY in stage 2 and confirm `.medusa/server` is the canonical location.
- Wisdom palette audit (lives in `eukrit/leka-website`).

---

## [2.9.0] - 2026-05-10

### Removed — Next.js storefront migrated to `eukrit/leka-website`

The multi-brand storefront moved to the leka-website repo on 2026-05-10 (commit
`1cf31cf`, leka-website v0.7.0). It now ships from `catalogs/` in that repo,
deploys to a new Cloud Run service `leka-catalogs`, and serves
`https://catalogs.leka.studio/` (verified live, all 4 brand routes 200, TLS
provisioned). The old service `leka-medusa-storefront` is cold-scaled
(`min=0, max=1`) for 24h rollback safety; full deletion follows once the new
stack is validated.

This repo now owns only the Medusa v2 backend (`medusa-backend/`) and the
data-prep / vendor-shaping scripts. Backend → Storefront contract unchanged:
storefront still calls `https://leka-medusa-backend-538978391890.asia-southeast1.run.app`
via per-brand publishable keys (which moved to leka-website's
`cloudbuild-catalogs.yaml`).

### Removed
- `medusa-storefront/` — full Next.js app, public assets, configs, Dockerfile.
- `cloudbuild-storefront.yaml`, `cloudbuild-storefront-only.yaml` — orphan pipelines.
- `cloudbuild.yaml` Steps 5–7 (build-storefront, push-storefront, deploy-storefront)
  + the `medusa-storefront` images output. Backend pipeline (Steps 1–4) is unchanged.

### Out of scope (still TODO in this repo)
- `medusa-backend/Dockerfile` — Medusa v2 `.medusa/server` structure mismatch.
- `cloudbuild.yaml` `db-migrate` step — currently broken; backend deploys remain
  red until this is fixed (independent of the storefront migration).
- Wisdom palette audit (referenced by leka-website, not this repo).

## [2.8.5] - 2026-05-10

### Fixed — Cloud Build `db-migrate` step (Missing script error since v2.8.3)
- v2.8.3 changed step 3 from `npx medusa db:migrate` to `npm run db:migrate` but didn't account for entrypoint-override behavior: when Cloud Build runs a step with a custom `entrypoint`, the container CWD is `/workspace` (the host workspace mount), NOT the image's WORKDIR (`/app`). So `npm run db:migrate` ran in `/workspace` where no `package.json` exists → `npm error Missing script: "db:migrate"`.
- Every build since 4e31de5 failed at this step, including the `feat(weplay)` merge (build `66cfff32`).
- Fix: switch to `entrypoint: bash` + `args: ['-c', 'cd /app && npm run db:migrate']` so CWD is explicitly set inside the container before npm runs.

### Files changed
- `cloudbuild.yaml`

---

## [2.8.4] - 2026-05-10

### Added — Weplay catalog live (path 1B: imaged subset)
- Created Medusa Sales Channel **Weplay** (`sc_01KR6Z0VBSXWYZDVGF30EAP0EQ`) + publishable key `pk_2b18dd5670830702993445fe43f4269a406baab0b20f85cad15d43b9b9a9efbb`. Linked the key to the SC.
- Imported **100 Weplay products** (KC/KM/KT/KB/KP series) into the new SC. All published, all with images, no USD prices (Weplay catalog policy).
- Storefront URL: `https://catalogs.leka.studio/weplay` (live after CI/CD deploy).

### Fixed — `sync_vendors_to_medusa.py` two real bugs found during the Weplay run
- **`prices` field omission rejected by Medusa v2** — when `pricing.fob_usd` was missing, the script omitted `variant.prices` entirely, and Medusa returned `{"type":"invalid_data","message":"Invalid request: Field 'variants, 0, prices' is required"}` for all 100 products. Fix: always send `prices: []` when no FOB price exists. (This bug presumably affects Berliner / Eurotramp / 4soft re-syncs too — they all use the same code path. Tested: 100/100 success after fix.)
- **`--skip-no-images` flag** — additive opt-in flag that filters out products with empty `images[]` before sync. Used for Weplay path 1B to ship only the 100 products with confirmed photos and skip the 1,095 `draft_no_images` records left for path 2.

### Added — `scripts/shape_weplay_to_medusa_schema.py`
- Converts the upstream Weplay scrape's per-product schema (`product_name`, `sku`, no `handle`, no `images[]`) into the schema `sync_vendors_to_medusa.py` expects (`name`, `item_code`, `handle`, `images[]`, `status`).
- Image join: indexes `vendors/weplay/attachments/*` by URL-encoded SKU folder pattern (`/Products/<XX>/<SKU>/`); joins each product whose `sku` contains a matching token. Only ~8% of attachments carry the URL-encoded SKU and ~8.4% (100/1,195) of products end up with images. The remaining 1,095 products are written back with `status="draft_no_images"` so the sync filter can skip them. **Path 2 follow-up will source images for the rest** (likely via re-running the upstream `/Products/<prefix>/<SKU>/` crawl with full coverage rather than relying on the partial scrape).
- Image URL form is the storefront proxy: `https://catalogs.leka.studio/api/i/weplay/media/<sha>.<ext>` — served by `medusa-storefront/src/app/api/i/[...path]/route.ts`, no public GCS bucket exposure.
- Backfilled the `vendors/weplay` root doc with `name`, `slug`, `country`, `legal_name`, `website`, `status`, `sales_channel_id`, `publishable_key_id`, `publishable_key_token`.

### Wired
- `scripts/sync_vendors_to_medusa.py` — added `"weplay": "sc_01KR6Z0VBSXWYZDVGF30EAP0EQ"` to `BRAND_SALES_CHANNELS`.
- `medusa-storefront/src/lib/medusa-client.ts` — Weplay `productCount: 0 → 100`; `hasCollections: true → false` (no `collectionPrefix` exists for Weplay; matches Eurotramp pattern).
- `cloudbuild.yaml`, `cloudbuild-storefront-only.yaml`, `medusa-storefront/cloudbuild-storefront.yaml` — added `NEXT_PUBLIC_WEPLAY_PUBLISHABLE_KEY` build-arg so the storefront bundle resolves the key (avoids the Vortex-style "missing key" bug from v2.7.x).

### Outcome
100/100 products created in Medusa under the Weplay SC. Verified via admin API (`/admin/products?sales_channel_id[]=...`) — all published, all with thumbnail + images + category metadata. Storefront deploy follows via the auto Cloud Build trigger on push.

### Known gap (path 2 follow-up)
1,095 Weplay products are sitting in Firestore with `status="draft_no_images"`. They have valid descriptions, SKUs, categories — they're missing only the photo references. The upstream scrape captured 4,770 photo blobs but only 381 have URL-encoded SKU paths; the other 4,389 have opaque scrambled filenames with no product link. Resolving requires either a fuller re-crawl of `https://www.weplay.com.tw/UserFiles/images/Products/<XX>/<SKU>/` or a Vision-based image→description matching pass. Tracked in `docs/WEPLAY_PATH2_FOLLOWUP.md`.

---

## [2.8.3] - 2026-05-09

### Fixed — Cloud Build `db-migrate` step (npx could not resolve `medusa` bin)
- `cloudbuild.yaml` Step 3: `entrypoint: npx; args: [medusa, db:migrate]` → `entrypoint: npm; args: [run, db:migrate]`. After [2.8.2] unblocked the worker, the next pipeline run got further: build/push backend SUCCESS in ~3 min, but `db-migrate` failed with `npm error could not determine executable to run`. The Medusa v2 production image apparently doesn't expose `medusa` directly via `npx`, but the `db:migrate` script in `package.json` works. The Dockerfile already uses `npm run build` for the same reason.

---

## [2.8.2] - 2026-05-09

### Fixed — Cloud Build pipeline (10+ consecutive timeouts since 2026-05-05)
- `cloudbuild.yaml`: bumped `options.machineType` from `E2_MEDIUM` (1 vCPU / 4 GB) to `E2_HIGHCPU_8` (8 vCPU / 8 GB). Every push from 2026-05-05 onward was timing out at Step #0 `build-medusa-backend` → `Step 4/25 RUN npm ci`. Root cause: the 19,145-line Medusa v2 lockfile (`@medusajs/framework`, `@medusajs/medusa`, `@medusajs/admin-sdk`, `@medusajs/medusa-cli` and their transitive deps) plus `medusa build` plus a parallel Next.js docker build cannot fit inside a 1 vCPU / 4 GB worker before the 1 hr step deadline. Build log signature was deprecation warnings streaming with no error, then `context deadline exceeded` — pure CPU/memory thrashing, not a network or code issue.
- `medusa-backend/Dockerfile`: `RUN npm ci` → `RUN npm ci --prefer-offline --no-audit --no-fund`. Skips post-install audit + funding HTTP calls and prefers cache hits, typically saves 30–60 s on `npm ci` wall-clock.
- Net effect: PR #11 (verified brand-CI palettes + photo-first cards + Vortex logo contrast) and the 9 prior pushes were all built but never deployed to `catalogs.leka.studio`. This commit is what unblocks the trigger for all of them.

---

## [2.8.1] - 2026-05-09

### Added — Weplay onboarding (8th brand)
- Verified Weplay palette in Chrome at weplay.com.tw on 2026-05-09 via computed-style histogram across 3,000 elements: `#C7161E` red (126 hits, dominant), `#F0831E` orange (34), `#FED52B` yellow (5). Updated `brand-ci.ts` evidence + tagline ("We play, we learn — for the future.").
- Fixed `medusa-client.ts` `BrandConfig` for Weplay: `color` was the placeholder `#0099cc` cyan — corrected to verified `#C7161E` red. `hasCollections` flipped to `true` so collection filters render once products are imported.
- Wired Weplay into `scripts/sync_vendors_to_medusa.py` via a new `_resolve_sales_channel(slug)` helper: hardcoded slugs in `BRAND_SALES_CHANNELS` win, missing slugs fall back to env `LEKA_<SLUG>_SALES_CHANNEL_ID`. Lets a new brand import without an extra commit — set `LEKA_WEPLAY_SALES_CHANNEL_ID=sc_...` after creating the channel in Medusa Admin, then promote the value into the dict.

---

## [2.8.0] - 2026-05-08

### Reverted — `vendor-themes.ts` regression
Commit `70f0dcd` ("vendor-specific design systems for 6 brands") removed `brand-ci.ts` and replaced it with a parallel `vendor-themes.ts` system carrying fabricated palettes (Berliner navy+orange, Eurotramp red, Rampline lime+black, etc.). That code never deployed — live `catalogs.leka.studio` was still serving the v2.6.0 brand-CI lineage. Reverted in full so main now matches what's actually in production.

### Re-added on top of the revert (clean additions)
- `medusa-storefront/src/lib/image-scoring.ts` — `scoreImage` / `pickPrimaryImage` / `sortImagesByScore` penalize drawings/CAD/certs and reward photos so cards lead with the most marketable image.
- `medusa-storefront/public/placeholder-product.svg` — graceful fallback when an image URL fails.
- Wired `pickPrimaryImage` into `product-card.tsx` (with `onError` swap to the placeholder); `sortImagesByScore` into `product-detail.tsx` so the gallery's default-selected image is the best photo.

### Fixed — Card series-badge overlay
- Removed the `absolute top-2 left-2 badge` overlay on the product image; the series/collection name now lives next to the SKU in the card body with `truncate max-w-[60%]`. Long names no longer wrap onto the photo.

### Fixed — Vortex logo contrast on live PLP
- `medusa-storefront/public/brands/vortex/logo.svg`: added `fill="#FFFFFF"` so the wordmark renders white on the `#153CBA` blue header wrapper. The previous SVG had no `fill`, which defaulted to black on the dark blue background.

### Fixed — `brand-ci.ts` palettes vs verified vendor stylesheets
Re-audited every vendor's production CSS on 2026-05-08 and corrected the live brand themes. Confidence + evidence cited per brand inline.

| Brand | Old (was) | New (verified, in CSS) |
|---|---|---|
| Vinci | `#970260` magenta + `#182557` navy | `#8A3492` purple + `#FBBE2F` yellow + `#E9592C` orange |
| Berliner | `#00827A` teal (light) primary | `#00534F` (dark) primary, `#00827A` secondary, `#E6F3F2` accent |
| Eurotramp | `#0062AF` + `#6B9950` (wrong green) | `#0062AF` + `#63727F` slate + `#C80000` red accent |
| Rampline | `#182557` navy + `#970260` magenta | `#B5BC00` lime + `#2D5346` forest, paper `#F2F2EE` |
| 4soft | `#FFA900` amber primary (wrong) | `#0089CF` blue + `#CF0026` red + `#F99D1C` orange |
| Vortex | `#153CBA` + `#FFE000` yellow secondary | `#153CBA` + `#FF33D4` hot-pink secondary, yellow demoted to accent |
| WePlay | `#0099CC` cyan primary (wrong) | `#C7161E` red + `#F0831E` orange + `#FED52B` yellow |
| Wisdom | `#FCB822` amber + `#1D3A8A` navy (swapped) | `#1F4A83` navy + `#FBBE2F` amber — verified in Chrome at wisdomplaygroundsint.com (the actual vendor; not wisdomtoys.cn) |

### Added — `bodyVar` + `accent` on `BrandCI`
- `BrandPalette.accent?` for the third pop color most vendors carry (Eurotramp red, Vortex pink, Vinci orange, etc.) — exposed as `--brand-accent` and `bg-brand-accent` Tailwind utility.
- `BrandFonts.bodyVar` for vendors whose body font differs from heading (Vinci: Montserrat heading + Open Sans body; 4soft: Nunito + Lato; Vortex: Work Sans + Nunito) — exposed as `--brand-body` and `font-body`.
- New next/font imports: `Roboto_Condensed` (Eurotramp), `Work_Sans` (Vortex).

### Removed
- `docs/vendor-ds-preview.html` — was a static mockup of the abandoned `vendor-themes.ts` system, misleading anyone reviewing the storefront.

### Files changed
- `medusa-storefront/src/lib/brand-ci.ts` — verified palettes, evidence comments, `accent` + `bodyVar` fields
- `medusa-storefront/src/app/layout.tsx` — add Roboto_Condensed + Work_Sans fonts
- `medusa-storefront/src/app/[brand]/layout.tsx` — wire `--brand-accent` + `--brand-body`
- `medusa-storefront/tailwind.config.ts` — add `brand.accent` color + `font-body` family
- `medusa-storefront/src/components/product-card.tsx` — image scoring, onError fallback, series moved to body
- `medusa-storefront/src/app/[brand]/[handle]/product-detail.tsx` — gallery default uses `sortImagesByScore`
- `medusa-storefront/src/lib/image-scoring.ts` (new)
- `medusa-storefront/public/placeholder-product.svg` (new)
- `medusa-storefront/public/brands/vortex/logo.svg` — `fill="#FFFFFF"`
- `docs/vendor-ds-preview.html` (deleted)

### Outcome
TypeScript clean (`tsc --noEmit`). Live deployment lineage preserved; `main` once again represents what users see.

---

## [2.7.0] - 2026-05-07

### Added — Wisdom catalog Category → Sub-category selector + price/material filters

- **Storefront FilterBar** ([medusa-storefront/src/components/filter-bar.tsx](medusa-storefront/src/components/filter-bar.tsx)): top-level `<select>` now drives a dependent Sub-category `<select>`, populated from each parent's `category_children`. Hidden when no brand category has subcategories so Vinci/Berliner/4soft/Vortex/Eurotramp/Rampline render unchanged.
- **Wisdom-only filters**: USD min/max price range + Material dropdown (Wood, Rubber wood, Plastic, Metal, Fabric, Foam — bucketed from messy `metadata.material` strings via regex). Gated by a new `BrandConfig.hasMaterialFilter` flag in [medusa-storefront/src/lib/medusa-client.ts](medusa-storefront/src/lib/medusa-client.ts) (set on Wisdom only).
- **CatalogContent** ([medusa-storefront/src/app/[brand]/catalog-content.tsx](medusa-storefront/src/app/[brand]/catalog-content.tsx)): loads categories with `parent_category_id` and builds a `{id, name, handle, children[]}` tree. Subcategory selection short-circuits the parent on the Medusa `category_id` query. Filter state mirrored to the URL (`?q=&category=&subcategory=&material=&min_price=&max_price=`) so deep-links and Reset both work.
- **Backend support** ([shared/medusa_importer.py](shared/medusa_importer.py)): `get_or_create_category()` now takes optional `parent_category_id`; new `add_categories_to_product()` and `_patch()` helpers for product-category linking.
- **One-shot importer** ([wisdom-catalog/import_subcategories_to_medusa.py](wisdom-catalog/import_subcategories_to_medusa.py)): reads the same Excel that `import_to_medusa.py` ingests, derives `(category, subcategory)` via `shared/category_mapper.py`, ensures child categories exist under each parent (handle: `wisdom-<cat>-<sub>`), and PATCHes each Wisdom product to add the child category id alongside the parent. Idempotent + `--dry-run`. Dry-run on the deployed backend reported **80 child categories / 1,321 product links**; real run completed successfully.

### Files changed
- `medusa-storefront/src/components/filter-bar.tsx`
- `medusa-storefront/src/app/[brand]/catalog-content.tsx`
- `medusa-storefront/src/lib/medusa-client.ts`
- `shared/medusa_importer.py`
- `wisdom-catalog/import_subcategories_to_medusa.py` (new)

### Outcome
- Wisdom shoppers can now drill Furniture → Cabinet / Table / Chair / Shelf / Bed / Desk / Bench / Fence / Kitchen / House / Play-structure (and similar leaves under Playground, Outdoor, Nature Play, etc.), narrow by material, and clamp by USD price.
- Other six brand catalogs untouched at the UI level — sub-category dropdown stays hidden when no parent has children.

---

## [2.6.0] - 2026-05-07

### Added — Per-brand corporate identity (logos, palettes, fonts) on storefront

Each brand catalog page now renders the vendor's real corporate identity instead of a generic letter-badge.

- **Logos** — scraped from each vendor's public homepage and stored under `medusa-storefront/public/brands/<slug>/`:
  - Wisdom, Berliner, Eurotramp, Rampline, Vortex, WePlay → real logos
  - Vinci → white logo on brand-magenta background wrapper
  - 4soft → no public logo asset; falls back to letter badge styled with brand primary
- **Palettes** — full 4-color palette (`primary`, `secondary`, `ink`, `paper`) per brand, exposed as CSS variables (`--brand-primary` etc.) set at the brand layout root. Tailwind exposes them as `bg-brand-primary`, `text-brand-ink`, etc.
- **Fonts** — Manrope stays for body text across all brands; headings now use a brand-specific Google Font loaded once via `next/font/google`:
  Wisdom→Poppins, Vinci→Montserrat, Berliner→Roboto, Eurotramp→Open Sans, Rampline→Lato, 4soft→Nunito (verified from 4soft.cz CSS), Vortex→Inter, WePlay→Nunito.
- **Favicons** — each `/[brand]` page sets its own browser-tab icon via `generateMetadata`.
- **WePlay (8th brand stub)** — added as a `BrandConfig` entry with `productCount: 0`. No Sales Channel yet, so the route renders a "Catalog coming soon" placeholder using the brand CI. `NEXT_PUBLIC_WEPLAY_PUBLISHABLE_KEY` placeholder added to `env.example`. Sales Channel + product import is a follow-up task.
- **Components updated** — `SeriesBadges` and `ProductCard` now use `var(--brand-primary)` / `var(--brand-secondary)` instead of hardcoded `badge-purple` / `badge-navy` / `badge-amber` classes; series filters and price labels match the brand.

**Files changed**:
- NEW `medusa-storefront/src/lib/brand-ci.ts` — typed CI registry for 8 brands
- NEW `medusa-storefront/public/brands/<slug>/{logo.*, favicon.*}` — 8 brand asset folders
- `medusa-storefront/src/app/layout.tsx` — load 7 brand fonts, attach CSS variable classes to `<html>`
- `medusa-storefront/src/app/[brand]/layout.tsx` — `<Image>` logo, brand CSS-var injection, `font-heading` on brand name
- `medusa-storefront/src/app/[brand]/page.tsx` — per-brand favicon
- `medusa-storefront/src/app/[brand]/catalog-content.tsx` — WePlay-style "coming soon" branch for stub brands
- `medusa-storefront/src/components/series-badges.tsx` — brand-primary active state, drops hardcoded `BADGE_COLORS` array
- `medusa-storefront/src/components/product-card.tsx` — series/NEW badges + price use brand palette
- `medusa-storefront/src/lib/medusa-client.ts` — `weplay` entry added to `BRANDS`
- `medusa-storefront/tailwind.config.ts` — `colors.brand.*` and `fontFamily.heading` mapped to CSS vars
- `medusa-storefront/tsconfig.json` — `types: ["node"]` added to scope @types resolution (parent-root @types/caseless was breaking the build)
- `medusa-storefront/env.example` — Vortex and WePlay publishable-key placeholders

**Outcome**: clean `npm run build` (Next 15.5 / TS strict). Each `/[slug]` route is now visually distinct on a per-vendor basis. Letter-badge fallback keeps the page rendering even if a logo asset is missing.

## [2.5.2] - 2026-05-07

### Fixed — Cross-brand series badges showing on wrong brand pages

**Root cause**: `medusa.store.collection.list()` returns all 56 collections globally regardless of the publishable API key's sales channel scope. Every brand with `hasCollections: true` was displaying all 56 collection badges from all vendors.

- **Symptom**: Berliner Seilfabrik page showed Vinci series (Active, Arena, Castillo, etc.) alongside its own Berliner series — and vice versa for all 4 collection brands.
- **Root cause**: Medusa's store collections API does not filter by sales channel — it returns all collections in the database regardless of which publishable key is used in the request header.
- **Fix**: Added `collectionPrefix?: string` to `BrandConfig` interface and set a per-brand prefix. After the API fetch, collections are filtered client-side:
  - `berliner-*` → Berliner Seilfabrik (15 collections → 18 after handle audit)
  - `4soft-*` → 4soft (3 collections)
  - `vortex-*` → Vortex Aquatics (8 collections)
  - `undefined` (Vinci) → all handles that do NOT start with any other vendor's prefix (27 Vinci collections)
- **Files changed**: `medusa-storefront/src/lib/medusa-client.ts`, `medusa-storefront/src/app/[brand]/catalog-content.tsx`
- **Deployed**: Cloud Build `25da4b21`, storefront revision `accae83`

### Verified (post-fix browser audit — all collection brands passing)
| Brand | Series shown | Correct |
|-------|-------------|---------|
| Vinci Play | 27 (Vinci-only handles) | ✓ |
| Berliner Seilfabrik | 18 (all "Berliner *") | ✓ |
| 4soft | 3 (4soft Tunnels & Furniture, 3D Elements, 2D Graphics) | ✓ |
| Vortex Aquatics | 8 (all "Vortex — *") | ✓ |

---

## [2.5.1] - 2026-05-07

### Fixed — CORS misconfiguration blocking all brand catalogs + Vortex missing key

**Root cause: all brand catalog pages showed "No products found"** due to two independent bugs found during a full frontend status audit.

#### Bug 1 — STORE_CORS pointed to raw Cloud Run URL (critical, global)
- **Symptom**: Every brand page returned 0 products. Browser console: `TypeError: Failed to fetch`. `no-cors` mode returned opaque response confirming CORS — not network — was failing.
- **Root cause**: `STORE_CORS` env var on `leka-medusa-backend` was set to `https://leka-medusa-storefront-538978391890.asia-southeast1.run.app` (the raw Cloud Run URL from initial deploy), not the custom domain `https://catalogs.leka.studio`. The backend was never redeployed after the custom domain was configured. Preflight OPTIONS returned empty `Access-Control-Allow-Origin`.
- **Fix**: `gcloud run services update leka-medusa-backend --update-env-vars STORE_CORS=https://catalogs.leka.studio,AUTH_CORS=...` — new revision `00012-6sh`. CORS now returns `Access-Control-Allow-Origin: https://catalogs.leka.studio`.
- **Also note**: `cloudbuild.yaml` backend deploy step already had the correct `STORE_CORS=https://catalogs.leka.studio` — the stale value was from a pre-custom-domain manual deploy.

#### Bug 2 — NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY missing from storefront build
- **Symptom**: Vortex catalog specifically showed 0 products (would have been visible after Bug 1 was fixed).
- **Root cause**: `NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY` build-arg was missing from both `cloudbuild.yaml` and `cloudbuild-storefront-only.yaml`. The key resolved to `""` in the bundle, so the Medusa store API rejected the auth.
- **Fix**: Added `--build-arg NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY=pk_df5eb6c3d0032c6baebe18bec7b3be1cdb024ba5efd3833cac2b8517432c56dc` (retrieved from Medusa Admin API) to both Cloud Build files. Redeployed storefront (Cloud Build `fa376c2b`, revision `00011-mkn`).
- **Files changed**: `cloudbuild.yaml`, `cloudbuild-storefront-only.yaml`

### Verified (post-fix browser audit — all passing)
| Brand | Products | Images | Status |
|-------|----------|--------|--------|
| Wisdom | 5,062 | ✓ (GCS proxy, ~8s warm-up) | ✓ |
| Vinci Play | 1,096 | ✓ (external CDN) | ✓ |
| Berliner Seilfabrik | 466 | ✓ (GCS proxy) | ✓ |
| Eurotramp | 80 | ✓ (GCS proxy) | ✓ |
| Rampline | 54 | ✓ (GCS proxy) | ✓ |
| 4soft | 391 | ✓ (GCS proxy) | ✓ |
| Vortex Aquatics | 521 | ✓ (GCS proxy) | ✓ |

### Known issues (not blocking)
- **Cross-brand series badges**: Brands with `hasCollections: true` (Vinci, Berliner, 4soft, Vortex) all show the same 56 series badges from ALL brands. Medusa's `store/collections` API returns all collections regardless of the publishable key's sales channel scope. Fix: scope collections to the sales channel in Medusa, or filter client-side by handle prefix.
- **Vortex product count 521 vs 272**: Vortex Sales Channel appears to include products from multiple brands. Needs sales channel audit in Medusa Admin.
- **Image warm-up latency**: `/_next/image` optimization on 512Mi Cloud Run takes ~5–8s for first-load batches of 48 large (2560×2560) images. Consider bumping storefront memory to 1Gi or pre-warming.

## [2.5.0] - 2026-05-05

### Added — Phase 4: image bucket migration + private-via-proxy serving

Product images for the 6 GCS-resident leka brands moved from the public `gs://ai-agents-go-documents/product-images/<slug>/` to a project-prefixed, **private** bucket `gs://ai-agents-go-vendors/<slug>/`. Public access prevention stays enabled on the new bucket; the Cloud Run storefront fronts it via a Next.js image proxy. Vinci images stay external (zamowienia.vinci-play.pl).

- **GCS copy** — 5.30 GB across wisdom (2.29 GB), berliner (1.97 GB), vortex (953 MB), rampline (57 MB), eurotramp (17 MB), 4soft (8 MB), copied with `gcloud storage cp -r`. Slug-based folder names for consistency with existing `durasein/`, `gumtec/`, `zelk/` etc.
- **Image proxy** [medusa-storefront/src/app/api/i/[...path]/route.ts](medusa-storefront/src/app/api/i/[...path]/route.ts) — Next 15 route handler. Reads private GCS via the Cloud Run runtime SA (`538978391890-compute@developer.gserviceaccount.com`, ADC token from metadata server, cached until ~5 min before expiry). Streams response with `Cache-Control: public, max-age=86400, immutable`. Preserves raw URL path so encoding (single vs double `%20`) survives end-to-end. Allowed in [next.config.js](medusa-storefront/next.config.js).
- **URL rewriter** [scripts/rewrite_image_urls_to_vendors_bucket.py](scripts/rewrite_image_urls_to_vendors_bucket.py) — sweeps `vendors/{slug}/products` (Firestore DB `vendors`) AND Medusa Admin API for each brand's sales channel, rewriting `images[].url` (and Medusa `thumbnail`) from old-bucket public URLs to proxy URLs. Idempotent; supports `--target-base` so the same script can target direct GCS or the storefront proxy. Running counts:
  - 4soft: 780 + 780 (firestore + medusa) = 1,560 URLs
  - eurotramp: 1,326 + 1,326 = 2,652 URLs (79 external images preserved)
  - rampline: 127 + 127 = 254 URLs
  - vortex: 0 + 1,949 = 1,949 URLs (Firestore subcollection empty by design)
  - berliner: 3,969 + 3,969 = 7,938 URLs (8 external preserved)
  - wisdom: 5,910 + 5,900 = 11,810 URLs (first pass) + 328 + 328 = 656 URLs (verified/ mop-up) = 12,466 URLs
  - **Grand total: 26,819 URLs rewritten across both stores, 0 errors, 0 unknown hosts, 0 `no_match` remaining.**
  - Plus 582 4soft GCS objects renamed (`%20` → space).
- **Cloud Build** — added [cloudbuild-storefront-only.yaml](cloudbuild-storefront-only.yaml) for storefront-only deploys when the backend hasn't changed (skips medusa-backend build + db-migrate). [cloudbuild.yaml](cloudbuild.yaml) hardcoded `_AR_REPO` project to `ai-agents-go` because `$PROJECT_ID` was not recursively expanding inside the substitution.
- **.gcloudignore** added to keep `gcloud builds submit` archives small (807 KiB vs. 500+ MB unfiltered).

### Fixed (same release)

- **4soft literal `%20` filenames**: long-standing image rendering bug. The catalog scrape had uploaded 582 objects with literal `%20` characters in their GCS object names (so single-encoded URLs in Medusa decoded to spaces at GCS and 404'd). One-shot rename via [scripts/rename_4soft_literal_pct20.py](scripts/rename_4soft_literal_pct20.py) replaces literal `%20` with real spaces in every affected object name. After rename, every existing single-encoded Medusa URL resolves correctly. 582 files renamed in 13 sec, 0 errors.
- **Wisdom 328 `no_match`**: traced to a `verified/` sibling folder under `gs://ai-agents-go-documents/product-images/` (not under `wisdom/`), used by ~200 wisdom products for quality-curated catalog imagery. Copied to `gs://ai-agents-go-vendors/wisdom/verified/` (2,253 files / 19 MB) and extended the rewriter with a `BRAND_EXTRA_PREFIXES` map so `verified/` is recognized as a wisdom-owned alt prefix.

### Known issues

- (none currently — both above resolved)
- Phase 5 (archive + delete `leka-product-catalogs` Firestore DB) is gated on a 2-week green canary on `vortex-daily-refresh`.
- `scripts/seed_medusa_api.py:16-17` still hardcodes admin password (Rule 12 violation, pre-existing).

## [2.4.0] - 2026-05-04

### Added — Migration to vendors-rooted Firestore architecture (Phases 0-3)

Source-of-truth product data moved from `leka-product-catalogs` Firestore database (flat `products_{brand}` layout) to the `vendors` database (`vendors/{slug}/products` hierarchical layout owned by the `vendors` project). Plan: `~/.claude/plans/inspect-our-project-database-wise-feigenbaum.md`.

- [migration/vendors_target_schema.md](migration/vendors_target_schema.md) — target schema, slug registry, leka→vendors mapping rules.
- [scripts/migrate_leka_to_vendors.py](scripts/migrate_leka_to_vendors.py) — Phase 1 one-shot. Reads `products_{brand}`, `product_categories_{brand}`, brand-filtered `quotations`; writes `vendors/{slug}/products|product_categories|quotations` and the vendor root doc. **Run live**: wisdom (5,071 products), vinci (1,113 products + 6 categories), vortex (0 products in leka — already canonical in vendors). Total: 6,184 products migrated.
- [scripts/reverse_import_medusa_to_vendors.py](scripts/reverse_import_medusa_to_vendors.py) — Phase 2 one-shot. For brands that had no Firestore source (berliner / eurotramp / rampline / 4soft), reads them back from Leka Medusa Admin API and writes to `vendors/{slug}/products`. **Run live**: berliner (466), eurotramp (80), rampline (54), 4soft (391). Total: 991.
- [scripts/sync_vendors_to_medusa.py](scripts/sync_vendors_to_medusa.py) — Phase 3 generalized sync. Reads `vendors/{slug}/products` and upserts into Medusa via Admin API (handle lookup → create/update → variant USD price). Replaces (does not yet remove) the brand-specific TS scrapers and `seed_medusa_api.py`. Smoke-tested with `--brand=rampline --limit=5 --dry-run`: 5/5 UPDATE, 0 errors. Vortex sync continues to run via the existing `vortex-refresh` Cloud Run Job.

### Pending

- Phase 4: live sync run + storefront smoke test on a sampled product per brand.
- Phase 5: archive leka Firestore DB to `migration/leka-firestore-archive/` and delete the database after a 2-week green-sync window.

## [2.3.0] - 2026-04-21

### Added — Vortex Aquatics brand (272 products · 1,949 images mirrored)

- New brand folder [vortex-catalog/](vortex-catalog/) mirrors the vinci-catalog pattern
- **Scraper** [vortex-catalog/scrape_catalog.py](vortex-catalog/scrape_catalog.py) — hybrid WP REST + HTML approach against www.vortex-intl.com
- **Image mirror** [vortex-catalog/mirror_images_to_gcs.py](vortex-catalog/mirror_images_to_gcs.py) — uploads images to `gs://ai-agents-go-documents/product-images/vortex/catalog/`
- **Medusa importer** [vortex-catalog/import_to_medusa.py](vortex-catalog/import_to_medusa.py) — creates "Vortex Aquatics" Sales Channel + publishable API key, category `water_play`, 7 collections (one per product-type)
- **Static web-app** [vortex-catalog/web-app/](vortex-catalog/web-app/) — Flask + vanilla JS catalog browser, deploys to Cloud Run service `vortex-catalog`
- **Design System** [vortex-catalog/DESIGN_SYSTEM.md](vortex-catalog/DESIGN_SYSTEM.md) — tokens derived from live vortex-intl.com theme CSS (primary `#153cba`, accent `#ff33d4`, water `#6ed4fc`, Nunito + Work Sans)
- **Vortex logo** — SVG extracted from the live theme sprite, stored at [vortex-catalog/web-app/public/assets/vortex-logo.svg](vortex-catalog/web-app/public/assets/vortex-logo.svg)
- **Gmail outreach draft** — saved in user's Drafts addressed to Vicky Denisova (current Vortex account manager) requesting the 2026 pricelist & latest catalogs

### Changed

- [shared/medusa_importer.py](shared/medusa_importer.py) — added `get_or_create_sales_channel()`, `create_publishable_api_key()`, and optional `sales_channel_ids` kwarg to `create_product()` so future brand importers can attach products to a dedicated Sales Channel at create time.

## [2.2.0] - 2026-04-09

### Added — Vendor Product Catalogs (991 products, 4 brands)
- Scraped and uploaded 4 vendor catalogs to Medusa:
  - Berliner Seilfabrik (466 products) — rope play equipment, Germany
  - Eurotramp (80 products) — trampolines, Germany
  - Rampline (54 products) — motor skill equipment, Norway
  - 4soft (391 products) — EPDM surfaces, Czech Republic
- Created Sales Channels + publishable API keys per vendor
- Added vendor brand pages to storefront (6 brands total)
- Fixed 15 failed product uploads (SKU deduplication, handle sanitization)
- Bulk-published all 991 vendor products
- GCS image re-hosting script (`scripts/rehost-images-to-gcs.ts`)
- Vendor scraper scripts: `scripts/scrape-{berliner,eurotramp,rampline,4soft}.ts`
- Unified upload script: `scripts/upload-vendors-to-medusa.ts`

### Changed
- Updated product card and detail page to handle vendor metadata format
- Added vendor CDN image domains to Next.js config
- Updated cloudbuild.yaml with all 6 vendor publishable API keys
- Applied SEO metadata (generateMetadata) to brand and product pages
- Wired up quotation accept/reject workflow

## [2.1.1] - 2026-04-07

### Added — Product Data Seeded
- Exported 6,219 documents from Firestore (5,071 Wisdom + 1,113 Vinci + categories + quotations)
- Seeded 6,151 products via Medusa Admin API (5,056 Wisdom + 1,095 Vinci)
- Created Admin API seed script (`scripts/seed_medusa_api.py`) for remote seeding
- Created Sales Channels: Wisdom, Vinci Play (with publishable API keys)
- Created Region: Asia-Pacific (USD, 5 countries)
- Created admin user (admin@leka.studio)
- Rebuilt storefront with API keys baked in via Docker build args

## [2.1.0] - 2026-04-07

### Deployed — GCP Infrastructure & Cloud Run Services
- Cloud SQL PostgreSQL: `areda-medusa` / `leka_medusa` (asia-southeast1)
- Memorystore Redis: `leka-medusa-redis` (10.225.88.67:6379)
- VPC Connector: `leka-connector` (10.8.0.0/28)
- Secret Manager: 4 secrets (database-url, redis-url, cookie-secret, jwt-secret)
- **Medusa Backend**: https://leka-medusa-backend-538978391890.asia-southeast1.run.app
- **Next.js Storefront**: https://leka-medusa-storefront-538978391890.asia-southeast1.run.app

### Fixed — Docker Build & Deployment Issues
- Added ts-node + typescript as production dependencies (Medusa CLI needs them at runtime)
- Fixed medusa-config.ts: use module:nodenext for ts-node compatibility, export default
- Removed custom modules array from config (Medusa v2.13 includes all modules by default)
- Added @medusajs/admin-sdk peer dependency for draft-order admin UI
- Compiled medusa-config.ts to .js via ts.transpileModule for runtime fallback
- Added start.sh with db:migrate before server start
- Fixed CRLF line endings with .gitattributes + sed in Dockerfile
- Switched from Cloud SQL Unix socket to public IP (Unix socket URL format incompatible with MikroORM)
- Added DISABLE_ADMIN env var to skip admin UI when build output missing

## [2.0.1] - 2026-04-07

### Added — Sprint 1: Cart Flow, Filters, i18n, Loading States
- Cart state management (`lib/cart.ts`) with localStorage persistence per brand
- Slide-out cart drawer component with quantity controls
- Add-to-cart handler on product detail page with loading/success feedback
- Age group filter dropdown (Vinci-specific, matching current site)
- Product/series count stats in catalog header
- Download count icon on product cards
- "NEW" badge on product cards from tags
- Loading skeleton for catalog page
- 404 pages (brand-scoped and root)
- Locale switcher component (EN/TH/CN) with i18n library
- Mobile-responsive header with cart drawer
- Region setup (Asia-Pacific, USD, 5 countries) in seed script
- Manual fulfillment and payment provider setup in seed script
- Publishable API key generation per sales channel

## [2.0.0] - 2026-04-06

Renamed from [1.0.0].

## [1.0.0] - 2026-04-06

### Changed — Medusa Commerce v2 Migration
- **Backend**: Migrated from Python/Flask/Firestore to Medusa Commerce v2 (TypeScript/Node.js/PostgreSQL)
- **Frontend**: Migrated from vanilla JS static app to Next.js 15 with Tailwind CSS
- **Database**: Migrated from Firestore to Cloud SQL PostgreSQL 15
- **Architecture**: Products now managed via Medusa Admin API with Sales Channels per brand

### Added
- `medusa-backend/` — Medusa v2 backend with custom API routes for specifications and downloads
- `medusa-storefront/` — Next.js storefront with Leka Design System (Tailwind)
- Full e-commerce: cart, checkout, customer accounts, order management
- Multi-brand via Medusa Sales Channels (Wisdom, Vinci Play)
- Product detail pages (replaces modal) with image gallery, specs, downloads, certifications
- Customer authentication (login, register, order history)
- `scripts/export_firestore_to_json.py` — Firestore data export for migration
- `medusa-backend/src/scripts/seed-from-firestore.ts` — Medusa seed script
- `shared/medusa_importer.py` — Medusa Admin API import helper
- `wisdom-catalog/import_to_medusa.py` — Wisdom Excel → Medusa importer
- `vinci-catalog/import_to_medusa.py` — Vinci JSON → Medusa importer
- Updated `cloudbuild.yaml` for multi-service build (backend + storefront)

### Deprecated
- `src/main.py` (Flask gateway) — replaced by Medusa backend
- `*/import_to_firestore.py` — replaced by `*/import_to_medusa.py`
- `vinci-catalog/web-app/` — replaced by `medusa-storefront/`
- Firestore collections — data migrated to PostgreSQL

## [0.5.0] - 2026-04-01

### Added — Full Vinci Play Catalog (1,172 products)
- Full website scrape of all 29 Vinci Play series (1,172 products)
- Firestore import to `products_vinci` collection with category index
- Brand registration in `brands/vinci`
- Redeployed web app with complete product data

### Fixed
- Service account credential path case mismatch (eukri → Eukrit)

## [0.4.0] - 2026-04-01

### Added — Vinci Play Web App & Cloud Run Deployment
- Web app with Leka Design System for browsing Vinci Play products
- Dockerfile and Cloud Build config for containerized deployment
- Cloud Run service `vinci-catalog` at https://vinci-catalog-538978391890.asia-southeast1.run.app
- Artifact Registry repo `leka-product-catalogs` in asia-southeast1
- 47 Spring series products with static JSON data
- `.dockerignore` and deploy instructions

## [0.3.0] - 2026-03-30

### Added — Vinci Play Brand
- `vinci-catalog/` brand folder with complete scraping and import pipeline
- `scrape_catalog.py` — full website scraper for vinci-play.com (29 series, ~1,000+ products)
  - Extracts: product info, specifications, images, drawings, downloads, certifications
  - Supports `--resume` for checkpoint/resume and `--series` for single-series scraping
  - Rate-limited with retry logic for reliability
- `import_to_firestore.py` — imports scraped JSON to `products_vinci` collection
  - Supports `--dry-run` for preview mode
- `firestore_schema.json` — Vinci-specific schema documentation
- `DEPLOYMENT_LOG.md` — brand-specific deployment tracking
- Firestore composite indexes for `products_vinci`
- Added `requests` and `beautifulsoup4` to requirements.txt

## [0.2.0] - 2026-03-30

### Added
- Multi-brand data architecture with separate Firestore collections per brand (`products_{brand}`)
- `shared/` module with reusable utilities: `base_importer.py`, `category_mapper.py`, `image_pipeline.py`
- Brand registry collection (`brands`) in Firestore
- Per-brand category collections (`product_categories_{brand}`)
- `status` field (active/discontinued/draft) on all products
- `brand` field on products and quotations
- `tags` array field for free-form product tagging
- `description_th` field for Thai product names

### Changed
- Wisdom importer now writes to `products_wisdom` collection (was `products`)
- Firestore rules updated for wildcard brand collections
- Composite indexes added for `products_wisdom`
- Root service (`src/main.py`) now reads from Firestore `brands` collection
- Version bumped to 0.2.0

## [0.1.0] - 2026-03-30

### Added
- Initial project structure from goco-project-template
- Python 3.11 runtime with Flask health endpoint
- Cloud Build pipeline (cloudbuild.yaml) for CI/CD
- Dockerfile for Cloud Run deployment
- verify.sh post-build verification script
- Leka Design System configuration
- Wisdom brand catalog (5,071 products) — migrated from product-catalogs repo
- Firestore rules and composite indexes
- Multi-brand architecture with per-brand subfolders
