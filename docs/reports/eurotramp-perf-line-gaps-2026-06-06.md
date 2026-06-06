# Eurotramp Performance-Line Enrichment — Residual Gaps (2026-06-06)

Scope: 34 handles in `data/curated/eurotramp_performance_line.json` (the
competition/performance line featured on
`next.leka.studio/education-solutions/performance-trampoline`).

## Outcomes
| axis | before | after | notes |
|---|---|---|---|
| Real price (THB/USD/EUR/SGD) | 0/34 | **28/34** | 6 pricelist gaps below |
| Core dimensions (L×W×H cm) | 0/34 | **28/34** | 6 no-dims below |
| Real-photo thumbnail | 22/34 | **33/34** | 1 true gap; 1 component-photo |

## Pricing gaps — not in the current 2025 (1E) pricelist (left unpriced)
These articles aren't in `Price list 2025 (1E).xlsx`; price them from the
component/configurator or a future list, then re-run
`sync_brand_prices_to_medusa.py --brand eurotramp --scope-file …`.
- `eurotramp-complete-competition-trampoline` (38000) — complete field set (configurator/sum-of-parts).
- `eurotramp-fivesquare` (40000) — freestyle five-square.
- `eurotramp-trampoline-set-freestyle` (98001B) — freestyle set variant (list has 98001K).
- `eurotramp-spieth-ground-safety-mat` (28330) — third-party (Spieth) mat.
- `eurotramp-spotting-mat-freestyle` (28600F) — freestyle variant (list has 28600).
- `eurotramp-set-of-landing-mats-dmt` (26200) — DMT landing-mat set.

## Dimension gaps — no open-frame dims in pricelist or vendor_data (left 0)
`eurotramp-complete-competition-trampoline`, `eurotramp-adaption-bars-safety-platform-integral-ultimate`,
`eurotramp-frame-pads-set-80mm-safety-plus`, `eurotramp-roller-stand`,
`eurotramp-bungee-longe`, `eurotramp-somersault-belt-twisting-belt`
(small parts / configurator items — add manually if needed).

## Image gaps
- **True gap (manual photo needed):** `eurotramp-trampoline-set-one-field` — only
  merchant logos + badges in the scrape (no hero photo for the one-field set).
- **Component photo (manual hero recommended):** `eurotramp-complete-competition-trampoline`
  auto-repointed from a FIG-approved cert badge to a real Ultimate component photo
  (`03150-ultimate80mmframepads…`). A dedicated assembled-field hero would be better.
- Note: the audit's `nonphoto_thumb=9` over-counts — `run-up-track-dmt`,
  `transport-case-hdts`, `safety-platforms-universal-freestyle`, and
  `spotting-mat-freestyle` already carry correct product photos with unconventional
  filenames (`preview-<art>…`, `<art>f-…`) the regex classifier marks "unknown".

## Follow-up (out of this task's scope)
- **Kids/spares price-push:** 123 of 187 `vendors/eurotramp/products` Firestore docs
  are priced (kids + BounceCloud + spares) but were **never pushed to Medusa** —
  they still show usd=0 stubs live. Run
  `python scripts/sync_brand_prices_to_medusa.py --brand eurotramp --write` (no
  `--scope-file`) to take all eurotramp prices live, after a pricing review.
