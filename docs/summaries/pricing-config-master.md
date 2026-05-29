# Leka Product Catalogs — Pricing Configuration Master Reference

> **Last updated:** 2026-05-29 (v2.38.0 — Vortex Aquatics added: per-product-line reseller discounts, Canada EXW USD)
> **Source of truth:** Firestore `leka-product-catalogs/pricing_config/canonical`
> **Editor UI:** `docs/forms/pricing-config.html` (served at `gateway.goco.bz/leka-product-catalogs/forms/pricing-config.html`)
> **Code files:** `shared/pricing_config.py`, `shared/landed_pricing.py`, `shared/wisdom_pricing.py`

---

## 1. Architecture Overview

All retail prices are derived independently in three currencies (THB, USD, SGD) from
the **source-currency FOB cost** through the same landed-cost pipeline.  The
pipeline is **not** `retail_usd = retail_thb / FX_USD_THB` — each currency
is calculated from the original cost so FX rounding does not cascade.

```
FOB (EUR or USD)
    │
    ├─ freight_thb (shipping-automation cost_engine, or flat-uplift fallback)
    ├─ insurance_thb  = fob_thb × 1%
    ├─ duty_thb       = cif_thb × import_duty_rate
    └─ vat_thb        = (cif_thb + duty_thb) × thai_vat_rate
          │
          └─→ landed_thb  (+ tier clamp)
                │
                ├─→ retail_thb = landed_thb / (1 - gm)   × 1.07 (TH customer VAT)
                ├─→ retail_usd = landed_usd / (1 - gm)   [independent calc, v2.31.0]
                └─→ retail_sgd = landed_sgd / (1 - gm)   [independent calc, v2.31.0]
```

---

## 2. FX Sources and Fallbacks

| Source | Priority | Module | Notes |
|--------|----------|--------|-------|
| `fx_rates.get_fx_rates(buffer_pct=2)` | 1 (primary) | `shipping-automation/mcp-server/fx_rates.py` | Live ECB/open.er-api rates +2% buffer |
| `FBX Global index` | 2 (Baltic calibration) | `shipping-automation/mcp-server/rate_feeds.py` | Used to calibrate LCL per-CBM rate |
| `open.er-api.com` (NOK→EUR) | 1 for NOK | `rampline-catalog/import_pricelist.py` | ECB daily, no key needed |
| `frankfurter.app` (NOK→EUR) | 2 for NOK | `rampline-catalog/import_pricelist.py` | Fallback when open.er-api fails |
| Module-level constants | Last resort | each brand's `import_pricelist.py` | Only when Firestore AND live FX both fail |

### FX Fallback Constants (offline only)
```python
USD_THB  = 35.0   # shared/wisdom_pricing.py DEFAULT_USD_THB
SGD_THB  = 25.0   # shared/wisdom_pricing.py DEFAULT_SGD_THB
EUR_THB  = 38.0   # shared/landed_pricing.py implicit (cost_engine FALLBACK_FX)
NOK_EUR  = 0.087  # rampline-catalog/import_pricelist.py
```

---

## 3. Global Config Params (Firestore `pricing_config/canonical.global`)

| Key | Value | Description | Code reference |
|-----|-------|-------------|----------------|
| `thai_vat_rate` | **0.07** | Thai VAT on (CIF + duty). Applied **after** import duty, before retail mark-up. | `shared/landed_pricing.py` line 78; `shared/wisdom_pricing.py` line 36 |
| `th_customer_vat_rate` | **0.07** | 7% VAT embedded in retail price (retail is VAT-inclusive). Applied as `retail_thb_final = retail_thb_pre_vat × 1.07`. Added v2.31.0. | `shared/landed_pricing.py`; `shared/wisdom_pricing.py` |
| `duty_rate_non_china` | **0.10** | Thai import duty for non-China origins (EU, Korea, Norway). | `shared/landed_pricing.py` line 77 |
| `duty_rate_china` | **0.00** | Thai import duty for China-origin under ASEAN-China FTA (Form E). | `shared/landed_pricing.py` line 78; `shared/wisdom_pricing.py` |
| `unmatched_landed_uplift` | **1.35** | Flat FOB→CIF multiplier (35% uplift) when no CBM dimension data. | `shared/landed_pricing.py` line 86 |
| `default_packing_factor` | **0.15** | CBM = L×W×H (m³) × packing_factor. Installed dims include air gaps. | `shared/landed_pricing.py` line 87 |
| `sg_customer_gst_rate` | **0.09** | Singapore GST rate (9%). Applied only if `sg_nubo_gst_registered = true`. | `shared/landed_pricing.py` line 133 |
| `sg_nubo_gst_registered` | **false** | SG sale is zero-rated export until Nubo registers. No GST on catalog. | `shared/landed_pricing.py` line 134 |

---

## 4. Brand-Specific Config Params (Firestore `pricing_config/canonical.brands`)

### 4a. Vinci Play (`brands.vinci`)

| Key | Value | Description |
|-----|-------|-------------|
| `gross_margin` | **0.35** | 35% GM. Changed from 40% on 2026-05-14. |
| Trade terms | FOB Poland/EU | No discount. `eur_fob` = pricelist EUR as-is. |
| Shipping | LCL Gdynia → Laem Chabang | `cost_engine` `origin=europe, method=lcl` |
| Duty | 10% | `duty_rate_non_china` global |

### 4b. Berliner Seilfabrik (`brands.berliner`)

| Key | Value | Description |
|-----|-------|-------------|
| `gross_margin` | **0.25** | 25% GM. |
| `exw_discount` | **0.15** | Our cost = `list_eur × (1 - 0.15)`. EXW terms. |
| Trade terms | EXW Germany | `eur_fob = list_eur × 0.85` |
| Shipping | LCL Hamburg/Europe → Laem Chabang | `cost_engine` `origin=europe, method=lcl` |
| Duty | 10% | `duty_rate_non_china` global |

### 4c. DesignPark (`brands.designpark`)

| Key | Value | Description |
|-----|-------|-------------|
| `gross_margin` | **0.35** | 35% GM (same as Vinci). |
| Trade terms | FOB Busan, Korea | `fob_usd` = pricelist USD as-is. |
| Shipping | Korea LCL flat-uplift → Bangkok | `cost_engine` `origin=japan_korea, method=lcl` (or flat 35%). As of v2.31.0, uses shipping-automation CBM where available; tier fallback otherwise. |
| Duty | 10% | `duty_rate_non_china` global (Korea is not China FTA) |

### 4d. Wisdom / Leka Project (`brands.wisdom`)

| Key | Value | Description |
|-----|-------|-------------|
| `gross_margin` | **0.50** | 50% GM. |
| `import_duty_rate` | **0.00** | Fixed to 0% in v2.31.0 (ASEAN-China FTA Form E). Previously 0.07 — that was incorrect. |
| `default_usd_thb` | 35.0 | Offline FX fallback only. |
| Trade terms | FOB China | `fob_usd` = catalog USD. |
| Shipping | China consolidated sea → Bangkok | As of v2.31.0, uses shipping-automation China LCL where CBM available; tier fallback otherwise. |
| Duty | **0%** | China-origin under ASEAN-China FTA Form E. |

### 4e. Rampline (`brands.rampline`)

| Key | Value | Description |
|-----|-------|-------------|
| `gross_margin` | **0.30** | 30% GM. |
| Trade terms | EXW Norway (net NOK) | `eur_fob = net_nok × NOK_EUR`. Already-discounted wholesale net price. |
| Shipping — with weight | Airfreight Norway → Bangkok | `cost_engine` `origin=europe, method=air` @ 120 THB/kg. Used when `weight_kg > 0`. **32/127 SKUs** use this path (v2.32.0). |
| Shipping — no weight | Flat 35% uplift + tier clamp | Fallback for products without published weight specs (Rampball, motor skills parks). **95/127 SKUs**. |
| Weight source | `data/scraped/rampline/products.json` | Scraped from rampline.com spec blocks (`<p><br>` format). Max across product variants (conservative). |
| Family-desc lookup | `FAMILY_DESC_TO_SLUG` map | Bridges pricelist descriptive family names to scraped product slugs. In `rampline-catalog/import_pricelist.py`. Fixed v2.32.0. |
| Duty | 10% | `duty_rate_non_china` global |

### 4f. Vortex Aquatics (`brands.vortex`)

Vortex's reseller discount is **per product LINE**, not a single brand discount.
The importer maps each pricelist *Collection* → top-level product line, then
applies that line's USD discount to the list price to get our EXW cost.

| Key | Value | Description |
|-----|-------|-------------|
| `gross_margin` | **0.35** | 35% GM (matches DesignPark / global default). |
| `origin` | `canada` | EXW Pointe-Claire, Quebec — non-China → 10% duty. |
| `currency` | `USD` | Pricelist is USD; `our_cost_usd = list_usd × (1 − line_discount)`. |
| Trade terms | EXW Canada (USD) | Confirmed from supplier Gmail thread + ECU Worldwide freight quote. |
| Shipping | Flat-uplift (no CBM in pricelist) | `cif = fob × 1.35`; same path as DesignPark/WePlay. |
| Duty | 10% | `duty_rate_non_china` global (Canada not FTA). |

**Per-line reseller discounts** (`brands.vortex.line_discounts`, all USD):

| Line | Discount | | Line | Discount |
|------|----------|-|------|----------|
| `splashpad` | 25% | | `elevations` | 15% |
| `poolplay` | 15% | | `wqms` | 15% |
| `spraypoint` | 25% | | `water_journey` | 20% |
| `water_slides` | 15% | | `coolhub` | **0%** (user decision 2026-05-29) |

**Collection → line map** (`brands.vortex.collection_to_line`, 22 collections):
Splashpad ← Essentials, Classic, Contemporary, Toons, Vectory, Explora,
Watergarden, Ground Sprays, Spraylink, Sea Silhouette, Nautical, Fine Mist,
Playable Fountain, Custom Items, **SmartPoint, Smartpoint N°4** (user 2026-05-29:
Spraypoint/Smartpoint classified as Splashpad 25%). · Poolplay ← Poolplay. ·
Elevations ← Elevations, **Playnuk** (Vortex groups "Elevations™ & PlayNuk™"). ·
Water Journey ← Water Journey, Lazy River. · CoolHub ← CoolHub (0%).

Source of truth for the maps: `vortex-catalog/vortex_config.py` (shared by the
importer and `seed_pricing_config.py`). Spraypoint / WQMS / Water Slides lines
exist in the discount map but match 0 SKUs in the 2026 R2 pricelist.

Code: `vortex-catalog/import_pricelist.py` `price_vortex_row()`

---

## 5. Tax Rules

### 5a. Thai Import Duty
```
CIF-value   = goods_thb + freight_thb + insurance_thb
duty_thb    = CIF-value × import_duty_rate

import_duty_rate (by origin):
  China    → 0.00  (ASEAN-China FTA, Form E required)
  EU       → 0.10  (non-FTA: Vinci, Berliner, Rampline)
  Korea    → 0.10  (non-FTA: DesignPark)
  Norway   → 0.10  (non-FTA: Rampline)
```
Code: `shared/landed_pricing.py` `duty_rate_non_china=0.10`, `duty_rate_china=0.0`

### 5b. Thai VAT (7%, on imports)
```
vat_thb = (cif_thb + duty_thb) × 0.07
```
This is the **import-stage** VAT paid on CIF+duty at customs clearance.
Code: `shared/landed_pricing.py` `THAI_VAT_RATE=0.07`

### 5c. Thai Customer VAT (7%, embedded in retail price)
```
retail_thb_final = retail_thb_pre_vat × 1.07
```
Retail prices displayed in Thailand are VAT-inclusive (TH practice). This
customer VAT is distinct from the import VAT — it is the 7% VAT that Leka
adds when selling to TH customers. Added in v2.31.0, `th_customer_vat_rate = 0.07`.

Code: `shared/landed_pricing.py` (`price_row`); `shared/wisdom_pricing.py` (`compute_wisdom_retail`)

### 5d. Singapore GST (9%, deferred)
```
sg_gst_mult = (1 + 0.09) if sg_nubo_gst_registered else 1.0
retail_sgd  = retail_pre_tax_thb × sg_gst_mult / (THB/SGD FX)
```
Currently `sg_nubo_gst_registered = false` — SG sale is zero-rated export.
No GST added at catalog price. This flips automatically when Nubo registers.

Code: `shared/landed_pricing.py` `_resolve_params()`; `shared/wisdom_pricing.py` `_params()`

---

## 6. Per-Brand Formulas (Cost → Landed → Retail)

### 6a. Vinci Play (EU FOB, EUR)
```python
fob_thb    = eur_fob × EUR_THB
cif_thb    = fob_thb + freight_thb + insurance_thb   # from cost_engine (CBM-based LCL)
             # OR: cif_thb = fob_thb × 1.35           # flat-uplift when no CBM
duty_thb   = cif_thb × 0.10
vat_thb    = (cif_thb + duty_thb) × 0.07
landed_thb = cif_thb + duty_thb + vat_thb
             → TIER CLAMP applied (see §7)
retail_thb_pre_vat = landed_thb / (1 - 0.35)
retail_thb = retail_thb_pre_vat × 1.07   # TH customer VAT (v2.31.0)
retail_usd = landed_usd / (1 - 0.35)     # landed_usd calculated independently
retail_sgd = landed_sgd / (1 - 0.35)     # landed_sgd calculated independently
```
Code: `shared/landed_pricing.py` `price_row(brand="vinci")`
Pricelist: `vinci-catalog/import_pricelist.py`

### 6b. Berliner Seilfabrik (EU EXW, EUR)
```python
eur_fob    = list_eur × (1 - 0.15)      # EXW-15% discount
fob_thb    = eur_fob × EUR_THB
# ... same as Vinci from here, with gross_margin = 0.25
retail_thb = retail_thb_pre_vat × 1.07
```
Code: `berliner-catalog/import_pricelist.py`; `shared/landed_pricing.py` `price_row(brand="berliner")`

### 6c. DesignPark (Korea FOB Busan, USD)
```python
fob_thb    = fob_usd × USD_THB
cif_thb    = fob_thb × 1.35              # flat-uplift (no CBM data in pricelist)
             # OR: cif_thb via cost_engine origin=japan_korea when CBM available
duty_thb   = cif_thb × 0.10
vat_thb    = (cif_thb + duty_thb) × 0.07
landed_thb = cif_thb + duty_thb + vat_thb
retail_thb = (landed_thb / (1 - 0.35)) × 1.07
retail_usd = landed_usd / (1 - 0.35)     # from Japan/Korea LCL in USD terms
retail_sgd = landed_sgd / (1 - 0.35)
```
Code: `scripts/ingest_designpark_pricelist.py` `price_designpark_row()`

### 6d. Wisdom / Leka Project (China FOB, USD)
```python
fob_thb    = fob_usd × USD_THB
cif_thb    = fob_thb                     # China consolidated sea: CIF ≈ FOB
             # OR: cif_thb via cost_engine origin=china when CBM available (v2.31.0)
duty_thb   = cif_thb × 0.00             # ASEAN-China FTA (0% — FIXED v2.31.0)
vat_thb    = (cif_thb + duty_thb) × 0.07
landed_thb = cif_thb + duty_thb + vat_thb
retail_thb = (landed_thb / (1 - 0.50)) × 1.07
retail_usd = landed_usd / (1 - 0.50)
retail_sgd = landed_sgd / (1 - 0.50)
```
Code: `shared/wisdom_pricing.py` `compute_wisdom_retail()`

### 6e. Rampline (Norway EXW net, NOK→EUR)
```python
nok_eur    = live FX (open.er-api.com / frankfurter.app fallback)
eur_fob    = net_nok × nok_eur
fob_thb    = eur_fob × EUR_THB

# Path A — airfreight (weight_kg available, 32/127 SKUs as of v2.32.0):
freight_thb = weight_kg × 120 THB/kg   # cost_engine origin=europe, method=air
cif_thb     = fob_thb + freight_thb + insurance_thb

# Path B — flat uplift (no weight, 95/127 SKUs):
cif_thb     = fob_thb × 1.35

duty_thb   = cif_thb × 0.10
vat_thb    = (cif_thb + duty_thb) × 0.07
landed_thb = cif_thb + duty_thb + vat_thb
             → TIER CLAMP applied (see §7)
retail_thb = (landed_thb / (1 - 0.30)) × 1.07
retail_usd = landed_usd / (1 - 0.30)
retail_sgd = landed_sgd / (1 - 0.30)
```
Code: `rampline-catalog/import_pricelist.py`; `shared/landed_pricing.py` `price_row(brand="rampline")`

### 6f. Vortex Aquatics (Canada EXW, USD — per-line reseller discount)
```python
line       = collection_to_line(collection)        # 22 collections → 7 lines
line_disc  = line_discounts[line]                  # e.g. splashpad 0.25, coolhub 0.0
our_cost_usd = list_usd × (1 − line_disc)          # EXW cost we pay Vortex
fob_usd    = our_cost_usd
fob_thb    = fob_usd × USD_THB
cif_thb    = fob_thb × 1.35                         # flat-uplift (no CBM in pricelist)
duty_thb   = cif_thb × 0.10                          # non-China (Canada)
vat_thb    = (cif_thb + duty_thb) × 0.07
landed_thb = cif_thb + duty_thb + vat_thb
             → TIER CLAMP applied (USD→EUR-equiv band, §7)
retail_thb = (landed_thb / (1 − 0.35)) × 1.07        # TH customer VAT
retail_usd = (landed_thb / USD_THB) / (1 − 0.35)     # independent, no TH VAT
retail_sgd = (landed_thb / SGD_THB) / (1 − 0.35)     # × SG GST mult when registered
```
Code: `vortex-catalog/import_pricelist.py` `price_vortex_row()`;
maps in `vortex-catalog/vortex_config.py`

---

## 7. Vinci Tier Floor/Cap System (EU brands)

All EU-origin brands (Vinci, Berliner, Rampline) share the same logistics tier table.
This system clamps the landed THB within a reasonable band relative to the FOB cost.

**Purpose:**
- **Floor** (`lo_pct`): Every SKU must carry a minimum share of fixed logistics costs
  (customs clearance ~18,000 THB, last-mile delivery, insurance). Without a floor,
  very cheap SKUs would show unrealistically low landed costs.
- **Cap** (`hi_pct`): Very large items (outdoor gym rigs) have disproportionate CBM
  that would make the LCL freight cost dominate. The cap prevents outliers.

### Tier Table (Firestore `pricing_config/canonical.logistics_tiers`)

| EUR FOB band | Floor pct (`lo_pct`) | Cap pct (`hi_pct`) | Floor formula | Cap formula |
|---|---|---|---|---|
| ≤ 500 EUR | 0.80 | 2.50 | `landed_min = fob_thb × 1.80` | `landed_max = fob_thb × 3.50` |
| ≤ 2,000 EUR | 0.60 | 1.80 | `landed_min = fob_thb × 1.60` | `landed_max = fob_thb × 2.80` |
| ≤ 10,000 EUR | 0.45 | 1.20 | `landed_min = fob_thb × 1.45` | `landed_max = fob_thb × 2.20` |
| > 10,000 EUR | 0.35 | 0.80 | `landed_min = fob_thb × 1.35` | `landed_max = fob_thb × 1.80` |

### Worked Examples (EUR=38 THB, USD=35 THB, Vinci 35% GM, 7% customer VAT)

**Example 1 — Small item, Tier 0 (EUR 150 FOB, no CBM data)**
```
fob_thb     = 150 × 38 = 5,700 THB
flat_cif    = 5,700 × 1.35 = 7,695 THB  (35% uplift)
duty        = 7,695 × 0.10 = 769.5 THB
vat         = (7,695 + 769.5) × 0.07 = 522.5 THB
landed_raw  = 7,695 + 769.5 + 522.5 = 8,987 THB

Tier 0 floor = 5,700 × 1.80 = 10,260 THB  ← raw (8,987) < floor → FLOORED
landed_thb  = 10,260 THB  (clamped up)
retail_thb_pre_vat = 10,260 / 0.65 = 15,785 THB
retail_thb  = 15,785 × 1.07 = 16,889 THB  (TH customer VAT included)
```

**Example 2 — Mid-range item, Tier 1 (EUR 800 FOB, CBM = 2.5 m³)**
```
fob_thb     = 800 × 38 = 30,400 THB
freight_lcl = 2.5 CBM × 5,500 THB/CBM = 13,750 THB  (Baltic rate)
insurance   = 30,400 × 0.01 = 304 THB
cif_thb     = 30,400 + 13,750 + 304 = 44,454 THB
duty        = 44,454 × 0.10 = 4,445 THB
vat         = (44,454 + 4,445) × 0.07 = 3,423 THB
landed_raw  = 44,454 + 4,445 + 3,423 + 18,000 (clearance) = 70,322 THB

Tier 1 floor = 30,400 × 1.60 = 48,640 THB
Tier 1 cap   = 30,400 × 2.80 = 85,120 THB
48,640 ≤ 70,322 ≤ 85,120 → no clamp needed
landed_thb  = 70,322 THB
retail_thb  = (70,322 / 0.65) × 1.07 = 115,694 THB
retail_usd  = (70,322 / (1 - 0.35)) × (1.07 / USD_THB)
```

**Example 3 — Large item capped, Tier 3 (EUR 15,000 FOB, huge CBM = 40 m³)**
```
fob_thb     = 15,000 × 38 = 570,000 THB
freight_lcl = 40 CBM × 5,500 = 220,000 THB  (enormous)
...landed_raw would exceed cap
Tier 3 cap  = 570,000 × 1.80 = 1,026,000 THB  ← CAPPED DOWN
retail_thb  = (1,026,000 / 0.65) × 1.07 ≈ 1,688,000 THB
```

Code: `shared/landed_pricing.py` `logistics_band()` + `price_row()` lines 299–313.

---

## 8. Shipping-Automation Integration

### 8a. How `price_row()` calls `cost_engine`

```python
from cost_engine import estimate_landed_cost

est = estimate_landed_cost(
    origin="europe",          # or "japan_korea", "china"
    method="lcl",             # or "air" for Rampline
    goods_value=eur_fob,
    goods_currency="EUR",
    cbm=cbm,                  # from parsed dimensions × packing_factor
    kg=weight_kg,             # for Rampline airfreight path
    duty_rate=0.10,           # explicit override bypasses route defaults
    fx_rates=fx,              # live FX snapshot (same for all SKUs in a run)
)
landed_thb = est["total_landed_thb"]
freight_thb = est["freight"]["thb"]
duty_thb    = est["customs"]["duty_thb"]
vat_thb     = est["customs"]["vat_thb"]
```

### 8b. Baltic Rate Calibration (EU LCL)

```python
baltic = calibrate_baltic_rate(fx)   # in shared/landed_pricing.py
# → tries FBX Global index for live rate; falls back to cost_engine static 5,500 THB/CBM
# → monkey-patches cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"]
#    for the duration of one SKU's estimate call, then restores the original
```

### 8c. Routes Available

| Brand | origin key | method key | Per-CBM / Per-kg rate (static) |
|-------|-----------|-----------|-------------------------------|
| Vinci, Berliner | `europe` | `lcl` | 5,500 THB/CBM |
| Rampline | `europe` | `air` | 120 THB/kg |
| DesignPark | `japan_korea` | `lcl` | 3,500 THB/CBM |
| Wisdom | `china` | `china_thai_sea` or `lcl` | 4,600 THB/CBM (consolidated) |

### 8d. Flat-Uplift Fallback (No CBM/Weight Data)

When no dimensions or weight are available (scrape failed, item has no published specs):
```python
cif_thb   = fob_thb × UNMATCHED_LANDED_UPLIFT   # 1.35 = 35% flat uplift
freight_thb = cif_thb - fob_thb
```
The tier clamp still applies after this, so very cheap items are floored.

---

## 9. Medusa Regions and Currency Routing

Medusa serves prices to storefront customers by matching the cart region to the
variant's price set. Each region has a single currency. SGD region was activated
2026-05-25.

| Region ID | Name | Currency | Countries | Notes |
|-----------|------|----------|-----------|-------|
| `reg_01KNKVD0TNN5G0HG3CSTF7JGWN` | Asia-Pacific | USD | KH, ID, MY, VN, PH, CN, US | `sg` removed 2026-05-25 |
| `reg_01KRD770VERSJ1CY1TPVJQ6DY9` | Thailand | THB | TH | |
| `reg_01KRD7714NWS07RGH38F2TM178` | Europe | EUR | IE, AT, BE, FI, FR, DE, GR, IT, NL, PT, ES, SE, PL | |
| `reg_01KSEBH1EAK9RWAYEW87QY8NWS` | **Singapore** | **SGD** | **SG** | Created 2026-05-25 |

### How SGD prices reach Medusa
All 5 brands have `retail_sgd` in Firestore (backfilled 2026-05-24, v2.31.0).
`scripts/sync_brand_prices_to_medusa.py` pushes `{"amount": ..., "currency_code": "sgd"}`
as currency-level price set entries. Medusa serves these to any cart in the
Singapore region. No `region_id` override needed — currency match is sufficient.

### SGD Region: Future Steps
- **When Nubo registers for SG GST**: set `sg_nubo_gst_registered=true` in
  `pricing_config/canonical.global`, re-run `backfill_sgd_pricing.py --brand all --write`,
  then re-run `sync_brand_prices_to_medusa.py --brand all --write`.
- **Vortex** now has full multi-currency pricing incl. SGD (v2.38.0). **When
  4soft has a pricelist**: create a full SGD pricing pass for it, then it can
  also sell into SG region.

---

## 10. Which Values Live Where

| Parameter | Storage | How to edit |
|-----------|---------|-------------|
| `gross_margin` per brand | Firestore `pricing_config/canonical.brands.<slug>.gross_margin` | pricing-config.html form |
| `import_duty_rate` (Wisdom) | Firestore `pricing_config/canonical.brands.wisdom.import_duty_rate` | pricing-config.html form |
| `exw_discount` (Berliner) | Firestore `pricing_config/canonical.brands.berliner.exw_discount` | pricing-config.html form |
| `thai_vat_rate` | Firestore `pricing_config/canonical.global.thai_vat_rate` | pricing-config.html form |
| `th_customer_vat_rate` | Firestore `pricing_config/canonical.global.th_customer_vat_rate` | pricing-config.html form |
| `duty_rate_non_china` | Firestore `pricing_config/canonical.global.duty_rate_non_china` | pricing-config.html form |
| `duty_rate_china` | Firestore `pricing_config/canonical.global.duty_rate_china` | pricing-config.html form |
| `logistics_tiers` | Firestore `pricing_config/canonical.logistics_tiers` | pricing-config.html form |
| LCL per-CBM rates | `shipping-automation/mcp-server/cost_engine.py` `ROUTE_PROFILES` | Edit cost_engine.py directly |
| Air per-kg rates | `shipping-automation/mcp-server/cost_engine.py` `ROUTE_PROFILES` | Edit cost_engine.py directly |
| `sg_customer_gst_rate` | Firestore `pricing_config/canonical.global.sg_customer_gst_rate` | pricing-config.html form |
| `sg_nubo_gst_registered` | Firestore `pricing_config/canonical.global.sg_nubo_gst_registered` | pricing-config.html form |

### Fallback constants (used when Firestore unreachable)
These **must stay in sync** with `scripts/seed_pricing_config.py`:

| Module | Constant | Value |
|--------|----------|-------|
| `shared/landed_pricing.py` | `GROSS_MARGIN` | 0.35 |
| `shared/landed_pricing.py` | `DUTY_RATE_NON_CHINA` | 0.10 |
| `shared/landed_pricing.py` | `DUTY_RATE_CHINA` | 0.0 |
| `shared/landed_pricing.py` | `THAI_VAT_RATE` | 0.07 |
| `shared/wisdom_pricing.py` | `IMPORT_DUTY_RATE` | **0.00** (fixed v2.31.0) |
| `shared/wisdom_pricing.py` | `GROSS_MARGIN` | 0.50 |
| `berliner-catalog/import_pricelist.py` | `EXW_DISCOUNT` | 0.15 |
| `berliner-catalog/import_pricelist.py` | `GROSS_MARGIN` | 0.25 |
| `rampline-catalog/import_pricelist.py` | `GROSS_MARGIN` | 0.30 |

---

## 11. Scripts Reference

| Script | Purpose | Run after |
|--------|---------|-----------|
| `scripts/backfill_sgd_pricing.py --brand all --write` | Recompute all brand prices from source FOB; write to Firestore `vendors/{slug}/products` | Any config/formula change |
| `scripts/sync_brand_prices_to_medusa.py --brand all --write` | Push computed prices to Medusa variants by SKU/handle match | After backfill |
| `scripts/seed_pricing_config.py` | Seed/reset Firestore `pricing_config/canonical` | Initial setup or `--force` reset |
| `scripts/ingest_designpark_pricelist.py --apply` | Parse DesignPark xlsx → Firestore `vendors/designpark/products` | When source pricelist updated |
| `rampline-catalog/import_pricelist.py` | Parse Rampline NOK pricelist → Firestore `vendors/rampline/pricelists/<date>` | When source pricelist updated |
| `vinci-catalog/import_pricelist.py` | Parse Vinci EUR pricelist → Firestore `vendors/vinci/products` | When source pricelist updated |
| `berliner-catalog/import_pricelist.py` | Parse Berliner EUR CSV → Firestore `vendors/berliner/products` | When source pricelist updated |
| `vortex-catalog/import_pricelist.py --apply` | Parse Vortex 2026 USD PDF → Firestore `vendors/vortex/products` + merge `brands.vortex` config | When source pricelist updated |

---

## 12. Version History for Pricing Changes

| Version | Date | Change |
|---------|------|--------|
| v2.38.0 | 2026-05-29 | Add **Vortex Aquatics** (`brands.vortex`): per-product-LINE reseller discounts (Splashpad 25% / Poolplay 15% / Spraypoint 25% / Elevations 15% / WQMS 15% / Water Journey 20% / Water Slides 15% / CoolHub 0%), Canada EXW USD, 311 SKUs ingested, 295 synced to Medusa. Maps in `vortex-catalog/vortex_config.py`. |
| v2.33.0 | 2026-05-25 | Create Medusa Singapore SGD region (`reg_01KSEBH1EAK9RWAYEW87QY8NWS`); move `sg` out of Asia-Pacific USD; re-sync all brand prices |
| v2.32.0 | 2026-05-24 | Rampline weight scraper fix: `<p><br>` spec parsing + `FAMILY_DESC_TO_SLUG` map. 32/127 Rampline SKUs now use `airfreight_weight` routing (was 0 before) |
| v2.31.0 | 2026-05-24 | Fix Wisdom duty 7%→0% (ASEAN-China FTA); add 7% TH customer VAT to all retail prices; Korea/China/Norway shipping-automation CBM routes; currency-independent retail calculations (THB/USD/SGD each from source FOB) |
| v2.28.0 | 2026-05-22 | Add `retail_sgd` across all 5 brands; backfill script; Medusa sync script |
| v2.21.1 | 2026-05-14 | TH retail VAT-inclusive config fix; Vinci GM 40%→35%; non-China duty 10% |
| v2.21.0 | 2026-05-14 | Add 7% import VAT layer; SG GST gate (`sg_nubo_gst_registered`) |
