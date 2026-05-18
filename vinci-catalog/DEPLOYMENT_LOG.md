# Vinci Play Catalog — Deployment Log

## 2026-05-11 — Pricelist v2.10.0 (EUR FOB → landed → THB/USD/EUR retail)

- **Source**: `2026-05-11 Vinci pricelist_export_1778483593.xlsx` (1,234 SKUs, EUR FOB Poland)
- **Run**: `python vinci-catalog/import_pricelist.py` then
  `python scripts/sync_vendors_to_medusa.py --brand=vinci`
- **FX snapshot**: USD=32.8915 EUR=38.7082 (exchangerate-api.com + 2% buffer)
- **Baltic LCL rate**: 5,319.49 THB/CBM (avg of 5,500 static + 5,138.97 FBX-derived)
- **Match outcomes**: 899 exact-dim / 335 flat-uplift / 0 fuzzy
- **Tier clamps**: 696 clean / 346 floored / 192 capped
- **Firestore**: 915 product docs written to `vendors/vinci/products/`
- **Medusa**: 915 product variants on `leka-medusa-backend` updated with THB+USD+EUR retail
- **Sample**: vinci-2211 EUR 1,868 → THB 222,551 / USD 6,766 / EUR 5,749 (verified live)
- **Audit trail**: `vinci-catalog/data/pricelist_2026-05-11_landed.csv`

## 2026-03-30 — Initial Setup

### Changes
- Created `vinci-catalog/` brand folder
- Built `scrape_catalog.py` — full website scraper for vinci-play.com
  - Covers all 29 product series
  - Extracts: product info, specs, images, drawings, downloads, certifications
  - Supports checkpoint/resume for reliability
  - Rate-limited at 1 req/sec with retry logic
- Built `import_to_firestore.py` — imports scraped JSON to `products_vinci` collection
- Created `firestore_schema.json` — documents the Vinci-specific schema

### Data Source
- Website: https://vinci-play.com/en/playground-equipment
- 29 product series (ROBINIA, WOODEN, NATURO, SOLO, etc.)
- Estimated 1,000+ products across all series

### Pipeline
1. `python vinci-catalog/scrape_catalog.py` → scrapes all products to JSON
2. `python vinci-catalog/import_to_firestore.py` → imports to Firestore `products_vinci`
3. `python vinci-catalog/import_to_firestore.py --dry-run` → preview without writing

### Firestore
- Collection: `products_vinci`
- Categories collection: `product_categories_vinci`
- Brand registry: `brands/vinci`

### Status
- [x] Scraper built
- [x] Firestore importer built
- [x] Initial scrape run (1,172 products across 29 series)
- [x] Firestore import run (products_vinci collection)
- [x] Web app built
- [x] Cloud Run deployed

---

## 2026-04-01 — Cloud Run Deployment

### Changes
- Created Artifact Registry repo `leka-product-catalogs` in asia-southeast1
- Built Docker image via Cloud Build (us-central1)
- Deployed to Cloud Run as `vinci-catalog` service

### Cloud Run
- Service: `vinci-catalog`
- URL: https://vinci-catalog-538978391890.asia-southeast1.run.app
- Region: asia-southeast1
- Memory: 256Mi
- Max instances: 3
- Image: `asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs/vinci-catalog`

### Data
- 47 products from Spring series (static JSON in web-app/public/data/)
- Full scrape of all 29 series still pending

### Issues Resolved
- Cloud Build failed in asia-south region — used `--region us-central1` for build
- Artifact Registry repo `leka-product-catalogs` didn't exist — created it

---

## 2026-04-01 — Full Scrape + Firestore Import + Redeploy

### Changes
- Full scrape of all 29 series completed (1,172 products, ~50 min)
- Redeployed web app with full product data (revision vinci-catalog-00002-vsj)
- Imported all 1,172 products to Firestore `products_vinci` collection
- Built category index in `product_categories_vinci`
- Registered Vinci brand in `brands/vinci`
- Fixed service account credential path (eukri → Eukrit)

### Product Breakdown by Category
| Category | Count |
|----------|-------|
| playground | 822 |
| fitness | 128 |
| climbing | 82 |
| outdoor | 52 |
| sports | 16 |
| early_years | 13 |

### Series Breakdown
29 series scraped — largest: ROBINIA (257), RECYCLED (158), SOLO (109)
