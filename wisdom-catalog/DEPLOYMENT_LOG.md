# Deployment Log — Wisdom Product Catalog

## v1.5.0 — 2026-05-30 (Outdoor-Play Collection — Medusa Link + Gemini Image Verify)

### Summary
Tagged the 272-SKU **Wisdom Outdoor Classroom — Outdoor Play** subset into a new Medusa collection `wisdom-outdoor-play` on `leka-medusa-backend`. Recognised mid-flight that 255 of the 272 SKUs already live in Medusa under the rebranded **Leka Project** sales channel (their original Wisdom item codes are preserved in `variants[].metadata.legacy_sku`), so the importer was redesigned as a hybrid: **link** the existing 255, **create** the 17 truly absent. Every candidate image was filtered through URL rewrite → HTTP HEAD → Gemini 2.5 Flash verify before being written.

### Pipeline
- **Source work-list:** `vendors` repo `wisdom-catalog/parsed/wisdom-outdoor-play-merged.json` (272 rows, top-level array). 17 rows have `firestore: null` (the unmatched ones); 255 have at least the `description` / `description_cn` enrichment.
- **Script:** `wisdom-catalog/import_outdoor_play_to_medusa.py` (new) — eight stages, idempotent, dry-runnable.
- **Shared helper added:** `update_product_images(product_id, thumbnail, gallery)` and `update_product_metadata(product_id, metadata)` in `shared/medusa_importer.py`.
- **Match strategy:** `build_legacy_sku_index(SC=sc_01KNKTHC0B7KFEDSZ3NNM49JQW)` indexes 10,123 Wisdom variant-SKU↔product-id pairs. For each outdoor-play SKU, the importer probes by (a) exact `sku`, (b) `firestore.matched_id`. No match → create with handle `wisdom-<code.lower()>`.
- **Image URL rewrite:** Firestore `images[].url` points at the **private** `gs://ai-agents-go-documents/product-images/wisdom/...` bucket (403 anonymously). A `rewrite_image_url()` helper flips every URL to the live storefront-proxy form `https://catalogs.leka.studio/api/i/leka-project/<path>` (backed by `gs://ai-agents-go-vendors/leka-project/`). Confirmed via memory `image-proxy-bucket.md` + curl spot-check.
- **HEAD pre-filter:** ThreadPoolExecutor(16) HEAD-checks all 300 unique URLs in ~0.5s. 255 return 200; 45 return non-2xx (object not present in `leka-project/` bucket).
- **Gemini verify:** For each HEAD-OK URL × product title pair (264 jobs), `gemini-2.5-flash` returns `{matches, confidence, depicted}`. Threshold `confidence >= 0.70`. Decisions cached in Firestore `wisdom_outdoor_play_verify/{sha1(url|title)}` for free reruns. Reused the `image_backfill_verify` prompt + schema established in v2.34.0.

### Outcome
| Bucket | Count |
|---|---:|
| SKUs in source merged JSON | 272 |
| Linked to existing Leka-Project product (via `legacy_sku` / `matched_id`) | 255 |
| Created fresh as `wisdom-<code>` | 17 |
| Skipped due to error | 0 |
| **Unique products now in `wisdom-outdoor-play` collection** | **227** |
| SKUs that ended with a verified thumbnail | 140 |
| SKUs that ended on the Leka "Image coming soon" placeholder | 132 |
| Broken image URLs (HEAD non-2xx) dropped | 45 |
| Gemini verdicts: accept / reject / error / cached | 168 / 96 / 0 / 4 |
| New images written to existing products | 0 (existing products already had non-placeholder images from v2.34.0; `--force-image-refresh` was not requested) |

The **227 vs 272 gap** is expected and reconciled in the report: many merged-JSON SKUs share a single `firestore.matched_id` (e.g. both `CSS-BZ` and `CSS-BZ-V02` map to `leka-project-qv8v9i2v`). Every source SKU is accounted for — none silently dropped.

### Collection on Medusa
- **Title:** `Wisdom Outdoor Classroom — Outdoor Play`
- **Handle:** `wisdom-outdoor-play`
- **ID:** `pcol_01KSTM5ZC4H197S057QC2TNATR`
- **Live URL (admin):** https://leka-medusa-backend-rg5gmtwrfa-as.a.run.app/admin/collections/pcol_01KSTM5ZC4H197S057QC2TNATR
- **Sub-areas covered (from `metadata.outdoor_play.sub_area` / `metadata.sub_area`):** `planting_breeding`, `sand_water`, `music`, `outdoor_planting`, `outdoor_classroom_misc`, `vision_weather`.

### Cost / wall-time
- Gemini: 260 verifications × ~$0.0015 ≈ **~$0.40** Vertex spend.
- Wall-time end-to-end: **~2 min** (Gemini fan-out at concurrency 4 dominates; Medusa upsert at ~5/s).
- Idempotent rerun (everything cached): expected <30s — second pass is essentially `HEAD` re-check + index rebuild + 272 read-modify-write PATCH/POSTs against an already-final state.

### New files
| File | Purpose |
|------|---------|
| `wisdom-catalog/import_outdoor_play_to_medusa.py` | Hybrid link/create orchestrator (this build). |
| `wisdom-catalog/IMPORT_OUTDOOR_PLAY_REPORT.md` | Auto-written report — re-emitted on every run. |
| `shared/medusa_importer.py` (extended) | `update_product_images`, `update_product_metadata`. |

### Notes for future runs
1. If we want to overwrite the v2.34.0-era thumbnails with the Gemini-verified outdoor-play images, rerun with `--force-image-refresh` — the Firestore Gemini cache makes this almost free.
2. The 132 SKUs that ended on a placeholder are a mix of (a) the 17 firestore-null rows, (b) 82 rows whose `firestore.images[]` is empty in the source JSON, and (c) ~33 rows where every candidate image was either bucket-missing (HEAD 4xx) or Gemini-rejected. The 96 Gemini-rejected URLs are likely "page collage" PDF extractions where multiple products appear in one frame — fixable by upstream PDF re-extraction, out of scope here.
3. CLAUDE.md's "Image Pipeline" note (upload to `gs://ai-agents-go-documents/product-images/<brand>/catalog/`) remains stale — the live serving bucket is `gs://ai-agents-go-vendors/<vendor>/`. The memory note `image-proxy-bucket.md` documents this; a follow-up should fix CLAUDE.md.

---

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
