# Rampline 2026 Price Go-Live — Run & Verification Report

**Date:** 2026-06-07 · **Version:** 2.72.0 · **Brand:** Rampline (`sc_01KNQAA448RY0YPR51FNPM2TVA`)

## Inputs & parameters
- **Source:** 2026 Rampline NOK price list (eff. 2025-12-01), 82 priced articles; `net_nok` (GO buy price = RRP − distributor discount) is the cost input.
- **Gross margin:** 35% · **Import duty:** 10% · **Freight:** 30% of goods (flat) · **Clearance:** 6% of goods · **Insurance:** 1% of goods · **Import VAT:** 7% (in landed) · **TH customer VAT:** 7% (in retail THB).
- **FX (frankfurter.app 2026-06-05):** 1 NOK = 3.5029 THB / 0.10734 USD / 0.09221 EUR / 0.13776 SGD → THB/USD 32.6337, THB/EUR 37.9883, THB/SGD 25.4276.
- Volumetric / CBM analysis is run **separately by the owner** — this stack is the flat model.

## Costing structure (landed THB → retail THB/USD/SGD/EUR)
```
goods     = net_nok × 3.5029
freight   = 30% × goods          insurance = 1% × goods
CIF       = goods + freight + insurance
duty      = 10% × CIF            import_vat = 7% × (CIF + duty)
clearance = 6% × goods
landed    = CIF + duty + import_vat + clearance
retail_thb        = landed / 0.65 × 1.07      (35% GM, 7% TH customer VAT INCLUDED)
retail_usd/eur/sgd = (landed / 0.65) / FX     (ex customer-VAT; SGD × SG-GST 1.0)
```
`retail_thb` is **VAT-inclusive**, matching the Vinci/Berliner/Wisdom/4soft/Vortex convention. USD/EUR/SGD are ex customer-VAT (VAT is TH-domestic). There is no independent USD/SGD landed stack — they convert the THB cost at the fixed FX snapshot.

**Worked example — RB35** (`net_nok 14,466`): goods 50,672.95 → freight 15,201.89 → insurance 506.73 → CIF 66,381.56 → duty 6,638.16 → import VAT 5,111.38 → clearance 3,040.38 → **landed 81,171.48** → **retail_thb 133,620.74** (VAT-incl) / USD 3,826.70 / EUR 3,287.31 / SGD 4,911.18.

## Change vs first cut
The initial v2.72.0 cut anchored THB/USD/EUR to the vendors stack (18% freight, fixed per-SKU clearance, **ex-VAT** retail). Per owner direction 2026-06-07 the landed cost is now recomputed (30% freight, 6% clearance, retained 1% insurance + 10% duty + 7% import VAT) and `retail_thb` is **VAT-inclusive (×1.07)**.

## Medusa push & verification
| Metric | Count |
|---|---|
| Priced articles computed | 82 |
| Eurotramp-owned (Kids Tramp) excluded from push | 7 |
| Pushable Rampline articles | 75 |
| Matched live Medusa variants (SKU) | 64 |
| **Read-back verified exact (THB/USD/EUR/SGD)** | **64 / 64 (0 mismatches)** |
| No Medusa variant yet (skipped) | 11 |

**Skipped (no variant on the Rampline channel):** `4005`, `4008`, `4010`, `4020`, `4022`, `4024-2`, `4046-2`, `946020` (spares) + `RL410 SD`, `FF1 1002`, `FF1 EXT 1002`.

## Cross-brand guard (Eurotramp shared SKUs)
The Rampline "Kids Tramp" family are Eurotramp-made items resold under **identical Eurotramp SKUs** (`97010B`, `E97047`, `E31120`, `E21898B`, `E97547`, `Loop 1.0`, `LED TR LOOP 1.0`), already priced by the Eurotramp catalog. They are **excluded** from the Rampline push (`EUROTRAMP_OWNED_FAMILIES`); the 4 Eurotramp variants remain at their correct Eurotramp prices (re-verified untouched after this re-push).

## Follow-ups
- When variants exist for the 11 skipped articles, re-run `python scripts/sync_brand_prices_to_medusa.py --brand rampline --write`.
- Owner's separate volumetric/CBM analysis may supersede the flat 30% freight assumption.
- The shared sync indexes Medusa SKUs globally; sales-channel-scoped matching is a hardening follow-up (see spawned task).
