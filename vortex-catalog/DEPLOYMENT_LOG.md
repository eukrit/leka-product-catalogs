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

### Pending — run after scrape completes

1. `python vortex-catalog/mirror_images_to_gcs.py` — mirror ~2,500 images to GCS
2. `python vortex-catalog/import_to_medusa.py --dry-run` — verify shape
3. `python vortex-catalog/import_to_medusa.py` — import to Medusa. Record the generated Sales Channel ID and publishable API key below.

### Sales Channel (fill after import)

- ID: _TBD_ (record after `get_or_create_sales_channel` runs)
- Publishable API key: _TBD_
- Category: `water_play`
- Collection handles: `vortex-splashpad`, `vortex-waterslide`, `vortex-elevations-playnuk`, `vortex-playable-fountains`, `vortex-coolhub`, `vortex-dream-tunnel`, `vortex-water-management-solutions`, `vortex-uncategorized`

### Cloud Run service (fill after deploy)

- URL: _TBD_
- Artifact: `gcr.io/ai-agents-go/vortex-catalog:latest`
