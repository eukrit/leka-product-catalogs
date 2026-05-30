# Wisdom SG retail — old (TH-derived) vs new (SG-landed)

_Generated 2026-05-29T19:51:17.098463+00:00 by scripts/compare_sg_pricing.py — dry-run, no writes._

## FX snapshot
- USD/THB: `33.2529`
- SGD/THB: `26.0437`
- USD/SGD: `1.2768`

## Sample (10 SKUs, strategy=spread)

| item_code | fob_usd | cbm | old retail_sgd (TH-derived) | new retail_sgd (SG-landed) | Δ% | freight_sgd | gst_sgd | landed_sgd | cbm_method | clamp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `CM6-3MG4012` | 1.57 | 0.000 | 4.30 | 4.38 | +1.9% | 0.00 | 0.18 | 2.19 | china_sg_flat | — |
| `CY40-3MG3133` | 7.15 | 0.000 | 63.88 | 63.88 | +0.0% | 124.79 | 12.06 | 31.94 | china_sg_lcl_cbm | sg:capped th:capped |
| `WY29-3BIY1013Z` | 13.95 | 0.000 | 38.11 | 38.82 | +1.9% | 0.00 | 1.60 | 19.41 | china_sg_flat | — |
| `N1-5572` | 23.28 | 0.001 | 208.09 | 208.10 | +0.0% | 124.79 | 13.93 | 104.05 | china_sg_lcl_cbm | sg:capped th:capped |
| `GP1-4220-04` | 40.12 | 0.004 | 358.58 | 358.58 | +0.0% | 124.79 | 15.89 | 179.29 | china_sg_lcl_cbm | sg:capped th:capped |
| `GP1-4241-V02` | 64.83 | 0.000 | 177.14 | 180.46 | +1.9% | 0.00 | 7.45 | 90.23 | china_sg_flat | — |
| `KB1-NW1B025` | 119.78 | 0.092 | 1070.53 | 858.36 | -19.8% | 124.79 | 25.13 | 429.18 | china_sg_lcl_cbm | th:capped |
| `HW1-S367-V01` | 483.64 | 0.341 | 3566.34 | 2223.08 | -37.7% | 124.79 | 67.36 | 1111.54 | china_sg_lcl_cbm | sg:floored |
| `HW1-S1A711` | 3913.24 | 9.691 | 14603.28 | 14657.76 | +0.4% | 1562.83 | 594.83 | 7328.88 | china_sg_lcl_cbm | — |
| `BS35CS-A0005-116131` | 9119.15 | 0.000 | 24916.97 | 25382.70 | +1.9% | 0.00 | 1047.91 | 12691.35 | china_sg_flat | — |

## Aggregate
- mean Δ%:   `-4.96%`
- median Δ%: `+0.19%`
- min Δ%:    `-37.66%`
- max Δ%:    `+1.87%`
- count new > old: 6 / 10
- count new < old: 2 / 10

## Sanity-check flags (|Δ| > 25%)

- `HW1-S367-V01`: -37.7% (old 3566.34 → new 2223.08; cbm=0.341, freight=124.79, clamp sg=floored th=—)

## Method notes

- **old**: `compute_wisdom_retail(...)`.`retail_sgd` — derives SGD from `landed_thb / sgd_thb / 0.50`. `landed_thb` already includes Thai freight (Xiamen→Laem Chabang), Thai 7% import VAT, Thai clearance + last-mile.
- **new**: `compute_wisdom_retail_sg(...)`.`retail_sgd` — routes through `cost_engine.ROUTE_PROFILES['china_to_singapore']` (LCL) with `duty_rate=0`, `vat_rate=0.09`, then `landed_sgd / 0.50`. SG customer GST stack stays off until `sg_nubo_gst_registered=True`.
- Both paths apply the same Vinci-style logistics tier clamp on landed cost for symmetry.