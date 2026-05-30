# Archimedes Water Play — Deployment Log

Brand: **Archimedes Water Play** (Wenzhou Daosen 温州道森游乐戏水)
Slug: `archimedes-water-play` · Origin: China (FOB, CNY) · 34 SKUs (AWP001–AWP034)

---

## 2026-05-29 — v2.38.0 — Landed pricing pass (deferred PR #59 work)

**Summary:** Completed the CNY→THB/USD/SGD landed-pricing pass that PR #59
(v2.36.0) deferred. Mirrors the Wisdom China-FOB pipeline.

### Task 1 — audit doc
- Ran `import_pricelist.py` (no `--dry-run`) on a machine with gcloud ADC.
- Wrote 34 variants to `vendors/archimedes-water-play/pricelists/2026-05-29`
  (database `vendors`, project `ai-agents-go`).

### Task 2 — landed pricing
- `price_archimedes.py` (NEW): China-origin pricing in CNY.
  - 0% duty (ASEAN-China FTA Form E), +7% Thai import VAT, +7% TH customer VAT
    (THB retail only), independent THB/USD/SGD retail, **GM 0.50**.
  - FX (live, +2% buffer): CNY=4.8903, USD=33.2529, SGD=26.0437 THB/unit.
  - Dimension→CBM: `lwh` only (cm unless an axis > 1000 ⇒ mm; explicit "cm" honored),
    `CBM = L·W·H(m³) × 0.15`; routed through China-LCL `cost_engine` + tier clamp.
    Other dim kinds → flat CIF ≈ FOB.
  - **34 SKUs priced** (28 CBM / 6 flat) → `vendors/archimedes-water-play/products/<sku>`.
  - Audit CSV: `data/pricelist_2026-05-29_priced.csv`.
  - Audit doc `landed_pricing_status` → `completed (v2.38.0)`.
- `scripts/add_archimedes_pricing_config.py` (NEW): merged `brands.archimedes-water-play`
  into `pricing_config/canonical` (GM 0.50, duty 0.00, CNY, default_cny_thb 4.80).

### Task 3 — Medusa
- Created the **Archimedes Water Play** sales channel `sc_01KSSP39K5DVH9TT2TMXCREHFV`
  and added it to the `sync_brand_prices_to_medusa.py` SC map.
- **Follow-up:** create the 34 AWP### products in Medusa, then run
  `python scripts/sync_brand_prices_to_medusa.py --brand archimedes-water-play --write`
  to push prices (no-op today — 0/34 matched, products don't exist yet).

### Outcome
Success. `verify.sh` 0 FAIL.

### How to re-run (after FX/GM change)
```bash
python archimedes-water-play-catalog/price_archimedes.py --dry-run
python archimedes-water-play-catalog/price_archimedes.py --apply
```

---

## 2026-05-29 — v2.36.0 — Pricelist parse (PR #59)
- `import_pricelist.py` parsed the Wenzhou Daosen pricelist (34 SKUs) → CSV +
  Firestore audit doc. Landed pricing deferred (completed in v2.38.0 above).
