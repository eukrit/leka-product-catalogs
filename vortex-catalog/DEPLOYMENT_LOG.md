# Vortex Aquatics Catalog — Deployment Log

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
  `Credentials Claude Code/ai-agents-go-4c81b70995db.json`
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

- GSM secret `medusa-admin-password` (v2, 13 bytes) holds `LekaAdmin2026`
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
