# Vortex Aquatics Catalog — Deployment Log

## v0.3.0 — 2026-06-08 (leka-product-catalogs v2.80.0)

### Fixed — "missing product images" investigation + 249 image-less SKUs unpublished

**Investigation finding (the bucket/URL data was already correct).** All 272
scraped Vortex products already had proxy image URLs
(`https://catalogs.leka.studio/api/i/vortex/catalog/<slug>/<file>`) that resolve
**200**; the blobs live in the proxy-served bucket `gs://ai-agents-go-vendors/vortex/`.
The reported "missing images" had **two distinct causes**:

1. **Storefront PDP query bug (272 products).** The PDP fetched the gallery with
   the bare `+images` field, which Medusa v2's **store** API returns as
   `images: null` — so the gallery was empty and showed the 📦 placeholder. Fixed
   in `eukrit/leka-website` (`product-detail.tsx` → `+images.url`,
   PR [#131](https://github.com/eukrit/leka-website/pull/131)). PLP cards were
   unaffected (they fall back to `thumbnail`).
2. **249 image-less pricelist/component SKUs.** The Vortex sales channel held 521
   products: the 272 scraped (with images + `source_url`) plus **249** bare
   `vortex-vor-XXXX` SKUs with no images, no collection, and poor/garbled titles
   (the "521 vs 272" discrepancy CHANGELOG flagged on day one). A website
   cross-check (against the WP REST products CPT — exhaustively the 272 scraped
   products) classified them: **9** duplicates of an existing imaged product, **0**
   standalone products missing from the catalog, **240** components/spares with no
   product page. None is a distinct product missing from the catalog, so all 249
   were **unpublished** (`status=draft`, reversible). Vortex catalog now: **272
   published, 0 without images; 249 draft.**

### Pricing / PDP link
- Vortex pricing **enabled** on the storefront (`hasPricing: true`); USD is the
  default display currency site-wide. 246/272 published products have a USD retail
  price (synced 2026-05-29); the USD region populates `calculated_price`.
- PDP → Vortex link already works: all 272 published products carry
  `metadata.source_url` = `vortex-intl.com/products/<slug>/` → "View on
  manufacturer website →". No change needed.

### Files added / changed (this repo)
- [vortex-catalog/crosscheck_bare_products.py](crosscheck_bare_products.py) (NEW) —
  website cross-check + unpublish (offline match to the 272 + optional live WP REST
  fallback; `--dry-run`). Auth: `admin@leka.studio` + Secret Manager
  `medusa-admin-password` (**v5** — note `:latest`/v6 is empty, see below).
- [vortex-catalog/bare_products_crosscheck.md](bare_products_crosscheck.md) /
  `.json` (NEW) — the flag report (per-SKU classification + best-effort match).
- [vortex-catalog/mirror_images_to_gcs.py](mirror_images_to_gcs.py) — now targets
  the proxy-served `ai-agents-go-vendors` bucket and writes proxy URLs (was the
  stale, never-served `ai-agents-go-documents` path).
- [vortex-catalog/import_to_medusa.py](import_to_medusa.py) — prefers the proxy
  URL and never emits a raw `storage.googleapis.com` private-bucket URL.

### ⚠️ Follow-up flag
- Secret Manager `medusa-admin-password` **`:latest` (v6, created 2026-06-08) is
  EMPTY** — only **v5** authenticates against `leka-medusa-backend`. Any consumer
  using `:latest` (scripts, next backend redeploy) will 401. Disable/fix v6.

## v0.2.0 — 2026-05-29 (leka-product-catalogs v2.38.0)

### Added — 2026 USD pricelist ingestion + per-product-line reseller discounts

Parsed the **Vortex 2026 USD Price List R2** (`2026-04-22 Vortex 2026_USD_Price
List_R2 (1).pdf`, released Feb 2026) — **311 SKUs / 22 collections** — into
`vendors/vortex/products` (vendors DB) with the shared landed-cost pipeline,
then synced multi-currency retail to Medusa.

**Trade terms (confirmed from `eukrit@goco.bz` Gmail "Pricelist 2026" thread):**
EXW Pointe-Claire, Quebec, **Canada**, USD. Non-China → 10% Thai import duty.

**Per-product-line reseller discounts (USD):** Splashpad 25% · Poolplay 15% ·
Spraypoint 25% · Elevations 15% · WQMS 15% · Water Journey 20% · Water Slides
15%. **CoolHub 0%** (user decision — not in the reseller agreement). SmartPoint
→ Splashpad 25%; PlayNuk → Elevations 15%. (Discount table cross-checked by OCR
of the image Vortex shared in-thread — exact match to the confirmed structure.)

**Pricing:** `our_cost_usd = list_usd × (1 − line_discount)` → flat-uplift CIF
(1.35) + 10% duty + 7% import VAT + Vinci tier clamp → landed THB. Independent
retail THB/USD/EUR/SGD; `gross_margin = 0.35`. `formula_version = vortex-v1-2026-05-29`.

### Files added / changed

- [vortex-catalog/vortex_config.py](vortex_config.py) (new) — canonical
  `LINE_DISCOUNTS`, `COLLECTION_TO_LINE` (22 collections), `GROSS_MARGIN`,
  origin/terms, `brand_config()`. Shared with `scripts/seed_pricing_config.py`.
- [vortex-catalog/import_pricelist.py](import_pricelist.py) (new) — pdfplumber
  parser → `price_vortex_row()` → `vendors/vortex/products`; deep-merges
  `brands.vortex` into `pricing_config/canonical`. `--dry-run`/`--apply`/`--dump-csv`.
- `scripts/sync_brand_prices_to_medusa.py` — `vortex` → SC `sc_01KPRY1T8HZJ57020JPZVGAKZK`.
- `scripts/seed_pricing_config.py` — `vortex` brand block (from `vortex_config`).
- `docs/summaries/pricing-config-master.md` — §4f, §6f, version history.

### Outcome

- Firestore `vendors/vortex/products`: **311** priced docs (splashpad 236,
  elevations 26, water_journey 25, coolhub 18, poolplay 6).
- Medusa: **295 / 311** variants updated (94.9% by `VOR-…` SKU; 0 errors). 16
  unmatched = stainless `VOR-…-304L` SmartPoint SKUs absent from Medusa. All
  four currencies (THB/USD/EUR/SGD) verified on synced variants.

**Note:** the formal reseller discount structure was requested from Vortex on
2026-05-29 (out-of-office reply until June 1); the percentages used here are
the user-confirmed structure (matching the image Eukrit shared in-thread).
Re-confirm with Vortex's written reply when received.

## v0.1.0 — 2026-04-21

### Added — initial brand scaffold

Added Vortex Aquatic Structures International (vortex-intl.com) as the third brand in `leka-product-catalogs`, alongside Wisdom and Vinci Play.

**Source:** www.vortex-intl.com (WordPress, theme `vortex`)
**Products:** 272 EN SKUs (confirmed via WP REST `X-WP-Total: 272`, `/wp-json/wp/v2/products?per_page=100`)
**Taxonomy:** 7 product-types — splashpad, waterslide, elevations-playnuk, playable-fountains, coolhub, dream-tunnel, water-management-solutions

### Files added

- [vortex-catalog/scrape_catalog.py](scrape_catalog.py) — Hybrid WP REST + HTML scraper. Uses `/wp-json/wp/v2/products` for bulk metadata (3 requests, 272 rows), then per-product HTML for descriptions/images/model codes. `Crawl-delay: 10` per robots.txt → ~45 min full run.
- [vortex-catalog/mirror_images_to_gcs.py](mirror_images_to_gcs.py) — Downloads scraped image URLs and uploads to `gs://ai-agents-go-documents/product-images/vortex/catalog/<slug>/<file>`. Idempotent (skips existing blobs). Writes `gcs_url` back into `products_all.json`.
- [vortex-catalog/import_to_medusa.py](import_to_medusa.py) — Medusa Admin API importer. Creates "Vortex Aquatics" Sales Channel + publishable API key, one collection per product-type, category `water_play`, then POST /admin/products × 272.
- [vortex-catalog/DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) — Derived Vortex tokens (colors, fonts, shape) extracted from `https://www.vortex-intl.com/wp-content/themes/vortex/dist/styles/main_4d2020b1.css`. Primary: `#153cba` (blue). Accent: `#ff33d4` (magenta). Water: `#6ed4fc`. Body font: Nunito. Heading font: Work Sans.
- [vortex-catalog/web-app/](web-app/) — Flask + static JSON viewer at Cloud Run service `vortex-catalog`.
  - `public/index.html`, `public/styles.css`, `public/app.js` — Vortex-tokened UI (not Leka's)
  - `public/assets/vortex-logo.svg` — Extracted from the live sprite `svg_map_68028944.svg`, symbol `#vortex-logo` (viewBox `0 0 192 41`)
  - `Dockerfile`, `cloudbuild.yaml`, `server.py` — mirror vinci-catalog pattern

### Files modified

- [shared/medusa_importer.py](../shared/medusa_importer.py) — Added `get_or_create_sales_channel()` + `create_publishable_api_key()` + `sales_channel_ids` kwarg on `create_product()`.

### External actions

- **Gmail draft created** (ID: `r6018115205171597500`) — Request to Vortex for 2026 pricelist & updated catalogs. To: vdenisova@vortex-intl.com (current account manager). CC: cezeta@vortex-intl.com, dlopez@vortex-intl.com. NOT SENT — user reviews in Gmail Drafts before sending.

### Scrape results (2026-04-21)

- Ran with `--skip-types --delay 10` → 272/272 products in 3433s (~57 min)
- 272/272 with name (100%)
- 272/272 with description (100%, extracted from `og:description`)
- 272/272 with at least one image (1,949 total images)
- 246/272 with Vortex model code (90%; e.g. `VOR-7281`)
- Specs parsing yielded 0 entries per product — Vortex public pages do not expose technical specs in HTML (likely gated behind the Resource Center). Non-blocking — specs can be enriched later from the pricelist/catalog once Vortex sends the 2026 PDFs.
- `product_types` left empty for this first pass — the WP listing pages at `/products/?product_types=<slug>` only returned 79/272 distinct slugs, so categorization will be done post-import via Medusa admin once products are loaded.
- Output: [web-app/public/data/products_all.json](web-app/public/data/products_all.json), [products_1.json](web-app/public/data/products_1.json), [families.json](web-app/public/data/families.json)

### Image mirror (2026-04-21) — complete

- Ran `python vortex-catalog/mirror_images_to_gcs.py` with GCS ADC from
  `Credentials Claude Code/ai-agents-go-0d28f3991b7b.json`
- Target: `gs://ai-agents-go-documents/product-images/vortex/catalog/<slug>/<filename>-<hash>.<ext>`
- **1,949/1,949 images mirrored · 0 failed · 7,649 s (~2h 7min)**
- `products_all.json` now carries both `images[].url` (original vortex-intl.com source) and `images[].gcs_url` (GCS public URL) for every image
- Example: `https://storage.googleapis.com/ai-agents-go-documents/product-images/vortex/catalog/deflex/2--vor-7281_deflex_pv2-68c1369f.png`

### Medusa import (2026-04-21) — complete

**272/272 products imported, 0 errors.**

- **Sales Channel**: `sc_01KPRY1T8HZJ57020JPZVGAKZK` · name "Vortex Aquatics"
- **Publishable API Key**: `apk_01KPRY4A8K6NCCDKAN91NFP4M9` · token `pk_df5eb6c3d0032c6baebe18bec7b3be1cdb024ba5efd3833cac2b8517432c56dc`
- **Category**: `pcat_01KNKVH8QGWEPES0FNZW3CT2VT` (`water_play`)
- **Collections** (one per product_type):
  - splashpad: `pcol_01KPRY1TK73RR8CHJ93BTGP5G3`
  - waterslide: `pcol_01KPRY1TQ64NGNE8WYXS7Z5SDC`
  - elevations-playnuk: `pcol_01KPRY1TV2ZYFQ6JSWQBJZX6AE`
  - playable-fountains: `pcol_01KPRY1TZ3YZ8PC8Y9EAVRRPRT`
  - coolhub: `pcol_01KPRY1V36S9RGVQNE72K1G06K`
  - dream-tunnel: `pcol_01KPRY1V78ZYEZ0AD5FX6VH2QF`
  - water-management-solutions: `pcol_01KPRY1VAZ9N7VNAY0JYDESHB3`
  - uncategorized: `pcol_01KPRY1VF4RSV2NTSBVMX1VHSQ` (initial landing; recategorize via admin)

### Auth setup

- GSM secret `medusa-admin-password` holds the Medusa admin password (value redacted — rotated 2026-06-06; fetch the current value with `gcloud secrets versions access latest --secret=medusa-admin-password --project=ai-agents-go`)
- `shared/medusa_importer.py` now uses Medusa v2 Bearer auth. If `MEDUSA_ADMIN_API_KEY` is empty, it falls back to `MEDUSA_ADMIN_EMAIL` + `MEDUSA_ADMIN_PASSWORD` and does `/auth/user/emailpass` auto-login.
- Re-run is idempotent: `batch_import()` skips products whose handle already exists.

### How to re-run

```powershell
$env:MEDUSA_BACKEND_URL = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
$pass = gcloud secrets versions access latest --secret=medusa-admin-password --project=ai-agents-go
$env:MEDUSA_ADMIN_EMAIL = "admin@leka.studio"
$env:MEDUSA_ADMIN_PASSWORD = $pass
python vortex-catalog/import_to_medusa.py
```

### Sales Channel (fill after import)

- ID: _TBD_ (record after `get_or_create_sales_channel` runs)
- Publishable API key: _TBD_
- Category: `water_play`
- Collection handles: `vortex-splashpad`, `vortex-waterslide`, `vortex-elevations-playnuk`, `vortex-playable-fountains`, `vortex-coolhub`, `vortex-dream-tunnel`, `vortex-water-management-solutions`, `vortex-uncategorized`

### Cloud Run service (deployed 2026-04-21)

- **URL: https://vortex-catalog-rg5gmtwrfa-as.a.run.app**
- Build ID: `fe0d65bd-2327-4708-a17c-de28a5a7b5b3` (SUCCESS, 1m55s)
- Artifact: `gcr.io/ai-agents-go/vortex-catalog:41f9755` (also tagged `:latest`)
- Region: asia-southeast1
- Commit deployed: `41f9755` (merge of PR #1)
- Health check: `GET /health` → `{"brand":"vortex","status":"ok"}`

### Note on trigger setup

The Vortex build was submitted manually because the root `leka-product-catalogs-deploy` Cloud Build trigger (us-central1, id `7cd91f80`) targets the root `cloudbuild.yaml` — which builds the original Medusa backend and currently fails on a pre-existing `$PROJECT_ID` substitution bug (failure IDs: `93b796f1` today and earlier). Fixing that trigger OR adding a dedicated `vortex-catalog-deploy` trigger pointing at `vortex-catalog/web-app/cloudbuild.yaml` is a follow-up task.
