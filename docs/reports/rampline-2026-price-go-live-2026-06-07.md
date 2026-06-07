# Rampline 2026 Price Go-Live — Run & Verification Report

**Date:** 2026-06-07 · **Version:** 2.72.0 · **Brand:** Rampline (`sc_01KNQAA448RY0YPR51FNPM2TVA`)

## Inputs & parameters
- **Source:** 2026 Rampline NOK price list (eff. 2025-12-01), 82 priced articles, parsed +
  cost-stacked in the `vendors` repo (`rampline-catalog/parsed/pricelist{,_landed}.json`).
- **Gross margin:** 35% · **Import duty:** 10% · **Retail basis:** ex-VAT (THB/USD/EUR).
- **FX snapshot (frankfurter.app 2026-06-05):** 1 NOK = 3.5029 THB / 0.10734 USD / 0.09221 EUR /
  0.13776 SGD → **THB/SGD = 25.4276**.

## Pricing methodology
- `retail_thb / retail_usd / retail_eur` **anchored verbatim** to the vendors cost-plus stack
  (`landed_thb / 0.65`) so the two catalogs agree exactly (0 drift).
- `retail_sgd = retail_thb / 25.4276 × SG-GST-mult`, where the multiplier comes from the house
  `shared/pricing_config.py` SG logic (`sg_nubo_gst_registered=false` → **×1.0**; Nubo is not yet
  GST-registered in Singapore, so the SG sale is a zero-rated export).
- `pricing_config/canonical` `brands.rampline.gross_margin` updated **0.30 → 0.35**.

## Reconciliation note (THB anchor)
THB/USD/EUR equal the vendors `pricelist_landed.json` outputs by construction → **drift = 0**.
The shared `shared/landed_pricing.py::price_row()` EUR-cost-engine path was **not** used to
re-derive amounts: it embeds 7% TH customer VAT in `retail_thb` and models landed cost via the
EUR CBM/air engine, which would diverge from the vendors NOK-direct stack (18% freight + 1%
insurance + 10% duty + 7% import VAT + fixed clearance). Per the task directive the vendors
NOK-direct, ex-VAT stack is the anchor; only the SGD currency derivation uses the house config.

## Medusa push & verification
| Metric | Count |
|---|---|
| Priced articles computed | 82 |
| Eurotramp-owned (Kids Tramp) excluded from push | 7 |
| Pushable Rampline articles | 75 |
| Matched live Medusa variants (SKU) | 64 |
| **Read-back verified exact (THB/USD/EUR/SGD)** | **64 / 64 (0 mismatches)** |
| No Medusa variant yet (skipped) | 11 |

**Skipped (no variant on the Rampline channel):** `4005`, `4008`, `4010`, `4020`, `4022`,
`4024-2`, `4046-2`, `946020` (spares) + `RL410 SD`, `FF1 1002`, `FF1 EXT 1002`. The sync never
creates products; these will price once their variants exist.

## Cross-brand incident & remediation
The Rampline list's **Kids Tramp** family are Eurotramp-made items resold under **identical
Eurotramp article codes** (`97010B`, `E97047`, `E31120`, `E21898B`, `E97547`, `Loop 1.0`,
`LED TR LOOP 1.0`). They already exist as Eurotramp Medusa products (Eurotramp + Leka Catalogs
channels). The first sync matched 4 of them by SKU and overwrote the correct Eurotramp prices
with Rampline-stack values (the list gives them 0% distributor discount → inflated).

**Remediated:**
1. Restored the 4 Eurotramp variants to their correct Eurotramp prices
   (`97010B`→ET-97010 144,273.78 THB; `E97047` 22,423.82; `E31120` 908.49; `E21898B` 47,173.77).
2. Deleted the 7 Kids-Tramp docs from `vendors/rampline/products`.
3. Added `EUROTRAMP_OWNED_FAMILIES` guard to `build_2026_pricing.py` so the family is
   permanently excluded from the Rampline products subcollection / Medusa push.

Re-verified: Rampline 64/64 exact; all 4 Eurotramp variants correct.

## Follow-ups
- When variants exist for the 11 skipped articles (RL410 SD, FF1 Forest, spares), re-run
  `python scripts/sync_brand_prices_to_medusa.py --brand rampline --write`.
- The shared sync indexes Medusa SKUs globally; cross-brand SKU collisions (Rampline⇄Eurotramp)
  are real. Consider sales-channel-scoped matching in the shared script as a hardening follow-up.
