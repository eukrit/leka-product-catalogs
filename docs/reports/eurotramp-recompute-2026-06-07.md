# Eurotramp Costing Recompute — HOUSE model go-live (2026-06-07, v2.75.0)

Recomputed Eurotramp landed + retail pricing, replacing the earlier **flat ×1.30**
model (computed in the sibling `vendors` repo by
`eurotramp-catalog/scripts/calc_landed_cost.py`) with the corrected **house
cost-plus** model. Firestore updated, Medusa re-pushed, read-back verified.

Script: [`scripts/recompute_eurotramp_pricing.py`](../../scripts/recompute_eurotramp_pricing.py)
· Reconciliation: [`eurotramp-recompute-2026-06-07.json`](eurotramp-recompute-2026-06-07.json)
/ [`.csv`](eurotramp-recompute-2026-06-07.csv)
· Pre-write snapshot: [`eurotramp-snapshot-2026-06-07-pre-house-costing.json`](eurotramp-snapshot-2026-06-07-pre-house-costing.json)

## What changed in the model

| Component | OLD (flat ×1.30) | NEW (house, owner directive 2026-06-07) |
|---|---|---|
| Freight | 18% of goods | **30% of goods** |
| Clearance | **fixed 512.5 THB/SKU** (= (18,000+2,500)/40) | **6% of goods** |
| Insurance | 1% of goods | 1% of goods *(retained — see flag)* |
| Duty | 10% of CIF | 10% of CIF |
| Import VAT | 7% of (CIF+duty) | 7% of (CIF+duty) |
| Retail markup | landed × 1.30 (effective **GM ≈ 23.1%**) | landed / (1 − **0.35**) → **GM 35%** |
| TH customer VAT in retail THB | **none** | **+7% embedded in retail_thb** (domestic) |
| USD / EUR / SGD retail | retail_thb / FX (so VAT-bearing) | derived from landed, **ex-VAT**; SG GST ×1.0 (Nubo not GST-registered) |

FX is **pinned** to the existing Eurotramp snapshot (EUR=38.7877, USD=33.0472,
SGD=25.974) so this reconciliation isolates the cost-model + margin + VAT change
and stays coherent with the prices already live on the storefront. An FX refresh
is a separate follow-up.

`pricing_config/canonical` → added `brands.eurotramp`:
`{ gross_margin: 0.35, import_duty_rate: 0.10, freight_pct_of_goods: 0.30,
clearance_pct_of_goods: 0.06, insurance_pct_of_goods: 0.01, costing_model: … }`.

## Results

- **151 / 187** docs repriced (36 have no EXW — configurator/pricelist gaps — left untouched).
- **Blended retail THB +44.1%** (sum old ฿20,589,507 → new ฿29,672,192).
- **137 SKUs rise** (mostly +30…+50%, driven by the higher freight%, the +7% TH
  VAT, and the 35% GM); **14 SKUs held flat** by the no-decrease floor (below).
- Firestore product pricing: **151 updated, 0 errors**.
- Medusa push (`sync_brand_prices_to_medusa.py --brand eurotramp --write`):
  **151/151 matched (100%), 151 updated, 0 errors**, SC `sc_01KNQAA3Y72W17B7CP2VQ93T3M`.
- **Read-back vs live Medusa: 151/151 match across THB/USD/EUR/SGD, 0 mismatch, 0 not-found.**

### No-decrease floor (owner directive)

The new "6% of goods" clearance removes the old **fixed 512.5 THB/SKU** clearance
floor, so 10 micro-spares (EXW ≤ €7.40) would otherwise have dropped 50–85% (the
smallest to ~110 THB / ~$3.30 — below realistic single-part pick/pack/ship cost).
Per owner decision, **no SKU's retail may fall below its current live price**: where
the computed retail_thb was lower, the **entire old retail set (THB/USD/EUR/SGD) is
held** and the doc is flagged `pricing.floored=true`,
`price_floor="no_decrease_held_old"` (computed value retained as
`retail_thb_computed` for audit). After the floor: **0 SKUs decrease**, min retail
฿742.52. 14 SKUs held:

torsion-spring (L/R), anchor-bar, clamping-jaw (×3), steel-spring-145×20, short-leaf
connecting-cable, adhesive-cartridge, and 4 other sub-€20 spares.

## Spot-check (FX-pinned, new model)

| Article | Handle | EXW € | landed THB old→new | retail THB old→new | Δ% |
|---|---|---:|---:|---:|---:|
| 03150 | albatross | 8,421.25 | 458,016 → 523,236 | 595,420 → **861,327** | +44.7% |
| 23201 | anti-slip-plate-dmt | 596.18 | 32,901 → 37,042 | 42,772 → **60,977** | +42.6% |
| 30800 | adaption-bars-ultimate | 167.68 | 9,622 → 10,418 | 12,509 → **17,150** | +37.1% |
| — | anchor-bar (floored) | 1.11 | 573 → 69 | 745 → **745** | 0.0% |

## Flags / open items

1. **Volumetric NOT applied here.** No Eurotramp SKU carries packing dimensions or
   shipping weights (the 63 docs with a `dimensions` field hold *installation/frame*
   dims, e.g. `frame_length_cm=1036` for a 10 m track; 0 docs carry `weight_kg`), so
   true volumetric CBM freight and air-vs-LCL routing can't be computed. Method is
   LCL-equivalent flat-percentage freight. **The owner will run the volumetric
   calculation separately.** Each doc carries `pricing.volumetric_applied=false`.
2. **Insurance retained at 1% of goods** (CIF insurance) even though the owner
   directive named only freight (30%) and clearance (6%). Kept for CIF correctness
   and parity with the prior model; trivial impact (~0.1% of landed). Zero it if the
   30% is meant to be freight-plus-insurance.
3. **FX is pinned, not live** — deliberate for an apples-to-apples reconciliation and
   storefront coherence. A live-FX refresh is a separate pass.
4. **36 unpriced docs** remain (no EXW match in the 2025 (1E) list) — unchanged.
5. **Shared-SKU note:** Rampline's "Kids Tramp" family (97010B, E97047, E31120,
   E21898B, Loop 1.0, E97547, LED TR LOOP 1.0) are Eurotramp-made and exist as
   Eurotramp Medusa products under those exact SKUs — these now carry the correct
   Eurotramp house prices (verified above), independent of Rampline PR #116.
