# Deployment Log — Wisdom Product Catalog

## v1.0.0 — 2026-03-22 (Initial Release)

### Summary
Built a complete product catalog system for Wisdom playground/furniture products. Data sourced from Slack channel `#vendor-wisdom-playground`, stored in Firestore, and served via Cloud Run with Leka Design System styling.

### Data Pipeline
- **Source**: 32 xlsx files downloaded from Slack `#vendor-wisdom-playground` via Slack Bot API
- **Storage**: `Wisdom Slack Downloads/` folder (local, git-ignored)
- **Import Script**: `import_to_firestore.py`
  - Full China 2025 catalog: 4,903 products
  - US 2025 catalog: 933 products (merged, adding weight data)
  - Quotations: 29 quotation documents
  - Categories: 12 auto-generated categories
  - **Total Firestore documents**: 5,071 products

### Firestore Schema (GCP project: `ai-agents-go`)
- **`products`** collection — 5,071 docs keyed by `item_code`
  - Fields: item_code, description, description_cn, category, subcategory, material, dimensions, volume_cbm, weight_kg, pricing (fob_usd, currency, price_date), catalog_page, catalog_source, images[], timestamps
- **`quotations`** collection — 29 docs
  - Fields: quotation_id, date, source, items[], created_at
- **`product_categories`** collection — 12 docs
  - Fields: name, prefix_patterns, product_count

### Categories Breakdown
| Category | Products |
|----------|----------|
| Other | 1,700 |
| Furniture | 1,261 |
| Playground | 986 |
| Outdoor | 303 |
| Nature Play | 285 |
| Balance | 159 |
| Climbing | 133 |
| Early Years | 83 |
| Creative | 82 |
| Loose Parts | 48 |
| Water Play | 30 |

### Web App
- **Tech**: Static HTML/CSS/JS with Flask server in Docker
- **Design System**: Leka Design System (Figma: `ER6pbDqrJ4Uo9FuldnYBfm`)
  - Font: Manrope (400-800 weights)
  - Colors: Purple `#8003FF`, Navy `#182557`, Cream `#FFF9E6`
  - Card component: 16px radius, cream image area, subtle shadow
  - Badges: pill-shaped with category colors
- **Data**: Pre-exported static JSON (26 pages × 200 products)
- **Features**: Category filtering, text search, price range, lazy loading

### Deployment
- **Platform**: Google Cloud Run
- **Region**: asia-southeast1
- **Service**: `wisdom-catalog`
- **URL**: https://wisdom-catalog-538978391890.asia-southeast1.run.app
- **Resources**: 256Mi memory, max 3 instances
- **Auth**: Public (unauthenticated)

### GitHub
- **Repository**: https://github.com/eukrit/product-catalogs
- **Branch**: main
- **Commit**: `4738dbd` — Initial release

### Known Limitations
- ~~Product images column is empty~~ — **resolved in v1.4.0** (63% coverage)
- "Other" category (1,700 products) needs further sub-classification
- Client-side search loads all data pages — could be slow on weak connections
- No authentication on web app (public read-only)

### Next Steps
- ~~Upload product images to GCS bucket and link to Firestore `images[]` array~~ ✅
- ~~Extract images from catalog PDFs~~ ✅
- Source images for remaining 1,839 products (36% still missing)
- Add image upload admin interface
- Implement server-side search for better performance
- Add quotation comparison view

---

## v1.4.0 — 2026-03-24 (Full Catalog Image Extraction)

### Summary
Extracted images from the **full 529-page** Wisdom catalog PDF (previously only processed 142-page international version). Image coverage improved from 27% to 63%.

### Image Pipeline
- **Source PDF**: `2025 Wisdom catalog.pdf` (529 pages, 320MB)
- **Script**: `extract_full_catalog.py`
- **Text indexing**: Built product code→PDF page mapping for 3,189 codes
- **Image extraction**: 3,205 unique images extracted (deduplicated by hash)
- **Upload**: 31,149 images uploaded to `gs://ai-agents-go-documents/product-images/wisdom/catalog/`
- **Mapping**: 1,817 new products received images (previously had 0)
- **Skipped**: 1,233 products already had images from v1.3.0

### Coverage by Category (After)
| Category | Coverage | Products |
|----------|----------|----------|
| Early Years | 100% | 83/83 |
| Loose Parts | 100% | 48/48 |
| Nature Play | 98% | 281/285 |
| Creative | 79% | 65/82 |
| Outdoor | 68% | 207/303 |
| Other | 66% | 1,135/1,700 |
| Water Play | 66% | 20/30 |
| Furniture | 66% | 840/1,261 |
| Climbing | 64% | 86/133 |
| Balance | 45% | 73/159 |
| Playground | 39% | 394/986 |
| **Total** | **63%** | **3,232/5,071** |

### Data Verification
- **Description accuracy**: 100% (4,170/4,170 checked match Excel source)
- **Website URL**: Set on all 5,071 products → `https://www.wisdomplaygroundsint.com/en/products`

### Remaining Gaps
- 1,107 product codes not found as text in the PDF (internal codes, discontinued items, or differently formatted codes)
- 1,839 products still without images — would need manual mapping or vendor sourcing

### New Files
| File | Purpose |
|------|---------|
| `extract_full_catalog.py` | Full 529-page catalog image extraction & mapping |

---

### Files
| File | Purpose |
|------|---------|
| `import_to_firestore.py` | Import xlsx data into Firestore |
| `export_to_json.py` | Export Firestore to static JSON for web |
| `firestore_schema.json` | Database schema documentation |
| `web-app/public/index.html` | Product catalog UI |
| `web-app/public/styles.css` | Leka Design System CSS |
| `web-app/public/app.js` | Frontend logic |
| `web-app/server.py` | Flask static file server |
| `web-app/Dockerfile` | Cloud Run container |
| `web-app/firestore.rules` | Firestore security rules |
