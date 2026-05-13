# Berliner Seilfabrik Catalog — Deployment Log

## 2026-05-13 — Initial pricelist load (Compendium 11, 2026)

- **Source**: `2025-12-17 20251217_Preisliste_Compendium 11_EN_Ausland.pdf`
  (11 pages, 2026 list prices in EUR, all prices ex works)
- **Trade terms**: EXW. Our EXW cost = list price × **0.85** (15 % vendor discount)
- **Pipeline** (mirrors `vinci-catalog/import_pricelist.py`):
  1. `python berliner-catalog/parse_pricelist.py` — PyMuPDF tables → CSV
  2. `python berliner-catalog/import_pricelist.py` — landed cost + Firestore write
  3. `python scripts/sync_vendors_to_medusa.py --brand=berliner` — push to Medusa
- **FX snapshot**: USD=33.0472 EUR=38.7877 (exchangerate-api.com + 2 % buffer)
- **Baltic LCL rate**: 5,331.65 THB/CBM (avg of cost_engine static 5,500 + FBX-derived 5,163.30)
- **Logistics tiers** (% of FOB-in-THB): same as Vinci — 80-250 % under EUR 500,
  60-180 % under EUR 2 k, 45-120 % under EUR 10 k, 35-80 % above
- **Gross margin**: 40 % (retail = landed / 0.60)
- **Parse outcomes**: 801 rows total
  - 380 priced + SKU (status: `active`)
  - 348 priced + name-only (status: `name_only_active`)
  - 16 SKU + on-request (status: `on_request`) — written as `draft`
  - 57 name-only + on-request (status: `name_only_on_request`) — written as `draft`
- **CBM method**: 728 `flat_uplift` + 73 `n/a` (on-request). 0 `dims_scaled` —
  no Berliner website scrape exists yet in `vendors/berliner/products`; re-run
  after `scripts/scrape-berliner.ts` to upgrade matched rows to CBM-driven cost.
- **Firestore**: 801 docs in `ai-agents-go/(vendors)/vendors/berliner/products/`
  (790 created new, 5 from earlier smoke-test, 6 idempotent re-writes)
- **Medusa**: 801 rows pushed to `leka-medusa-backend`, sales channel
  `sc_01KNQAA3QDYHP15Y9K4PPRMDF0`. Priced rows carry THB+USD+EUR retail;
  on-request rows are `draft` status with no price.
  - **Existing pre-scrape**: 498 Berliner products already existed in the
    Medusa SC with handles like `berliner-swingo-02` (slug-of-name, not
    slug-of-item-code). Wrote `berliner-catalog/push_pricelist_to_medusa.py`
    that paginates the SC, builds a SKU → variant map, and either UPDATEs
    matched variants' prices or CREATEs new products (using the same
    slug-of-name handle convention).
  - **Result**: 349 variants updated (price refresh on existing products),
    440 new products created (accessory rows + new pricelist SKUs),
    12 skipped (on-request rows that matched an existing SKU — kept as-is),
    **0 errors**, rate ~2.2 req/s, total runtime ~6 min.
- **Sample**: berliner-lu-001-001 (LevelUp.01.1) list EUR 34,333 → EXW EUR 29,183
  → landed THB 1,528,124 → retail THB 2,546,873 / USD 77,068 / EUR 65,662
- **Audit trail**:
  - `berliner-catalog/data/pricelist_2026-01-01.csv` (parsed PDF)
  - `berliner-catalog/data/pricelist_2026-01-01_landed.csv` (landed cost)
  - `berliner-catalog/data/medusa-sync-YYYYMMDD-HHMMSS.log` (Medusa push log)
