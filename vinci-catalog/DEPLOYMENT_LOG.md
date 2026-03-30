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
- [ ] Initial scrape run
- [ ] Firestore import run
- [ ] Web app built
- [ ] Cloud Run deployed
