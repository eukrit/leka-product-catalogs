# CHANGELOG entry for v2.21.0 (Rampline variant migration)

Pre-existing merge conflict in `CHANGELOG.md` (lines 5–309, `Updated upstream`
vs `Stashed changes`) prevented inserting this directly. Resolve the conflict,
then paste this block immediately under the `# Changelog` / intro header.

---

## [2.21.0] - 2026-05-16

### Added — Rampline pricelist → Medusa variants

127 article codes from the 2025 NOK pricelist now live as Medusa variants
across 40 Rampline sub-products. The default placeholder variants (keyed
on WooCommerce post IDs from the original rampline.com scrape) are
removed from every product that received real variants.

#### Structure

Per user decision 2026-05-16 (mixed model based on family shape):

- **Size-as-product** for clean Size × Surface families:
  - `rampline-rampball` → 4 new size sub-products `-35`, `-50`, `-50r`, `-70r`
    (4 Surface variants each = 16 variants)
  - `rampline-jumpstone-en` → 4 new size sub-products `-27`, `-50`, `-3`, `-5`
    (4 Surface variants each = 16 variants)
- **Single-product-with-options** for multi-axis / service families:
  - `rampline-balancebuddy-en` — 6 variants on `Length × Style`
  - `rampline-balancebuddy-wave` — 2 variants on `Surface`
  - `rampline-fungi-eng` — 3 variants on `Size`
  - `rampline-rampit` — 3 variants on `Size`
  - `rampline-rampit-hopper` — 6 variants on `Component × Surface`
  - `rampline-rampit-swing` — 2 variants on `Size`
  - `rampline-rampit-storm-en` — 1 variant on synthetic `Type` (Medusa v2 forbids option-less products)
  - `rampline-rampbow` — 2 variants on `Surface`
  - `rampline-rampline-slackline` — 2 variants on `Surface`
  - `rampline-floating-bench` — 4 variants on `Type` (Bench/LED/Customization/Rigging)
- **Group B park bundles** — each of the 21 SHOCKDECK-priced parks gets
  3 surface variants (Wet pour / Loose fills / Artificial grass). The
  `SD 02` U-piece sits on `rampline-shockdeck` as a Standard-type variant.

#### Counts

- Products: 54 → **62** (8 new Rampball/Jumpstone size sub-products, `status=draft`)
- Variants total: **149** (127 real + 22 untouched placeholders on legacy parks / unpriced equipment / family parents)
- Placeholder deletions: 24 default variants removed
- Default option removals: 25 across affected parents
- Zero pricelist SKUs missing, zero unexpected real SKUs

#### Out of scope (intentional, per user)

- The 17 legacy parks (ABILITY, AGILE, BOUNCE, …) untouched — not in the 2025 pricelist.
- 3 unpriced equipment products (Spare parts ×2, Playground Loop trampoline) untouched.
- Variants carry full audit `metadata` (`article_code`, `family`, `family_discount`, `net_nok`, `recommended_nok`, `pricelist_date`, `source`) but **no prices** — pricing handled separately via the Firestore-backed pricing-config flow (v2.20.1).
- New size sub-products inherit parent images + description; refine per-size assets later.

#### Files

- NEW: `rampline-catalog/build_variants.py` — Medusa write script with `--dry-run` / `--apply` / `--limit-family`
- NEW: `rampline-catalog/data/mapping/generate_mapping_drafts.py` — parser + scaffold generator
- NEW: `rampline-catalog/data/mapping/family_mapping_draft.csv` (40 rows) — one row per sub-product
- NEW: `rampline-catalog/data/mapping/variant_scaffold_draft.csv` (127 rows) — one row per article code with option breakdown
- NEW: `rampline-catalog/data/mapping/medusa_snapshot_2026-05-14.json` — read-only Medusa state at planning time
- NEW: `rampline-catalog/data/build_runs/*.json` — dry-run + applied action logs (full audit trail)
- NEW: `docs/summaries/rampline-variants.html` — Leka-styled summary page

#### Verification (live)

```
Total Rampline products: 62  (was 54 + 8 new size sub-products)
Total variants: 149  (127 from pricelist + 22 untouched placeholders)
Pricelist SKUs missing from Medusa: 0
Unexpected non-placeholder SKUs in Medusa: 0
```

#### Next

- Set prices on the 127 new variants (likely via the pricing-config form +
  a sync_vendors_to_medusa.py extension that reads `vendors/rampline/pricelists/<date>`).
- Flip the 8 new Rampball/Jumpstone size sub-products from `status=draft` to
  `status=published` once prices land.
- Consider deleting the placeholder defaults on `rampline-rampball` and
  `rampline-jumpstone-en` (currently retained — they make those products
  "navigational" parents with no orderable variant; revisit if storefront
  needs them gone).
- Re-run the landed-cost pipeline once Rampline tech-sheet PDFs are
  parsed for proper per-SKU CBM (currently all flat-uplift).
