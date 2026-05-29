# 4soft — Deployment Log

Brand: **4soft, s.r.o.** (Tanvald, Czech Republic · VAT CZ28703324 · graphics@4soft.cz / roger@4soft.cz)
Slug: `4soft` · Medusa sales channel: `sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y`
Pricing config: `pricing_config/canonical.brands.4soft` (db `leka-product-catalogs`)
Products: `vendors/4soft/products` (db `vendors`)

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
