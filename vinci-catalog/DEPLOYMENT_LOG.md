# Vinci Play Catalog — Deployment Log

## 2026-04-01 — Cloud Run Deployment (v1 — Spring Series)

### Live URL
**https://vinci-catalog-538978391890.asia-southeast1.run.app/**

### What's Live
- Web app with Leka Design System (Manrope, purple/navy/cream palette)
- 47 Spring series products with full data
- Search, filter by series/category/age, series badges
- Product detail modal: specs, images, downloads, certifications
- Health endpoint: `/health`
- Data endpoint: `/data/products_all.json`

### GCP Resources
- Cloud Run Service: `vinci-catalog`
- Region: `asia-southeast1`
- Project: `ai-agents-go`
- Memory: 256Mi
- Image: built via `gcloud run deploy --source`

### Verified
- [x] Health check returns `{"status": "ok", "brand": "vinci"}`
- [x] Product data serves 47 products via JSON API
- [x] Images load from `zamowienia.vinci-play.pl`
- [x] Downloads link to tech sheets, DWG 2D/3D

---

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
- [x] Test scrape run (47 Spring products)
- [ ] Full scrape run (all 29 series)
- [ ] Firestore import run
- [x] Web app built
- [x] Cloud Run deployed
