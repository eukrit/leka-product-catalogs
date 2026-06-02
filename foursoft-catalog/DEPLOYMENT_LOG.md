# 4soft — Deployment Log

Brand: **4soft, s.r.o.** (Tanvald, Czech Republic · VAT CZ28703324 · graphics@4soft.cz / roger@4soft.cz)
Slug: `4soft` · Medusa sales channel: `sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y`
Pricing config: `pricing_config/canonical.brands.4soft` (db `leka-product-catalogs`)
Products: `vendors/4soft/products` (db `vendors`)

---

## 2026-06-02 — Recorded 2.5% prepay + 2.5% e-shop discounts as available-but-NOT-applied

- **Context:** the 20% flat discount (entry below) is the **basic** EXW reseller rate.
  Supplier 4soft (Roger, email 2026-05-31) additionally offers a **2.5% prepayment**
  discount and a **2.5% e-shop** discount. Per user decision (2026-06-02) these stay
  **NOT applied** — the catalog is held at the 20% basic rate for now.
- **Annotation only — no reprice.** `pricing_config/canonical.brands.4soft` now carries:
  - `additional_discounts_available = { prepayment_pct: 0.025, eshop_pct: 0.025, applied: false }`
  - `additional_discounts_note` documenting the decision (ASCII).
  `exw_discount` stays `0.20`, `gross_margin` stays `0.40`. `vendors/4soft/products`
  and Medusa variant prices are **unchanged** (already at 20% from the entry below).
- **Verification (read-only, 2026-06-02):** Firestore + Medusa SGD match at 20% on
  spot-checked codes — C5-01A-05 S$1374.47, G2-14A-02 S$284.61, V9-01A-001 S$11048.45;
  Dulwich R2 proposal live (HTTP 200), 4soft = optional add-on.

---

## 2026-06-02 — Flat 20% reseller discount applied LIVE (sea-LCL retained)

- **User decision (2026-06-02):** raise the EXW reseller discount **15% → 20% flat**
  (`eur_fob = list × 0.80`). Stay on the **sea-LCL** freight basis — the air pivot
  (v2.45.0) remains dry-run only.
- **2026-05-31 pricelist file** (`2026-05-31 4soft_EPDM_graphics-price_list_2025.xls`)
  diffed against the committed 2025 list: **2,410 SKUs, 0 added / 0 removed / 0 price
  changes** — it is a re-export of the same 2025 list (internal header still
  "Valid from 1.3.2025"). So only the discount changed; list prices are unchanged.
- **Code:** `import_pricelist.py` reverted `METHOD="air"→"lcl"` and restored the
  sea-LCL Baltic per-CBM dims_scaled branch; module `EXW_DISCOUNT 0.15→0.20`.
- **Firestore `pricing_config/canonical.brands.4soft`:** `exw_discount=0.20`
  (read-modify-write merge; gm 0.40 unchanged).
- **Firestore `vendors/4soft/products`:** 2,410 docs repriced. FX this run:
  USD 33.254, EUR 38.689, SGD 26.009. By CBM method: dims_scaled 251 / flat_uplift
  2,159. Clamp: none 177 / floored 2,061 / capped 172.
- **Medusa** (`sync_brand_prices_to_medusa.py --brand 4soft --write`): **2,394
  updated, 0 errors**, 16 unmatched (packaging/accessory not in Medusa).
- **Price impact:** median **−5.80%** vs the 15% basis (≈ 0.80/0.85). 0 zero/negative.
  13 SKUs near the €500 FOB tier boundary rose ≤9% (lower FOB drops them into the
  higher-floor tier — existing clamp model behaviour, not a regression).
- **Dulwich R2 proposal** (`sync_dulwich_epdm_prices.py --write`): the 22 EPDM lines
  refreshed in place via the draft-order edit workflow. **The confirm produced a new
  draft-order id** `order_01KT33G0MZFM06NNS0GA3HWEFE` (display #12), replacing the
  prior `order_01KSTN74NRPQ3DGETVHERQ1Z2G` (#10). 51 lines intact, 22/22 EPDM at 20%.
  ⚠️ Scripts hardcoding the old id (`scripts/_sync_draftorder_prices.py`,
  `build_r2_curated.py`'s delete-by-`rev` is safe) must be repointed to #12.
- **Audit deliverables:** `docs/reports/4soft-pricing-audit.html`,
  `foursoft-catalog/data/4soft_pricing_audit.csv`, `dulwich_r2_vs_medusa.csv`.
- **Unchanged:** the 29 Wisdom proposal lines (separate pricing path; 6 still S$0 —
  pre-existing, out of scope here) and the sea-tuned `LOGISTICS_TIERS`.

### Run commands
```bash
# config already set: brands.4soft.exw_discount=0.20
python foursoft-catalog/import_pricelist.py --no-seed --xls ".../2026-05-31 4soft_EPDM_graphics-price_list_2025.xls"
python scripts/sync_brand_prices_to_medusa.py --brand 4soft --write
python foursoft-catalog/sync_dulwich_epdm_prices.py --write
```

---

## 2026-05-30 — v2.45.0-dryrun — Air-freight pricing pivot (dry-run, NOT deployed)

- **Scope:** switch the pricing engine from sea-LCL to air freight (4soft ships
  Czech Republic → Thailand by air, not by sea). Dry-run only — Firestore and
  Medusa untouched. Awaiting user sign-off before promoting.
- **Cross-repo changes:**
  - `shipping-automation/mcp-server/cost_engine.py` — added chargeable-weight
    (volumetric kg = cbm × 167) to the `air` branch of `calc_freight`; added
    `volumetric_divisor_kg_per_m3` to the EU air method; fixed stale
    `VENDOR_COUNTRY_MAP["4soft"]` from `china` → `europe`.
  - `foursoft-catalog/import_pricelist.py` — `METHOD="lcl"` → `"air"`; new
    CLI flags `--air-rate`, `--landed-csv`, `--load-dims`; per-SKU override
    pattern (overrides air `per_kg` and zeroes `min_charge` for the call
    window, since 5 000 THB shipment minimum doesn't apply per-SKU).
- **Rate research:** [air-freight-rates-2026-05-30.md](./data/air-freight-rates-2026-05-30.md).
  No public PRG→BKK spot rate available; used 6 backhaul-relevant data points
  (Xeneta Europe-origin avg, WorldACD week-18 + April global yields, FreightAmigo
  FRA→HKG, TH→EU reverse proxy, Suaid EU→USA). Low **90 / median 105 / high
  135 THB/kg chargeable**, all-in (FSC + SSC + war-risk included). Volumetric
  divisor 167 kg/m³ (IATA general cargo).
- **Dry-runs:** 3 runs at 90 / 105 / 135 THB/kg. FX this run: USD 33.25,
  EUR 38.71, SGD 26.04 (exchangerate-api.com + 2% buffer). dim_index from
  Firestore: **520 docs indexed** (was 338 in previous runs).
- **Diff doc:** [air-freight-dryrun-diff-2026-05-30.md](./data/air-freight-dryrun-diff-2026-05-30.md)
  with 10 representative SKUs + summary stats.
- **Headline counts under MID (105 THB/kg):**
  - `dims_scaled` 251, `flat_uplift` 2 159 (unchanged from OLD — 0 byte-diffs)
  - clamp `none` 198 → 207 (+9), `floored` 2 045 → 2 069 (+24), `capped` 167 → 134 (–33)
  - p90 landed THB: 75 680 → 63 575 (–16%) — heavy tail lighter under air
    because the 18 000 THB LCL clearance fee drops to 3 800 THB for air
- **Tests:** new `TestAirFreightChargeable` (7 cases) in
  `shipping-automation/tests/test_pricing_engine.py`. 26/26 pass.
- **`LOGISTICS_TIERS` untouched** — still sea-tuned. Retune is a follow-up PR
  after the user reviews the dry-run diff (per plan §4).
- **Decisions deferred to the user:**
  1. Pick a baseline rate (LO 90 / **MID 105 recommended** / HI 135 THB/kg).
  2. Decide whether to retune `LOGISTICS_TIERS` now or in a follow-up PR.
  3. Investigate the suspiciously small CBM on A6-01A-00 (0.0002 m³ for a
     40 cm hexagon mat — probably a missing-thickness default).

### Run commands
```bash
# Engine unit tests
cd C:/Users/Eukrit/OneDrive/Documents/Claude Code/shipping-automation
python -m pytest tests/test_pricing_engine.py -v

# Dry-runs (worktree: inspiring-chandrasekhar-c387ff)
cd C:/Users/Eukrit/OneDrive/Documents/Claude Code/leka-product-catalogs/.claude/worktrees/inspiring-chandrasekhar-c387ff
python foursoft-catalog/import_pricelist.py --dry-run --load-dims --air-rate 90  --landed-csv foursoft-catalog/data/pricelist_2025-03-01_landed_AIR-DRYRUN-lo.csv
python foursoft-catalog/import_pricelist.py --dry-run --load-dims --air-rate 105 --landed-csv foursoft-catalog/data/pricelist_2025-03-01_landed_AIR-DRYRUN-mid.csv
python foursoft-catalog/import_pricelist.py --dry-run --load-dims --air-rate 135 --landed-csv foursoft-catalog/data/pricelist_2025-03-01_landed_AIR-DRYRUN-hi.csv
```

### Follow-ups
- Retune `LOGISTICS_TIERS` for air freight (separate PR — needs the dry-run
  evidence to bound the floor/cap by tier).
- Get a real Czech→BKK air-freight RFQ from Profreight / DHL Global Forwarding
  to replace the synthesized 105 THB/kg.
- Fix the A6-01A-00 style tiny-CBM bug in Firestore dim records (likely
  missing-thickness default in the dim-backfill pipeline).

---

## 2026-05-30 — v2.44.0 — 2D ground markings created in Medusa (catalog completion)

- **Scope:** deferred **2D** SKUs (hopscotch, numbers/letters, footprints, flat
  shapes). Pure extraction from `vendors/4soft/products` — `create_medusa_products.py
  --scope 2D --status draft`. No AI.
- **Create:** **1,553 new** (843 with a PDF image, ~712 image-less), **247**
  existing updated (Czech → EN title + metadata), **2** benign "handle already
  exists" skips. All new = **draft**.
- **Price sync** (`sync_brand_prices_to_medusa.py --brand 4soft --write`): match
  **2,394 / 2,410 (99.3%)**, THB/USD/EUR/SGD.
- **Excluded (16):** packaging (10) + accessory (6) — codes like `BOX-typ2`,
  `BOXOSB-A`; look like packaging surcharges / fixed-fee items, not sellable
  products. Left out pending a decision.
- **Follow-ups:** review + publish the 1,553 2D drafts (~712 image-less →
  optionally AI-generate placeholders); decide on the 16 packaging/accessory;
  2026 pricelist + discount structure requested by email 2026-05-29.

---

## 2026-05-29 — v2.43.0 — Product images from the picture-pricelist PDF

- **Source:** `2025-06-25 4soft_EPDM_graphics_-_picture_-_price_list_2025_optimized.pdf`
  (89 pages, picture variant of the v2.40.0 `.xls`). Grid layout: 100x100 image
  per design at x≈44-99, code at x≈135.
- **Extract** (`extract_pdf_images.py`, PyMuPDF): y-row match image→code,
  validate vs pricelist, prefer DeviceRGB jpeg. **989 images** (964 native /
  25 rendered) → `data/pdf_images/` (gitignored) + `data/pdf_images_map.json`.
- **Host:** uploaded to `gs://ai-agents-go-vendors/4soft/pdf/<handle>.jpg` — the
  bucket the storefront image proxy reads (leka-website `api/i/[...path]`; the
  CLAUDE.md `ai-agents-go-documents` note is stale). Proxy URL:
  `https://catalogs.leka.studio/api/i/4soft/pdf/<handle>.jpg`.
- **Enrich** (`enrich_pdf_images.py`): UV-class-matched base-design borrowing →
  **1,635/2,410 (67.8%)** products imaged. Firestore: 1,263 PDF-primary
  (162 replaced borrowed-web, 1,101 added), 372 kept higher-res web, 775 no
  image. Medusa: **419** in-channel products updated (thumbnail + images),
  0 errors; 844 PDF-imaged codes are deferred 2D (Firestore only).
- **Follow-ups:** 775 codes (mostly flat 2D markings) have no PDF image; PDF
  embeds are 100px (higher-res would need another source).

### Run commands (v2.43.0)
```bash
python foursoft-catalog/extract_pdf_images.py
python foursoft-catalog/enrich_pdf_images.py --upload --write-firestore
export LEKA_MEDUSA_ADMIN_EMAIL=$(gcloud secrets versions access latest --secret=medusa-admin-email --project ai-agents-go)
export LEKA_MEDUSA_ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=medusa-admin-password --project ai-agents-go)
python foursoft-catalog/enrich_pdf_images.py --sync-medusa
```

---

## 2026-05-29 — v2.42.0 — 3D play elements created in Medusa + dims pricing

> Follow-up to the 2025 pricelist ingest (CHANGELOG **v2.40.0**, PR #63 — this
> brand log labels that ingest v2.38.0 below; the root CHANGELOG was renumbered
> to 2.40.0 on merge).

- **2026 re-verification:** checked `eukrit@goco.bz` (SA DWD). The *"Our Pricing
  for 2026"* newsletter (graphics@4soft.cz, 2026-04-01) is image-only — **no
  pricelist attachment, no figures.** No 2026 `.xls` in the inbox; latest actual
  pricelist is still the 2025 `.xls`. **EXW 15% / GM 40% retained** (no
  superseding doc). 2026 pricelist = open follow-up.
- **Website reality:** 4soft.cz publishes only **400 products** (256 2D / 90 3D /
  54 other), not ~2,033. 377 match the pricelist 1:1; site EN names == pricelist
  EN names (cross-checked). 2,033 pricelist codes are colour/UV/size variants
  with no web page.
- **Scope (user 2026-05-29): 3D only** = `dimension == "3D"` (592 SKUs: animals,
  nature, shapes, sport, **tunnels+slides 41**, **water fountains 29**, houses 5,
  furniture 112). Deferred the ~1,800 flat 2D ground markings.
- **Dims+images backfill** (`backfill_scraped_details.py`): 260 dimensions +
  163 borrowed base-design images written to `vendors/4soft/products`.
- **Recompute** (`import_pricelist.py`): **251 SKUs → `dims_scaled`** CBM landed
  cost (was 0). FX: USD 33.25, EUR 38.71, SGD 26.04.
- **Medusa create** (`create_medusa_products.py`, **status=draft**): created
  **462** (163 with images), renamed **130** Czech → EN, 0 errors. Channel
  `sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y`: 391 → **853 products**.
- **Price sync** (`sync_brand_prices_to_medusa.py --brand 4soft --write`):
  match **377 → 839** (THB/USD/EUR/SGD). 1,571 unmatched = deferred 2D/etc.
- **Follow-ups:** publish the 462 drafts after review; request the 2026 `.xls`;
  later create the deferred 2D markings.

### Run commands (v2.42.0)
```bash
# auth: GOOGLE_APPLICATION_CREDENTIALS → ai-agents-go SA key
python foursoft-catalog/backfill_scraped_details.py --borrow-base-images --scope 3D
python foursoft-catalog/import_pricelist.py
export LEKA_MEDUSA_ADMIN_EMAIL=$(gcloud secrets versions access latest --secret=medusa-admin-email --project ai-agents-go)
export LEKA_MEDUSA_ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=medusa-admin-password --project ai-agents-go)
python foursoft-catalog/create_medusa_products.py --scope 3D --status draft   # --dry-run first
python scripts/sync_brand_prices_to_medusa.py --brand 4soft --write
```

---

## 2026-05-29 — v2.38.0 — Initial 2025 pricelist ingest

- **Source:** `2025-06-25 4soft_EPDM_graphics-price_list_2025.xls` (single "POHODA"
  sheet, valid from 2025-03-01). Parsed → committed
  `foursoft-catalog/data/pricelist_2025-03-01.csv` (2,410 priced SKUs, EUR).
- **Reconciliation:** the 4soft pricelist is **discrete per-item EUR SKUs**
  (moulded-EPDM 3D/2D play elements), NOT the area-priced wet-pour EPDM/Infill
  CFH pricer (`products_epdm`/`products_infill`, `scripts/sync_epdm_pricelist.py`).
  **No overlap** — added as a new EUR-FOB brand, the wet-pour pricer untouched.
- **Trade terms:** EXW, EUR, EU/Czech origin. Basic reseller discount **15%**
  (2020 "Price conditions" PDF). User decisions 2026-05-29: **GM 40%**, bake
  **15% basic EXW** only (`eur_fob = list × 0.85`).
- **Pipeline:** same shared landed-cost flow as Berliner (10% Thai duty, 7%
  import VAT, tiered floor/cap, 7% TH customer VAT in `retail_thb`, independent
  THB/USD/EUR/SGD). No published dims yet → flat-35% uplift; 2,265/2,410 floored.
  FX this run: USD 33.25, EUR 38.71, SGD 26.04 (exchangerate-api.com live, +2%).
- **By category:** 3D 592 · 2D 1,802 · accessory 6 · packaging 10.
- **Firestore `vendors/4soft/products`:** 2,410 written (2,033 new, 377 updated).
- **Firestore `pricing_config/canonical.brands.4soft`:** seeded (gm 0.40, exw 0.15).
- **Medusa:** 377/2,410 matched to existing variants by SKU; **377 updated, 0 errors**.
  2,033 are pricelist-only (not yet Medusa products — `sync_brand_prices_to_medusa.py`
  is update-only).

### Run commands
```bash
# auth: GOOGLE_APPLICATION_CREDENTIALS → ai-agents-go SA key
python foursoft-catalog/import_pricelist.py --dry-run --limit 12   # validate
python foursoft-catalog/import_pricelist.py                         # write Firestore + seed config

export LEKA_MEDUSA_ADMIN_EMAIL=$(gcloud secrets versions access latest --secret=medusa-admin-email --project ai-agents-go)
export LEKA_MEDUSA_ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=medusa-admin-password --project ai-agents-go)
python scripts/sync_brand_prices_to_medusa.py --brand 4soft --dry-run
python scripts/sync_brand_prices_to_medusa.py --brand 4soft --write
```

### Open follow-ups
- **Scrape the ~2,020 missing SKUs** from 4soft.cz (only 391 of 2,410 exist as
  Medusa products), then create + price them. Spawned as a separate session.
- **Confirm 2026 discount / pricelist** — a "Our Pricing for 2026" newsletter
  (graphics@4soft.cz, 2026-04-01) exists; re-verify the 15% basic EXW discount
  and whether a 2026 pricelist supersedes this 2025 one.
- Backfill product **dimensions** (from 4soft.cz spec pages) so CBM-based landed
  cost replaces the flat-uplift + tier-floor approximation on the many 2D items.
