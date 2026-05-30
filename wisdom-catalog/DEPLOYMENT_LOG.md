# Deployment Log — Wisdom Product Catalog

## v2.48.0 — 2026-05-30 (Outdoor-Play Collection — Medusa Link + Gemini Image Verify)

> Renumbered from v1.5.0 → v2.48.0 during merge with main: the wisdom brand
> log was migrated to the project-wide semver scheme (matching the v2.45.0
> Furniture Catalog entry that landed below). The work itself is unchanged.

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

### Post-import audit (2026-05-30, same session)

Re-enumerated the collection live to decide whether `--force-image-refresh` was worth running. Result:

| Thumbnail state | Count | Source |
|---|---:|---|
| Real proxy URL (catalogs.leka.studio/api/i/leka-project/…) | 182 | v2.34.0 backfill carried these in — left untouched by this run |
| Placeholder (leka-coming-soon.png) | 28 | Pre-existing v2.34.0 placeholders — Gemini also failed our outdoor-play pass on the same source images |
| Placeholder (new wisdom-*) | 17 | The firestore-null SKUs — no candidate images existed |
| Null | 0 | — |
| **Total** | **227** | |

**Decision: do NOT run `--force-image-refresh`.** A refresh would replace ~40+ verified v2.34.0 thumbnails with placeholders (because our outdoor-play Gemini pass rejected all candidate images for those specific SKUs — they're the "page collage" PDF extractions where multiple products appear in one frame). The current state (182 real / 45 placeholder) is strictly better than what re-running with refresh would produce (~125 real / ~102 placeholder estimated). The conservative default in `link_existing()` — only refresh when current thumb is null or `metadata.image_status == "placeholder"` — was the right call.

### Notes for future runs
1. The 96 Gemini-rejected URLs are mostly PDF page-collage extractions (multiple products per frame). Fixable by upstream PDF re-extraction (out of scope here). When that lands, the cached Gemini decisions in `wisdom_outdoor_play_verify` will need invalidation (or run with `--force-gemini`).
2. `CLAUDE.md` Image Pipeline section updated in this commit to point at `gs://ai-agents-go-vendors/<vendor>/` + the storefront proxy form. Stops future scripts from reproducing the bug we hit during this build.
3. Storefront cache: the leka-website proxy caches 404s for ~24h. The 17 new placeholder URLs are stable + the placeholder object exists in GCS, so no propagation work needed.

---

## v2.45.0 — 2026-05-30 (Furniture Catalog image backfill)

### Summary
Extracted and attached real product imagery from the brand-new `2025-08-11
Wisdom International Furniture Catalog.pdf` (355 pages, never previously
ingested) to Leka Project placeholder products on Medusa.

### Pipeline
1. `wisdom-catalog/extract_furniture_pdf_images.py --extract` — spatial PDF
   attribution (PyMuPDF span-bbox + image-rect nearest-neighbor, MAX_IMAGES=2,
   MAX_DISTANCE=600 px). Output: 1,538 JPEGs to local cache + mapping JSON.
2. `wisdom-catalog/enrich_furniture_pdf_images.py --upload` — 1,222 new
   objects in `gs://ai-agents-go-vendors/wisdom/furniture_2025/`.
3. `wisdom-catalog/enrich_furniture_pdf_images.py --write-firestore` — 93
   `vendors/wisdom/products` docs gained furniture image entries.
4. `wisdom-catalog/enrich_furniture_pdf_images.py --verify` — Gemini 2.5
   Flash @ 0.70, 93 calls / $0.86 spent / 39 accept / 47 reject / 0 error.
5. `wisdom-catalog/enrich_furniture_pdf_images.py --sync-medusa` — 33
   placeholder products flipped to `backfilled_furniture` on Medusa.

### Outcome
- Live placeholders: 2,138 → 2,105 (delta −33).
- Backfilled with real imagery: 67 → 100 (delta +33).
- 93 vendor docs populated for future Medusa onboarding (some not yet on
  Medusa).

### Quality / spend
- 96.5 % of spatial attributions had centroid distance < 200 px.
- Verify accept rate 42 % — Gemini correctly rejected multi-product-page
  mis-attributions; accepts cluster on KB / GP / HW / MGF prefixes.
- $0.86 Vertex spend, $19.14 under ceiling.

### Sibling worktree (resolved post-merge)
`claude/great-hopper-c0fd71` (now v2.48.0 above) did NOT re-extract images
— it tagged the outdoor-play collection. Image re-extraction was scoped out
and spawned as a separate task. No file or write-key overlap with this
branch's furniture wave.

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

---

## v2.45.0 — 2026-05-30 (SG-channel landed cost, dry-run)

### Summary
Parallel Singapore-channel landed-cost path added for Nubo SG. TH path
unchanged. Firestore-only this round (no Medusa SG push). See
[`CHANGELOG.md`](../CHANGELOG.md) `[2.45.0]` for full detail and the
[comparison report](../scripts/reports/sg_pricing_compare_2026-05-30.md).

### Files (this folder)
- `update_pricing.py` — new `--sg-channel` flag (default OFF). When set,
  computes SG pricing alongside TH and merges `pricing.sg.*` into the
  same per-SKU batch update. Prints `[sg-compare]` preview lines.

### Runs to date
- 2026-05-30: dry-run `python wisdom-catalog/update_pricing.py --dry-run
  --skip-medusa --sg-channel` against `products_wisdom` (5,071 docs, 4,809
  with FOB). No writes. Preview shows flat-path SKUs +1.9% (GST premium),
  CBM SKUs varying ±0–70% driven by genuine freight-rate differences.
- Comparison report `scripts/compare_sg_pricing.py --limit 10`:
  median +0.19%, mean −4.96%, one |Δ|>25% outlier
  (`HW1-S367-V01` SG-floored on logistics-tier clamp).

### Pending before SG goes live
- Replace benchmark freight constants in `cost_engine.ROUTE_PROFILES["china_to_singapore"]` with a real forwarder quote.
- Identify Medusa SG sales-channel ID + wire `update_pricing.py` to push retail_sgd there when ready.
- Decide on a pricing.th.* / pricing.sg.* migration if storefront wants to read both natively.
