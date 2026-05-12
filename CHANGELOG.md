# Changelog

All notable changes to this project will be documented in this file.

## [2.13.0] - 2026-05-12

### Added — Weplay coverage closes follow-ups: catalog 136 → 149 + cached/flipbook fallback sources

Three small follow-up scripts that close out the v2.12.0 out-of-scope items
(missing actives, unreachable drafts, unscored vision images).

#### `scripts/scrape_weplay_cached.py` (new)
Mines `gs://ai-agents-go-vendors/weplay/pages/*.html` (1,453 pages from
the original scrape) for English product detail content the live
crawler missed. Same parser as `scrape_weplay_en.py`; only writes when
the doc lacks both `source_url_en` and `source_url_cached`.

**Result:** 597 cached HTML pages parsed → 181 unique SKUs → 31 new
Firestore writes. Recovered EN content for 4 of the 9 originally-missing
actives (KB1303 Gym Ball, KB1307 Gym Roll, KC3001 Learning Cube, KC3004
Stepping Shape) plus 27 more drafts. After re-running the existing
ingest pipeline + Medusa sync: **+13 new active products promoted**.
Catalog grew **136 → 149**.

The remaining 5 missing actives (KC0001, KP1001, KP1002, KP1003, KT0003)
aren't in any cached page — likely never crawled.

#### `scripts/ocr_weplay_flipbook.py` (new)
OCRs the 188-page Weplay EN 2025 Flash flipbook (one high-res JPG per
page at `weplay.com.tw/download/EN/Catalog/2025/files/mobile/N.jpg`)
via Gemini 2.5 Flash. Per-page prompt asks for every product card on
the page as `{sku, name_en, description_en, age_range}`.

**Result:** 257 SKUs extracted, 251 matched to Firestore docs, 248
already had richer source data (live or cached) and were skipped, **3
new writes** (KM1004 Balance Rocking Ice, KM1006 Honey Hills, KM1007
Coral Adventure). 103 catalog SKUs found with no matching Firestore
doc — could become new products in a future pass. Cost ~$2-3.

The 116 originally-uncovered drafts are mostly OLDER products
(`KB0001`, `KC0007` style) discontinued before the 2025 catalog — the
flipbook doesn't help them. They'd need an older catalog edition or
hand-curation.

#### Vision rerun (no new script — `vision_rank_weplay_images.py --apply` again)
Second pass picked up the ~460 images Gemini 429'd on first run.
**+110 images scored, +15 reordered, +8 primary changes.** Cumulative
totals across the two passes: 600 images scored, 82 products
reordered, 66 new card thumbnails.

### Composite outcome
- `catalogs.leka.studio/weplay`: **149 product cards** (was 136 in v2.12.0)
- Provenance fields per product: `source_url_en` (live), `source_url_cached`
  (GCS HTML), `source_url_flipbook` (page N OCR) — explicit lineage
- Drafts left: 113 with real-SKU `item_code` not in any source we tried
  (mostly KB0001-style discontinued products)

### Files changed
- `scripts/scrape_weplay_cached.py` (new)
- `scripts/ocr_weplay_flipbook.py` (new)
- `CHANGELOG.md`

---

## [2.12.0] - 2026-05-12

### Added — Weplay catalog grew 100 → 136 + kids-first card photos

Three small data-pipeline scripts, each one shippable, that close out the
Weplay onboarding asks (rewrite English content, lift drafts to active,
make the storefront cards lifestyle-led).

#### `scripts/ingest_weplay_images.py` (new)
Walks every `vendors/weplay/products/*` doc whose `source_image_urls_en` is
non-empty (set by `scrape_weplay_en.py` at v2.11.0). For each upstream URL:
fetch, sha256-hash, upload to `gs://ai-agents-go-vendors/weplay/media/<sha>.<ext>`
(skip when the sha-named blob already exists), then append
`{url: <proxy>, sha: <sha>}` to `images[]` via the existing storefront
proxy at `https://catalogs.leka.studio/api/i/weplay/media/<sha>.<ext>`.
Only fills products that currently have NO `images[]` (--enrich-actives
opts in to also widen actives).

**Result:** 122 products had EN-page URLs available; 36 of those were
`draft_no_images` and got promoted to `status: "active"` after the ingest.
Upload count was zero — every sha was already in GCS from the original
pipeline scrape, just unlinked from product docs. Re-sync to Medusa
created the 36 new SKUs (Edusante line, Pattern Cubes, School Set,
Anti Burst Ball, Baby and Toddler Set, etc.). Catalog grew **100 → 136**
active Weplay products on `catalogs.leka.studio/weplay`.

#### `scripts/vision_rank_weplay_images.py` (new)
For each active product's `images[]`, ask Gemini 2.5 Flash to score each
image 0-100 on "kids/users in scene with the product" + tag it with one
of `kids_using | adults_using | lifestyle_no_people | packshot_white_bg |
technical_drawing | certification | logo | other`. Caches `score_kids` +
`tag_kids` per image so re-runs are free; reorders `images[]` desc by
score. Batches images in groups of 5 per call (max_output_tokens=800,
thinking_budget=0) — single-call multi-image was hitting JSON truncation
at ~17 images.

**Run** processed all 136 active products: 490 images scored across
~190 batched calls, **67 products reordered, 58 had their primary photo
change**. Tag distribution: `kids_using: 319`, `packshot_white_bg: 62`,
`certification: 29`, `technical_drawing: 25`, others ~30. The remaining
~460 images weren't scored — Gemini free-tier returned 429 on the back
half of the run; second pass (`--rescore` not needed) will pick them up
when quota resets. `_sort_by_score` puts unscored images at the end so
the storefront still gets a lifestyle-first card today.

API key pulled from Secret Manager (`gemini-api-key`); ~$2-3 spend for
the run.

#### `scripts/sync_weplay_thumbnails.py` (new)
`sync_vendors_to_medusa.py`'s update path only refreshes title /
description / metadata on existing products — not `images[]` or
`thumbnail`. This script fills the gap for Weplay: pulls all 136 SC
products from Medusa, compares against Firestore-side image order, and
POSTs `{thumbnail, images[]}` updates where they diverged. Run pushed
**59 thumbnail changes + 70 image-order changes** to Medusa. 0 errors.

#### Composite outcome
- `catalogs.leka.studio/weplay` now serves **136 cards** (was 100).
- 58 of the 100 pre-existing products got new card thumbnails — the
  technical-drawing / packshot photos are now buried in PDP gallery,
  lifestyle/kids shots lead.
- All 136 carry English titles + descriptions from `weplay.com.tw`.

### Out of scope (small follow-ups)
- Re-run `vision_rank_weplay_images.py` for the ~460 images that hit 429
  — should free-tier reset within an hour. Idempotent.
- Some Gemini responses invented tag variants (e.g.
  `isolated_product_on_patterned_background`) instead of the rubric's
  canonical labels. Sort-by-score still works; tag normalization can be
  a one-liner if needed.
- 9 active products not in the EN catalog still carry their AI-generated
  EN descriptions (`KB1303, KB1307, KC0001, KC3001, KC3004, KP1001,
  KP1002, KP1003, KT0003`).
- 112 draft products with real-SKU `item_code` not reachable via the EN
  nav — would need a different source (older catalog, Vision OCR of the
  Flash flipbook page JPGs, or hand curation).

---

## [2.11.0] - 2026-05-12

### Added — Authoritative English content for Weplay catalog
- New `scripts/scrape_weplay_en.py` — BFS crawler for the English variant of Weplay's product detail pages on `www.weplay.com.tw` (parameter `?lang=en`). The Chinese e-commerce host `e-weplay.com.tw` has no working language switch, but the parent corporate site does — and serves the same product detail pages with full English copy: title (`Weplay <product name>`), structured spec fields (`<span class="ftit">Item No.</span><span class="ftxt">KM1003</span>` style), product description paragraph (under a `Product Feature` header in `<div class="pdesc fold-desc">`), and image gallery URLs.
- Probed and rejected three other EN sources first (recorded in [docs/WEPLAY_PATH2_FOLLOWUP.md](docs/WEPLAY_PATH2_FOLLOWUP.md) lineage):
  1. `download/EN/Catalog/2025/` — Adobe Flash flipbook, JS-extracted text covers 2 of 188 pages
  2. `e-weplay.com.tw?lang=en` — query param ignored, content stays Chinese
  3. site_structure URL re-crawl — all return generic "商品一覽" listing
- Crawl ran in 52s (121 pages, polite 300ms): **100 detail SKUs** found, all with rich EN description (avg ~400 chars), full specs dict (age, max load, weights, package size), and 8–11 image URLs each.

### Updated — Firestore + Medusa with EN content
- 157 `vendors/weplay/products/*` docs touched (covers 100 unique SKU folders × 1.57 variant docs avg). Merge writes:
  - `name` ← EN scraped title (e.g. `Pile Balance Up`, `Brick Me`, `Squishy Tactile Shell`)
  - `description` ← per-product EN feature paragraph
  - `description_orig` ← previous Anthropic-generated description (audit/rollback)
  - `name_zh` ← original `product_name` only when it contained CJK chars (preserved)
  - `specs` ← `{age, maximum_load, product_weight, package_size, package_weight}`
  - `spec_block` ← components / dimensions / country-of-origin paragraph
  - `source_url_en` ← provenance
  - `source_image_urls_en` ← upstream URLs (image ingest is a follow-up)
- Re-ran `python scripts/sync_vendors_to_medusa.py --brand=weplay --skip-no-images` — 100/100 Medusa products updated to English titles + descriptions, 0 errors.

### Fixed — `SKU_TOKEN_RE` word-boundary bug
First writeback only touched 126 docs (and only `kb0304` got the EN content for the 5 spot-checked products). Root cause: `\b([A-Z]{2}[0-9]{4,})\b`. For an item code like `6800KM1003`, there's no word boundary between `0` and `K` (both are `\w`), so the regex didn't match the inner SKU. Fixed by removing `\b` boundaries — now matches `KM1003` inside `6800KM1003`. Re-ran writeback: 157 docs.

### Fixed — Description anchor ("Product Feature" extraction)
Initial parser fell back to the `<meta description>` tag, which is the same generic Weplay marketing boilerplate on every page. Switched to anchor on `Product Feature` header inside `<div class="pdesc fold-desc">`. Now every product gets its own per-product description.

### Coverage
- 58/67 actives covered with EN content (87%)
- 31/143 drafts get EN name+desc (still draft until image ingest)
- 9 actives not in EN catalog (keep prior AI-generated descriptions)
- 3 catalog SKUs have no Firestore product (`KT2005B, KP5001, EM5501`)
- 112 drafts not in EN nav at all

### Files changed
- `scripts/scrape_weplay_en.py` (new)
- `CHANGELOG.md`

---

## [2.10.0] - 2026-05-11

### Added — Vinci Play landed-cost pricelist pipeline (THB + USD + EUR retail)

End-to-end ingestion of the **2026-05-11 Vinci pricelist** (1,234 SKUs, EUR FOB
Poland) → landed cost in THB → 40% gross margin retail in THB / USD / EUR →
Medusa product variants. Replaces the previous USD-only pricing path for Vinci
on `catalogs.leka.studio`.

- **NEW** [vinci-catalog/import_pricelist.py](vinci-catalog/import_pricelist.py)
  — orchestrator. Reads the EUR pricelist, joins to scraped dimensions in
  [vinci-catalog/web-app/public/data/products_all.json](vinci-catalog/web-app/public/data/products_all.json),
  computes packing CBM (installed L×W×H × 0.15 factor), and calls
  `shipping-automation/mcp-server/cost_engine.estimate_landed_cost()`
  (EU LCL Gdynia → LCB route) with **live Baltic-rate calibration** averaging
  the static rate card with FBX-derived LCL estimate. Writes to
  `vendors/vinci/products/{vinci-<lc-code>}.pricing.*` in Firestore (db `vendors`).
- **Tiered min/max logistics %** (`LOGISTICS_TIERS`) — caps total logistics
  cost as a % of FOB-in-THB by FOB band: < €500 → 80–250%, < €2,000 → 60–180%,
  < €10,000 → 45–120%, ≥ €10,000 → 35–80%. Floor prevents small SKUs being
  priced near-FOB despite carrying fixed clearance/last-mile costs; cap
  clamps outliers where scraped installed dimensions wildly overstate
  packing CBM. Audit fields `landed_thb_raw`, `logistics_pct`,
  `logistics_clamp` preserved on every row.
- **Live FX** — `fx_rates.get_fx_rates(buffer_pct=2)` resolves USD=32.89,
  EUR=38.71 from exchangerate-api.com with a 2% buffer.
- **MODIFIED** [scripts/sync_vendors_to_medusa.py](scripts/sync_vendors_to_medusa.py)
  — new `_build_variant_prices()` returns up to 3 currencies when `pricing.retail_thb`,
  `pricing.retail_usd`, `pricing.retail_eur` are set; legacy `fob_usd` USD-only
  path preserved for other brands. **Bug fix:** variant update endpoint
  corrected from `/admin/products/variants/{id}` (404'd) to
  `/admin/products/{product_id}/variants/{variant_id}` per Medusa v2 API.

### Numbers
- **Match rate**: 899 / 1,234 SKUs (73%) priced via scraped-dimension CBM
  (`match_strategy=exact`). 335 priced via flat 35% landed-cost uplift
  (`match_strategy=flat_uplift`) — no scraped dimensions available.
- **Tier clamp outcomes**: 696 clean / 346 floored (small SKUs lifted to
  carry fixed costs) / 192 capped (outliers from oversized installed dims).
- **Retail/EUR-THB ratio**: median 3.00× (was unbounded at 16.9× max before
  tiering); p90 5.63×, max 5.83×.
- **Firestore**: 915 product docs updated. 319 pricelist SKUs have no
  matching `vendors/vinci/products/*` doc (out of scope here).

### Reads from sibling repo (no edits there)
- `shipping-automation/mcp-server/cost_engine.py` — `estimate_landed_cost`,
  `ROUTE_PROFILES["europe"]["lcl"]`
- `shipping-automation/mcp-server/fx_rates.py` — `get_fx_rates(buffer_pct)`
- `shipping-automation/mcp-server/rate_feeds.py` — `get_fbx_index` for Baltic
  rate calibration

### Out of scope (follow-ups)
- Empirical packing-CBM ingestion — pull Vinci invoices/packing lists from
  Gmail/Drive into Firestore `vinci_shipments` to replace the 0.15 packing
  factor with per-series ratios.
- Create `vendors/vinci/products/*` docs for the 319 pricelist SKUs the
  current scrape doesn't cover.

## [2.9.1] - 2026-05-10

### Verified — backend pipeline green end-to-end

Manually submitted `cloudbuild.yaml` against `medusa-backend/` to validate the
v2.8.5 db-migrate fix had actually been exercised — it had not, because no
Cloud Build trigger exists for this repo (the storefront's build was driven
manually too). Build [`5628a71c-3485-47dd-bf29-4eb99fdeefa4`](https://console.cloud.google.com/cloud-build/builds;region=asia-southeast1/5628a71c-3485-47dd-bf29-4eb99fdeefa4?project=538978391890):
4m3s, **SUCCESS** through all four steps (build / push / db-migrate / deploy).
Backend image `medusa-backend:fixmigratetest` is now serving on Cloud Run
service `leka-medusa-backend`. Storefront at `https://catalogs.leka.studio/`
continues to call this backend — no client-visible change.

### Added
- **Cloud Build trigger `deploy-leka-medusa-backend`** — watches `main` branch
  on `eukrit/leka-product-catalogs`, build config `cloudbuild.yaml`, included
  files `medusa-backend/**` + `cloudbuild.yaml`. So future backend changes
  auto-deploy the same way the storefront now does. Service account
  `claude@ai-agents-go.iam.gserviceaccount.com` runs the build.

### Out of scope (still TODO)
- `medusa-backend/Dockerfile` — Medusa v2 `.medusa/server` structure mismatch.
  The fact that builds pass and the runtime works suggests the mismatch is
  cosmetic / partial; flagged as a separate task to clean up the layered
  COPY in stage 2 and confirm `.medusa/server` is the canonical location.
- Wisdom palette audit (lives in `eukrit/leka-website`).

## [2.9.0] - 2026-05-10

### Removed — Next.js storefront migrated to `eukrit/leka-website`

The multi-brand storefront moved to the leka-website repo on 2026-05-10 (commit
`1cf31cf`, leka-website v0.7.0). It now ships from `catalogs/` in that repo,
deploys to a new Cloud Run service `leka-catalogs`, and serves
`https://catalogs.leka.studio/` (verified live, all 4 brand routes 200, TLS
provisioned). The old service `leka-medusa-storefront` is cold-scaled
(`min=0, max=1`) for 24h rollback safety; full deletion follows once the new
stack is validated.

This repo now owns only the Medusa v2 backend (`medusa-backend/`) and the
data-prep / vendor-shaping scripts. Backend → Storefront contract unchanged:
storefront still calls `https://leka-medusa-backend-538978391890.asia-southeast1.run.app`
via per-brand publishable keys (which moved to leka-website's
`cloudbuild-catalogs.yaml`).

### Removed
- `medusa-storefront/` — full Next.js app, public assets, configs, Dockerfile.
- `cloudbuild-storefront.yaml`, `cloudbuild-storefront-only.yaml` — orphan pipelines.
- `cloudbuild.yaml` Steps 5–7 (build-storefront, push-storefront, deploy-storefront)
  + the `medusa-storefront` images output. Backend pipeline (Steps 1–4) is unchanged.

### Out of scope (still TODO in this repo)
- `medusa-backend/Dockerfile` — Medusa v2 `.medusa/server` structure mismatch.
- `cloudbuild.yaml` `db-migrate` step — currently broken; backend deploys remain
  red until this is fixed (independent of the storefront migration).
- Wisdom palette audit (referenced by leka-website, not this repo).

## [2.8.5] - 2026-05-10

### Fixed — Cloud Build `db-migrate` step (Missing script error since v2.8.3)
- v2.8.3 changed step 3 from `npx medusa db:migrate` to `npm run db:migrate` but didn't account for entrypoint-override behavior: when Cloud Build runs a step with a custom `entrypoint`, the container CWD is `/workspace` (the host workspace mount), NOT the image's WORKDIR (`/app`). So `npm run db:migrate` ran in `/workspace` where no `package.json` exists → `npm error Missing script: "db:migrate"`.
- Every build since 4e31de5 failed at this step, including the `feat(weplay)` merge (build `66cfff32`).
- Fix: switch to `entrypoint: bash` + `args: ['-c', 'cd /app && npm run db:migrate']` so CWD is explicitly set inside the container before npm runs.

### Files changed
- `cloudbuild.yaml`

---

## [2.8.4] - 2026-05-10

### Added — Weplay catalog live (path 1B: imaged subset)
- Created Medusa Sales Channel **Weplay** (`sc_01KR6Z0VBSXWYZDVGF30EAP0EQ`) + publishable key `pk_2b18dd5670830702993445fe43f4269a406baab0b20f85cad15d43b9b9a9efbb`. Linked the key to the SC.
- Imported **100 Weplay products** (KC/KM/KT/KB/KP series) into the new SC. All published, all with images, no USD prices (Weplay catalog policy).
- Storefront URL: `https://catalogs.leka.studio/weplay` (live after CI/CD deploy).

### Fixed — `sync_vendors_to_medusa.py` two real bugs found during the Weplay run
- **`prices` field omission rejected by Medusa v2** — when `pricing.fob_usd` was missing, the script omitted `variant.prices` entirely, and Medusa returned `{"type":"invalid_data","message":"Invalid request: Field 'variants, 0, prices' is required"}` for all 100 products. Fix: always send `prices: []` when no FOB price exists. (This bug presumably affects Berliner / Eurotramp / 4soft re-syncs too — they all use the same code path. Tested: 100/100 success after fix.)
- **`--skip-no-images` flag** — additive opt-in flag that filters out products with empty `images[]` before sync. Used for Weplay path 1B to ship only the 100 products with confirmed photos and skip the 1,095 `draft_no_images` records left for path 2.

### Added — `scripts/shape_weplay_to_medusa_schema.py`
- Converts the upstream Weplay scrape's per-product schema (`product_name`, `sku`, no `handle`, no `images[]`) into the schema `sync_vendors_to_medusa.py` expects (`name`, `item_code`, `handle`, `images[]`, `status`).
- Image join: indexes `vendors/weplay/attachments/*` by URL-encoded SKU folder pattern (`/Products/<XX>/<SKU>/`); joins each product whose `sku` contains a matching token. Only ~8% of attachments carry the URL-encoded SKU and ~8.4% (100/1,195) of products end up with images. The remaining 1,095 products are written back with `status="draft_no_images"` so the sync filter can skip them. **Path 2 follow-up will source images for the rest** (likely via re-running the upstream `/Products/<prefix>/<SKU>/` crawl with full coverage rather than relying on the partial scrape).
- Image URL form is the storefront proxy: `https://catalogs.leka.studio/api/i/weplay/media/<sha>.<ext>` — served by `medusa-storefront/src/app/api/i/[...path]/route.ts`, no public GCS bucket exposure.
- Backfilled the `vendors/weplay` root doc with `name`, `slug`, `country`, `legal_name`, `website`, `status`, `sales_channel_id`, `publishable_key_id`, `publishable_key_token`.

### Wired
- `scripts/sync_vendors_to_medusa.py` — added `"weplay": "sc_01KR6Z0VBSXWYZDVGF30EAP0EQ"` to `BRAND_SALES_CHANNELS`.
- `medusa-storefront/src/lib/medusa-client.ts` — Weplay `productCount: 0 → 100`; `hasCollections: true → false` (no `collectionPrefix` exists for Weplay; matches Eurotramp pattern).
- `cloudbuild.yaml`, `cloudbuild-storefront-only.yaml`, `medusa-storefront/cloudbuild-storefront.yaml` — added `NEXT_PUBLIC_WEPLAY_PUBLISHABLE_KEY` build-arg so the storefront bundle resolves the key (avoids the Vortex-style "missing key" bug from v2.7.x).

### Outcome
100/100 products created in Medusa under the Weplay SC. Verified via admin API (`/admin/products?sales_channel_id[]=...`) — all published, all with thumbnail + images + category metadata. Storefront deploy follows via the auto Cloud Build trigger on push.

### Known gap (path 2 follow-up)
1,095 Weplay products are sitting in Firestore with `status="draft_no_images"`. They have valid descriptions, SKUs, categories — they're missing only the photo references. The upstream scrape captured 4,770 photo blobs but only 381 have URL-encoded SKU paths; the other 4,389 have opaque scrambled filenames with no product link. Resolving requires either a fuller re-crawl of `https://www.weplay.com.tw/UserFiles/images/Products/<XX>/<SKU>/` or a Vision-based image→description matching pass. Tracked in `docs/WEPLAY_PATH2_FOLLOWUP.md`.

---

## [2.8.3] - 2026-05-09

### Fixed — Cloud Build `db-migrate` step (npx could not resolve `medusa` bin)
- `cloudbuild.yaml` Step 3: `entrypoint: npx; args: [medusa, db:migrate]` → `entrypoint: npm; args: [run, db:migrate]`. After [2.8.2] unblocked the worker, the next pipeline run got further: build/push backend SUCCESS in ~3 min, but `db-migrate` failed with `npm error could not determine executable to run`. The Medusa v2 production image apparently doesn't expose `medusa` directly via `npx`, but the `db:migrate` script in `package.json` works. The Dockerfile already uses `npm run build` for the same reason.

---

## [2.8.2] - 2026-05-09

### Fixed — Cloud Build pipeline (10+ consecutive timeouts since 2026-05-05)
- `cloudbuild.yaml`: bumped `options.machineType` from `E2_MEDIUM` (1 vCPU / 4 GB) to `E2_HIGHCPU_8` (8 vCPU / 8 GB). Every push from 2026-05-05 onward was timing out at Step #0 `build-medusa-backend` → `Step 4/25 RUN npm ci`. Root cause: the 19,145-line Medusa v2 lockfile (`@medusajs/framework`, `@medusajs/medusa`, `@medusajs/admin-sdk`, `@medusajs/medusa-cli` and their transitive deps) plus `medusa build` plus a parallel Next.js docker build cannot fit inside a 1 vCPU / 4 GB worker before the 1 hr step deadline. Build log signature was deprecation warnings streaming with no error, then `context deadline exceeded` — pure CPU/memory thrashing, not a network or code issue.
- `medusa-backend/Dockerfile`: `RUN npm ci` → `RUN npm ci --prefer-offline --no-audit --no-fund`. Skips post-install audit + funding HTTP calls and prefers cache hits, typically saves 30–60 s on `npm ci` wall-clock.
- Net effect: PR #11 (verified brand-CI palettes + photo-first cards + Vortex logo contrast) and the 9 prior pushes were all built but never deployed to `catalogs.leka.studio`. This commit is what unblocks the trigger for all of them.

---

## [2.8.1] - 2026-05-09

### Added — Weplay onboarding (8th brand)
- Verified Weplay palette in Chrome at weplay.com.tw on 2026-05-09 via computed-style histogram across 3,000 elements: `#C7161E` red (126 hits, dominant), `#F0831E` orange (34), `#FED52B` yellow (5). Updated `brand-ci.ts` evidence + tagline ("We play, we learn — for the future.").
- Fixed `medusa-client.ts` `BrandConfig` for Weplay: `color` was the placeholder `#0099cc` cyan — corrected to verified `#C7161E` red. `hasCollections` flipped to `true` so collection filters render once products are imported.
- Wired Weplay into `scripts/sync_vendors_to_medusa.py` via a new `_resolve_sales_channel(slug)` helper: hardcoded slugs in `BRAND_SALES_CHANNELS` win, missing slugs fall back to env `LEKA_<SLUG>_SALES_CHANNEL_ID`. Lets a new brand import without an extra commit — set `LEKA_WEPLAY_SALES_CHANNEL_ID=sc_...` after creating the channel in Medusa Admin, then promote the value into the dict.

---

## [2.8.0] - 2026-05-08

### Reverted — `vendor-themes.ts` regression
Commit `70f0dcd` ("vendor-specific design systems for 6 brands") removed `brand-ci.ts` and replaced it with a parallel `vendor-themes.ts` system carrying fabricated palettes (Berliner navy+orange, Eurotramp red, Rampline lime+black, etc.). That code never deployed — live `catalogs.leka.studio` was still serving the v2.6.0 brand-CI lineage. Reverted in full so main now matches what's actually in production.

### Re-added on top of the revert (clean additions)
- `medusa-storefront/src/lib/image-scoring.ts` — `scoreImage` / `pickPrimaryImage` / `sortImagesByScore` penalize drawings/CAD/certs and reward photos so cards lead with the most marketable image.
- `medusa-storefront/public/placeholder-product.svg` — graceful fallback when an image URL fails.
- Wired `pickPrimaryImage` into `product-card.tsx` (with `onError` swap to the placeholder); `sortImagesByScore` into `product-detail.tsx` so the gallery's default-selected image is the best photo.

### Fixed — Card series-badge overlay
- Removed the `absolute top-2 left-2 badge` overlay on the product image; the series/collection name now lives next to the SKU in the card body with `truncate max-w-[60%]`. Long names no longer wrap onto the photo.

### Fixed — Vortex logo contrast on live PLP
- `medusa-storefront/public/brands/vortex/logo.svg`: added `fill="#FFFFFF"` so the wordmark renders white on the `#153CBA` blue header wrapper. The previous SVG had no `fill`, which defaulted to black on the dark blue background.

### Fixed — `brand-ci.ts` palettes vs verified vendor stylesheets
Re-audited every vendor's production CSS on 2026-05-08 and corrected the live brand themes. Confidence + evidence cited per brand inline.

| Brand | Old (was) | New (verified, in CSS) |
|---|---|---|
| Vinci | `#970260` magenta + `#182557` navy | `#8A3492` purple + `#FBBE2F` yellow + `#E9592C` orange |
| Berliner | `#00827A` teal (light) primary | `#00534F` (dark) primary, `#00827A` secondary, `#E6F3F2` accent |
| Eurotramp | `#0062AF` + `#6B9950` (wrong green) | `#0062AF` + `#63727F` slate + `#C80000` red accent |
| Rampline | `#182557` navy + `#970260` magenta | `#B5BC00` lime + `#2D5346` forest, paper `#F2F2EE` |
| 4soft | `#FFA900` amber primary (wrong) | `#0089CF` blue + `#CF0026` red + `#F99D1C` orange |
| Vortex | `#153CBA` + `#FFE000` yellow secondary | `#153CBA` + `#FF33D4` hot-pink secondary, yellow demoted to accent |
| WePlay | `#0099CC` cyan primary (wrong) | `#C7161E` red + `#F0831E` orange + `#FED52B` yellow |
| Wisdom | `#FCB822` amber + `#1D3A8A` navy (swapped) | `#1F4A83` navy + `#FBBE2F` amber — verified in Chrome at wisdomplaygroundsint.com (the actual vendor; not wisdomtoys.cn) |

### Added — `bodyVar` + `accent` on `BrandCI`
- `BrandPalette.accent?` for the third pop color most vendors carry (Eurotramp red, Vortex pink, Vinci orange, etc.) — exposed as `--brand-accent` and `bg-brand-accent` Tailwind utility.
- `BrandFonts.bodyVar` for vendors whose body font differs from heading (Vinci: Montserrat heading + Open Sans body; 4soft: Nunito + Lato; Vortex: Work Sans + Nunito) — exposed as `--brand-body` and `font-body`.
- New next/font imports: `Roboto_Condensed` (Eurotramp), `Work_Sans` (Vortex).

### Removed
- `docs/vendor-ds-preview.html` — was a static mockup of the abandoned `vendor-themes.ts` system, misleading anyone reviewing the storefront.

### Files changed
- `medusa-storefront/src/lib/brand-ci.ts` — verified palettes, evidence comments, `accent` + `bodyVar` fields
- `medusa-storefront/src/app/layout.tsx` — add Roboto_Condensed + Work_Sans fonts
- `medusa-storefront/src/app/[brand]/layout.tsx` — wire `--brand-accent` + `--brand-body`
- `medusa-storefront/tailwind.config.ts` — add `brand.accent` color + `font-body` family
- `medusa-storefront/src/components/product-card.tsx` — image scoring, onError fallback, series moved to body
- `medusa-storefront/src/app/[brand]/[handle]/product-detail.tsx` — gallery default uses `sortImagesByScore`
- `medusa-storefront/src/lib/image-scoring.ts` (new)
- `medusa-storefront/public/placeholder-product.svg` (new)
- `medusa-storefront/public/brands/vortex/logo.svg` — `fill="#FFFFFF"`
- `docs/vendor-ds-preview.html` (deleted)

### Outcome
TypeScript clean (`tsc --noEmit`). Live deployment lineage preserved; `main` once again represents what users see.

---

## [2.7.0] - 2026-05-07

### Added — Wisdom catalog Category → Sub-category selector + price/material filters

- **Storefront FilterBar** ([medusa-storefront/src/components/filter-bar.tsx](medusa-storefront/src/components/filter-bar.tsx)): top-level `<select>` now drives a dependent Sub-category `<select>`, populated from each parent's `category_children`. Hidden when no brand category has subcategories so Vinci/Berliner/4soft/Vortex/Eurotramp/Rampline render unchanged.
- **Wisdom-only filters**: USD min/max price range + Material dropdown (Wood, Rubber wood, Plastic, Metal, Fabric, Foam — bucketed from messy `metadata.material` strings via regex). Gated by a new `BrandConfig.hasMaterialFilter` flag in [medusa-storefront/src/lib/medusa-client.ts](medusa-storefront/src/lib/medusa-client.ts) (set on Wisdom only).
- **CatalogContent** ([medusa-storefront/src/app/[brand]/catalog-content.tsx](medusa-storefront/src/app/[brand]/catalog-content.tsx)): loads categories with `parent_category_id` and builds a `{id, name, handle, children[]}` tree. Subcategory selection short-circuits the parent on the Medusa `category_id` query. Filter state mirrored to the URL (`?q=&category=&subcategory=&material=&min_price=&max_price=`) so deep-links and Reset both work.
- **Backend support** ([shared/medusa_importer.py](shared/medusa_importer.py)): `get_or_create_category()` now takes optional `parent_category_id`; new `add_categories_to_product()` and `_patch()` helpers for product-category linking.
- **One-shot importer** ([wisdom-catalog/import_subcategories_to_medusa.py](wisdom-catalog/import_subcategories_to_medusa.py)): reads the same Excel that `import_to_medusa.py` ingests, derives `(category, subcategory)` via `shared/category_mapper.py`, ensures child categories exist under each parent (handle: `wisdom-<cat>-<sub>`), and PATCHes each Wisdom product to add the child category id alongside the parent. Idempotent + `--dry-run`. Dry-run on the deployed backend reported **80 child categories / 1,321 product links**; real run completed successfully.

### Files changed
- `medusa-storefront/src/components/filter-bar.tsx`
- `medusa-storefront/src/app/[brand]/catalog-content.tsx`
- `medusa-storefront/src/lib/medusa-client.ts`
- `shared/medusa_importer.py`
- `wisdom-catalog/import_subcategories_to_medusa.py` (new)

### Outcome
- Wisdom shoppers can now drill Furniture → Cabinet / Table / Chair / Shelf / Bed / Desk / Bench / Fence / Kitchen / House / Play-structure (and similar leaves under Playground, Outdoor, Nature Play, etc.), narrow by material, and clamp by USD price.
- Other six brand catalogs untouched at the UI level — sub-category dropdown stays hidden when no parent has children.

---

## [2.6.0] - 2026-05-07

### Added — Per-brand corporate identity (logos, palettes, fonts) on storefront

Each brand catalog page now renders the vendor's real corporate identity instead of a generic letter-badge.

- **Logos** — scraped from each vendor's public homepage and stored under `medusa-storefront/public/brands/<slug>/`:
  - Wisdom, Berliner, Eurotramp, Rampline, Vortex, WePlay → real logos
  - Vinci → white logo on brand-magenta background wrapper
  - 4soft → no public logo asset; falls back to letter badge styled with brand primary
- **Palettes** — full 4-color palette (`primary`, `secondary`, `ink`, `paper`) per brand, exposed as CSS variables (`--brand-primary` etc.) set at the brand layout root. Tailwind exposes them as `bg-brand-primary`, `text-brand-ink`, etc.
- **Fonts** — Manrope stays for body text across all brands; headings now use a brand-specific Google Font loaded once via `next/font/google`:
  Wisdom→Poppins, Vinci→Montserrat, Berliner→Roboto, Eurotramp→Open Sans, Rampline→Lato, 4soft→Nunito (verified from 4soft.cz CSS), Vortex→Inter, WePlay→Nunito.
- **Favicons** — each `/[brand]` page sets its own browser-tab icon via `generateMetadata`.
- **WePlay (8th brand stub)** — added as a `BrandConfig` entry with `productCount: 0`. No Sales Channel yet, so the route renders a "Catalog coming soon" placeholder using the brand CI. `NEXT_PUBLIC_WEPLAY_PUBLISHABLE_KEY` placeholder added to `env.example`. Sales Channel + product import is a follow-up task.
- **Components updated** — `SeriesBadges` and `ProductCard` now use `var(--brand-primary)` / `var(--brand-secondary)` instead of hardcoded `badge-purple` / `badge-navy` / `badge-amber` classes; series filters and price labels match the brand.

**Files changed**:
- NEW `medusa-storefront/src/lib/brand-ci.ts` — typed CI registry for 8 brands
- NEW `medusa-storefront/public/brands/<slug>/{logo.*, favicon.*}` — 8 brand asset folders
- `medusa-storefront/src/app/layout.tsx` — load 7 brand fonts, attach CSS variable classes to `<html>`
- `medusa-storefront/src/app/[brand]/layout.tsx` — `<Image>` logo, brand CSS-var injection, `font-heading` on brand name
- `medusa-storefront/src/app/[brand]/page.tsx` — per-brand favicon
- `medusa-storefront/src/app/[brand]/catalog-content.tsx` — WePlay-style "coming soon" branch for stub brands
- `medusa-storefront/src/components/series-badges.tsx` — brand-primary active state, drops hardcoded `BADGE_COLORS` array
- `medusa-storefront/src/components/product-card.tsx` — series/NEW badges + price use brand palette
- `medusa-storefront/src/lib/medusa-client.ts` — `weplay` entry added to `BRANDS`
- `medusa-storefront/tailwind.config.ts` — `colors.brand.*` and `fontFamily.heading` mapped to CSS vars
- `medusa-storefront/tsconfig.json` — `types: ["node"]` added to scope @types resolution (parent-root @types/caseless was breaking the build)
- `medusa-storefront/env.example` — Vortex and WePlay publishable-key placeholders

**Outcome**: clean `npm run build` (Next 15.5 / TS strict). Each `/[slug]` route is now visually distinct on a per-vendor basis. Letter-badge fallback keeps the page rendering even if a logo asset is missing.

## [2.5.2] - 2026-05-07

### Fixed — Cross-brand series badges showing on wrong brand pages

**Root cause**: `medusa.store.collection.list()` returns all 56 collections globally regardless of the publishable API key's sales channel scope. Every brand with `hasCollections: true` was displaying all 56 collection badges from all vendors.

- **Symptom**: Berliner Seilfabrik page showed Vinci series (Active, Arena, Castillo, etc.) alongside its own Berliner series — and vice versa for all 4 collection brands.
- **Root cause**: Medusa's store collections API does not filter by sales channel — it returns all collections in the database regardless of which publishable key is used in the request header.
- **Fix**: Added `collectionPrefix?: string` to `BrandConfig` interface and set a per-brand prefix. After the API fetch, collections are filtered client-side:
  - `berliner-*` → Berliner Seilfabrik (15 collections → 18 after handle audit)
  - `4soft-*` → 4soft (3 collections)
  - `vortex-*` → Vortex Aquatics (8 collections)
  - `undefined` (Vinci) → all handles that do NOT start with any other vendor's prefix (27 Vinci collections)
- **Files changed**: `medusa-storefront/src/lib/medusa-client.ts`, `medusa-storefront/src/app/[brand]/catalog-content.tsx`
- **Deployed**: Cloud Build `25da4b21`, storefront revision `accae83`

### Verified (post-fix browser audit — all collection brands passing)
| Brand | Series shown | Correct |
|-------|-------------|---------|
| Vinci Play | 27 (Vinci-only handles) | ✓ |
| Berliner Seilfabrik | 18 (all "Berliner *") | ✓ |
| 4soft | 3 (4soft Tunnels & Furniture, 3D Elements, 2D Graphics) | ✓ |
| Vortex Aquatics | 8 (all "Vortex — *") | ✓ |

---

## [2.5.1] - 2026-05-07

### Fixed — CORS misconfiguration blocking all brand catalogs + Vortex missing key

**Root cause: all brand catalog pages showed "No products found"** due to two independent bugs found during a full frontend status audit.

#### Bug 1 — STORE_CORS pointed to raw Cloud Run URL (critical, global)
- **Symptom**: Every brand page returned 0 products. Browser console: `TypeError: Failed to fetch`. `no-cors` mode returned opaque response confirming CORS — not network — was failing.
- **Root cause**: `STORE_CORS` env var on `leka-medusa-backend` was set to `https://leka-medusa-storefront-538978391890.asia-southeast1.run.app` (the raw Cloud Run URL from initial deploy), not the custom domain `https://catalogs.leka.studio`. The backend was never redeployed after the custom domain was configured. Preflight OPTIONS returned empty `Access-Control-Allow-Origin`.
- **Fix**: `gcloud run services update leka-medusa-backend --update-env-vars STORE_CORS=https://catalogs.leka.studio,AUTH_CORS=...` — new revision `00012-6sh`. CORS now returns `Access-Control-Allow-Origin: https://catalogs.leka.studio`.
- **Also note**: `cloudbuild.yaml` backend deploy step already had the correct `STORE_CORS=https://catalogs.leka.studio` — the stale value was from a pre-custom-domain manual deploy.

#### Bug 2 — NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY missing from storefront build
- **Symptom**: Vortex catalog specifically showed 0 products (would have been visible after Bug 1 was fixed).
- **Root cause**: `NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY` build-arg was missing from both `cloudbuild.yaml` and `cloudbuild-storefront-only.yaml`. The key resolved to `""` in the bundle, so the Medusa store API rejected the auth.
- **Fix**: Added `--build-arg NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY=pk_df5eb6c3d0032c6baebe18bec7b3be1cdb024ba5efd3833cac2b8517432c56dc` (retrieved from Medusa Admin API) to both Cloud Build files. Redeployed storefront (Cloud Build `fa376c2b`, revision `00011-mkn`).
- **Files changed**: `cloudbuild.yaml`, `cloudbuild-storefront-only.yaml`

### Verified (post-fix browser audit — all passing)
| Brand | Products | Images | Status |
|-------|----------|--------|--------|
| Wisdom | 5,062 | ✓ (GCS proxy, ~8s warm-up) | ✓ |
| Vinci Play | 1,096 | ✓ (external CDN) | ✓ |
| Berliner Seilfabrik | 466 | ✓ (GCS proxy) | ✓ |
| Eurotramp | 80 | ✓ (GCS proxy) | ✓ |
| Rampline | 54 | ✓ (GCS proxy) | ✓ |
| 4soft | 391 | ✓ (GCS proxy) | ✓ |
| Vortex Aquatics | 521 | ✓ (GCS proxy) | ✓ |

### Known issues (not blocking)
- **Cross-brand series badges**: Brands with `hasCollections: true` (Vinci, Berliner, 4soft, Vortex) all show the same 56 series badges from ALL brands. Medusa's `store/collections` API returns all collections regardless of the publishable key's sales channel scope. Fix: scope collections to the sales channel in Medusa, or filter client-side by handle prefix.
- **Vortex product count 521 vs 272**: Vortex Sales Channel appears to include products from multiple brands. Needs sales channel audit in Medusa Admin.
- **Image warm-up latency**: `/_next/image` optimization on 512Mi Cloud Run takes ~5–8s for first-load batches of 48 large (2560×2560) images. Consider bumping storefront memory to 1Gi or pre-warming.

## [2.5.0] - 2026-05-05

### Added — Phase 4: image bucket migration + private-via-proxy serving

Product images for the 6 GCS-resident leka brands moved from the public `gs://ai-agents-go-documents/product-images/<slug>/` to a project-prefixed, **private** bucket `gs://ai-agents-go-vendors/<slug>/`. Public access prevention stays enabled on the new bucket; the Cloud Run storefront fronts it via a Next.js image proxy. Vinci images stay external (zamowienia.vinci-play.pl).

- **GCS copy** — 5.30 GB across wisdom (2.29 GB), berliner (1.97 GB), vortex (953 MB), rampline (57 MB), eurotramp (17 MB), 4soft (8 MB), copied with `gcloud storage cp -r`. Slug-based folder names for consistency with existing `durasein/`, `gumtec/`, `zelk/` etc.
- **Image proxy** [medusa-storefront/src/app/api/i/[...path]/route.ts](medusa-storefront/src/app/api/i/[...path]/route.ts) — Next 15 route handler. Reads private GCS via the Cloud Run runtime SA (`538978391890-compute@developer.gserviceaccount.com`, ADC token from metadata server, cached until ~5 min before expiry). Streams response with `Cache-Control: public, max-age=86400, immutable`. Preserves raw URL path so encoding (single vs double `%20`) survives end-to-end. Allowed in [next.config.js](medusa-storefront/next.config.js).
- **URL rewriter** [scripts/rewrite_image_urls_to_vendors_bucket.py](scripts/rewrite_image_urls_to_vendors_bucket.py) — sweeps `vendors/{slug}/products` (Firestore DB `vendors`) AND Medusa Admin API for each brand's sales channel, rewriting `images[].url` (and Medusa `thumbnail`) from old-bucket public URLs to proxy URLs. Idempotent; supports `--target-base` so the same script can target direct GCS or the storefront proxy. Running counts:
  - 4soft: 780 + 780 (firestore + medusa) = 1,560 URLs
  - eurotramp: 1,326 + 1,326 = 2,652 URLs (79 external images preserved)
  - rampline: 127 + 127 = 254 URLs
  - vortex: 0 + 1,949 = 1,949 URLs (Firestore subcollection empty by design)
  - berliner: 3,969 + 3,969 = 7,938 URLs (8 external preserved)
  - wisdom: 5,910 + 5,900 = 11,810 URLs (first pass) + 328 + 328 = 656 URLs (verified/ mop-up) = 12,466 URLs
  - **Grand total: 26,819 URLs rewritten across both stores, 0 errors, 0 unknown hosts, 0 `no_match` remaining.**
  - Plus 582 4soft GCS objects renamed (`%20` → space).
- **Cloud Build** — added [cloudbuild-storefront-only.yaml](cloudbuild-storefront-only.yaml) for storefront-only deploys when the backend hasn't changed (skips medusa-backend build + db-migrate). [cloudbuild.yaml](cloudbuild.yaml) hardcoded `_AR_REPO` project to `ai-agents-go` because `$PROJECT_ID` was not recursively expanding inside the substitution.
- **.gcloudignore** added to keep `gcloud builds submit` archives small (807 KiB vs. 500+ MB unfiltered).

### Fixed (same release)

- **4soft literal `%20` filenames**: long-standing image rendering bug. The catalog scrape had uploaded 582 objects with literal `%20` characters in their GCS object names (so single-encoded URLs in Medusa decoded to spaces at GCS and 404'd). One-shot rename via [scripts/rename_4soft_literal_pct20.py](scripts/rename_4soft_literal_pct20.py) replaces literal `%20` with real spaces in every affected object name. After rename, every existing single-encoded Medusa URL resolves correctly. 582 files renamed in 13 sec, 0 errors.
- **Wisdom 328 `no_match`**: traced to a `verified/` sibling folder under `gs://ai-agents-go-documents/product-images/` (not under `wisdom/`), used by ~200 wisdom products for quality-curated catalog imagery. Copied to `gs://ai-agents-go-vendors/wisdom/verified/` (2,253 files / 19 MB) and extended the rewriter with a `BRAND_EXTRA_PREFIXES` map so `verified/` is recognized as a wisdom-owned alt prefix.

### Known issues

- (none currently — both above resolved)
- Phase 5 (archive + delete `leka-product-catalogs` Firestore DB) is gated on a 2-week green canary on `vortex-daily-refresh`.
- `scripts/seed_medusa_api.py:16-17` still hardcodes admin password (Rule 12 violation, pre-existing).

## [2.4.0] - 2026-05-04

### Added — Migration to vendors-rooted Firestore architecture (Phases 0-3)

Source-of-truth product data moved from `leka-product-catalogs` Firestore database (flat `products_{brand}` layout) to the `vendors` database (`vendors/{slug}/products` hierarchical layout owned by the `vendors` project). Plan: `~/.claude/plans/inspect-our-project-database-wise-feigenbaum.md`.

- [migration/vendors_target_schema.md](migration/vendors_target_schema.md) — target schema, slug registry, leka→vendors mapping rules.
- [scripts/migrate_leka_to_vendors.py](scripts/migrate_leka_to_vendors.py) — Phase 1 one-shot. Reads `products_{brand}`, `product_categories_{brand}`, brand-filtered `quotations`; writes `vendors/{slug}/products|product_categories|quotations` and the vendor root doc. **Run live**: wisdom (5,071 products), vinci (1,113 products + 6 categories), vortex (0 products in leka — already canonical in vendors). Total: 6,184 products migrated.
- [scripts/reverse_import_medusa_to_vendors.py](scripts/reverse_import_medusa_to_vendors.py) — Phase 2 one-shot. For brands that had no Firestore source (berliner / eurotramp / rampline / 4soft), reads them back from Leka Medusa Admin API and writes to `vendors/{slug}/products`. **Run live**: berliner (466), eurotramp (80), rampline (54), 4soft (391). Total: 991.
- [scripts/sync_vendors_to_medusa.py](scripts/sync_vendors_to_medusa.py) — Phase 3 generalized sync. Reads `vendors/{slug}/products` and upserts into Medusa via Admin API (handle lookup → create/update → variant USD price). Replaces (does not yet remove) the brand-specific TS scrapers and `seed_medusa_api.py`. Smoke-tested with `--brand=rampline --limit=5 --dry-run`: 5/5 UPDATE, 0 errors. Vortex sync continues to run via the existing `vortex-refresh` Cloud Run Job.

### Pending

- Phase 4: live sync run + storefront smoke test on a sampled product per brand.
- Phase 5: archive leka Firestore DB to `migration/leka-firestore-archive/` and delete the database after a 2-week green-sync window.

## [2.3.0] - 2026-04-21

### Added — Vortex Aquatics brand (272 products · 1,949 images mirrored)

- New brand folder [vortex-catalog/](vortex-catalog/) mirrors the vinci-catalog pattern
- **Scraper** [vortex-catalog/scrape_catalog.py](vortex-catalog/scrape_catalog.py) — hybrid WP REST + HTML approach against www.vortex-intl.com
- **Image mirror** [vortex-catalog/mirror_images_to_gcs.py](vortex-catalog/mirror_images_to_gcs.py) — uploads images to `gs://ai-agents-go-documents/product-images/vortex/catalog/`
- **Medusa importer** [vortex-catalog/import_to_medusa.py](vortex-catalog/import_to_medusa.py) — creates "Vortex Aquatics" Sales Channel + publishable API key, category `water_play`, 7 collections (one per product-type)
- **Static web-app** [vortex-catalog/web-app/](vortex-catalog/web-app/) — Flask + vanilla JS catalog browser, deploys to Cloud Run service `vortex-catalog`
- **Design System** [vortex-catalog/DESIGN_SYSTEM.md](vortex-catalog/DESIGN_SYSTEM.md) — tokens derived from live vortex-intl.com theme CSS (primary `#153cba`, accent `#ff33d4`, water `#6ed4fc`, Nunito + Work Sans)
- **Vortex logo** — SVG extracted from the live theme sprite, stored at [vortex-catalog/web-app/public/assets/vortex-logo.svg](vortex-catalog/web-app/public/assets/vortex-logo.svg)
- **Gmail outreach draft** — saved in user's Drafts addressed to Vicky Denisova (current Vortex account manager) requesting the 2026 pricelist & latest catalogs

### Changed

- [shared/medusa_importer.py](shared/medusa_importer.py) — added `get_or_create_sales_channel()`, `create_publishable_api_key()`, and optional `sales_channel_ids` kwarg to `create_product()` so future brand importers can attach products to a dedicated Sales Channel at create time.

## [2.2.0] - 2026-04-09

### Added — Vendor Product Catalogs (991 products, 4 brands)
- Scraped and uploaded 4 vendor catalogs to Medusa:
  - Berliner Seilfabrik (466 products) — rope play equipment, Germany
  - Eurotramp (80 products) — trampolines, Germany
  - Rampline (54 products) — motor skill equipment, Norway
  - 4soft (391 products) — EPDM surfaces, Czech Republic
- Created Sales Channels + publishable API keys per vendor
- Added vendor brand pages to storefront (6 brands total)
- Fixed 15 failed product uploads (SKU deduplication, handle sanitization)
- Bulk-published all 991 vendor products
- GCS image re-hosting script (`scripts/rehost-images-to-gcs.ts`)
- Vendor scraper scripts: `scripts/scrape-{berliner,eurotramp,rampline,4soft}.ts`
- Unified upload script: `scripts/upload-vendors-to-medusa.ts`

### Changed
- Updated product card and detail page to handle vendor metadata format
- Added vendor CDN image domains to Next.js config
- Updated cloudbuild.yaml with all 6 vendor publishable API keys
- Applied SEO metadata (generateMetadata) to brand and product pages
- Wired up quotation accept/reject workflow

## [2.1.1] - 2026-04-07

### Added — Product Data Seeded
- Exported 6,219 documents from Firestore (5,071 Wisdom + 1,113 Vinci + categories + quotations)
- Seeded 6,151 products via Medusa Admin API (5,056 Wisdom + 1,095 Vinci)
- Created Admin API seed script (`scripts/seed_medusa_api.py`) for remote seeding
- Created Sales Channels: Wisdom, Vinci Play (with publishable API keys)
- Created Region: Asia-Pacific (USD, 5 countries)
- Created admin user (admin@leka.studio)
- Rebuilt storefront with API keys baked in via Docker build args

## [2.1.0] - 2026-04-07

### Deployed — GCP Infrastructure & Cloud Run Services
- Cloud SQL PostgreSQL: `areda-medusa` / `leka_medusa` (asia-southeast1)
- Memorystore Redis: `leka-medusa-redis` (10.225.88.67:6379)
- VPC Connector: `leka-connector` (10.8.0.0/28)
- Secret Manager: 4 secrets (database-url, redis-url, cookie-secret, jwt-secret)
- **Medusa Backend**: https://leka-medusa-backend-538978391890.asia-southeast1.run.app
- **Next.js Storefront**: https://leka-medusa-storefront-538978391890.asia-southeast1.run.app

### Fixed — Docker Build & Deployment Issues
- Added ts-node + typescript as production dependencies (Medusa CLI needs them at runtime)
- Fixed medusa-config.ts: use module:nodenext for ts-node compatibility, export default
- Removed custom modules array from config (Medusa v2.13 includes all modules by default)
- Added @medusajs/admin-sdk peer dependency for draft-order admin UI
- Compiled medusa-config.ts to .js via ts.transpileModule for runtime fallback
- Added start.sh with db:migrate before server start
- Fixed CRLF line endings with .gitattributes + sed in Dockerfile
- Switched from Cloud SQL Unix socket to public IP (Unix socket URL format incompatible with MikroORM)
- Added DISABLE_ADMIN env var to skip admin UI when build output missing

## [2.0.1] - 2026-04-07

### Added — Sprint 1: Cart Flow, Filters, i18n, Loading States
- Cart state management (`lib/cart.ts`) with localStorage persistence per brand
- Slide-out cart drawer component with quantity controls
- Add-to-cart handler on product detail page with loading/success feedback
- Age group filter dropdown (Vinci-specific, matching current site)
- Product/series count stats in catalog header
- Download count icon on product cards
- "NEW" badge on product cards from tags
- Loading skeleton for catalog page
- 404 pages (brand-scoped and root)
- Locale switcher component (EN/TH/CN) with i18n library
- Mobile-responsive header with cart drawer
- Region setup (Asia-Pacific, USD, 5 countries) in seed script
- Manual fulfillment and payment provider setup in seed script
- Publishable API key generation per sales channel

## [2.0.0] - 2026-04-06

Renamed from [1.0.0].

## [1.0.0] - 2026-04-06

### Changed — Medusa Commerce v2 Migration
- **Backend**: Migrated from Python/Flask/Firestore to Medusa Commerce v2 (TypeScript/Node.js/PostgreSQL)
- **Frontend**: Migrated from vanilla JS static app to Next.js 15 with Tailwind CSS
- **Database**: Migrated from Firestore to Cloud SQL PostgreSQL 15
- **Architecture**: Products now managed via Medusa Admin API with Sales Channels per brand

### Added
- `medusa-backend/` — Medusa v2 backend with custom API routes for specifications and downloads
- `medusa-storefront/` — Next.js storefront with Leka Design System (Tailwind)
- Full e-commerce: cart, checkout, customer accounts, order management
- Multi-brand via Medusa Sales Channels (Wisdom, Vinci Play)
- Product detail pages (replaces modal) with image gallery, specs, downloads, certifications
- Customer authentication (login, register, order history)
- `scripts/export_firestore_to_json.py` — Firestore data export for migration
- `medusa-backend/src/scripts/seed-from-firestore.ts` — Medusa seed script
- `shared/medusa_importer.py` — Medusa Admin API import helper
- `wisdom-catalog/import_to_medusa.py` — Wisdom Excel → Medusa importer
- `vinci-catalog/import_to_medusa.py` — Vinci JSON → Medusa importer
- Updated `cloudbuild.yaml` for multi-service build (backend + storefront)

### Deprecated
- `src/main.py` (Flask gateway) — replaced by Medusa backend
- `*/import_to_firestore.py` — replaced by `*/import_to_medusa.py`
- `vinci-catalog/web-app/` — replaced by `medusa-storefront/`
- Firestore collections — data migrated to PostgreSQL

## [0.5.0] - 2026-04-01

### Added — Full Vinci Play Catalog (1,172 products)
- Full website scrape of all 29 Vinci Play series (1,172 products)
- Firestore import to `products_vinci` collection with category index
- Brand registration in `brands/vinci`
- Redeployed web app with complete product data

### Fixed
- Service account credential path case mismatch (eukri → Eukrit)

## [0.4.0] - 2026-04-01

### Added — Vinci Play Web App & Cloud Run Deployment
- Web app with Leka Design System for browsing Vinci Play products
- Dockerfile and Cloud Build config for containerized deployment
- Cloud Run service `vinci-catalog` at https://vinci-catalog-538978391890.asia-southeast1.run.app
- Artifact Registry repo `leka-product-catalogs` in asia-southeast1
- 47 Spring series products with static JSON data
- `.dockerignore` and deploy instructions

## [0.3.0] - 2026-03-30

### Added — Vinci Play Brand
- `vinci-catalog/` brand folder with complete scraping and import pipeline
- `scrape_catalog.py` — full website scraper for vinci-play.com (29 series, ~1,000+ products)
  - Extracts: product info, specifications, images, drawings, downloads, certifications
  - Supports `--resume` for checkpoint/resume and `--series` for single-series scraping
  - Rate-limited with retry logic for reliability
- `import_to_firestore.py` — imports scraped JSON to `products_vinci` collection
  - Supports `--dry-run` for preview mode
- `firestore_schema.json` — Vinci-specific schema documentation
- `DEPLOYMENT_LOG.md` — brand-specific deployment tracking
- Firestore composite indexes for `products_vinci`
- Added `requests` and `beautifulsoup4` to requirements.txt

## [0.2.0] - 2026-03-30

### Added
- Multi-brand data architecture with separate Firestore collections per brand (`products_{brand}`)
- `shared/` module with reusable utilities: `base_importer.py`, `category_mapper.py`, `image_pipeline.py`
- Brand registry collection (`brands`) in Firestore
- Per-brand category collections (`product_categories_{brand}`)
- `status` field (active/discontinued/draft) on all products
- `brand` field on products and quotations
- `tags` array field for free-form product tagging
- `description_th` field for Thai product names

### Changed
- Wisdom importer now writes to `products_wisdom` collection (was `products`)
- Firestore rules updated for wildcard brand collections
- Composite indexes added for `products_wisdom`
- Root service (`src/main.py`) now reads from Firestore `brands` collection
- Version bumped to 0.2.0

## [0.1.0] - 2026-03-30

### Added
- Initial project structure from goco-project-template
- Python 3.11 runtime with Flask health endpoint
- Cloud Build pipeline (cloudbuild.yaml) for CI/CD
- Dockerfile for Cloud Run deployment
- verify.sh post-build verification script
- Leka Design System configuration
- Wisdom brand catalog (5,071 products) — migrated from product-catalogs repo
- Firestore rules and composite indexes
- Multi-brand architecture with per-brand subfolders
