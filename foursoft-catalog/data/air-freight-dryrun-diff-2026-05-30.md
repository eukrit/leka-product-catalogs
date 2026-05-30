# 4soft Air-Freight Pivot — Dry-Run Validation Diff — 2026-05-30

**Status:** dry-run only. Firestore was NOT touched. Cloud Run deploy NOT triggered.

## Setup

Three dry-runs against `pricelist_2025-03-01.csv` (2,410 rows) with the air-freight pivot landed:

| Run | THB/kg chargeable | Output CSV |
|---|---|---|
| LO  | 90  | `data/pricelist_2025-03-01_landed_AIR-DRYRUN-lo.csv`  |
| MID | 105 (recommended baseline) | `data/pricelist_2025-03-01_landed_AIR-DRYRUN-mid.csv` |
| HI  | 135 | `data/pricelist_2025-03-01_landed_AIR-DRYRUN-hi.csv`  |

Rate source: [`air-freight-rates-2026-05-30.md`](./air-freight-rates-2026-05-30.md) — backhaul Europe→Asia, all-in (base + FSC + SSC + war-risk + handling). Volumetric divisor 167 kg/m³ (IATA general cargo). FX snapshot: USD 33.25, EUR 38.71, SGD 26.04 (exchangerate-api.com live + 2% buffer).

`LOGISTICS_TIERS` **unchanged** — still sea-tuned (`0.80–2.50` cap at tier 1, etc.). This is intentional per the plan; the diff is supposed to surface where the cap dominates.

## Headline counts

| Metric | OLD (LCL) | LO (air 90) | MID (air 105) | HI (air 135) |
|---|---|---|---|---|
| Total rows | 2 410 | 2 410 | 2 410 | 2 410 |
| `cbm_method = dims_scaled` | 251 | 251 | 251 | 251 |
| `cbm_method = flat_uplift` | 2 159 | 2 159 | 2 159 | 2 159 |
| `logistics_clamp = none`     | 198 | 205 | **207** | 211 |
| `logistics_clamp = floored`  | 2 045 | 2 071 | **2 069** | 2 065 |
| `logistics_clamp = capped`   | **167** | 134 | 134 | 134 |
| Median landed THB | 4 086 | 4 086 | 4 086 | 4 086 |
| p90 landed THB | 75 680 | 63 469 | 63 575 | 64 235 |

**Reads:**

- `flat_uplift` rows (2 159 / 2 410) are **byte-identical** between OLD and MID — the `else` branch of `price_row` was untouched, as planned. Verified row-by-row: 0 differences.
- 33 fewer rows are capped (167 → 134). Air freight on tiny-CBM items collapses (3-5 THB) and stops blowing past the cap. The savings come from the LCL clearance fee being 18 000 THB (high fixed) vs air's 3 800 THB.
- p90 drops from 75 680 → 63 575 THB. The heavy tail is lighter under air because dimensional items no longer pay the 18 000 THB LCL clearance.
- Median landed and most `floored` rows are unmoved — the floor clamp (FOB × 1.80) is the dominant binding constraint for ~86% of the catalog.

## Per-SKU validation (10 representative rows)

Columns: `cbm`, `eur_fob`, `freight_{OLD,LO,MID,HI}` (THB), `landed_raw_MID` (pre-clamp), `landed_{OLD,LO,MID,HI}` (post-clamp), `clamp_{OLD,MID}`, `retail_sgd_{OLD,MID}`, `Δ landed %` (MID vs OLD).

| Code | Name | Dim | CBM-method | CBM | FOB € | freight OLD / LO / MID / HI | landed_raw MID | landed OLD / LO / MID / HI | clamp OLD / MID | retail SGD OLD / MID | Δ % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A6-01A-00** | Hexagon 40 cm std | 2D | dims_scaled | 0.0002 | 29.75 | 15 000 / 3 / 4 / 5 | 21 923 | 4 030 / 4 030 / 4 030 / 4 030 | capped / capped | 258 / 258 | +0.0% |
| **A6-01A-50UV** | Hexagon 40 cm UV | 2D | flat_uplift | 0 | 35.70 | 484 / 484 / 484 / 484 | 2 196 | 2 487 / 2 487 / 2 487 / 2 487 | floored / floored | 159 / 159 | +0.0% |
| **A6-01B-00** | Hexagon 60 cm std | 2D | flat_uplift | 0 | 45.05 | 610 / 610 / 610 / 610 | 2 771 | 3 139 / 3 139 / 3 139 / 3 139 | floored / floored | 201 / 201 | +0.0% |
| **A6-01C-00** | Hexagon 80 cm std | 2D | flat_uplift | 0 | 102.00 | 1 382 / 1 382 / 1 382 / 1 382 | 6 274 | 7 107 / 7 107 / 7 107 / 7 107 | floored / floored | 455 / 455 | +0.0% |
| **J3-01A-20** | LUDO big 3D circle | 3D | dims_scaled | 0.9004 | 3 461 | 15 000 / 13 533 / **15 789** / 20 300 | 198 401 | 197 423 / 195 746 / **198 401** / 203 710 | – / – | 12 634 / 12 697 | **+0.5%** |
| **V9-02A-001** | MINI Arena | 3D | dims_scaled | 0.945  | 3 002 | 15 000 / 14 203 / **16 571** / 21 305 | 178 200 | 176 302 / 175 414 / **178 200** / 183 773 | – / – | 11 282 / 11 404 | **+1.1%** |
| **V1-03B-001** | 3D Bench PLAY PROMO | 3D | dims_scaled | 0.0698 | 2 168 | 15 000 / 1 049 / **1 224** / 1 574 | 121 728 | 137 893 / 121 655 / **121 728** / 122 140 | – / – | 8 824 / 7 790 | **−11.7%** |
| **A1-01A-00** | Circle 18 cm std | 2D | flat_uplift | 0 | 17.00 | 230 / 230 / 230 / 230 | 1 046 | 1 184 / 1 184 / 1 184 / 1 184 | floored / floored | 76 / 76 | +0.0% |
| **J1-02B-05** | 3D Monkey girl target | 3D | flat_uplift | 0 | 1 742 | 23 607 / 23 607 / 23 607 / 23 607 | 107 173 | 107 918 / 107 918 / 107 918 / 107 918 | floored / floored | 6 906 / 6 906 | +0.0% |
| **J3-02A-20** | LUDO big 3D square | 3D | dims_scaled | 1.283 | 4 709 | 15 000 / 19 288 / **22 503** / 28 932 | 263 721 | 264 302 / 264 302 / **264 302** / 271 288 | floored / floored | 16 914 / 16 914 | +0.0% |

## Interpretation

### Where the air pivot moves prices: 92 unclamped `dims_scaled` 3D items

These are mid-to-large 3D products with realistic CBM. Examples in the table: J3-01A-20, V9-02A-001, V1-03B-001.

- **V1-03B-001** is the clearest air-vs-sea contrast: CBM 0.0698 (small for a 3D item), high FOB €2 168. Chargeable kg = 0.0698 × 167 = 11.66 kg → air freight 1 224 THB at 105 THB/kg. Under LCL the same item was paying 15 000 THB (capped) freight. Landed drops 12% — air is *cheaper* here because the item is high-FOB-low-volume, and LCL's per-CBM rate plus 18 000 THB clearance dominated.
- For big-CBM 3D items (J3-01A-20, V9-02A-001), air gets more expensive than sea on freight alone (15-22k THB vs 15k cap), but the lower clearance still keeps landed within ±1%. Sensitivity 90→135 THB/kg shifts these by ±3%.

### Where the air pivot does NOT move prices: the rest (2 318 / 2 410)

- **2 159 flat_uplift rows**: untouched by design (no CBM data → 35% uplift fallback).
- **134 capped `dims_scaled` rows**: cap is binding. Raw landed exceeds FOB × 2.50; clamp pulls it back. Air freight on these is tiny (0.0001-0.001 m³ items at 1-3 THB) but `landed_thb_raw` is still 5-10× the FOB because of the fixed clearance/last-mile overhead. The cap protects the user-facing price.
- **2 069 floored rows**: floor is binding. Raw landed is below FOB × 1.80; clamp pushes it up. Air freight at 1-25 THB barely registers vs the FOB.

### Anomaly worth flagging

**Hexagon A6-01A-00 has CBM 0.0002 m³ = 200 cm³** — that's a 5 cm × 4 cm × 1 cm volume. A real 40 cm hexagon mat at 1 cm thick should be ~0.4 × 0.4 × 0.01 × 1.15 packing factor ≈ 0.002 m³ (10× larger). The Firestore dimension is suspect (likely a missing thickness defaulting to ~0.1 cm somewhere). **Pre-existing data-quality issue, out of scope for this pivot** — but worth fixing in a follow-up because it'll dominate the post-cap landed price once the clamps are retuned.

## Acceptance against plan

| Check | Status |
|---|---|
| `cbm_method=flat_uplift` rows byte-identical between OLD and MID | ✅ 0 diffs across 2 159 rows |
| All 3 dry-runs complete without exceptions | ✅ |
| Dimensional 3D items move sensibly (±15% range, sensitivity-driven) | ✅ |
| No negative or NaN retail prices | ✅ (median 4 086, p90 63 575, max ~280k) |
| Firestore untouched | ✅ (`DRY RUN complete — Firestore untouched.` in all 3 runs) |
| New unit tests pass (7 new + 19 existing in `shipping-automation/tests/test_pricing_engine.py`) | ✅ 26/26 passed |

## What the user should decide before the next PR

1. **Pick a baseline rate**: LO (90), **MID (105 — recommended)**, or HI (135) THB/kg.
2. **Decide on clamp retune timing**: the cap is binding on 134 rows and the floor on 2 069 rows; raw landed differs from clamped landed by 5-10× for many SKUs. Worth a separate PR with new air-tuned `LOGISTICS_TIERS`?
3. **Fix the dim-data bug for A6-01A-00 and similar** before this rolls to production? Or live with the cap until dim backfill?

## Reproduction

```bash
cd C:/Users/Eukrit/OneDrive/Documents/Claude Code/leka-product-catalogs/.claude/worktrees/inspiring-chandrasekhar-c387ff
python foursoft-catalog/import_pricelist.py --dry-run --load-dims --air-rate 90  --landed-csv foursoft-catalog/data/pricelist_2025-03-01_landed_AIR-DRYRUN-lo.csv
python foursoft-catalog/import_pricelist.py --dry-run --load-dims --air-rate 105 --landed-csv foursoft-catalog/data/pricelist_2025-03-01_landed_AIR-DRYRUN-mid.csv
python foursoft-catalog/import_pricelist.py --dry-run --load-dims --air-rate 135 --landed-csv foursoft-catalog/data/pricelist_2025-03-01_landed_AIR-DRYRUN-hi.csv
```

Engine unit tests:

```bash
cd C:/Users/Eukrit/OneDrive/Documents/Claude Code/shipping-automation
python -m pytest tests/test_pricing_engine.py -v
```
