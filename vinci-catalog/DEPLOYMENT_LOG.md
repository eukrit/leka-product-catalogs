# Vinci Play Catalog — Deployment Log

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
- [ ] Initial scrape run (full — only Spring series scraped so far)
- [ ] Firestore import run
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
