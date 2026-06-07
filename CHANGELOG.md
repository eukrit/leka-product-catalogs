# Changelog

All notable changes to this project will be documented in this file.

---

## [2.78.0] - 2026-06-07

### Added — Eurotramp: close 4 image gaps + spec enrichment from the local 2023 asset pack

Enriches the live Medusa Eurotramp catalog from the **EuroTramp 2023 Info-Package** local asset
pack (`Info-Package-KidsTramp-PlayPro_EN` + `Info-Package-Playground-Outdoor-Trampolines-2023`;
98 photos + 9 spec PDFs, all verified hydrated). New reusable script
`scripts/enrich_eurotramp_from_local_assets.py` (dry-run → apply → `--rollback`), reusing the
`classify` / `photo_rank` / `handle_overlap` helpers. Rollback metadata stashed
(`previous_thumbnail` / `previous_images`); timestamped reports under `docs/reports/`.

> **Note vs already-merged work:** this branch was authored against `main` @ v2.69.0 and rebased
> over v2.70.0–v2.77.0. The **merge proposal** below predates **#122 (v2.77.0, Kids Tramp Impact
> Protection option + PlayPro/Bonded Tiles bundle variants)** — reconcile the single-tile /
> adhesive / PlayPro sections against what #122 already implemented before acting on them. #113
> (competition/performance hero images) may also have independently closed some gaps.

**Asset → product map (dry-run first):** `docs/reports/eurotramp-asset-map-2026-06-06.json` + `.md`
— 13 assets mapped with confidence/evidence; **85 generic `Eurotramp-0XX` marketing-library photos
left for review** (not force-assigned).

**Images closed — 4 of the 40 documented gaps** (real-photo thumbnails + galleries on live Medusa,
proxy verified HTTP 200): `kids-tramp-playground` (art 97000, in-ground EPDM),
`kids-tramp-playground-loop` (97010B), `kids-tramp-kindergarten` (square daycare-garden shoot),
`wehrfritz-fun-xl-kindergarten` (wheelchair signature). Plus official PlayPro photos onto 3 non-gap
parts (E97047 / E97048 / E97548). 13 photos → `gs://ai-agents-go-vendors/eurotramp/<handle>/`.

**Metadata enrichment — 15 products** (additive only): DIN EN 1176, TÜV-GS, `facility_type`
(Kindergarten = supervised / Playground = unsupervised), catalog dimensions, PlayPro / PLAY! specs.

**Merge proposal (no auto-merge)** — `docs/reports/eurotramp-merge-proposal-2026-06-06.md`. The
Fallschutz flyer revealed the **old vs new (2023 EPDM-top) system** split (single-tile 33 SKUs → 9
groups; adhesive E97003 old / E97043 new system, not 2 sizes; Top-Sheet BounceCloud held — 3 ≠ 9
colours). See the reconcile note above re: #122.

**Upload hardening:** `gcloud storage cp`'s multiprocessing worker pool deadlocks on Windows under a
non-interactive shell; uploads force `CLOUDSDK_STORAGE_PROCESS_COUNT/THREAD_COUNT=1` + timeout/retry.

**Follow-up:** the live **Eurotramp dealer media pool** (login portal) is the source for a
higher-confidence pass on the remaining ~36 gaps + the BounceCloud colour-vs-size question — being
ingested into the `vendors` project.

---

## [2.77.0] - 2026-06-07

### Added — Kids Tramp "Impact Protection" option + 32 bundle variants (PlayPro / Bonded Tiles) on Medusa

Each Eurotramp **Kids Tramp** base product now carries an **`Impact Protection`** product
option so customers can configure the impact-protection surface inline instead of buying the
accessory as a separate line item. Existing variants are set to `Impact Protection = None`
(prices unchanged); **32 new bundle variants** were created across 9 base products, priced
**base-variant + accessory retail** in all four currencies (THB/USD/EUR/SGD).

**Option values** (created per product, only where the accessory SKU exists):
- `PlayPro` — PlayPro rubber protection lip/ring (single colour).
- `Bonded Tiles (Grey)` / `Bonded Tiles (Red)` — bonded EPDM tile system. The vendor code
  encodes colour: `…41` = Grey, `…44` = Red (confirmed in pricelist descriptions).

**Coverage** (mirrors what exists in `vendors/eurotramp/products`):
- Playground (both coatings) → PlayPro + Bonded Grey + Bonded Red.
- Playground Loop / Loop XL → Grey only; Playground XL → Red only; PlayPro on all except Loop XL.
- Kindergarten line (Default) → same value sets as the matching Playground model.
- Track "Playground" → PlayPro + Bonded Grey per length (4/6/8/10m), on the **Track-only** base
  variants only ("With EPDM" skipped — already includes EPDM protection).

**SKU convention:** composite `<base_sku>+<accessory_sku>` (e.g. `97000+E97041`). Each new
variant carries `metadata.{base_sku, accessory_sku, impact_protection}`.

**Excluded (logged):** `E94541`/`E94700` are **Wehrfritz Fun** products, not Kids Tramp;
`E97541`/`E97547` do not exist in the source data.

**Files:**
- `scripts/add_kidstramp_impact_protection.py` — idempotent writer: adds the option, backfills
  existing variants to `None`, creates the bundle variants, verifies each product against live
  Medusa, aborts on first real error. Tolerant of transient Cloud Run 503s (retry + already-exists
  skip). Re-runs as a pure verifier once everything exists. Read-only on Firestore; no source-price
  mutation.

**Outcome:** success — all 32 variants verified live (prices match in THB/USD/EUR/SGD); existing
variants intact at `Impact Protection = None`.

---

## [2.76.0] - 2026-06-07

### Added — Lappset brand: consumer wiring + storefront import (clean-white heroes)

_(Renumbered → 2.76.0 on rebase: main reached 2.75.0 via PR #120.)_

Consumer half of the permanent Lappset hero-image fix. The producer lives at the
catalog source (`eukrit/vendors` PR #52, `lappset-catalog/scripts/step8_normalize_heroes.py`):
it normalizes every Lappset hero to a clean white background and records it as
`images[0]` (`source:"hero_white"`) + `hero_white_gcs` on `vendors/lappset/products/*`.
This release consumes that and brings Lappset into Leka Medusa.

**Why:** Lappset catalogue renders ship transparent/studio-background, so every
`leka-projects` proposal re-die-cut them per-project — a fix that kept regressing
(re-ingest wiped the cache; Gemini die-cut was billing-blocked; classifier
non-deterministic). Fixing it once at the source + consuming `images[0]` here means
the storefront and downstream renderers never re-die-cut.

**`scripts/sync_vendors_to_medusa.py`:**
- Added `"lappset"` to `BRAND_SALES_CHANNELS` (`sc_01KTGNBRJZ71VWWH3W7FAW0E4R`, new "Lappset" channel).
- `metadata.hero_white_gcs` propagated to Medusa on create + update (None-filtered for other brands).
- Brand-agnostic normalization of raw vendor-template docs (Lappset stores
  `product_name`/`sku`, no `handle`) into the payload-builder shape; URL-safe
  handle (hyphenated slug) so Medusa accepts `000502.1`-style SKUs.
- **Guard `_lappset_hero_ok`** — refuses to publish a Lappset product unless
  `images[0]` is the proxy-served `hero_white` variant, OR a documented
  `needs_fallback` original (in-situ photo); rejects raw `webapi.lappset.com`
  URLs and empty images. `thumbnail`/`images[0]` come from the hero_white proxy URL.

**`tests/test_lappset_hero_guard.py`** (new, 9 tests, no network): guard accepts
white heroes + documented fallbacks; rejects raw/empty/un-flagged; create/update
payloads carry hero_white thumbnail + metadata; no `hero_white_gcs` key leaks for
other brands.

**`medusa-backend/src/scripts/migrate-to-brand-module.ts`:** added the `lappset`
Brand spec + `"Lappset"` → `lappset` sales-channel mapping so the existing
idempotent brand-module migration creates the Lappset Brand and links its products.

**Import (2026-06-07):** created the "Lappset" Medusa sales channel and synced all
imageable Lappset products with hero_white as the primary image — **1064 created /
12 updated → 1076 live**; 8 no-image products skipped by the guard; 7 in-situ
fallbacks published with their proxy original. Live audit of all 1076: **1069
hero_white + 7 original thumbnails, 0 raw `webapi.lappset.com` URLs, 0 missing**.

**Follow-up (storefront switcher visibility):** after this merges and
`leka-medusa-backend` redeploys (image then contains the `lappset` BRAND_SPEC),
run `npx medusa exec ./src/scripts/migrate-to-brand-module.ts` in-cluster (dry-run
first) to create the Lappset Brand record + link the products + add the shared
"Leka Catalogs" sales channel — same one-time step used for all 11 existing brands.

## [2.75.0] - 2026-06-07

### Changed — Eurotramp costing moved to the HOUSE cost-plus model (volumetric deferred)

Replaced the over-simplistic **flat ×1.30** Eurotramp pricing (computed in the
sibling `vendors` repo by `eurotramp-catalog/scripts/calc_landed_cost.py`) with a
corrected house cost-plus model. New
[`scripts/recompute_eurotramp_pricing.py`](scripts/recompute_eurotramp_pricing.py)
(dry-run → snapshot → write); full run report under
[`docs/reports/eurotramp-recompute-2026-06-07.md`](docs/reports/eurotramp-recompute-2026-06-07.md).

Model (owner directive 2026-06-07): **freight = 30% of goods**, **clearance = 6%
of goods** (replacing the old fixed 512.5 THB/SKU floor), insurance 1%, 10% non-China
duty on CIF, 7% Thai import VAT; retail = landed / (1 − **GM 0.35**); **retail_thb now
embeds the 7% TH customer VAT** while USD/EUR/SGD stay ex-VAT (SG GST ×1.0 — Nubo not
GST-registered). FX **pinned** to the existing snapshot (EUR=38.7877 / USD=33.0472 /
SGD=25.974) so the reconciliation isolates the model change and stays coherent with
live prices. Added `brands.eurotramp` to `pricing_config/canonical`.

This is a standalone per-SKU recompute (does not use `shared/landed_pricing.py`):
Eurotramp has no packing dims/weights, so the v2.74.0 vendor-freight branch does
not apply here — the owner runs the volumetric calculation separately.

- **151/187** docs repriced (36 unpriced/no-EXW left untouched); Firestore 151 updated, 0 errors.
- **Blended retail THB +44.1%** (฿20.59M → ฿29.67M); 137 SKUs rise, **14 held flat**.
- **No-decrease floor:** 14 micro-spares that would have dropped 50–85% (old fixed
  clearance removed) are held at their current price (`pricing.floored=true`); 0 SKUs decrease.
- Medusa push `sync_brand_prices_to_medusa.py --brand eurotramp --write`:
  **151/151 matched → 151 updated, 0 errors**;
  **read-back 151/151 exact across THB/USD/EUR/SGD, 0 mismatch**.
- **FLAGGED:** volumetric CBM / air-vs-LCL **not** applied — no SKU has packing
  dims or weights (frame dims only); owner runs volumetric separately
  (`pricing.volumetric_applied=false`).

---

## [2.74.0] - 2026-06-07

### Added — landed-cost engine consumes real per-SKU vendor freight (Vinci/Vortex/Rampline)

Wires this repo's master landed-cost engine to the new per-SKU DDP freight that
the sibling `vendors` repo (`scripts/sync_freight.py`, BUILD_LOG v1.31.0) writes
to `vendors/<brand>/products` once a SKU has **confirmed vendor packing data**.
This is the last leg of the cross-repo pipeline: shipping-automation refreshes
Europe DDP LCL rates + a `ddp_air` method → vendors syncs `pricing.freight_thb`
per SKU → **this repo re-runs landed + retail from that real freight** → Medusa.

**What changed:**
- `shared/landed_pricing.py` — `price_row()` gains an optional, highest-priority
  **vendor-freight branch**. When the caller passes `vendor_freight_thb` and a
  `vendor_packing_source` in the new `VENDOR_PACKING_SOURCES`
  (`vendor_email`/`vendor_attachment`/`vendor_pricelist`), it uses that real
  freight verbatim (CIF = FOB + vendor_freight; duty on CIF; VAT on CIF+duty —
  the same treatment as the flat-uplift branch and consistent with cost_engine's
  customs base), **bypassing the CBM estimate and the 1.35× flat uplift**. The
  tiered logistics floor/cap clamp and the independent per-currency retail
  derivation (35% GM, 7% TH customer VAT embedded in `retail_thb` only) are
  unchanged and still apply. With no vendor freight supplied the output is
  byte-identical to before — existing callers (`*-catalog/import_pricelist.py`)
  are unaffected.
- **New** `scripts/recompute_landed_from_vendor_freight.py` — gated recompute +
  write-back. Scans `vendors/<brand>/products`, and **only** for SKUs carrying a
  vendor-sourced `pricing.freight_thb` re-runs `price_row` and writes back
  `pricing.{landed_thb,landed_thb_raw,logistics_pct,logistics_clamp,retail_thb,
  retail_usd,retail_eur,retail_sgd,retail_basis,recompute_fx_snapshot,
  recomputed_at}`. Per-brand EUR-FOB resolver: Vinci `eur_fob`; Rampline
  `from_net_nok`×live NOK→EUR; Vortex `fob_usd`→EUR-equivalent at FX (Canada/USD
  origin — DDP-EUR premise flagged). `--dry-run` default; estimate/none rows are
  never touched, so it is a safe no-op before the upstream sync.

**Ordering / current state (verified 2026-06-07):** this step is gated behind two
upstream preconditions that are **not yet met**, exactly as anticipated:
- shipping-automation `cost_engine.py` still exposes only a generic `ddp` method
  (no `ddp_lcl`/`ddp_air`) — the Europe DDP-Air rate refresh has not landed.
- `vendors/scripts/sync_freight.py --write` has **not** populated any
  vendor-sourced freight: a direct query of Firestore DB `vendors` finds **0**
  SKUs across Vinci (1,416)/Vortex (311)/Rampline (241) with `pricing.freight_thb`
  + a vendor `packing_source` (every existing `freight_thb` is an old CBM/flat
  estimate with `packing_source = null`). Per the vendors coverage report only
  **1** SKU (Rampline RL410) is even vendor-confirmed, and it has no product doc yet.

Therefore the recompute (`--dry-run --brand all`) reports **0 eligible / 0 updated**
and **no Medusa push** is performed (there is no *updated* retail to push). The
engine + tool are in place and validated, so a re-run will pick up vendor-freight
SKUs automatically as soon as the upstream sync writes them — no further code
change required.

**Verified:** `price_row` self-test (vendor branch math freight/duty/VAT/landed;
gate holds for estimate sources & zero freight; identical output when vendor
params omitted) — all assertions pass. FOB resolver self-test (Vinci/Vortex/
Rampline, USD→EUR-equiv reproduces THB FOB exactly) — pass. `recompute … --brand
all --dry-run` → 0 eligible across all three brands. `./verify.sh` green.

**Files changed:** `shared/landed_pricing.py`,
`scripts/recompute_landed_from_vendor_freight.py` (new), `CHANGELOG.md`,
`docs/build-summary.html` + `docs/hub.html` (regenerated), `.claude/PROGRESS.md`.

---

## [2.73.0] - 2026-06-07

### Fixed — `scripts/sync_brand_prices_to_medusa.py`: sales-channel-scoped matching (cross-brand-clobber root cause)

The shared price sync built a **global** Medusa SKU index (`_index_all`) and
matched each vendor doc's `item_code`/`handle` against ALL products regardless
of sales channel (first-wins `setdefault`). Because Rampline "Kids Tramp"
articles are Eurotramp-made and resold under **identical** SKUs (97010B, E97047,
E31120, E21898B …), a Rampline run could match — and overwrite — the Eurotramp
variant. v2.72.0 patched this reactively in `rampline-catalog/build_2026_pricing.py`
(`EUROTRAMP_OWNED_FAMILIES` exclusion); this release removes the **root cause**
in the shared sync itself.

**What changed:**
- `_index_all` now keeps **every** candidate per key (list, not first-wins) and
  tags each with its product's `sales_channels.id` set (added `sales_channels.id`
  to the admin `fields`).
- `_match_key(dd, idx, brand_sc, other_brand_channels)` resolves a vendor doc to
  a variant **safe for the requesting brand**: (1) prefer a candidate on the
  brand's own channel `SC[brand]`; (2) else accept one not claimed by any other
  brand (no channel, or only the shared aggregate channels — "Leka Catalogs",
  "Default", "Proposal"); (3) else refuse and record a **cross-brand guard**.
- `run_brand` logs guarded docs (`CROSS-BRAND GUARD: …`) and reports a `guarded`
  count in the per-brand summary.
- `SC` map completed to mirror `sync_vendors_to_medusa.py` — added **rampline**
  and **weplay** (their absence was part of what let the global index clobber).
- `--scope-file` (JSON) and `--brand all` behaviors preserved.

**Why "Leka Catalogs" is allowed:** it's the shared aggregate channel powering
the unified `catalogs.leka.studio` storefront; many brand products live there
only. Pricing those is not a clobber — the guard fires solely when a SKU resolves
**exclusively** to another brand's *dedicated* channel.

**Verified (dry-run):** rampline **64/64** (unchanged, 11 SKUs absent from
Medusa), eurotramp **151/151** (unchanged), vinci **1234/1234** (no over-guard
regression), `--brand all` healthy with `guarded=0` across all 10 brands.
Targeted check: all four collision SKUs are **refused** for a rampline run and
resolve to the correct Eurotramp variant for a eurotramp run.

**Files changed:** `scripts/sync_brand_prices_to_medusa.py`.

---

---

## [2.72.0] - 2026-06-07

### Added — Rampline 2026 retail pricing (THB/USD/SGD/EUR) → Firestore + Medusa go-live

The 2026 Rampline NOK price list (82 priced articles, eff. 2025-12-01) is priced
at **35% gross margin / 10% import duty**, against a fixed FX snapshot
(frankfurter.app 2026-06-05: 1 NOK = 3.5029 THB / 0.10734 USD / 0.09221 EUR /
0.13776 SGD). Supersedes the older 2025 xlsx that `import_pricelist.py` reads.

New `rampline-catalog/build_2026_pricing.py` recomputes the **landed cost** from
`net_nok` via a flat NOK-direct stack (owner-set params 2026-06-07; volumetric is
analysed separately):

```
goods     = net_nok × 3.5029
freight   = 30% × goods          insurance = 1% × goods
CIF       = goods + freight + insurance
duty      = 10% × CIF            import_vat = 7% × (CIF + duty)
clearance = 6% × goods
landed    = CIF + duty + import_vat + clearance
retail_thb = landed / 0.65 × 1.07      ← 35% GM, 7% TH customer VAT INCLUDED
retail_usd/eur/sgd = (landed / 0.65) / FX   ← ex customer-VAT (VAT is TH-domestic)
```

- `retail_thb` is **VAT-inclusive** (×1.07), matching the Vinci/Berliner/Wisdom/
  4soft/Vortex convention. USD/EUR/SGD stay ex customer-VAT; SGD applies the house
  SG-GST multiplier (`sg_nubo_gst_registered=false` → ×1.0) at THB/SGD = 25.4276.
- Writes `rampline-catalog/parsed/rampline_pricing_2026.json` (committed; includes
  the per-article `cost_stack`) and upserts `vendors/rampline/products/{code}`
  (`item_code` + `pricing.*`). Refreshes audit doc
  `vendors/rampline/pricelists/2026-12-01`. Re-runnable offline (falls back to the
  committed JSON's `net_nok` when the vendors worktree is absent).
- Bumped `pricing_config/canonical` `brands.rampline.gross_margin` **0.30 → 0.35**.

Example (RB35): goods 50,673 → landed 81,171 → **retail_thb 133,621** (VAT-incl) /
USD 3,826.70 / EUR 3,287.31 / SGD 4,911.18.

`scripts/sync_brand_prices_to_medusa.py`: added `rampline` → its sales channel.
Pushed prices to Medusa and **read-back verified 64/64 matched variants exact
across THB/USD/EUR/SGD (0 mismatches)**; SGD now live on the Rampline channel.
11 priced articles have no Medusa variant yet (8 spares + RL410 SD + FF1 1002 +
FF1 EXT 1002) and were safely skipped (the sync never creates products).

**Cross-brand guard:** the Rampline list's "Kids Tramp" family (Loop trampolines,
PlayPro rings, springs, jumping beds — 97010B, E97047, E31120, E21898B, …) are
Eurotramp-manufactured items resold under **identical Eurotramp SKUs**, already
priced by the Eurotramp catalog. The first push matched 4 of them by SKU and
overwrote the correct Eurotramp prices; those were **restored** and the whole
Kids-Tramp family is now **excluded** from the Rampline products subcollection
(`EUROTRAMP_OWNED_FAMILIES`) so re-syncs can't clobber Eurotramp.

### Files
- `rampline-catalog/build_2026_pricing.py` (new)
- `rampline-catalog/parsed/rampline_pricing_2026.json` (new)
- `scripts/sync_brand_prices_to_medusa.py` (rampline SC entry)
- `docs/reports/rampline-2026-price-go-live-2026-06-07.md` (new run/verification report)
- Firestore: `vendors/rampline/products/*` (75 pushable), `vendors/rampline/pricelists/2026-12-01`, `pricing_config/canonical`

> Note: v2.71.0 is reserved for in-flight Rampline hero-spec work staged on
> another machine (not yet pushed to origin); this entry is sequenced as 2.72.0
> to avoid a version collision.

---

## [2.71.0] - 2026-06-06

### Added — Rampline hero-product spec enrichment (PDP-perfect specs for the Leka education page)

New `rampline-catalog/enrich_hero_specs.py` (dry-run → apply, idempotent diff-only,
run-log under `rampline-catalog/data/build_runs/`). Hand-curated, vendor-sourced
(rampline.com) spec metadata for the four products featured on Leka Studio's
`/education-solutions/active-challenge-balancing` page, written to the **exact keys
the catalog PDP reads** (the previous crawl-based `enrich_specifications.py` wrote
to `installed_dimensions`, which the PDP ignores, and the crawl had no numeric dims
for these four — so every structured spec field had stayed `0`).

Per product (`rampline-rampball`, `rampline-jumpstone-en`,
`rampline-rampline-slackline`, `rampline-trampoline-loop-en`):
- `metadata.specifications` — `subcategory`, `indoor_outdoor`, and `free_fall_height_cm` (single-size items).
- flat `metadata.fall_height_cm` (single-size items).
- `metadata.spec_table` — `{ title, note?, columns[], rows[][] }` per-model table
  (Rampball ×4 sizes, Jumpstone ×2, Slackline dims, Loop dims) consumed by the new
  `spec_table` renderer in `leka-website` `catalogs/.../product-detail.tsx`.

Medusa v2 metadata shallow-merge preserves existing keys (materials, downloads,
certifications, brand_country, …). Applied to live `leka-medusa-backend` and verified
via the Store API. Run logs: `hero_specs_dryrun_*.json` / `hero_specs_applied_*.json`.

---

## [2.70.1] - 2026-06-06

### Added — Eurotramp full catalog price go-live (kids / BounceCloud / spares)

Pushed the remaining priced-but-unsynced Eurotramp products to Medusa. v2.70.0
only pushed the 34-handle competition/performance line (via `--scope-file`); the
kids, BounceCloud, and accessory/spare-part lines were already priced in
Firestore (`vendors/eurotramp/products[].pricing`, computed by
`vendors/eurotramp-catalog` at FX EUR 38.7877 / USD 33.0472 / SGD 25.974,
retail = landed × 1.30) but had never reached Medusa — so they still showed
`usd=0` stubs on `catalogs.leka.studio`.

**Push.** Ran `scripts/sync_brand_prices_to_medusa.py --brand eurotramp --write`
with **no `--scope-file`**, so all priced vendor docs were included. The sync is
update-only (never creates products), matching Firestore `item_code` → Medusa
variant SKU, falling back to `legacy_sku`, then product handle.

- **151 / 151 priced vendor docs matched (100%) → 151 updated, 0 errors, 0 unmatched.**
- 36 of the 187 `vendors/eurotramp/products` docs remain unpriced (no `pricing`
  block) and were correctly skipped.
- THB/USD/EUR/SGD now live on every priced variant — from spares (~€19; anchor
  bar E20970 ฿744.65, adhesive cartridge E97003 ฿1,645.83) through accessories
  (Adaption bars ET-30800 ฿12,508.71), BounceCloud kids (single ฿86,899.84 /
  3-piece ฿259,367.02 / 6-piece ฿492,197.72), up to playground installs
  (kids-tramp-track-playground 97049 ฿1,126,294.99 / €29,037.43).
- The competition/performance line (already live in v2.70.0) was verified
  **unchanged** (Albatross ฿595,420.25 / €15,350.75).

**Safety.** Pre-push structural backup of all 162 live Eurotramp Medusa products
written to `docs/reports/eurotramp-snapshot-2026-06-06-pre-kids-price-push.json`
(`scripts/eurotramp_snapshot.py --tag pre-kids-price-push`). The full dry-run
price distribution was audited for order-of-magnitude and FX-consistency
anomalies before the live write — **0 anomalies** (every THB = EUR × 38.7877
within 3%, with USD/SGD cross-consistent; `retail_eur` range €19.14–€29,037.43,
median €1,275.69).

### Files
- `docs/reports/eurotramp-snapshot-2026-06-06-pre-kids-price-push.json` (NEW) — pre-push backup snapshot.
- `CHANGELOG.md`, `docs/build-summary.html`, `docs/hub.html` updated. (No code change — the
  sync + snapshot scripts already shipped in v2.70.0; this is a config-free re-run at full scope.)

---

## [2.70.0] - 2026-06-06

### Added — Eurotramp competition/performance line: pricing, dimensions, hero images

Enriched the 34 published products behind
`next.leka.studio/education-solutions/performance-trampoline` (the Eurotramp
competition/performance line — Master, Grand Master, Ultimate + freestyle/DMT,
sets, safety envelope, roller stands, booster boards). Scope pinned in
`data/curated/eurotramp_performance_line.json`. All Medusa writes carry rollback
metadata (`previous_*`); reports under `docs/reports/eurotramp-perf-line-*`.

**Pricing (was 0/34 → 28/34 live).** Fetched the current full **"Price list 2025
(1E)"** (full range, incl. competition) from Gmail via
`scripts/fetch_eurotramp_pricelist.py`. New
`vendors/eurotramp-catalog/scripts/price_performance_line.py` computes landed +
retail (THB/USD/EUR/SGD) with the established model (ins 1% + freight 18% + duty
10% + VAT 7% + clearance/40, retail = landed × 1.30) at the pinned kids-run FX
(EUR 38.7877 / USD 33.0472 / SGD 25.974) and writes `pricing.*` to
`vendors/eurotramp/products`. Pushed to Medusa via
`scripts/sync_brand_prices_to_medusa.py` — **added `eurotramp` to the SC map** and
a new **`--scope-file`** filter so only the competition line went live (Master
฿313,809 / Ultimate ฿503,099 / …). 6 products not in the list are flagged.

**Dimensions (was 0/34 → 28/34).** New `scripts/backfill_eurotramp_dimensions.py`
parses open-frame dims from the pricelist descriptions (e.g. Ultimate
520×305×115 cm) → `metadata.length/width/height_cm`, falling back to
`vendor_data`. The storefront spec table already renders these rows
(`product-detail.tsx` length/width/height guards) — Dimensions now appear; no
storefront change needed.

**Hero images + gallery (33/34 real-photo thumbnails).** New
`scripts/fix_eurotramp_perf_images.py` re-points junk thumbnails (cert/badge/
placeholder) to real photos — repointing in-gallery photos (hdts, set-of-landing-
mats) and rehosting real scrape photos to GCS for bungee-longe, spieth-ground-
safety-mat, booster-board-freestyle and trampoline-set-stationary — and
de-clutters galleries (real photos first, merchant logos/badges demoted, never
dropped). 1 true gap flagged (`trampoline-set-one-field`).

**Reports.** `scripts/audit_eurotramp_perf_line.py` (pre/post),
`docs/reports/eurotramp-perf-line-gaps-2026-06-06.md` (residual gaps + the
kids/spares price-push follow-up: 123 Firestore docs priced-but-never-pushed).

### Added (scripts)
- `scripts/audit_eurotramp_perf_line.py`, `scripts/backfill_eurotramp_dimensions.py`,
  `scripts/fix_eurotramp_perf_images.py`, `data/curated/eurotramp_performance_line.json`.
- `scripts/sync_brand_prices_to_medusa.py`: `eurotramp` SC + `--scope-file`.
- (vendors repo) `eurotramp-catalog/scripts/price_performance_line.py`.

---

## [2.69.0] - 2026-06-05

### Changed — Eurotramp catalog cleanup: categories, collections, images, variant merges

End-to-end cleanup of the **Eurotramp** brand (was 187 → now **162** products) on the
live Medusa catalog (`leka-medusa-backend`), driven by new reusable scripts. All
changes carry rollback metadata (`previous_*`) and timestamped reports under
`docs/reports/`.

**Phase 1 — Categories + family collections + discontinued (`scripts/reassign_eurotramp_categories.py`,
`data/curated/eurotramp_category_map.json`).** The original uploader had dumped every
Eurotramp product into a single broken `competition-trampolines` category (the scrape's
`category` field was uniformly corrupt). Created the **13 real eurotramp.com categories**
and reassigned all 187 products (REPLACE semantics, verified by probe) — `competition-trampolines`
went 80 → 5; **0 uncategorized, 0 multi-category**. Added **10 cross-cutting family
collections** (BounceCloud, Kids Tramp, Wehrfritz FUN, Ground Trampoline, Trampoline Track,
Grand Master, Ultimate, Minitramp, Safety & Landing Mats, Roller Stands & Transport).
**Unpublished 10 discontinued products** (Premium, Grand Master Exclusiv [+Open-End],
Double-Minitramp 190, Hobbytramp, Octotramp, Trampoline Track Stationary/Vario, Tchoukball,
Trimm Tramp) → `status=draft`.

**Phase 2 — Image correction (`scripts/fix_eurotramp_thumbnails.py`,
`scripts/backfill_eurotramp_recoverable_photos.py`).** Re-pointed **24** products whose
thumbnail was a cert/feature-badge/symbol/placeholder to the best real photo already in
their gallery (handle-overlap-guarded, photos-first reorder, never drops images).
Backfilled **71 real product photos** to **32** products from eurotramp.com (size-upgraded
to largest available, rehosted to `gs://ai-agents-go-vendors/eurotramp/<handle>/`), fixing a
scrape↔Medusa handle mismatch (`112--125`) that had hidden recoverable photos. Real-photo
thumbnails: 115 → **147** (122/162 after merges). Remaining 40 gaps (vendor JS
configurators / uncrawled spare parts) are listed in `docs/reports/eurotramp-image-gaps-2026-06-05.md`
for manual sourcing — not fabricated.

**Phase 3 — Variant merges (`scripts/merge_eurotramp_variants.py`,
`data/curated/eurotramp_merge_groups.json`).** Consolidated over-split products into single
products with proper Medusa options + variants, deleting 25 redundant members:
- **BounceCloud** → 9 variants (Configuration {Single, 3-Piece, 6-Piece} × Colour {Green, Orange, Yellow}).
- **Kids Tramp Track "Playground"** → 8 variants (Length {4/6/8/10 m} × Variant {Type A/Type B}; the
  Type A/B labels are placeholders for the 9704x/9705x spec series — rename when confirmed).
- **Bonded impact protection / Jumping bed / PlayPro lip — Kids Tramp Track** → 4 Length variants
  each (draft accessory ladders, renamed to clean generic handles).

Member SKUs preserved on the new variants; canonical handles preserved (ladders renamed);
brand/category/collection links intact; `merged_handles` breadcrumbs + redirects written
(`docs/reports/eurotramp-merge-redirects-2026-06-05.json`). Held back as `needs_review`
(distinct parts / ambiguous spec): clamping-jaw, torsion-spring L/R, single-tile
cornerpiece/centrepiece families, top-sheet-for-bouncecloud, adhesive-cartridge.

### Added
- `scripts/eurotramp_snapshot.py` — full pre/post-change product backup + diff source.
- `scripts/reassign_eurotramp_categories.py`, `scripts/fix_eurotramp_thumbnails.py`,
  `scripts/backfill_eurotramp_recoverable_photos.py`, `scripts/merge_eurotramp_variants.py`.
- `data/curated/eurotramp_category_map.json`, `data/curated/eurotramp_merge_groups.json`.

---

## [2.68.0] - 2026-06-02

### Added — `scripts/hide_leka_project_lowres_products.py`: hide Leka Project products with no/low-res photos

New maintenance script that removes "Leka Project" (the Wisdom-rebranded SC
`sc_01KNKTHC0B7KFEDSZ3NNM49JQW`) products from the storefront when they have no
real photo or only a low-resolution image, so `catalogs.leka.studio` only shows
products with a usable picture.

**How it hides:** flips the Medusa product `status` from `published` to
`draft`. The storefront reads the Store API, which returns only published
products, so a draft product silently drops off the catalog — no storefront
(`eukrit/leka-website`) code change needed.

**A product is hidden when either:**
- **no_image** — `metadata.image_status == "placeholder"` (on the v2.34.0
  "Image coming soon" card), or it has no `images[]` and no `thumbnail`.
- **low_resolution** — its representative image's longest edge is `<`
  `--min-dimension` (default **400 px**). Measured by downloading the thumbnail
  through the public proxy and reading the dimensions with Pillow. Images whose
  size can't be read (transient/network) are **left published** — never hidden
  on an unreadable probe.

**Reversible + idempotent.** Each hidden product is tagged
`metadata.hidden_by="image-quality-filter"`, `hidden_reason`, `hidden_at`, and
`hidden_dims` (low-res only). `--restore` re-publishes exactly the products this
script hid and clears those keys, so a bad threshold is a one-command undo.

**Phases (pick one):** `--audit` (read-only report), `--hide` (with `--dry-run`
to preview, `--limit N` to smoke-test, `--min-dimension N` to tune the cutoff),
`--restore`. Admin enumeration uses the admin API (not the Store API) so it can
see already-drafted products for restore/audit. Auth + retry mirror
`scripts/backfill_leka_project_images.py` (Medusa admin creds from Secret
Manager `medusa-admin-email`/`medusa-admin-password` or env vars).

Recommended run order against prod:
`--audit` → `--hide --dry-run` → `--hide` → `--audit`.

#### Files

- `scripts/hide_leka_project_lowres_products.py` — new
- `VERSION`, `CHANGELOG.md`, `docs/build-summary.html`, `.claude/PROGRESS.md`

---

## [2.67.0] - 2026-06-02

### Changed — tighten CBM-based tiered logistics bands across all brands (supersedes draft #100)

Per user direction (2026-06-02), tightened the shared `LOGISTICS_TIERS` clamp
table (logistics cost as % of FOB/EXW-in-THB, by EUR-equivalent FOB band). The
lower ceilings clamp outlier landed costs harder, generally **lowering** landed
and retail prices for affected SKUs. Rebuilt cleanly on `main` — the original
draft PR #100 (branched at v2.59.0) was stale/conflicting and is superseded.

| FOB band (EUR) | OLD min,max | NEW min,max |
|---|---|---|
| < 500   | 0.80, 2.50 | 0.60, 1.20 |
| < 2,000 | 0.60, 1.80 | 0.50, 1.00 |
| < 10,000| 0.45, 1.20 | 0.40, 0.80 |
| ≥ 10,000| 0.35, 0.80 | 0.30, 0.60 |

**Files (tier literals + fallbacks):** `shared/landed_pricing.py` (master table),
`shared/wisdom_pricing.py` (top-tier fallback `0.35,0.80 → 0.30,0.60`),
`shared/pricing_config.py` (docstring), `src/main.py` (`_empty_config` Flask
fallback), `berliner-catalog/import_pricelist.py` + `foursoft-catalog/import_pricelist.py`
(local copies — these two read their own literal, not Firestore). The 4soft
`EXW_DISCOUNT = 0.20` (PR #98) is preserved untouched; only its tier clamp moved.

**Seed hygiene:** `scripts/seed_pricing_config.py` 4soft block reconciled to the
live doc (`exw_discount: 0.20` + reseller note) so a future `--force` re-seed no
longer reverts PR #98's discount.

**Activation:** the Firestore canonical doc `pricing_config/canonical` was updated
**surgically** via new `scripts/update_logistics_tiers.py` (only `logistics_tiers`,
leaving brand blocks intact — a full `--force` re-seed would have clobbered 4soft's
live 0.20 discount). Per-brand:
- **4soft** — Firestore repriced + **pushed to live Medusa** (`sync_brand_prices_to_medusa`, updated=2394, errors=0, ~−11.5%).
- **Archimedes** — Firestore repriced (~−15%; no Medusa storefront yet).
- **Berliner** — **held**: a reprice bundles a pre-existing +22.6% duty/VAT catch-up (last repriced 2026-05-13, before the v2.20–v2.29 duty+VAT add), unrelated to the tier change.
- **Vinci** — Firestore repriced (mean −8%) but **Medusa push held**: 48 SKUs rise up to +25% from v2.29/FX drift since its 2026-05-22 push.
- **Rampline** (−0.8%, deferred-Medusa path) and **Wisdom/WePlay** (not tier-affected, flat paths) — not pushed.

## [2.66.1] - 2026-06-02

### Cleanup — drop the last broken Wisdom image + sweep unreferenced old GCS objects (follow-up to 2.66.0)

New script `scripts/cleanup_old_wisdom_images.py` (`--drop-broken` / `--sweep` /
`--all`, dry-run default, `--write`).

- **drop-broken:** removed the single `_wisdom_2025_` gallery image whose GCS
  source object never existed (`leka-project-aid1ofsb`, a dead link the 2.66.0
  re-host couldn't copy). Not the thumbnail; the 2 neutral images remain. This
  clears the last store-API residual.
- **sweep:** deleted **4,340** now-unreferenced old objects under
  `leka-project/{spatial_v2,verified}/` that carry the `_wisdom_2025_` token —
  each only after confirming (a) no live product references it and (b) an
  identical neutral `catalog2025/` copy exists (bytes preserved). **1,678
  copy-less orphans were left in place** (never re-hosted; private + unreferenced,
  so not a leak — deleting them would lose the only bytes; sweep them later only
  if explicitly desired). 0 errors.

**Verification:** `--verify` now reports **all** trace counts = 0
(`wisdom_image_products` = 0). Spot-checked: a neutral `catalog2025/` image still
serves HTTP 200; a deleted old `_wisdom_2025_` URL now 404s.

#### Files
- `scripts/cleanup_old_wisdom_images.py` (NEW).

---

## [2.66.0] - 2026-06-02

> Renumbered v2.58.0 → v2.66.0 during rebase onto main: main had advanced to
> 2.65.0 while this work was in flight. Work unchanged.

### Security/Privacy — Scrub avoidable internal "Wisdom" vendor traces from the Leka Project brand

The Wisdom→Leka Project rebrand left several internal vendor traces in Medusa.
A store-API exposure audit (with the browser-exposed publishable key) confirmed
which traces reach an **unauthenticated** customer; we then scrubbed the
avoidable leaks. New script `scripts/scrub_leka_project_wisdom_traces.py`
(`--verify` / `--dry-run` / `--write`, idempotent).

**Store-API exposure found (before):**
- `variant.metadata.exw_source` "(Wisdom/TUMACO EXW Shanghai…)" + `exw_shanghai_usd`
  — returned **by default** (no special query). Worst leak: vendor name **and** cost.
- Image URLs `…/spatial_v2/<code>_wisdom_2025_pNN_*.jpeg` — in every `<img src>`
  **by default**.
- 17 products still carried literal `wisdom-…` **handles** (the product URL slug) —
  public by default.
- `product.metadata.{source_brand_internal, legacy_handle, outdoor_play.wisdom_item_code,
  source, wisdom_item_code}` — hidden by default but retrievable by anyone via
  `?fields=+metadata` (the publishable key is browser-exposed).

**Scrubbed (Medusa + GCS only — internal codes on Firestore/Firebase left intact):**
- Metadata: removed `source_brand_internal`, `legacy_handle`, top-level
  `wisdom_item_code`, and `outdoor_play.wisdom_item_code`; rewrote
  `source` "wisdom-outdoor-play-merged" → "outdoor-play-merged". **6,376 products.**
  (Medusa v2 metadata is a shallow merge — keys are deleted by sending value `""`,
  the empty-string sentinel; `null`/omission do **not** delete.)
- `exw_source`: "PI 2026031801 (Wisdom/TUMACO EXW Shanghai, 2026-03-18)" →
  **"PI 2026031801 (EXW Shanghai, 2026-03-18)"**. **4 variants.** Kept PI ref,
  EXW Shanghai, USD cost, `legacy_sku`.
- Images: server-side GCS copy (same bucket, no download)
  `leka-project/spatial_v2/…_wisdom_2025_…` → `leka-project/catalog2025/spatial_v2_…_2025_….jpeg`
  and repointed each product's thumbnail+gallery to the neutral proxy URL.
  **2,405 products / 4,340 objects** (1 source object missing → original left in place,
  deferred). Old objects left for a later cleanup sweep.
- Handles: renamed the 17 leftover `wisdom-…` slugs to `leka-project-<id>`;
  appended old→new to `migration/wisdom-handle-redirects.json` so storefront
  redirects survive.

**Kept intentionally:** `variant.metadata.legacy_sku` (the Medusa↔Firestore bridge
used by pricing/image tooling), brand `handle="wisdom"` (storefront
`?filters[brand][handle]=wisdom`), and geography tokens (`_usa_2025_`, `_intl_2025_`,
`_china_2025_`, `catalog_source`).

**Post-scrub verification (store API):** residual `_wisdom_2025_` images = 1
(the missing-source object), exw vendor traces = 0, wisdom- handles = 0,
`outdoor_play.wisdom_item_code` = 0, `source_brand_internal`/`legacy_handle` = 0.
Re-hosted image confirmed serving HTTP 200 `image/jpeg` via the proxy; exw + handle
redirect confirmed live.

#### Files
- `scripts/scrub_leka_project_wisdom_traces.py` (NEW) — verify + scrub.
- `docs/reports/leka-project-wisdom-exposure.json` (NEW) — exposure audit.
- `migration/wisdom-handle-redirects.json` — +17 handle redirects.

---

## [2.65.1] - 2026-06-02

### Documented — 4soft conditional discounts (2.5% prepay + 2.5% e-shop) available but NOT applied

The 20% reseller discount applied in v2.65.0 (see `foursoft-catalog/DEPLOYMENT_LOG.md`)
is the **basic** EXW rate. Supplier 4soft (Roger, 2026-05-31) additionally offers a
2.5% prepayment discount and a 2.5% e-shop discount; per the user these stay
**unapplied** for now — the catalog is held at the 20% basic rate.

- Firestore `pricing_config/canonical.brands.4soft` annotated with
  `additional_discounts_available { prepayment_pct 0.025, eshop_pct 0.025, applied false }`
  + `additional_discounts_note`. **Metadata only** — `exw_discount` stays `0.20`,
  `gross_margin` stays `0.40`; no `vendors/4soft/products` or Medusa reprice.
- `foursoft-catalog/DEPLOYMENT_LOG.md` — follow-up entry; verified Firestore/Medusa
  SGD still match at 20% (C5-01A-05 S$1374.47, G2-14A-02 S$284.61, V9-01A-001 S$11048.45).

## [2.65.0] - 2026-06-02

### Changed — `scripts/build_r2_curated.py`: Medusa-SGD-first pricing + versioned PO codes + 840 sq.m

Brings the curated Dulwich Rev2 BoQ builder up to the state that produced the
live draft order `order_01KT34JZ7MPE7JT887R3JCKJFR` (consumed by
`eukrit/leka-projects` main, v1.58.0):

- **`price_of()` now prefers the Medusa variant SGD price** (the authoritative
  pipeline retail) over the old Rev1-BoQ / Wisdom-FOB×4.44 fallbacks, for both
  4soft EPDM graphics and Wisdom/"Leka Project" items. The manual/draft branch
  prices an item only when its Medusa variant carries an SGD price.
- **7 PO Wisdom codes corrected to their versioned published forms**
  (HW1-S256→`-V01`, HW1-S367→`-V01`, HW1-S270→`-V02`, HW1-S281→`-V02`,
  CSS-DMGD-BZ→`-V01`, HW4-SZ006-V01→`-V02`, HW1-S016-V02→`-V03`) + catalog
  names — they now resolve to the priced published products instead of the
  unpriced `proposal-*` draft stubs.
- **Zone A Grass Green EPDM surfacing 974 → 840 sq.m.**
- **`LP` data path now `$LEKA_PROJECTS_WORKTREE`-overridable** (the hardcoded
  goofy-snyder worktree path was machine-specific / lost to OneDrive prunes).

## [2.64.0] - 2026-06-02

### Fixed — rampline SGD backfill derived from VAT-inclusive THB (latent double-tax)

Audited how every Leka brand derives `retail_sgd` to rule out a "double FX
conversion" / tax-contaminated SGD price. **8 brands are correct**; the canonical
formula is `retail_sgd = ((landed_thb / sgd_thb) / (1 - gm)) * sg_gst_mult` —
derived from the genuine THB **landed cost** (freight/duty/import-VAT accrue in
THB), excluding the 7% Thai *domestic* customer VAT, with `sg_gst_mult = 1`
(Nubo not GST-registered).

**The one wrong path** was `scripts/backfill_sgd_pricing.py` → `_run_rampline()`,
which divided the **VAT-inclusive `retail_thb`** by the SGD rate
(`sgd = rt / sgd_thb`). Replaced with the canonical landed-cost derivation,
matching rampline's own importer (`rampline-catalog/import_pricelist.py:588`).

**Severity = latent, not live.** The stored audit doc
`vendors/rampline/pricelists/2026-05-13` predates the TH-customer-VAT convention
(v2.29.0, 2026-05-22), so its `retail_thb` is *pre-VAT* (e.g. `SD 02`: landed 468,
retail_thb 669 = 468/0.70, no ×1.07). The old formula therefore produced correct
SGD *by accident*. The current importer now writes a **VAT-inclusive** `retail_thb`,
so regenerating that audit doc would have made the old backfill overstate SGD by
7%. The fix removes that landmine and makes the backfill VAT-convention-agnostic.
Re-ran `--write`: 127 variants refreshed (drift +0.10%, pure FX), old values
backed up to `scripts/backfill_backups/rampline_2026-06-02T02-01-06*.csv`.

Regression dry-run `--brand all`: vinci/berliner/designpark/wisdom THB drift
≤0.33% (FX only) — their formulas untouched.

**Verified non-issues (no change):** the 2% FX buffer does *not* double-compound —
in `landed_thb / sgd_thb` the +2% on the source rate (EUR/USD→THB) and on SGD→THB
cancel for the goods pass-through, surviving only on the genuinely-THB cost stack
(intended). `src/main.py` divides a THB figure by SGD but off `retail_pre_tax_thb`
(no TH VAT) → equivalent to canonical.

Also corrected the stale `weplay-catalog/import_pricelist.py` docstring, which
described the old `retail_thb * sg_gst_mult / SGD_THB` SGD formula (code at line
269 was already canonical) — a copy-paste hazard for new brands.

#### Files

- `scripts/backfill_sgd_pricing.py` — rampline SGD off `landed_thb`; skip-if-no-landed guard; SGD-drift report line
- `weplay-catalog/import_pricelist.py` — docstring corrected to canonical SGD/USD/THB formulas
- `VERSION`, `CHANGELOG.md`, `docs/build-summary.html`, `docs/hub.html`

---

## [2.63.0] - 2026-06-02

### Changed — New hero photo for Wallboard Toys Standard Package (CSS-QBWJ-BZ)

Set the vendor-supplied product photo as the **primary/hero image** for the
Wisdom (Leka Project) product **Wallboard Toys Standard Package** (item code
`CSS-QBWJ-BZ`, Medusa `prod_01KNKW16TS5FCYTGN4VVGR7PPW`).

The new photo was uploaded to the private, UBLA image bucket
`gs://ai-agents-go-vendors` under both `leka-project/catalog/` and
`wisdom/catalog/` as `CSS-QBWJ-BZ_hero.jpg` (no `make_public`; served via the
storefront proxy) and propagated to all three surfaces:

- **Medusa** — `thumbnail` + image `rank 0` set to the hero proxy URL; the
  three existing catalog images follow at ranks 1–3.
- **Firestore** `products_wisdom/CSS-QBWJ-BZ` (DB `leka-product-catalogs`) —
  `images[]` reordered so the hero is `is_primary: true`; the legacy
  `storage.googleapis.com/ai-agents-go-documents/...` URLs migrated to the
  `catalogs.leka.studio/api/i/leka-project/...` proxy path; `thumbnail` +
  `primary_image` set to the hero.
- **Static JSON** `wisdom-catalog/web-app/public/data/cat_other.json` — same
  migration (hero first, deprecated documents-bucket URLs → proxy URLs).

Hero proxy URL:
`https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-QBWJ-BZ_hero.jpg`
(verified HTTP 200, 18,513 bytes).

> Note (Hexagon Grid): a requested image update for the "EPDM Hexagon Grid
> 45 mm" interlocking tile (`NGHG`/`NGHR`/`NGHB`/`NGHGY`) was **not applied** —
> the product does not exist on Medusa (title/SKU/`natural grass` searches all
> returned 0) nor in Firestore `products_epdm`/`products_infill`. Creating a
> product is out of scope for an image-update task; flagged for confirmation.

#### Files

- `wisdom-catalog/web-app/public/data/cat_other.json` — CSS-QBWJ-BZ `images[]`
  hero + proxy migration.

## [2.62.0] - 2026-06-02

### Fixed — proposal-export draft-order retrieval + build_r2 stale data paths

Two fixes uncovered while wiring the Dulwich R2 proposal to the synced Medusa
prices.

**`medusa-backend` `GET /admin/draft-orders/:id/proposal-export`** — the endpoint
the leka-projects proposal renderer calls returned **404 for every draft order**:
`orderModule.retrieveOrder(id)` does not return draft orders in Medusa v2.13
(verified live). Replaced it with `query.graph({ entity: "order", filters: { id,
is_draft_order: true } })` (the same path the core `/admin/draft-orders/:id`
route uses), keeping the response contract byte-identical. **Requires a Medusa
backend deploy to take effect** — the R2 render pipeline is blocked until then.

**`scripts/build_r2_draft_order.py`** — the hardcoded `LP` data dir pointed at a
stale worktree (`goofy-snyder-ab838e`) whose R2 data files no longer exist.
Made it overridable via `LEKA_PROJECTS_R2_DIR` so the builder can target whichever
worktree/checkout holds the current `dulwich-singapore-r2-selection.json` etc.

Verified end-to-end against live Medusa: building the R2 draft order now prices
**85/86 published lines from the Medusa SGD price** (0 from the `fob×4.44`
heuristic), e.g. HW1-S292 S$16,003.49 — the synced catalog value.

#### Files

- `medusa-backend/src/api/admin/draft-orders/[id]/proposal-export/route.ts` — `query.graph` draft-order retrieval
- `scripts/build_r2_draft_order.py` — `LEKA_PROJECTS_R2_DIR` env override for the data dir
- `VERSION`, `CHANGELOG.md`, `docs/build-summary.html`, `docs/hub.html`

---

## [2.61.0] - 2026-06-02

### Changed — Sync Dulwich R2 proposal pricing to Medusa (drop the fob×4.44 heuristic)

Made the **Medusa SGD price authoritative** for the customer-facing Dulwich R2
proposal, replacing the divergent `SGD ≈ FOB × 4.44` quick heuristic that ran
~63% above the reconciled catalog retail.

**Root cause:** the Wisdom→Medusa price push only ever wrote THB (retail) + USD
(FOB), so the 36 Leka-Project variants had **no SGD price** in Medusa — forcing
`build_r2_draft_order.py` onto `fob×4.44`.

**Part A — backfill SGD into Medusa** (`wisdom-catalog/sync_po_sgd_to_medusa.py`,
new): pushes `sgd = pricing.retail_sgd` (+ unchanged `thb = retail_thb`,
`usd = fob_usd`) onto the 36 Dulwich variants, sourced from
`products_wisdom/<code>.pricing` (the values reconciled in the v2.60.0 report).
`update_variant_prices` replaces the list, so all three currencies are sent
together. **36/36 variants updated and verified live** (SGD added, THB/USD
preserved).

**Part B — repoint the R2 builder** (`scripts/build_r2_draft_order.py`): the SGD
unit price now resolves **Medusa variant SGD price → Rev1 BoQ retail_sgd →
fob×4.44 last-resort → TBC**. `index_all` captures each variant's SGD price;
`price_for` returns a `source` recorded as per-line `metadata.price_source`; a
warning lists any line that still falls back to the heuristic. Validated live:
all 36 Dulwich Wisdom codes now resolve via `medusa` at the catalog price
(e.g. DDGT-BZ S$1,462.64 → **S$899.41**; PO-wide S$337,748.96 → **S$207,690.51**).

> The leka-projects Dulwich R2 session must **re-run** `build_r2_draft_order.py`
> (`--write`) to rebuild the draft order with the synced prices — that step
> writes a live customer-facing draft order and was intentionally not triggered
> here.

#### Files

- `wisdom-catalog/sync_po_sgd_to_medusa.py` (new) — SGD→Medusa backfill (dry-run default)
- `scripts/build_r2_draft_order.py` — Medusa SGD authoritative; `fob×4.44` demoted to last-resort
- `VERSION`, `CHANGELOG.md`, `docs/build-summary.html`, `docs/hub.html`

---

## [2.60.0] - 2026-06-02

### Added — Dulwich PO 2026060101 FOB→SGD per-product pricing breakdown (report + CSV)

Auditable, per-product pricing report for the Wisdom Dulwich proforma invoice
(PO `2026060101` from TUMACO LIMITED, dated 2026-06-01, 36 line items, USD
76,020.52). Shows the full chain from **FOB USD → retail SGD** step by step for
every line, using the **flat China path** (CIF ≈ FOB) exactly as the ingest
called `shared/wisdom_pricing.py` (without CBM).

- Reconstructs the chain locally from live Firestore
  (`leka_vendor_quotations/wisdom-PO-2026060101` + `products_wisdom/<code>.pricing.*`)
  and reconciles every computed value against the stored pricing:
  **36/36 rows match exactly** across VAT / Landed THB / Retail THB / Retail USD /
  Retail SGD (0 mismatches). Worked example: DDGT-BZ FOB $329.21 → CIF ฿10,930.43
  → landed ฿11,695.56 → retail **S$899.41** (== stored `pricing.retail_sgd`).
- Highlights the **7 first-time-priced sets** (`DDJM-JQ01-V01`, `DDGT-BZ`,
  `DDHD-BZ`, `CSS-QB-BZ`, `CSS-DMGD-BZ-V01`, `CSS-CBZJ-BZ`, `CSS-QBWJ-BZ`).
- Shows the catalog flat-path retail (≈ FOB × 2.732) alongside the customer-facing
  Dulwich **R2 proposal** heuristic `SGD ≈ FOB × 4.44`
  (`leka-projects/build_r2_draft_order.py`, `104.09 × 1.05 ÷ 24.6`) so the
  difference is visible (PO-wide S$207,690.51 vs S$337,748.96, +63%).
- Constants at ingest: USD→THB 33.2020, SGD→THB 26.0071, import duty 0%
  (ASEAN–China FTA Form E), import VAT 7%, gross margin 50%, TH customer VAT 7%
  (THB retail only), SG GST off (Nubo not GST-registered → ×1.0).

Report served via the gateway:
`https://gateway.goco.bz/leka-product-catalogs/reports/dulwich-po-2026060101-pricing.html`.

#### Files

- `docs/reports/dulwich-po-2026060101-pricing.html` (new) — Leka Design System report
- `docs/reports/dulwich-po-2026060101-pricing.csv` (new) — spreadsheet export
- `data/dulwich-po-2026060101-report.json` (new) — reconciled dataset
- `scripts/_build_dulwich_report_data.py` (new) — pulls live Firestore + reconciles
- `scripts/_gen_dulwich_report_html.py` (new) — renders HTML + CSV
- `VERSION`, `CHANGELOG.md`, `docs/build-summary.html`, `docs/hub.html`

---

## [2.59.0] - 2026-06-01

> Renumbered 2.56.0 → 2.59.0 during merge with main (2.55.0–2.57.0 were taken by
> the Gum-tec brand work + raw-media request that landed first). Work unchanged.

### Added — Enrich Medusa with the embedded product photos from the Dulwich PO Excel

The 2026-06-01 Dulwich PO Excel embeds one clean single-product studio photo per
line item (column C), stored as EMF/WMF/PNG inside the `.xlsx`. Extracted all 36,
mapped each to its item code via the drawing anchors, rasterized the EMFs, and
used them to enrich the matching Medusa (Leka Project) products.

Three new scripts (the pipeline is reproducible):

- `wisdom-catalog/extract_po_images.py` — reads `xl/drawings/drawing1.xml`
  anchors + `.rels` to pair each embedded media file with its PO line-item code,
  writes `exports/po_images_raw/<code>.<ext>` + `manifest.json`. (36/36 mapped.)
- `wisdom-catalog/convert_po_emf.ps1` — rasterizes EMF/WMF/PNG → normalized PNG
  via Windows GDI+ (`System.Drawing`), upscaled to 800px long-side
  (HighQualityBicubic). No ImageMagick/Inkscape/LibreOffice on the box; .NET
  renders the metafiles natively. 36/36 converted.
- `wisdom-catalog/enrich_medusa_from_po_images.py` — uploads each PNG to
  `gs://ai-agents-go-vendors/leka-project/po-20260601/<code>.png` (the PRIVATE
  proxy bucket; served via `https://catalogs.leka.studio/api/i/leka-project/…`,
  never made public), resolves the Medusa product via the Leka Project
  legacy_sku index, and updates images (full-replace semantics).

Hero policy (`--hero-all` overrides): set the PO photo as the hero/thumbnail only
where the current hero is a placeholder or a 2025-catalog crop
(`/spatial_v2/`, `_wisdom_2025_`, `/catalog/…_imgN`); curated `_notionr2_` heroes
are kept. The PO photo is added to the gallery in all cases.

Result: **31 heroes replaced** (incl. the 2 placeholders `HW1-S281-V02`,
`CSS-CBZJ-BZ`), **5 curated `notionr2` heroes kept** with the PO photo added to
gallery; 36 GCS objects uploaded, 0 errors. Verified proxy serves HTTP 200.

#### Files

- `wisdom-catalog/extract_po_images.py`, `wisdom-catalog/convert_po_emf.ps1`,
  `wisdom-catalog/enrich_medusa_from_po_images.py` (new)
- `wisdom-catalog/.gitignore` (ignore regenerable `exports/po_images_{raw,png}/`)
- `CHANGELOG.md`, `VERSION`, `docs/build-summary.html`, `wisdom-catalog/DEPLOYMENT_LOG.md`

---

## [2.58.0] - 2026-06-01

> Renumbered 2.55.0 → 2.58.0 during merge with main. Work unchanged.

### Added — Ingest Wisdom Dulwich PO `2026060101` pricing (Firestore + Medusa + quotation)

Ingested the **2026-06-01 Dulwich Singapore proforma invoice** (PO `2026060101`
from TUMACO LIMITED, 36 line items, 242 units, **USD 76,020.52**, price term
*Ex-work Shanghai*) as the authoritative FOB for those Wisdom codes.

New script `wisdom-catalog/ingest_po_pricing.py` (dry-run by default, `--write`):
reads the PO Excel, matches every code to `products_wisdom` (36/36 matched, exact
+ normalized fallback), recomputes landed/retail (THB/USD/SGD) via the canonical
`shared/wisdom_pricing.py`, and writes:

- `products_wisdom/{code}.pricing.*` — clean PO `fob_usd` + recomputed
  landed/retail + rates + `price_date=2026-06-01` + `price_source`; plus
  top-level `volume_cbm` from the PO. Overwrites all 36 (PO is authoritative).
- **7 codes priced for the first time** (previously no FOB → would render TBC in
  the Dulwich R2 proposal): `DDJM-JQ01-V01`, `DDGT-BZ`, `DDHD-BZ`, `CSS-QB-BZ`,
  `CSS-DMGD-BZ-V01`, `CSS-CBZJ-BZ`, `CSS-QBWJ-BZ` (Holey Block sets + Water Play
  standard packages). `HW1-S016-V03` corrected 225.00 → 225.64.
- `leka_vendor_quotations/wisdom-PO-2026060101` — the PO snapshot (vendor, date,
  price term, total, 36 `{item_code, fob_usd, volume_cbm, qty, amount_usd}` items).
- Medusa: pushed recomputed THB retail + USD FOB to **36 Leka-Project variants**
  (auth via Secret Manager `medusa-admin-email`/`-password`).
- Handoff `wisdom-catalog/exports/dulwich-po-2026060101-priced.json` for the
  downstream leka-projects Dulwich R2 proposal session.

Reuses `update_pricing.update_medusa` + `shared/medusa_importer.py` (legacy_sku
index) — no new pricing math. EPDM Graphics are 4soft (not in this Wisdom PO).

#### Files

- `wisdom-catalog/ingest_po_pricing.py` (new)
- `wisdom-catalog/exports/dulwich-po-2026060101-priced.json` (new)
- `wisdom-catalog/DEPLOYMENT_LOG.md`, `CHANGELOG.md`, `VERSION`, `docs/build-summary.html`

---

## [2.57.0] - 2026-06-01

### Changed — Wisdom raw-media request email now asks for weight + a per-code shared drive

Sent the full Wisdom vendor-data request to the Huasenwei team
(`alex@`, `amanda@`, `martin_zhu@`, `martin@huasenwei.com`) via Gmail DWD
as `eukrit@goco.bz`, attaching the timestamped 5,071-SKU Excel export
(`wisdom_raw_media_request_2026-06-01.xlsx`). Message id `19e832026e7becde`.

Two body changes were made to `request_raw_media_from_wisdom.py` before
sending:

1. Added an explicit **product weight (kg) + packed/carton gross weight**
   bullet to the "For each item code we would like" list (the Excel already
   carried a Weight column; the ask now matches). Weight is our biggest gap
   — only 916 / 5,071 SKUs have it on file.
2. Rewrote the image paragraph into a firm request for **a single shared
   Google Drive (or Dropbox / WeTransfer) folder of high-resolution photos
   for all 5,000+ SKUs, organized by item code**, so we can bulk-download
   and auto-map each photo to its code. Our current images mostly came from
   shared catalog-page layouts that can't be assigned per SKU.

Coverage rollup at send time: descriptions 5,029/5,071 · FOB 4,816 ·
dimensions 3,813 · weight 916 · images 2,840.

#### Files

- `wisdom-catalog/request_raw_media_from_wisdom.py` — `build_email_body()`
  weight bullet + shared-drive image ask.

---

## [2.56.0] - 2026-06-01

### Changed — Rename brand "Gum-tec" → "Gum-tech" (typo fix, full slug rename)

The brand added in v2.55.0 was onboarded with a typo: the real vendor is
**Gum-tech GmbH** (gum-tech.de). Corrected the brand everywhere — display
name, Brand-module handle, and the live prod data (sales channel + product
handles + metadata). Full structural rename: slug `gumtec` → `gumtech`.

#### Files

- `medusa-backend/src/scripts/migrate-to-brand-module.ts` —
  `BRAND_SPECS` entry now `handle: "gumtech"`, `name: "Gum-tech"`. Canonical
  `SC_NAME_TO_BRAND` keys are now `"Gum-tech"`/`"Gumtech"` → `gumtech`; the
  legacy `"Gum-tec"`/`"Gumtec"` keys are kept as aliases (→ `gumtech`) so an
  in-flight prod SC still resolves during the rename.

#### Live data (runtime migration, see `eukrit/vendors` `gumtech-catalog/`)

- Medusa sales channel renamed `Gum-tec` → `Gum-tech`.
- ~50 product handles migrated `gumtec-gmt-*` → `gumtech-gmt-*`; metadata keys
  `gumtec_sku`/`gumtec_website` → `gumtech_sku`/`gumtech_website`.
- Storefront brand filter is now `?filters[brand][handle]=gumtech`.

---

## [2.55.0] - 2026-05-31

### Added — Gum-tec as the 11th brand in `migrate-to-brand-module.ts`

The v2.54.0 dry-run against prod produced excellent results — 12,308 /
12,381 products (99.4%) brand-linkable, all 10 brand SCs mapped — but
surfaced ~50 unmapped products with `gumtec-gmt-corner-tile-*` handles
on a `Gum-tec` SC that wasn't in my original brand list.

Gum-tec is a separate EPDM rubber-tile vendor (different from 4soft EPDM
graphics, which it shares pricing-pipeline characteristics with). Added
as the 11th first-class Brand record so its products are queryable via
`?filters[brand][handle]=gumtec` and show up in the storefront brand
switcher just like every other brand.

#### Files

- `medusa-backend/src/scripts/migrate-to-brand-module.ts` — added `gumtec`
  to `BRAND_DEFINITIONS` + `Gum-tec`/`Gumtec` aliases to
  `SC_NAME_TO_BRAND`.

After this lands + redeploys, the dry-run should drop no-brand to ~25
(only `test-*` dev products + the `Default Sales Channel` + the
`Proposal` SC's products remain unmapped, which is correct).

---

## [2.54.0] - 2026-05-31

### Fixed — `migrate-to-brand-module` script: dry-run output + missing SC alias + Leka Project handle prefix

Three fixes surfaced by the v2.53.0 dry-run against prod:

1. **Dry-run brandMap was empty.** Step 1's `[would]` branch never
   populated `brandMap` in `MIGRATION_DRY_RUN=1` mode, so Steps 4 + 5
   reported every SC as `[unmapped]` and every product as `no-brand`.
   Misleading output that didn't reflect what a real run would do. Fixed
   by populating a `brand_dryrun_<handle>` placeholder during dry-run.
2. **`Design Park` SC name was missing from the alias table.** Prod has
   `Design Park` (with a space); my map only had `Designpark` (no space).
   Added the space variant.
3. **`leka-project-XXX` handle prefix didn't match `wisdom`.** Wisdom
   was rebranded to "Leka Project" — handles are now `leka-project-…`,
   not `wisdom-…`. Added an explicit prefix rule mapping
   `leka-project-*` → `wisdom` brand in the handle-prefix fallback.

Brand `wisdom` keeps its handle (don't break the storefront's existing
`?filters[brand][handle]=wisdom` queries); only the display name on the
admin is "Leka Project".

#### Files

- `medusa-backend/src/scripts/migrate-to-brand-module.ts`

---

## [2.53.0] - 2026-05-31

### Fixed — Add missing Brand-module migration file (the `brand` table)

Companion hotfix to v2.49.0 (PR #76) + v2.52.0 (PR #87). The Brand module
was registered and its model defined, but the migration file that
actually creates the `brand` table was never generated (the v2.49.0
build said "MODULE: brand — Skipped. Database is up-to-date" — meaning
no migration files to run, not "already done"). The `migrate-to-brand-module`
job from v2.52.0 therefore exited(1) on its first SQL call.

Hand-wrote `medusa-backend/src/modules/brand/migrations/Migration20260531000000.ts`
matching the shape Medusa v2 emits for similar small modules:

- `brand` table — id text PK, name text, handle text, description text
  null, logo_url text null, plus soft-delete timestamps.
- Partial unique index on `(handle) WHERE deleted_at IS NULL`.

After this migration lands and Cloud Build redeploys, `db:migrate` will
create the table on the prod DB (idempotent — `create table if not
exists`). The `migrate-to-brand-module` Cloud Run Job can then be
re-executed.

#### Files

- `medusa-backend/src/modules/brand/migrations/Migration20260531000000.ts` (new)

---

## [2.52.0] - 2026-05-31

### Added — In-place Brand-module migration script (safe alternative to wipe+reseed)

Companion to v2.49.0 (PR #76). Adds an idempotent in-place migration
script that promotes brand from "sales channel" to "first-class entity
via the Brand module" without touching live product data, so the cart
can carry products from multiple brands at the same time.

#### Why an in-place migration

The v2.49.0 plan was "wipe + reseed", which would have worked if every
brand's products lived in Firestore. They don't: only Wisdom (5,071) and
Vinci (1,113) are in Firestore. The other 7 brands (Berliner, Designpark,
Vortex, 4soft, Archimedes Water Play, Eurotramp, Rampline, WePlay) live
ONLY in Medusa, populated by independent per-brand ingestion pipelines
(vendor PDFs, Google Sheets, scrapers). `db:reset` + `seed-from-firestore`
would have permanently deleted them.

#### What the script does

`medusa-backend/src/scripts/migrate-to-brand-module.ts`:

1. Ensures a Brand record exists for each of the 10 live brands.
2. Ensures a shared `Leka Catalogs` sales channel + `Leka Catalogs
   Storefront` publishable API key exist (and that the key is linked to
   the SC).
3. Iterates every live Product:
   - Infers the brand from the product's current SC association
     (fallback: handle prefix).
   - Creates the `brand ↔ product` link if missing.
   - Adds the shared SC to `sales_channels` ALONGSIDE the existing
     per-brand SC. Per-brand SCs and their publishable keys are left in
     place so the storefront keeps working through the cut-over.

Idempotent, dry-runnable, capped via `MIGRATION_MAX=N` for a first-N
smoke test before a full run.

```bash
# Dry run
MIGRATION_DRY_RUN=1 npx medusa exec ./src/scripts/migrate-to-brand-module.ts
# 50-product smoke test
MIGRATION_MAX=50 npx medusa exec ./src/scripts/migrate-to-brand-module.ts
# Full run
npx medusa exec ./src/scripts/migrate-to-brand-module.ts
```

Recovery: every link is a row in the link tables (`brand_product`,
`product_sales_channel`, `publishable_api_key_sales_channel`) and can be
deleted via the admin API or a follow-up cleanup script. No product,
SC, brand record, or publishable key is mutated destructively.

#### Files

- `medusa-backend/src/scripts/migrate-to-brand-module.ts` (new) — the
  migration script described above.

#### Follow-ups (NOT in this PR)

- Take a Cloud SQL snapshot.
- Run the dry run, then the 50-product smoke test, then the full run.
- Update `eukrit/leka-website/catalogs/.env.local` with the new
  `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY` printed by the script.
- Storefront PR in `eukrit/leka-website` to use the single key + brand
  filters in `?filters[brand][handle]=…` (coordinate with in-flight
  multi-brand-bag PRs there).
- Optional later cleanup: disable / delete the now-redundant per-brand
  publishable keys + SCs once the storefront is fully cut over.

---

## [2.51.0] - 2026-05-30

### Added — 4soft EPDM-graphic pricing in `build_r2_curated.py` + Dulwich R2 script set

Headline: **4soft EPDM surface-graphic codes are now priced** in the curated
Dulwich Rev2 BoQ / Singapore SGD draft-order builder. The graphic codes
(regex `^[A-Z]\d-\d{2}[A-Z]-\d{2,3}`, e.g. `C5-01A-05`, `V9-01A-001`,
`G2-14A-02`) carry no Rev1 BoQ `retail_sgd` and no Wisdom FOB, so they
previously fell through `price_of()` to TBC. The catalog now carries SGD prices
on the 4soft Medusa variants (= `vendors/4soft/products.retail_sgd`, verified
identical), so `scripts/build_r2_curated.py` reads them back:

- The `/admin/products` paging loop now also requests
  `variants.prices.amount,variants.prices.currency_code` and builds a `med_sgd`
  dict: `norm(sku | metadata.legacy_sku) -> SGD unit price (dollars)`.
- `price_of(code)` gains a fallback after the Rev1/FOB checks:
  `if is_epdm(code) and med_sgd.get(n): return med_sgd[n], "priced"`.
- The manual/draft branch (items not published in Medusa) now sets `pricing`
  via `price_of()` for `is_epdm(code)` codes; non-EPDM missing items
  deliberately stay TBC.

Result: **24 of 26** 4soft items now priced (22 published draft-order lines + 2
draft-bucket via manual); only `D2-02A-09UV` and `G2-27A-09UV` stay TBC. This
produced the live SGD draft order **`order_01KSTN74NRPQ3DGETVHERQ1Z2G`** that the
`leka-projects` Dulwich Rev2 proposal renders from. Code change only — no Medusa
writes, no price push (all already live).

#### Dulwich Rev2 (R2) script set — first commit to `main`

These scripts authored the R2 proposal pipeline across prior sessions and were
untracked working-tree files; consolidated here on `main`:

- `scripts/build_r2_curated.py` — authors the curated Rev2 BoQ (zones A/C/CS/D)
  from the user's exact equipment lists + quantities, builds the SGD Medusa draft
  order for published items (qty carried in line `metadata.qty` because
  `/admin/draft-orders` create drops per-line `quantity`), and emits the
  manual_yaml (surfacing lines + draft/missing TBC items). Creates missing codes
  as draft "Proposal"-bucket products. **Contains the 4soft pricing change above.**
- `scripts/build_r2_draft_order.py` — builds the SGD (Singapore region) draft
  order from the R2 selection, one line per published item with
  zone/subzone/category/selection/dimensions metadata + explicit SGD `unit_price`
  (Rev1 retail or Wisdom landed `fob×4.44`, else TBC). Idempotent on
  `metadata.rev == "dulwich-r2"`.
- `scripts/create_r2_missing_products.py` — creates products absent from the
  catalog/Medusa as **draft** (variant `title="Default"`, sku=code, no price,
  `metadata.source_url`+`supplier_url`=Notion vendor URL). Idempotent via handle.
- `scripts/backfill_r2_vendor_urls.py` — merges the Notion vendor URL into
  `metadata.supplier_url`+`source_url` on matching Medusa products, resolving
  variants via a full product index (sku + `metadata.legacy_sku`).
- `scripts/fix_r2_images.py` — R2 image-quality pass: `--reorder` vision-classifies
  (Gemini 2.5 Flash via Vertex, `Part.from_bytes`) and reorders so a real
  render/photo is hero; `--attach-notion` pulls Notion R2 photos for placeholder-only
  products. Bounded to the R2 product set.
- `scripts/rehost_4soft_images.py` — re-hosts the real Notion R2 graphic previews
  flat under `leka-project/` (the `gs://…/4soft/` objects were HTML error pages
  and the `/api/i/` proxy doesn't route the `4soft/` prefix) and repoints 4soft
  products' Medusa images.
- `scripts/reorg_r2_proposal_bucket.py` — keeps the genuinely-new items (EPDM
  graphics, UBX) **draft** in a dedicated "Proposal" sales channel + Firestore
  `products_proposal_draft`, not mixed into official brand channels.

> **Version note:** these scripts were drafted against an out-of-sequence
> `[2.35.0]`–`[2.35.2]` numbering on a stale local `main` (v2.34.0 era) that
> never merged. Renumbered to **2.51.0** above current `main` HEAD (`[2.50.1]`)
> after `main` advanced past the initially-chosen `2.49.0` (taken by PR #76's
> Brand-module multi-brand cart) and `2.50.0` (PR #83 Urbanix). `VERSION` bumped
> 2.50.1 → 2.51.0.

## [2.50.1] - 2026-05-30

### Fixed — Correct `proposal-export` auth documentation (HTTP Basic, not `x-medusa-access-token`)

Comment/doc-only fix — no behavior change. The docstring of
`medusa-backend/src/api/admin/draft-orders/[id]/proposal-export/route.ts`
instructed callers to authenticate by sending `x-medusa-access-token: <api-key>`.
That is wrong.

Verified live on 2026-05-29 against the deployed backend: a Medusa v2 **secret**
admin API key authenticates via **HTTP Basic** — the key as the username with an
empty password (`Authorization: Basic base64("<key>:")`) → 200. Both
`x-medusa-access-token: <key>` and `Authorization: Bearer <key>` return 401.
Medusa's built-in admin route middleware accepts Basic auth for secret keys.

The downstream Python consumer
(`eukrit/leka-projects:src/proposal_engine/medusa_adapter.py`) was already
fixed in leka-projects v1.52.0 to use `requests(..., auth=(key, ""))`.

**Files changed:**

- `medusa-backend/src/api/admin/draft-orders/[id]/proposal-export/route.ts` — docstring auth section corrected.
- `CHANGELOG.md` — corrected the stale `x-medusa-access-token` note in the 2.29.0 proposal-export release entry.

---

## [2.50.0] - 2026-05-30

### Added — Urbanix → Leka Project import (1,298 products under fresh internal SKU scheme)

Imported the full Urbanix vendor catalog from the `vendors` Firestore DB
(landed as part of `eukrit/vendors` PR #29, v1.19.1) into the existing
**Leka Project** sales channel under a brand-new internal SKU scheme.
Source identity ("Urbanix" / "UBX International Limited" / source item
codes) is stripped from every customer-visible surface; the audit trail
back to the original vendor doc lives in an admin-only Firestore mapping
collection.

#### SKU scheme decision

The "Leka Project" Medusa sales channel `sc_01KNKTHC0B7KFEDSZ3NNM49JQW`
already holds 5,061 Wisdom-origin products with random nanoid SKUs
(`LP-XXXXXXXX`). To keep Urbanix-origin products structurally distinguishable
from Wisdom-origin within the same brand, the Urbanix import uses
**sequential** sub-namespaced codes:

| Source line       | Count | SKU pattern              | Namespace style    |
|-------------------|------:|--------------------------|--------------------|
| Wisdom (existing) | 5,061 | `LP-XXXXXXXX`            | 8-char nanoid      |
| Urbanix fitness   |   339 | `LP-F-0001 … LP-F-0339`  | sequential 4-digit |
| Urbanix playground|   959 | `LP-P-0001 … LP-P-0959`  | sequential 4-digit |

The three namespaces are disjoint by structure — nanoid never matches
`LP-[FP]-\d{4}`. Operations can filter by source line with a simple SKU
prefix check; the public-facing handle (`leka-project-{nanoid8}`) stays
opaque.

#### Per-line counts (sourced from Firestore DB `vendors`)

- `urbanix_fitness`: **339 docs** (all 339 have specs, 4 have pricing,
  317 have description).
- `urbanix_playground`: **959 docs** (all 959 have specs, 300 have
  pricing, 955 have description).
- **Total imported: 1,298** Medusa products + 1,298 audit-mapping docs.

(The source-PR brief estimated 1,021 spec-bearing docs and 307 with
pricing; reality is all 1,298 have Gemini specs and 304 have pricing.)

#### Pricing posture

All 1,298 products are imported with **no Medusa price rows** and
`metadata.pricing_pending=true`. The 304 docs that carry Urbanix
`pricing.landed_thb` get the same treatment — Leka pricing is set per-SKU
by the merchandiser, not inherited from the source. The mapping doc
flags `pricelist_linked: true` on those 304 for future reference.

#### Sanitization

`scripts/import_from_urbanix.py` strips, from title + description:
`Urbanix`, `UBX`, `UBX International Limited`, item codes (`UBX-####`,
`CC-##`, `TPF-####-#`). Then patches orphan determiners
("The is" → "This is") and empty parens left by inline-identifier
removal. A live scan of all 1,298 imported products found **zero**
occurrences of these tokens in title / description / handle.

#### 5-row mapping sample (admin-only audit trail)

| Leka SKU   | Urbanix SKU            | Vendor               | Source path                                                            | Pricelist linked |
|------------|------------------------|----------------------|------------------------------------------------------------------------|------------------|
| LP-F-0001  | angled-monkey-bars-9   | urbanix_fitness      | vendors/urbanix_fitness/products/angled_monkey_bars_9                  | False            |
| LP-F-0006  | CC-01                  | urbanix_fitness      | vendors/urbanix_fitness/products/cc_01                                 | True             |
| LP-F-0174  | UBX-104                | urbanix_fitness      | vendors/urbanix_fitness/products/ubx_104                               | False            |
| LP-P-0001  | 114-al-post-cover      | urbanix_playground   | vendors/urbanix_playground/products/114_al_post_cover                  | False            |
| LP-P-0615  | TPF-2509-800           | urbanix_playground   | vendors/urbanix_playground/products/tpf_2509_800                       | True             |

#### Brand-record updates

- Medusa Sales Channel `sc_01KNKTHC0B7KFEDSZ3NNM49JQW` description refreshed
  to "Leka Project — house collection spanning early-years toys,
  commercial playground equipment, and outdoor fitness stations." Name
  unchanged.
- Firestore `pricing_config/canonical.brands.leka_project` block written
  with `internal_code_prefix: "LP"` and the per-source `internal_code_scheme`
  map above.

#### Files

- `scripts/import_from_urbanix.py` (new — 825 lines). Reads
  `vendors/urbanix_{fitness,playground}/products/*` (Firestore DB
  `vendors`, read-only), allocates sequential `LP-F-####` / `LP-P-####`
  codes via a transactional counter at
  `urbanix_mapping/_counters` (Firestore DB `leka-product-catalogs`),
  sanitizes title + description, builds the Medusa create-product payload
  (no prices, `pricing_pending=true`, full `specifications` carried verbatim,
  source audit trail in `metadata.source_*`), POSTs to Medusa admin API,
  writes one audit doc per product to `urbanix_mapping/{leka_sku}`.
  Idempotent: re-run keys on `urbanix_doc_path`; existing mappings refresh
  only when `source_sha` changes. CLI: `--dry-run`, `--limit N`,
  `--vendor {fitness,playground,all}`, `--report`, `--refresh-brand-only`,
  `--revert` (safety-checked).

#### Mapping collection (admin-only)

`urbanix_mapping/{leka_sku}` in Firestore DB **`leka-product-catalogs`**
(NOT the source `vendors` DB — keeps the source side read-only per the
brief). Doc shape:

```jsonc
{
  "leka_sku": "LP-F-0174",
  "urbanix_sku": "UBX-104",
  "urbanix_doc_path": "vendors/urbanix_fitness/products/ubx_104",
  "urbanix_vendor_id": "urbanix_fitness",
  "urbanix_source_sha": "23989734fe6140fa...",
  "medusa_product_id": "prod_01KSWPM4FT5CHD2Y1V4KKZYDHZ",
  "medusa_handle": "leka-project-ywaesjvf",
  "imported_at": <serverTimestamp>,
  "last_synced_at": <serverTimestamp>,
  "pricelist_linked": false
}
```

The Medusa storefront API has no route that reads this collection
(verified by greppage); it's admin-scoped by construction. A Firestore
rule update would belong to a separate hardening PR if the project moves
to client-side Firestore access.

#### Run results (live, 2026-05-30)

- Stage 1 (`--limit 5`): 10 products created, 0 errors.
- Stage 2 (full): 1,288 new products created, 10 unchanged-skipped
  (idempotency confirmed via `source_sha`), 0 errors. Runtime 9.5 min.
- Verification: 4/4 brief-required checks pass (brand record, 3
  spot-checks `UBX-104`/`TPF-2509-800`/Gemini-only, **0 leaks across all
  1,298 products**, mapping admin-scoped).

#### Source PR (vendors workspace)

[eukrit/vendors#29](https://github.com/eukrit/vendors/pull/29) — v1.19.1
landed the rich Urbanix product docs (Gemini-extracted specs +
pricelist-driven landed cost for the priced subset).

---

## [2.49.0] - 2026-05-30

### Changed — Native multi-brand cart (Brand Module replaces brand=sales-channel)

Reworked the Medusa v2 backend so the cart can carry products from any
combination of brands. Brands are no longer Sales Channels — they're a
first-class entity linked to products via a custom module link. The cart
lives in one shared sales channel and accepts items regardless of brand.

#### Why

Each brand (Wisdom, Vinci Play, Vortex Aquatics) was a separate Medusa
Sales Channel, and Medusa binds a cart to one sales channel. A customer
could not put a Wisdom playground unit and a Vortex water-play feature in
the same cart, and the B2B "Send to Proposal" flow could not produce a
mixed-brand draft order. The user's commerce model treats brands as
catalogs-to-browse, not separate stores — multi-brand baskets are required.

#### Shape

Adopted the Medusa v2 **Brand Module** recipe:

1. New custom module `medusa-backend/src/modules/brand/` with one `Brand`
   model (`id`, `name`, `handle` unique, `description?`, `logo_url?`) and a
   `BrandModuleService` extending `MedusaService({ Brand })`.
2. New module link `medusa-backend/src/links/brand-product.ts` — one brand
   → many products, one product → one brand. Powers the query graph so
   `GET /store/products?fields=+brand.*&filters[brand][handle]=wisdom`
   filters products by brand without a custom route.
3. New store route `GET /store/brands` for the storefront brand switcher.
4. `medusa-config.ts` registers the brand module.
5. **One** Sales Channel ("Leka Catalogs") instead of one-per-brand. All
   products publish to it. **One** publishable API key for the storefront.
6. Seed script (`src/scripts/seed-from-firestore.ts`) creates the Brand
   records, links each product to its brand via
   `ContainerRegistrationKeys.LINK`, and optionally loads
   `vortex_products.json` if present.

Cart routes (`/store/carts/:id/complete`,
`/store/proposal-builder/convert-cart`) are unchanged — they were already
brand-agnostic and just pass `sales_channel_id` through.

#### Files

- `medusa-backend/src/modules/brand/{index,service,models/brand}.ts` (new)
- `medusa-backend/src/links/brand-product.ts` (new)
- `medusa-backend/src/api/store/brands/route.ts` (new)
- `medusa-backend/medusa-config.ts` — added brand module to modules array
- `medusa-backend/src/scripts/seed-from-firestore.ts` — single SC, brand
  records, brand-product link wiring, single publishable key, optional
  Vortex loader

#### Migration sequence (DEPLOY-TIME — not run in this PR)

The seed script is fresh-DB only. The live Medusa DB carries v2.37.0
state (5,061 Wisdom enrichments + Toys category links). To migrate:

1. Re-export Firestore → `migration/{wisdom,vinci,vortex}_products.json`
   (latest state).
2. Tag prod DB / take Cloud SQL snapshot for rollback.
3. `cd medusa-backend && npx medusa db:reset` (or drop schema).
4. `npx medusa db:migrate` (picks up the brand module migration + link).
5. `npx medusa exec ./src/scripts/seed-from-firestore.ts` — prints the new
   `Leka Catalogs Storefront` publishable key.
6. Re-run `python scripts/apply_wisdom_enrichment.py` (idempotent — restores
   the AI metadata + descriptions from the Firestore `wisdom_enrichment/`
   cache).
7. Re-run `python scripts/medusa_create_toys_category.py --ensure-categories
   --link` (idempotent — restores Toys + 15 other top-level categories
   and their product links).
8. Update `eukrit/leka-website/catalogs/.env` with the new publishable
   key (single key replaces per-brand keys); redeploy storefront.

#### Storefront follow-up (eukrit/leka-website — separate PR)

- Replace `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY_{WISDOM,VINCI}` with one
  `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY`.
- Brand landing pages: query
  `/store/products?fields=+brand.*&filters[brand][handle]=<slug>`.
- Brand switcher: hit `/store/brands` once, cache client-side.
- Drop any per-brand cart cookie logic — share the cart across
  `/wisdom`, `/vinci`, `/vortex`.

#### Verification

- Backend builds (`npm run build` in `medusa-backend/`) with new module +
  link + route + seed edits compiling clean.
- After deploy:
  1. `GET /store/brands` → 3 brands.
  2. `GET /store/products?fields=+brand.*&limit=5` → every product carries
     a `brand` object.
  3. `GET /store/products?filters[brand][handle]=wisdom` → only Wisdom.
  4. **The decisive test:** create a cart, add a Wisdom variant, add a
     Vinci variant → both line items persist; `POST /store/proposal-builder
     /convert-cart` produces one draft order with both brands.

---



## [2.48.0] - 2026-05-30

### Added — Wisdom outdoor-play collection in Medusa (link existing 255 + create 17)

Tagged the 272-SKU **Wisdom Outdoor Classroom — Outdoor Play** subset into a
new Medusa collection `wisdom-outdoor-play` on `leka-medusa-backend`. Hybrid
strategy after discovering that 255 of the 272 SKUs already exist in Medusa
under the rebranded `Leka Project` sales channel — original Wisdom item codes
live in `variants[].metadata.legacy_sku`.

> **Renumbered from v2.40.0 during merge** — main moved to v2.47.0 (PR #78
> Furniture Catalog backfill) while this branch was in flight. The two builds
> are complementary: v2.47.0 swapped 33 placeholders to real furniture imagery
> on the broader Leka-Project SC; this one tags 227 of those products into the
> new outdoor-play collection. PR #74's CLAUDE.md fix superseded the matching
> doc edit on this branch, so that part was dropped in the merge.

#### `wisdom-catalog/import_outdoor_play_to_medusa.py` (new)
Orchestrator: load merged JSON → Firestore enrichment → URL rewrite → HEAD
filter → Gemini 2.5 Flash verify (cached in Firestore
`wisdom_outdoor_play_verify`) → idempotent link or create. Stages each gated
by a flag (`--dry-run`, `--skip-gemini`, `--skip-head-check`, `--no-firestore`,
`--force-image-refresh`, `--limit N`). Source list pulled from sibling
`vendors` repo (`wisdom-catalog/parsed/wisdom-outdoor-play-merged.json`).

#### Image URL rewrite — proxy form
Firestore `images[].url` points at the private
`gs://ai-agents-go-documents/...` bucket (403 anonymously). The importer flips
every URL to the live storefront-proxy form
`https://catalogs.leka.studio/api/i/leka-project/<path>` (backed by
`gs://ai-agents-go-vendors/leka-project/`). Of 300 unique URLs: 255 HEAD-OK,
45 broken. Of HEAD-OK URLs: Gemini accepted 168, rejected 96.

#### `shared/medusa_importer.py` — `update_product_images`, `update_product_metadata`
Added two thin helpers. The four-helper list in the task brief was mostly
fulfilled by pre-existing methods (`find_product_by_handle`,
`get_or_create_collection`, `set_product_collection`); only image PATCH was
missing.

#### Outcome
- Collection `wisdom-outdoor-play` (`pcol_01KSTM5ZC4H197S057QC2TNATR`) created.
- **227 unique products** now linked to the collection (272 SKUs collapse via
  shared `firestore.matched_id`; e.g. `CSS-BZ` and `CSS-BZ-V02` both map to
  `leka-project-qv8v9i2v`).
- 255 existing products got collection link + `metadata.outdoor_play` merge
  (no image overwrite — v2.34.0 / v2.47.0 thumbnails preserved).
- 17 new `wisdom-<code>` products created for the firestore-null SKUs; they
  carry the Leka "Image coming soon" placeholder where no Gemini-verified
  image was available.
- Wall-time ~2 min; Vertex spend ~$0.40.

Full report: `wisdom-catalog/IMPORT_OUTDOOR_PLAY_REPORT.md`. Brand log:
`wisdom-catalog/DEPLOYMENT_LOG.md` (v2.48.0).

---

## [2.47.0] - 2026-05-30

### Added — Leka Project image backfill from the 2025-08-11 Furniture Catalog

Follow-up to v2.34.0 (placeholder backfill). Of the **2,138 Leka Project
products** still rendering the cream "Image coming soon" placeholder, **33
now display real catalog imagery** sourced from the never-previously-ingested
`2025-08-11 Wisdom International Furniture Catalog.pdf` (355 pages, 1,418
SKU codes, 5,286 raw embedded images). KB / GP / HW prefix furniture.

Pattern mirrors the v2.43.0 4soft picture-pricelist enrichment (extract →
upload → vendors-write → Medusa-sync), with a Gemini verify step inserted
between vendors-write and Medusa-sync because the furniture catalog's
free-form multi-product pages require spatial-proximity attribution
(stricter than 4soft's y-row grid layout).

#### Discovery + sizing
Two source folders were inspected (`docs/wisdom-image-backfill-discovery.md`):
- `…\WeChat OneDrive\WeChat Wisdom Playground` — 1 custom-order PDF + 1
  xlsx, no catalog imagery. Skipped.
- `…\My Drive\Catalogs GO\Wisdom Playground` — 3 catalog PDFs. The
  2025-06-13 USA + International catalogues are being re-extracted by the
  sibling worktree `claude/great-hopper-c0fd71` (outdoor-play / QSWP
  prefixes). This wave handles only the brand-new Furniture catalog.

Empirical bridge sizing (`data/bridge-sizing.json`,
`data/wisdom-placeholder-summary.json`): **2,137 / 2,138 placeholders already
have a `vendors/wisdom/products` doc with `images=[]`**. The prior
v2.34.0 + v2.36-37 extractions left them empty; bridge-from-vendors
alone yields zero. PDF→image extraction is the only path.

#### `wisdom-catalog/extract_furniture_pdf_images.py` (new)

Spatial PDF→image extractor. Mirrors `wisdom-catalog/map_images_verified.py`'s
span-bbox-center + image-rect-center euclidean-nearest attribution, plus PR
#73's DeviceRGB-JPEG preference over JPX and 3× zoom render fallback.

- Reads gap codes once from `vendors/wisdom/products` (empty `images=[]` OR
  new SKU not yet in vendors).
- MAX_IMAGES = 2 per code, MAX_DISTANCE = 600 px.
- Output: `wisdom-catalog/data/pdf_images/*.jpg` (gitignored, reproducible
  from PDF) and `wisdom-catalog/data/pdf_images_map.json` (committed
  provenance).
- Idempotent: page-level checkpoint in Firestore
  `wisdom_pdf_extract/{pdf_sha16}/pages/{N}`.
- Flags: `--dry-run` (default), `--extract`, `--pages 1-30`, `--limit-codes N`,
  `--no-gap-filter`.

**Extraction run (355 pages, full):**
- 1,631 distinct codes detected in PDF.
- 858 in the gap (102 in vendors with empty images, 756 new SKUs).
- 250 pages processed, 1,842 raw attributions, **1,538 unique JPEGs written**.
- Distance distribution p50=100 px, p80=142 px, p95=181 px, max=361 px;
  **96.5 % of attributions < 200 px** (tight spatial match).
- 36 attributions dropped due to decode failure (acceptable noise).

#### `wisdom-catalog/enrich_furniture_pdf_images.py` (new)

Four sub-phases (`--upload`, `--write-firestore`, `--verify`,
`--sync-medusa`), each idempotent and resumable.

**A. `--upload`** → 1,222 new + 35 existing = 1,257 unique objects in
`gs://ai-agents-go-vendors/wisdom/furniture_2025/`. Zero errors. Mirrors the
4soft `<vendor>/<source-tag>/<file>` layout; served via
`https://catalogs.leka.studio/api/i/wisdom/furniture_2025/<filename>`
(proxy validated `200 OK image/jpeg`).

**B. `--write-firestore`** → 93 `vendors/wisdom/products` docs updated with
furniture image entries (`source = catalog_pdf_furniture_2025_spatial_v2`).
Precedence rule from PR #73: keep real images, replace borrowed/base-design
entries, ADD where `images=[]`. 742 codes skipped — they're new SKUs without
a vendor doc (would require Medusa onboarding before backfill applies).

**C. `--verify`** → Gemini 2.5 Flash @ Vertex location `global`, threshold
0.70, concurrency 4. **93 calls, $0.86 spent** (under the $18 ceiling).
**39 accepted / 47 rejected / 0 errors** (42 % accept rate). Decisions
checkpoint in Firestore `image_backfill_verify/{sha1(code)}` (same
collection as v2.34.0); per-image `image_verified` and `image_match_score`
also written back to vendor docs.

The reject rate is the spatial extractor's signal: on multi-product pages,
the nearest-image heuristic can attribute an image whose code is spatially
close but belongs to a neighbouring product. Gemini correctly catches
these. The 39 accepts are tightly grouped on KB / GP / HW / MGF prefixes.

**D. `--sync-medusa`** → 33 Medusa placeholder products flipped to
`metadata.image_status = "backfilled_furniture"` (the other 6 of the 39
verified codes don't have a matching live placeholder product). Each
product's `images` + `thumbnail` replace the placeholder atomically.

#### Outcome — `scripts/_audit_placeholders.py`

| Metric | Before | After |
|---|---:|---:|
| Total Leka Project products | 5,062 | 5,062 |
| Showing placeholder | **2,138** | **2,105** |
| Backfilled (real image) | 67 | **100** |
| New: vendors/wisdom/products with furniture image entries | — | 93 |
| New: future-onboarding imagery (vendor doc not yet created) | — | 742 codes |

Spot-checked product **GP1-12036 (Wallboard Handrail-Straight Rod)**:
storefront thumbnail `200 OK`, `image_status = backfilled_furniture`, 2
images served from `wisdom/furniture_2025/`. ✅

#### Files

- `wisdom-catalog/extract_furniture_pdf_images.py` (new, ~370 LOC)
- `wisdom-catalog/enrich_furniture_pdf_images.py` (new, ~450 LOC)
- `wisdom-catalog/data/pdf_images_map.json` (new, committed provenance)
- `wisdom-catalog/data/furniture_candidates.csv` (new, committed)
- `wisdom-catalog/data/pdf_images/` (gitignored)
- `docs/wisdom-image-backfill-discovery.md` (new)
- `data/wisdom-placeholder-skus.csv`, `data/wisdom-placeholder-summary.json`,
  `data/bridge-candidates.csv`, `data/bridge-sizing.json`,
  `data/vendors-wisdom-snapshot.json` (new audit artifacts)
- `scripts/_audit_placeholders.py`, `scripts/_peek_pdfs.py`,
  `scripts/_peek_vendors_wisdom.py`, `scripts/_size_bridge.py`
  (new audit helpers — names prefixed `_` to mark them internal)
- `.gitignore` — added `wisdom-catalog/data/pdf_images/`
- New GCS objects: 1,222 under `gs://ai-agents-go-vendors/wisdom/furniture_2025/`
- New Firestore docs: `wisdom_pdf_extract/{pdf_sha16}/pages/{0..354}` +
  93 new entries in `image_backfill_verify/` (source=furniture_2025).
- `CHANGELOG.md`, `VERSION` → 2.45.0
- `wisdom-catalog/DEPLOYMENT_LOG.md` → run summary
- `.claude/PROGRESS.md` → last-touched + recent-sessions

#### Vertex AI spend (this wave)

$0.86 — well under the $20 ceiling. 47 rejected codes can be re-verified
later if a different image source emerges; their vendor-doc entries remain
with `image_verified=False`.

#### Sibling-branch coordination

`claude/great-hopper-c0fd71` is independently re-extracting the
2025-06-13 USA + International catalogues to chase the QSWP / SR / BS
outdoor-play prefixes. This wave only writes `source` strings containing
`furniture_2025` and only flips `image_status` to `backfilled_furniture`
(distinct from `backfilled` v2.34 and from whatever tag the sibling chooses).
No file-level conflicts expected.

---

## [2.46.0] - 2026-05-30 — Eurotramp product-photo backfill

> **STATUS:** SHIPPED. 16 Medusa products updated, 62 photos uploaded to GCS.
> Audit report: [`docs/reports/eurotramp-image-audit-2026-05-30.md`](docs/reports/eurotramp-image-audit-2026-05-30.md)
> Sibling-repo context: leka-website storefront v0.19.2 (#87) extended the cert-penalty regex but cannot rescue a product whose only image data IS a cert.

### Result — before / after on live storefront

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| Eurotramp products with a non-photo thumbnail | 88 | 72 | −16 |
| Eurotramp products whose thumbnail is a TÜV/cert image | 23 | 10 | **−13** |
| Eurotramp products with zero real photos (backfill targets) | 33 | 27 | −6 |
| Post-backfill `og:image` flipped to a real photo (spot-check, 9/10 handles) | — | 9 ✅ | — |

Post-backfill `og:image` verification (live `curl https://catalogs.leka.studio/eurotramp/<handle>`):

```
✅ photo  eurotramp-wehrfritz-fun-round         → productdetails-wehrfritzfunroundplayground_1202e5eb57_1920x1080.jpg
✅ photo  eurotramp-kids-tramp-track-playground → 97054-kidstramptrack4mepdm_83ccaccd40_1920x1080.jpg
✅ photo  eurotramp-wehrfritz-fun-xl-playground → productdetail-wehrfritzfunxlplayground_672451331b_1920x1080.jpg
✅ photo  eurotramp-impact-protection-system    → e97541-impactprotectionsystemepdmforkidstrampxlgrey_6f6c5cb7b8_1920x1080.jpg
✅ photo  eurotramp-grand-master                → productdetails-grandmaster13mm_49d719a380_1920x1080.jpg
✅ photo  eurotramp-ultimate                    → productdetails-ultimate_1a9386d18e_1920x1080.jpg
✅ photo  eurotramp-teamgym                     → productdetails-minitrampteamgym_c4e2140598_1920x1080.jpg
✅ photo  eurotramp-underwater-trampoline       → productdetails-underwatertrampoline_8fb7b817d5_1920x1080.jpg
✅ photo  eurotramp-mats-tramp                  → 91000-preview-matstrampoline_f249c65994_1920x1080.jpg
❌ cert   eurotramp-kids-tramp-kindergarten-loop-xl → tuev_1176_2021.jpg  (in upstream-gap list — no photo upstream)
```

### Audit summary (live Medusa, 2026-05-30)

| Metric | Count |
|---|---:|
| Total Medusa products scanned | 11,064 |
| Eurotramp products | 187 |
| **Backfill targets** — zero real product photos in Medusa (neither in `images[]` nor as `thumbnail`) | **33** |
| └ of which have only `cert` + `feature-badge` + `symbol` + `vector` (no photo, but ≥1 image) | 31 |
| └ of which have **no images at all** | 2 |
| Products whose `thumbnail` is not a real photo | 88 |
| └ of which `thumbnail` is a TÜV/cert image | 23 |

A product image was classified as:

- `photo` — leading article number (`97004-`, `e97941-`), `productdetails-`, or `<articleNo>-preview-`
- `cert` — `tuev_*`, `tuv_*`, ISO, CE-mark, GS-mark, compliance
- `feature-badge` — `madeingermany_*`, `uv-lightresistant_*`, `flame-retardant_*`, etc.
- `symbol` / `vector` / `merchant` / `placeholder` — UI icons, CAD line drawings, distributor logos, literal placeholder

Storefront-visible failure example — `eurotramp-wehrfritz-fun-round`:
`og:image` today = `…/tuev_1176_2021.jpg` (cert). Medusa has 19 images: 1 cert, 6 feature badges, 11 symbol/mediaType icons, 1 vector drawing, 0 real photos.

### Root cause

**Upstream Eurotramp DOES have real product photos** — confirmed by direct fetch of the vendor product pages:

- `/products/wehrfritz-fun-round/` → `productdetails-wehrfritzfunroundplayground_*.jpg` (multi-size), `94700-wehrfritzfunroundplayground_*.jpg` (multi-size)
- `/products/kids-tramp-track-playground/` → `97004-kidstramptrackplayground_*.jpg`, `97004-kidstramptrackplaypro_*.jpg`, `97054-/97056-/97058-/97059-kidstramptrack…_*.jpg`
- `/products/wehrfritz-fun-xl-playground/` → `97610-wehrfritzfunxlplayground_*.jpg` (multi-size), `productdetail-wehrfritzfunxlplayground_*.jpg` (multi-size)

These photos live under the same `/_resources.d/images.d/` path that the current scraper in [`scripts/scrape-eurotramp.ts`](scripts/scrape-eurotramp.ts) (lines 295–310) already targets:

```ts
$("img").each((_, el) => {
  const src = $(el).attr("data-src") || $(el).attr("src") || ""
  if (src && (src.includes("/_resources.d/images.d/") || src.includes("/images.d/")) &&
      !src.includes("icon") && !src.includes("logo") && !imageUrls.includes(src)) {
    imageUrls.push(src.startsWith("http") ? src : `${BASE_URL}${src}`)
  }
})
```

The current selector would catch them — so the gap is from a prior ingest pass that pushed an older (narrower) image set. Likely sources:
1. Initial scrape pre-dated the current `$("img")` selector — an older version filtered to `productFeatureImages.d/` only, capturing badges + cert and missing `images.d/` photos.
2. The GCS re-host in [`scripts/rehost-images-to-gcs.ts`](scripts/rehost-images-to-gcs.ts) / [`scripts/rewrite_image_urls_to_vendors_bucket.py`](scripts/rewrite_image_urls_to_vendors_bucket.py) may have processed an older `data/scraped/eurotramp/products.json` and the photos never landed in `gs://ai-agents-go-vendors/eurotramp/<handle>/`.

**Either way the fix is the same:** re-scrape Eurotramp with the current scraper, then push the new photos to Medusa for the 33 backfill targets + re-point the 23 cert thumbnails.

### Backfill plan — phased, reversible

#### Phase 1 — Fresh scrape (read-only, no Medusa writes)

1. `npx tsx scripts/scrape-eurotramp.ts` — repopulate `data/scraped/eurotramp/products.json` and `data/scraped/eurotramp/images/`. Already targets all 13 category slugs; no code change needed.
2. New script `scripts/diff_eurotramp_scrape_vs_medusa.py` — for each handle in the audit's 33 backfill targets, list the scraped image URLs that are NOT in the current Medusa `images[]`. Flag any handle where the fresh scrape still finds 0 real photos (true upstream gap; manual photo procurement required).
3. Expected output: most 33 targets gain ≥1 fresh `productdetails-…_*.jpg` / `<articleNo>-…_*.jpg` photo URL. Hard cases (e.g. the 2 zero-image accessories and some spare-parts SKUs whose vendor pages are sub-pages without their own gallery) will be listed for manual handling.

#### Phase 2 — Re-host the new photos to GCS (`gs://ai-agents-go-vendors/eurotramp/<handle>/`)

4. Extend `scripts/rehost-images-to-gcs.ts` (or add `scripts/rehost_missing_eurotramp_photos.ts`) to download each new photo URL discovered in Phase 1 and upload to `gs://ai-agents-go-vendors/eurotramp/<handle>/<filename>` with the standard image-proxy headers. (Per the workspace `image-proxy-bucket` memory: catalog images live in `ai-agents-go-vendors`, served via `catalogs.leka.studio/api/i/`.)
5. Dry-run first (`--dry-run`) and print download/upload counts before writing.

#### Phase 3 — Update Medusa products (the only write step)

6. New script `scripts/backfill_eurotramp_photos_to_medusa.py` (model after [`scripts/apply_wisdom_enrichment.py`](scripts/apply_wisdom_enrichment.py) — Medusa admin auth, idempotency marker in `metadata.photo_backfilled_at`):
    - For each of the 33 backfill targets: append the new photo URLs to `images[]` (do NOT replace — leave existing badges/certs for now, sorted by storefront scorer) and set `thumbnail` to the highest-resolution `productdetails-…` or `<articleNo>-…` URL.
    - For each of the 23 cert-thumbnail products that already have real photos in `images[]`: re-point `thumbnail` to the first non-cert non-badge non-symbol non-vector image (a `photo`-class URL).
    - Use Medusa Admin API `POST /admin/products/:id` with `{thumbnail, images}`. Same pagination + retry-on-429 as the apply script.
    - Idempotency: write `metadata.photo_backfilled_at = "2026-05-30T…"` per product; skip products with that marker on re-run unless `--force`.
7. Run order: `--dry-run --limit 5` → spot-check the diff → `--dry-run` full → live run.

#### Phase 4 — Verification

8. Re-curl `https://catalogs.leka.studio/eurotramp/<handle>` for at least these handles:
    - `eurotramp-wehrfritz-fun-round`
    - `eurotramp-kids-tramp-track-playground`
    - `eurotramp-wehrfritz-fun-xl-playground`
    - `eurotramp-kids-tramp-kindergarten-loop-xl`
    - one of the zero-image accessories (if a photo was found)
   Assert that `<meta property="og:image">` no longer matches `/(tuev|tuv)[_-]/i`. Append curl output to this CHANGELOG entry under "Post-backfill verification".
9. Re-run `scripts/audit_eurotramp_images.ts` + `scripts/reclassify_eurotramp_images.py` and confirm the backfill-target count drops to its irreducible minimum (the products with no upstream photos).

### Rollback path

- All writes are to Medusa product `thumbnail` + `images[]`. The fresh scrape's `data/scraped/eurotramp/products.json` is committed first (Phase 1) — a single git revert restores the pre-backfill state of that file.
- The backfill script writes `metadata.previous_thumbnail` and `metadata.previous_images` before mutating, so a `scripts/rollback_eurotramp_photo_backfill.py` can restore the original Medusa state product-by-product.
- GCS uploads (Phase 2) are non-destructive (new object names, no overwrites). Leaving the photos in the bucket after rollback is fine — they're unreferenced storage, not visible to users.

### Out of scope (this entry)

- Other vendors' image quality (Vinci, Berliner, Rampline, etc.) — separate audit, separate ticket.
- Storefront code changes in `eukrit/leka-website` — the v0.19.2 cert-penalty regex uses `\b…\b` which JS evaluates as `(?<=\w)(?!\w)` / `(?<!\w)(?=\w)`. Because `_` is a word character, `\btuev\b` does NOT match `tuev_1176_2021.jpg`. This is a separate bug in the storefront scorer; fixing it would let `pickPrimaryImage()` reject cert URLs even when they're the thumbnail, masking part of this data problem. Flag-only here; fix in `leka-website` as a follow-up.
- The 2 zero-image products (`eurotramp-bonded-impact-protection-system-kids-tramp-xl-e97544`, `eurotramp-impactprotection-system-kids-tramp-e97044`) — empty `vendor_url`; if Phase 1's scrape still finds no photos, these need manual procurement.

### Files added (audit only; no behavior change yet)

- [`scripts/audit_eurotramp_images.ts`](scripts/audit_eurotramp_images.ts) — Medusa-side audit; emits `docs/reports/eurotramp-image-audit-<date>.md` + `.json`.
- [`scripts/reclassify_eurotramp_images.py`](scripts/reclassify_eurotramp_images.py) — applies the `photo`/`cert`/`badge`/`symbol`/`vector` classifier to the raw audit JSON and writes the storyboard report.
- [`docs/reports/eurotramp-image-audit-2026-05-30.md`](docs/reports/eurotramp-image-audit-2026-05-30.md) — human-readable report.
- [`docs/reports/eurotramp-image-audit-2026-05-30-classified.json`](docs/reports/eurotramp-image-audit-2026-05-30-classified.json) — machine-readable; consumed by the Phase 1 diff script.

### Sign-off (received 2026-05-30)

All four checkboxes approved; executed in a single chained pass.

### What ran

1. **Phase 1 — fresh scrape** ([`scripts/scrape-eurotramp.ts`](scripts/scrape-eurotramp.ts)) — 81 product pages crawled, `data/scraped/eurotramp/products.json` repopulated. 0 errors.
2. **Phase 1 — diff vs Medusa** ([`scripts/diff_eurotramp_scrape_vs_medusa.py`](scripts/diff_eurotramp_scrape_vs_medusa.py)) — wrote [`docs/reports/eurotramp-backfill-diff-2026-05-30.json`](docs/reports/eurotramp-backfill-diff-2026-05-30.json). Found:
    - 6 backfill targets with new upstream photos (fixable now)
    - 9 cert-thumb products with new upstream photos (cosmetic re-point + add)
    - 4 cert-thumb products with only existing Medusa photos (thumb-only re-point)
    - **13 backfill targets with no upstream photos** (page found, no real-photo URLs)
    - **15 backfill/cert-thumb products not in scrape at all** (sub-page accessories — not reached by 13-category crawl)
3. **Phase 2 — GCS rehost** ([`scripts/rehost_missing_eurotramp_photos.py`](scripts/rehost_missing_eurotramp_photos.py)) — downloaded 62 photos, uploaded all to `gs://ai-agents-go-vendors/eurotramp/<handle>/`. Each URL was upgraded from the 200x112 gallery thumb (the only size the scraper captured) to 1920x1080 by HEAD-probing the size ladder `_1920x1080`/`_920x512`/`_680x378`/`_200x112` and using the largest that returned HTTP 200. 0 failures. Manifest: [`docs/reports/eurotramp-rehost-manifest-2026-05-30.json`](docs/reports/eurotramp-rehost-manifest-2026-05-30.json).
4. **Phase 3 — Medusa backfill** ([`scripts/backfill_eurotramp_photos_to_medusa.py`](scripts/backfill_eurotramp_photos_to_medusa.py)) — **16 products updated, 8 skipped (no change needed), 0 failed**. Each updated product got:
    - new `images[]` (photos appended; existing badges/certs preserved; dups collapsed)
    - re-pointed `thumbnail` to the highest-rank `productdetails-*` / `<articleNo>-*` URL, but **only when the candidate filename shares at least one token with the product handle** — this prevented 4 `kids-tramp-kindergarten*` products from getting an unrelated `impactprotectionsystem` accessory photo as their thumbnail.
    - `metadata.previous_thumbnail` + `metadata.previous_images` (for rollback)
    - `metadata.photo_backfilled_at` (for idempotency on re-run)
    Per-product log: [`docs/reports/eurotramp-backfill-log-2026-05-30.json`](docs/reports/eurotramp-backfill-log-2026-05-30.json).
5. **Phase 4 — verification** — re-curled 10 handles; 9/10 now serve a real product photo as `og:image`. The 1 still-broken one (`kids-tramp-kindergarten-loop-xl`) is in the upstream-gap list — no fix possible without procuring photos manually.

### Remaining work — not fixable from upstream

These 28 products still have non-photo thumbnails after this backfill. They need photos procured manually (vendor PDF, manufacturer brochure, or fresh photoshoot):

- **Upstream gap (13)** — vendor page crawled, no real-photo URLs found: `booster-board-freestyle`, `customized-fabrications`, `eurotramp-play`, `kids-tramp-{kindergarten,playground}-loop[-xl]` (4), `safety-platforms-universal-freestyle`, `set-of-landing-mats-dmt`, `spotting-mat-freestyle`, `trampoline-set-{one-field,stationary}` (2), `transport-case-hdts`.
- **Not in 13-category scrape (15)** — most are sub-page accessories/spare-parts: 4× `adhesive-cartridge-…`, `bonded-impact-protection-…`, `eurotramp-play-light-…`, `impactprotection-system-…`, 2× `jumping-bed-…`, `minitrampoline-112-125`, 6× `single-tile-impact-protection-…`, 2× `wehrfritz-fun-…-kindergarten…`. Either re-crawl with deeper accessory traversal or procure manually.

Recommended next step: open a follow-up ticket "Eurotramp manual photo procurement" with these 28 handles; close it once images are uploaded to `gs://ai-agents-go-vendors/eurotramp/<handle>/` and the backfill script is re-run with `--force`.

### Storefront sibling-repo follow-up (out of scope here)

The `\btuev\b` regex in [`leka-website/catalogs/src/lib/image-scoring.ts:8`](https://github.com/eukrit/leka-website/blob/main/catalogs/src/lib/image-scoring.ts) fails on `tuev_*.jpg` because JS `\b` treats `_` as a word character (`\btuev\b` ≠ match in `tuev_1176_2021.jpg`). This bug is masked for now: after this backfill the 13 still-cert products have ONLY a cert and the scorer can't choose any better. But it should be fixed in `leka-website` (replace `\b…\b` with `(?<![a-z0-9])…(?![a-z0-9])`) so the scorer correctly penalises `tuev_*` filenames once any real photo exists.

### Rollback path (if needed)

Per-product:
```bash
TOKEN=$(curl -s -X POST "$MEDUSA/auth/user/emailpass" -d '{"email":"...","password":"..."}' | jq -r .token)
curl -s -H "Authorization: Bearer $TOKEN" "$MEDUSA/admin/products?handle=$HANDLE&fields=metadata,id" | jq '.products[0]' > /tmp/p.json
ID=$(jq -r .id /tmp/p.json)
THUMB=$(jq -r '.metadata.previous_thumbnail' /tmp/p.json)
jq -r '.metadata.previous_images' /tmp/p.json > /tmp/imgs.json
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"thumbnail\":\"$THUMB\",\"images\":$(jq '[.[] | {url: .}]' /tmp/imgs.json)}" \
  "$MEDUSA/admin/products/$ID"
```
GCS uploads were `--no-clobber` and don't need rollback.
## [2.45.0-dryrun] - 2026-05-30

### Pivoted — 4soft pricing pipeline from sea-LCL to air-freight (dry-run only, NOT deployed)

4soft is imported by air (Czech Republic → Thailand), but
`foursoft-catalog/import_pricelist.py` was routing every SKU through the EU
sea-LCL freight engine with `kg=0`. This release pivots the pipeline to
air-freight with proper chargeable-weight handling. **Dry-run only — Firestore
and Medusa untouched, no Cloud Run deploy.** Awaiting user review of the
validation diff before promoting.

- **Engine (cross-repo, `shipping-automation/mcp-server/cost_engine.py`):**
  `calc_freight` air branch now derives a chargeable kg from CBM (volumetric =
  cbm × 167 kg/m³, IATA general cargo) when `kg=0` is passed. Adds
  `volumetric_divisor_kg_per_m3` knob to the EU air method. Fixes stale
  `VENDOR_COUNTRY_MAP["4soft"] = "china"` → `"europe"`.
- **Importer (`foursoft-catalog/import_pricelist.py`):** `METHOD="lcl"` →
  `"air"`. Adds `--air-rate <THB/kg>`, `--landed-csv <path>`, and `--load-dims`
  CLI flags so the dry-run can pull dim_index from Firestore (520 docs indexed)
  and override the rate per run. Overrides cost_engine's air `per_kg` for the
  call window and zeroes `min_charge` (per-SKU pricing — the 5 000 THB shipment
  minimum is amortized across the whole shipment, not per item).
- **Rate research:** new file `foursoft-catalog/data/air-freight-rates-2026-05-30.md`.
  No public PRG→BKK spot quote; used 6 backhaul-relevant data points (Xeneta
  Europe-origin avg, WorldACD week-18 and April global yields, FreightAmigo
  FRA→HKG, TH→EU reverse proxy, Suaid EU→USA). Low **90**, median **105**
  (recommended), high **135** THB/kg chargeable, all-in.
- **Dry-runs:** 3 runs at 90 / 105 / 135 THB/kg. Outputs:
  `foursoft-catalog/data/pricelist_2025-03-01_landed_AIR-DRYRUN-{lo,mid,hi}.csv`.
  Diff doc: `foursoft-catalog/data/air-freight-dryrun-diff-2026-05-30.md`.
  - `flat_uplift` rows (2 159 / 2 410) are byte-identical to the current sea
    landed CSV — 0 diffs. The `else` branch was intentionally untouched.
  - **92 `dims_scaled` rows** move user-facing prices (most by ±5%; one
    representative — V1-03B-001 3D Bench PLAY — drops -11.7% because the LCL
    18 000 THB clearance fee was dominating). High-CBM 3D items shift ±1%.
  - **134 capped + 2 069 floored** rows are unchanged at the user level — the
    sea-tuned clamps still bind. Cap count fell 167 → 134 (–20%) because air's
    3 800 THB clearance is much lower than LCL's 18 000 THB.
- **`LOGISTICS_TIERS`** intentionally left at the current sea-tuned values
  (`0.80–2.50` at tier 1, etc.). The dry-run produces the evidence needed for
  a follow-up PR to retune them with real numbers.
- **Tests:** new `TestAirFreightChargeable` class with 7 cases in
  `shipping-automation/tests/test_pricing_engine.py` (volumetric fallback,
  actual-kg precedence, min_charge floor + zero-override, default divisor 167,
  regression guards for EU air profile and VENDOR_COUNTRY_MAP). 26/26 passed.

**Plan:** `~/.claude/plans/goal-4soft-is-imported-hazy-mochi.md`.
**Out of scope:** clamp retune, Firestore writes, dim-data fix for
A6-01A-00-style tiny-CBM rows, real Czech→BKK forwarder RFQ (defer to
follow-up PRs).

---

## [2.44.0] - 2026-05-30

### Added — 4soft 2D ground markings created in Medusa (catalog completion)

Follow-up to v2.42.0 (3D) / v2.43.0 (PDF images). Materializes the deferred
**2D scope** — the flat ground markings (hopscotch, numbers/letters, footprints,
shapes) — into Medusa from the existing pricelist records. Pure extraction (no
AI): `create_medusa_products.py --scope 2D --status draft` pushes the
`vendors/4soft/products` docs (code / EN name / EUR-derived prices / dims /
category) as handle-based products, attaching the picture-pricelist PDF images
already written to Firestore in v2.43.0.

- **Create:** **1,553 new** 2D products (843 with a PDF image, ~712 image-less),
  **247 existing** updated (Czech → EN title + metadata), **2** benign
  "handle already exists" skips (present but not SC-indexed). Created as
  **draft** for review before publish.
- **Price sync** (`sync_brand_prices_to_medusa.py --brand 4soft --write`):
  match rose to **2,394 / 2,410 (99.3%)** — THB/USD/EUR/SGD.
- **Remaining 16** = the **packaging (10) + accessory (6)** SKUs (codes like
  `BOX-typ2`, `BOXOSB-A`) — deliberately NOT created; they look like packaging
  surcharges / fixed-fee line items rather than sellable catalog products.

The 4soft brand is now effectively complete in Medusa: **~3,960 products**
(2,408 of the 2,410 priced pricelist SKUs present + earlier web-only extras).
3D published (v2.42.0 follow-up); 2D created as drafts pending review.

#### Deferred follow-ups
- Review + publish the 1,553 2D drafts; ~712 are image-less (no image in the PDF
  or on 4soft.cz) — optionally AI-generate placeholders later.
- Decide whether the 16 packaging/accessory SKUs belong in the catalog.
- 2026 pricelist + discount structure requested from 4soft (email sent 2026-05-29).


## [2.43.0] - 2026-05-29

### Added — 4soft product images from the picture-pricelist PDF

Follow-up to v2.42.0 (4soft 3D create). The 3D drafts mostly fell back to
borrowed base-design web images (only 130 web bases existed). The official
**picture-pricelist PDF** (`4soft_EPDM_graphics_-_picture_-_price_list_2025_optimized.pdf`,
89 pages, the picture variant of the v2.40.0 `.xls`) carries a 100x100 image per
product design — the only image source for the ~2,000 colour/UV/size variants
4soft.cz does not publish on the web.

- `foursoft-catalog/extract_pdf_images.py` (new) — PyMuPDF grid extractor:
  matches each left-column image to its code by y-row, validates against the
  pricelist, prefers the DeviceRGB jpeg (renders the cell for jpx-only).
  Extracted **989 images** (964 native jpeg / 25 rendered), verified by eye
  (crocodile, Rubik's cube, sea star). Mapping → `data/pdf_images_map.json`.
- `foursoft-catalog/enrich_pdf_images.py` (new) — uploads the 989 images to
  `gs://ai-agents-go-vendors/4soft/pdf/<handle>.jpg` (the bucket the storefront
  image proxy reads — see leka-website `api/i/[...path]`), then writes
  `vendors/4soft/products[].images` via the proxy URL
  `https://catalogs.leka.studio/api/i/4soft/pdf/<handle>.jpg`. UV-class-matched
  base-design borrowing lifts coverage to **1,635 / 2,410 = 67.8%**.
- **Precedence:** keep the 372 higher-res web images as primary (no downgrade);
  REPLACE the 162 v2.41.0/v2.42.0 borrowed-web base-design images with the real
  PDF image; ADD a PDF image to 1,101 previously image-less products.
- **Medusa:** 419 in-channel products updated with the PDF image (thumbnail +
  images), 0 errors. 844 PDF-imaged codes are the deferred 2D SKUs (not yet in
  Medusa) — images held in Firestore for when they are created.

The 989 extracted JPGs are reproducible (`extract_pdf_images.py`) and live in
GCS, so they are gitignored; the mapping JSON is committed as provenance.

#### Note on automation
The picture-pricelist note in CLAUDE.md's "Image Pipeline" (upload to
`ai-agents-go-documents/product-images/`) is **stale** — the live storefront
proxy reads `gs://ai-agents-go-vendors/<vendor>/<path>`.

#### Deferred follow-ups
- 775 codes (mostly flat 2D markings) have no image in the PDF — still
  image-less.
- Higher-resolution images would need a different source (PDF embeds are 100px).


## [2.42.0] - 2026-05-29

### Added — 4soft 3D play elements created in Medusa + dims-based pricing

Follow-up to the 4soft pricelist ingest (**v2.40.0**, PR #63). That release
priced all 2,410 pricelist SKUs in `vendors/4soft/products` but only **377**
existed as Medusa products — the other 2,033 were pricelist-only. This release
creates the **3D scope** in Medusa and upgrades pricing for the SKUs with real
dimensions.

#### 2026 pricing re-verification (user decision 2026-05-29)

Checked `eukrit@goco.bz` (SA domain-wide delegation, ~201 emails from 4soft.cz):
- The *"Our Pricing for 2026"* newsletter (graphics@4soft.cz, 2026-04-01) is an
  **image-only marketing blast — no pricelist attachment, no price/discount
  figures.** No 2026 `.xls` exists in the inbox; the latest actual pricelist is
  still `4soft_EPDM_graphics-price_list_2025.xls` (2025-06-25).
- No document supersedes the **15% basic EXW** discount (2020 Price Conditions
  PDF). The 2025 pricelist email confirms a reseller % applies on list prices.
  → **EXW 15% / GM 40% retained.** 2026 pricelist is an open follow-up.

#### Website reality

4soft.cz publishes only **400 products** (256 2D / 90 3D / 54 other), not the
~2,033 assumed. 377 match the pricelist 1:1 (EN site names == pricelist EN
names — cross-checked); 2,033 pricelist codes (mostly colour/UV/size variants of
2D ground markings) have **no individual web page**. User decision: create the
**3D scope only** (the hero physical play elements) and defer the flat 2D
markings.

#### Scope created (dimension == "3D" = 592 SKUs)

3D animals/nature/shapes/sport, **tunnels+slides (41)**, **water fountains
(29)**, EPDM houses (5), furniture (112). Created as **draft** for review before
publish.

- `foursoft-catalog/backfill_scraped_details.py` (new) — wrote **260
  dimensions** + **163 borrowed base-design images** (a colour variant inherits
  its base design's photo, flagged `representative=true`) into
  `vendors/4soft/products`.
- Re-ran `foursoft-catalog/import_pricelist.py` → **251 SKUs now use
  `dims_scaled` CBM** landed cost (was 0; rest flat-uplift). FX this run:
  USD 33.25, EUR 38.71, SGD 26.04.
- `foursoft-catalog/create_medusa_products.py` (new) — handle-based create
  reusing `scripts/sync_vendors_to_medusa.py` helpers, scope-filtered, draft
  status, EN pricelist titles, base-image attach. **Created 462** new 3D
  products (163 with images), **renamed 130** existing Czech titles → EN,
  0 errors. Medusa 4soft channel: 391 → **853 products**.
- `scripts/sync_brand_prices_to_medusa.py --brand 4soft --write` — multi-currency
  THB/USD/EUR/SGD prices pushed; match rose **377 → 839** (the 1,571 unmatched
  are the deferred 2D/accessory/packaging pricelist-only SKUs).

#### Deferred follow-ups

- ~1,800 flat **2D ground markings** (hopscotch, numbers/letters, footprints) —
  not created this pass (image-less, lower catalog value).
- Confirm the **2026 pricelist** (request the `.xls` from 4soft) and re-verify
  the 15% basic EXW before a full re-sync.
- Review the 462 draft 3D products and **publish** when approved.

## [2.41.0] - 2026-05-29

### Added — Archimedes Water Play landed pricing (the deferred PR #59 work)

Continues the `archimedes-water-play` brand (Wenzhou Daosen 温州道森游乐戏水,
34 children's water-play SKUs, slugs AWP001–AWP034) merged in PR #59 (v2.36.0),
which parsed the CNY pricelist but **deferred** landed pricing
(`landed_pricing_status: "deferred — CNY→USD + dim normalization required"`).

This release runs the parser against live Firestore and completes the landed
CNY→THB/USD/SGD pricing pass, mirroring the Wisdom (China FOB) pipeline.

#### Task 1 — audit doc populated
- Ran `archimedes-water-play-catalog/import_pricelist.py` (this machine has gcloud
  ADC; the authoring machine did not). Wrote the audit doc with all 34 variants to
  Firestore `vendors/archimedes-water-play/pricelists/2026-05-29` (database `vendors`).

#### Task 2 — landed pricing
- **`archimedes-water-play-catalog/price_archimedes.py`** (NEW) — faithful mirror of
  `shared/wisdom_pricing.compute_wisdom_retail`, but in CNY:
  - Origin China → **0% import duty** (ASEAN-China FTA Form E), **+7% Thai import VAT**
    on (CIF+duty), **+7% TH customer VAT** embedded in `retail_thb` only.
  - **Independent** THB/USD/SGD retail — each derived from `landed_thb` (USD/SGD via
    `landed_thb / FX`, no TH customer VAT), never `retail_thb / FX`.
  - **Gross margin 0.50** — China-origin default, same as Wisdom. Adjustable via the
    pricing-config form (`brands.archimedes-water-play.gross_margin`).
  - **FX:** live THB-per-unit rates from shipping-automation `fx_rates.get_fx_rates`
    (+2% buffer). Snapshot used: CNY=4.8903, USD=33.2529, SGD=26.0437 THB/unit
    (⇒ CNY→USD 0.1471, CNY→SGD 0.1878). Fallback constants CNY 4.80 / USD 35 / SGD 25.
  - **Dimension → CBM (documented, conservative):** only `kind == "lwh"` rows get a CBM.
    Unit per row: explicit "cm" marker → cm; else any axis > 1000 → mm (e.g. `2000*1100*1250`);
    else cm (e.g. `95×45×95`). `CBM = L·W·H (m³) × 0.15` packing factor. `lwh` rows route
    through the China-LCL `cost_engine` + Vinci tier clamp (floor/cap by FOB band, which
    bounds any cm/mm mis-guess — and most small items hit the LCL `min_charge`, so the CBM
    value barely moves the result). `custom` / `diameter` / `two-dim` / `length` / `unknown`
    rows fall back to the flat China **CIF ≈ FOB** path (no freight uplift), exactly like Wisdom.
  - Result: **34 SKUs priced** (28 via China-LCL CBM, 6 via flat CIF≈FOB). Audit CSV at
    `archimedes-water-play-catalog/data/pricelist_2026-05-29_priced.csv`.
  - **Known caveat:** lwh (CBM) SKUs carry the per-shipment fixed clearance/last-mile of the
    China-LCL route, so an `lwh` item can price ~2× an equivalently-priced flat (`custom`/
    `diameter`) item. This is the standard Wisdom-pipeline behaviour; the tier clamp bounds it.
    Adjust GM or method via the pricing-config form + re-run if a flatter curve is preferred.
  - Writes priced product docs to `vendors/archimedes-water-play/products/<sku>` (vendors DB),
    matching the rampline/designpark per-product shape; updates the audit doc
    `landed_pricing_status → "completed (v2.38.0)"` with the FX snapshot.
- **`scripts/add_archimedes_pricing_config.py`** (NEW) — merge-only writer that adds
  `brands.archimedes-water-play` (GM 0.50, `import_duty_rate` 0.00, `currency` CNY,
  `origin` china, `default_cny_thb` 4.80, source pricelist pointer) to
  `pricing_config/canonical` (database `leka-product-catalogs`) **without disturbing** the
  other brands added by later PRs (vortex/4soft/weplay). Idempotent (`--force` to overwrite).
- **`scripts/seed_pricing_config.py`** — `build_seed_doc()` now includes the
  `archimedes-water-play` block so a future `--force` reseed stays consistent.

#### Task 3 — Medusa
- Created/confirmed the **"Archimedes Water Play"** Medusa sales channel
  (`sc_01KSSP39K5DVH9TT2TMXCREHFV`) and added it to the `SC` map in
  `scripts/sync_brand_prices_to_medusa.py`. **Product creation is a follow-up** — there are
  no AWP### products in Medusa yet, so the price sync is a documented no-op (0/34 matched)
  until the 34 products are created. Once created (SKU = AWP###), the existing sync will
  push THB/USD/SGD prices by SKU match.

#### Docs
- `docs/summaries/pricing-config-master.md` — added §4f (brand config), §6f (formula),
  scripts-reference rows, and a v2.38.0 version-history row.
- `archimedes-water-play-catalog/DEPLOYMENT_LOG.md` (NEW) — dated brand deploy log.

### Files
- NEW `archimedes-water-play-catalog/price_archimedes.py`
- NEW `archimedes-water-play-catalog/data/pricelist_2026-05-29_priced.csv`
- NEW `archimedes-water-play-catalog/DEPLOYMENT_LOG.md`
- NEW `scripts/add_archimedes_pricing_config.py`
- EDIT `scripts/seed_pricing_config.py` (+ archimedes seed block)
- EDIT `scripts/sync_brand_prices_to_medusa.py` (+ SC map entry)
- EDIT `docs/summaries/pricing-config-master.md`, `docs/build-summary.html`, `VERSION`,
  `.claude/PROGRESS.md`

### Outcome
- Success. 34 SKUs priced + written to `vendors/archimedes-water-play/products`; audit doc
  status → completed; brand config + sales channel landed. `verify.sh` 0 FAIL.
- **Version note:** rebased onto `origin/main` (2.40.0 after WePlay #61, Vortex #62, 4soft #63);
  renumbered to **2.41.0** (next free minor). The Firestore audit doc
  `landed_pricing_status` still reads "completed (v2.38.0)" — the version at write time.

---

## [2.40.0] - 2026-05-29

### Added — 4soft EPDM-graphics 2025 pricelist ingested (2,410 EUR SKUs)

Parsed and priced the **4soft 2025 EPDM-graphics pricelist** (`.xls`,
`2025-06-25 4soft_EPDM_graphics-price_list_2025.xls`, valid 2025-03-01) and
ingested it as a first-class EUR-FOB brand following the **Berliner EXW
pattern**.

#### Reconciliation decision (Step 4) — new brand, NOT the EPDM/Infill pricer

The task flagged the existing **EPDM/Infill CFH pricer** (v2.10.0 —
`products_epdm`/`products_infill`, area-priced THB/m², CFH lookup contract,
`scripts/sync_epdm_pricelist.py`) as a possible overlap. **There is no
overlap:**

- The EPDM/Infill pricer is **generic wet-pour surfacing** (SBR granule,
  Sand/Rubber infill, Miroad, Eurosia Non-UV/UV, TPV) sourced from the
  "EPDM 2024 / Pricelist" Google Sheet — priced **per m² of installed area**
  at a thickness, with a `cfh_m` field for the storefront CFH pricer. It is
  **not** 4soft-branded.
- The 4soft `.xls` is **2,410 discrete, per-item EUR SKUs** — moulded-EPDM
  3D play elements (animals, shapes, tunnels, furniture, fountains) and 2D
  markings (hopscotch, numbers/letters, footprints). Single "POHODA" sheet
  (Czech accounting export); columns code / name / `Target SALE price EUR`.
  **No per-m² surfacing section, no CFH.**

The 4soft `.xls` is the **authoritative pricelist for the existing 4soft
Medusa brand** (sales channel `sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y`; 391 SKUs
scraped from 4soft.cz in earlier work, previously **unpriced**). Decision:
add a **`brands.4soft`** config (NOT extend the EPDM pricer), price all 2,410
SKUs through the shared landed pipeline, and leave the wet-pour pricer
untouched. The CFH/per-m² contract is fully preserved.

#### Trade terms (Step 3) — EXW, EUR, EU/Czech origin

- 4soft, s.r.o. is **Czech** (Tanvald, CZ — EU origin, VAT CZ28703324), prices
  in **EUR**, terms **EXW** (`2019-11-26 Price conditions 2020` PDF). Basic
  **reseller discount 15%** off list (+5% for orders >€2,500, +2.5% prepay,
  min €5k/yr turnover — order-specific, not baked into catalog cost).
- Gmail (eukrit@goco.bz) confirms 4soft is an active vendor (roger@4soft.cz,
  graphics@4soft.cz); recent quotes seen EXW and project-CFR Bangkok. No email
  superseding the 15% basic EXW discount surfaced. A *"Our Pricing for 2026"*
  newsletter exists (2026-04-01) — **follow-up: confirm 2026 discount/pricelist.**
- **User decisions (2026-05-29):** gross margin **40%**; bake **15% basic EXW**
  discount only (`eur_fob = list × 0.85`); price the 391 existing Medusa
  variants now + spawn a follow-up to scrape the ~2,020 missing SKUs.

#### Cost structure (same shared pipeline as Vinci/Berliner/Rampline)

`eur_fob = list_eur × 0.85` → EUR→THB FX → landed THB via shipping-automation
`cost_engine` (LCL EU, Baltic-rate calibration) → **10% Thai duty**, **7%
import VAT** on (CIF+duty), tiered logistics floor/cap → retail. Independent
THB/USD/EUR/SGD; **7% TH customer VAT embedded in `retail_thb` only**; SG GST
gated on `sg_nubo_gst_registered` (off). No published dims yet → all rows use
the flat-35%-uplift path; the tier-0 floor (×1.80) re-bounds the many cheap 2D
items (**2,265 / 2,410 floored**). FX snapshot this run: USD 33.25, EUR 38.71,
SGD 26.04 (exchangerate-api.com live, +2% buffer).

#### Files & outcomes

- **`foursoft-catalog/import_pricelist.py`** (new) — parses the `.xls`
  (`xlrd`), applies EXW 15%, computes landed/retail via the shared pipeline
  with `brand="4soft"`, writes `vendors/4soft/products`, and self-seeds
  `brands.4soft` into `pricing_config/canonical` via a safe read-modify-write
  merge (never a full `--force` reseed). Emits a committed parsed CSV +
  landed CSV.
- **`foursoft-catalog/data/pricelist_2025-03-01.csv`** (new) — in-repo parsed
  source of truth (2,410 rows: code, name, list_eur, section, dimension,
  product_group, unit).
- **`foursoft-catalog/data/pricelist_2025-03-01_landed.csv`** (new) — full
  landed-cost / retail audit trail.
- **`scripts/sync_brand_prices_to_medusa.py`** — added `4soft` →
  `sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y` to the SC map.
- **`scripts/seed_pricing_config.py`** — added the `brands.4soft` block
  (gm 0.40, exw 0.15) so a future `--force` reseed includes it.
- **`docs/summaries/pricing-config-master.md`** — new §4f (4soft brand),
  §6f formula, §11 script row, §12 version-history row.
- **Firestore `vendors/4soft/products`:** wrote **2,410** docs (**2,033 new**,
  377 updated existing). Vendor root `product_count = 2410`.
- **Firestore `pricing_config/canonical.brands.4soft`:** seeded (gm 0.40,
  exw 0.15, EXW, EU/Czech).
- **Medusa:** matched **377 / 2,410** vendor docs to existing 4soft variants
  by SKU (= item_code); **updated 377 variants, 0 errors** (THB/USD/EUR/SGD).
  The **2,033 unmatched** are pricelist-only — not yet Medusa products
  (`sync_brand_prices_to_medusa.py` is update-only by design). **Follow-up:
  scrape the ~2,020 missing SKUs from 4soft.cz, then create + price them.**

Spot-check: `4soft-a1-01a-00` ("Circle 18 cm", list €20) → retail ฿2,112.30 /
$59.37 / €51.00 / S$75.80 (live in Medusa).
---

## [2.39.0] - 2026-05-29

### Added — WePlay landed-cost retail pricing (THB/USD/SGD) + Medusa sync

Turned the raw WePlay quotation prices (`AQ1251030077`, ingested audit-only in
v2.26.0) into full landed-cost retail across all three currencies, added the
brand to the pricing engine, and pushed prices to Medusa.

**Trade terms verified** off the quotation header (authoritative source):
FOB Taiwan, **net USD** unit prices (no list/discount split — these are GO
Corp's negotiated reseller prices), country of origin Taiwan, T/T in advance,
30–45 day lead time, MOQ = full master carton, MOV USD 10,000/shipment.
_(Gmail confirmation of terms was not available in this session — the printed
quotation terms were used directly.)_

#### `weplay-catalog/import_pricelist.py` (new)
Parses the 7-page text-layer PDF (`pdfplumber`), capturing SKU, description,
USD net price, unit, master-carton **PACK qty**, **carton CBM**, and G.W.
Taiwan/USD cost cascade (route-correct sibling of the `shared/landed_pricing`
EU path and the `shared/wisdom_pricing` China path), following the canonical
v2.31.0 independent-currency convention:

```
per_unit_cbm = carton_cbm / pack_qty
fob_thb      = fob_usd · USD_THB
freight_thb  = per_unit_cbm · sea_lcl_per_cbm_thb (5500)   # CBM path; flat 1.35x fallback
insurance    = fob_thb · 1%
cif_thb      = fob_thb + freight_thb + insurance
duty_thb     = cif_thb · 0.10            # Taiwan non-FTA import duty
import_vat   = (cif_thb + duty_thb) · 0.07
landed_thb   = cif_thb + duty_thb + import_vat
retail_thb   = (landed_thb / (1 - 0.50)) · 1.07     # +TH customer VAT (THB only)
retail_usd   = (landed_thb / USD_THB) / (1 - 0.50)  # independent, no TH VAT
retail_sgd   = (landed_thb / SGD_THB) / (1 - 0.50) · sg_gst_mult
```

Writes `pricing.retail_thb/usd/sgd` + full audit map to matching
`vendors/weplay/products` docs (boundary-less `[A-Z]{2}[0-9]{4,}` SKU-token
match). Idempotent, merge-only. **Gross margin 0.50** (user-confirmed 2026-05-29).

#### Pricing config
- `pricing_config/canonical` → added `brands.weplay`
  `{gross_margin: 0.50, import_duty_rate: 0.10, sea_lcl_per_cbm_thb: 5500, default_usd_thb: 33.0}`
  (targeted merge — existing brands preserved).
- `scripts/seed_pricing_config.py` → added the matching `weplay` seed block.
- `docs/summaries/pricing-config-master.md` → new §4f WePlay brand section + version-history row.

#### Run results
- 167 quotation rows → 151 unique SKU tokens → **189** Firestore docs priced (0 misses).
- Medusa sync (`scripts/sync_vendors_to_medusa.py --brand=weplay --skip-no-images`):
  200 image-having products → 162 updated, 38 created, **151 priced**, 0 errors.
  Pushed to existing WePlay sales channel `sc_01KR6Z0VBSXWYZDVGF30EAP0EQ`.

---

## [2.38.0] - 2026-05-29

### Added — Vortex Aquatics 2026 USD pricelist ingestion + per-product-line reseller discounts

Ingested Vortex's **2026 USD Price List (R2, released Feb 2026)** — 311 SKUs
across 22 collections — into `vendors/vortex/products` with the shared
landed-cost pipeline, then synced multi-currency retail to Medusa.

Vortex's reseller discount is **per product LINE**, not a flat brand discount.
The engine maps each pricelist *Collection* to one of Vortex's top-level
product lines and applies that line's confirmed USD discount before the
landed-cost pipeline runs.

#### Reseller terms (cross-checked from the supplier Gmail thread, 2026-05-29)

- **Origin / trade terms:** EXW Pointe-Claire, Quebec, **Canada**, USD
  (Vortex Aquatic Structures International). Non-China origin → 10% Thai import
  duty. Confirmed via the ECU Worldwide freight quote ("EXW. Term", shipper
  VORTEX Pointe-Claire) in `eukrit@goco.bz`'s mailbox.
- **Per-line reseller discounts (USD)** — confirmed by OCR of the discount
  table Vortex shared in the "Pricelist 2026" thread, exact match to the
  user-provided structure:
  Splashpad 25% · Poolplay 15% · Spraypoint 25% · Elevations 15% · WQMS 15% ·
  Water Journey 20% · Water Slides 15%.
- **User mapping decisions (2026-05-29):** CoolHub™ → its own line, **0%**
  (not covered by the reseller agreement; our cost = full list); SmartPoint /
  Smartpoint N°4 → classified under **Splashpad 25%**; PlayNuk™ → grouped with
  **Elevations 15%** (per Vortex's own "Elevations™ & PlayNuk™" taxonomy).

#### Pricing model

`our_cost_usd = list_usd × (1 − line_discount)`, then flat-uplift CIF (1.35) +
10% non-China duty + 7% import VAT + Vinci tier floor/cap clamp → landed THB.
Retail derived independently per currency: `retail_thb = (landed/(1−gm))×1.07`
(TH customer VAT, THB only); `retail_usd/eur/sgd` from the same landed cost.
`gross_margin = 0.35` (matches the other USD-FOB import brands; editable via
the pricing-config form). Every SKU uses the flat-uplift path (the pricelist
carries no dimensions) — same as DesignPark / WePlay.

#### Files

- `vortex-catalog/vortex_config.py` (new) — canonical maps: `GROSS_MARGIN`,
  `LINE_DISCOUNTS` (7 lines + CoolHub 0%), `COLLECTION_TO_LINE` (22 collections),
  origin/terms, `brand_config()`. Single source of truth shared with the seeder.
- `vortex-catalog/import_pricelist.py` (new) — pdfplumber PDF parser →
  `price_vortex_row()` → `vendors/vortex/products`; deep-merges `brands.vortex`
  into `pricing_config/canonical` (mirrors WePlay's `brands.weplay seed`).
  `--dry-run` / `--apply` / `--dump-csv` / `--skip-config`.
- `scripts/sync_brand_prices_to_medusa.py` — added `vortex` →
  `sc_01KPRY1T8HZJ57020JPZVGAKZK` (SKUs `VOR-<zero-padded code>`).
- `scripts/seed_pricing_config.py` — added the `vortex` brand block (imported
  from `vortex_config`) so a future `--force` re-seed stays complete.
- `docs/summaries/pricing-config-master.md` — new §4f Vortex brand, §6f
  formula, version-history row.

#### Outcome

- Firestore: **311** priced docs in `vendors/vortex/products`; line coverage
  splashpad 236 · elevations 26 · water_journey 25 · coolhub 18 · poolplay 6.
- Config: `pricing_config/canonical.brands.vortex` merged (other brands intact).
- Medusa: **295 / 311** variants updated (94.9% match by `VOR-…` SKU; 0 errors).
  The 16 unmatched are stainless `VOR-…-304L` SmartPoint SKUs absent from
  Medusa under that form (price-only-in-Firestore until reconciled). All four
  currencies (THB/USD/EUR/SGD) verified on synced variants — USD region
  (Asia-Pacific) serves Vortex correctly.
## [2.37.0] - 2026-05-29

### Added — AI enrichment of Wisdom / Leka Project specs + Toys category

> **Status: ✅ LIVE on Medusa.** Full enrichment + apply + category-link pass
> shipped 2026-05-29. Renumbered to 2.37.0 at rebase (2.35.0 = checkout fix PR #58;
> 2.36.0 = archimedes-water-play PR #59).

Live audit found the PDP at `leka-website/catalogs/src/app/[brand]/[handle]/product-detail.tsx`
reads `metadata.materials[]`, `metadata.specifications.{age_group,num_users,indoor_outdoor,...}`
plus a real product `description`. Wisdom products carry **none** of these — they were
imported from a China OEM pricelist with only SKU, title (EN+CN), L×W×H, FOB price,
page number. 100% of 5,061 Wisdom products show only L/W/H/Weight on PDP.

Also: storefront has no top-level "Toys" category. Wisdom products fell into 0 categories
on Medusa (`category_ids=[]`), so admin and PDP breadcrumbs are bare.

#### Pipeline added

- `scripts/enrich_wisdom_with_ai.py` — Gemini 2.5 Flash vision pass over all 5,061 Wisdom-origin
  products on live Medusa. Sends `{title, dimensions, thumbnail}` and gets back structured
  JSON: `{category, subcategory, age_min/max_years, materials[], num_users_min/max,
  indoor_outdoor, description, confidence}`. Category vocab includes a dedicated **toys**
  bucket separate from large `playground_equipment`. Idempotent + resumable; checkpoints
  to Firestore `wisdom_enrichment/{sha1(sku)}`. Concurrency 4. Cost: ~$0.50 for full pass.
- `scripts/apply_wisdom_enrichment.py` — Push enrichment to Medusa via `/admin/products/{id}`:
  fills `metadata.materials[]`, `metadata.specifications`, `metadata.category_inferred`,
  and overwrites `description` only when current desc equals title (preserves manual edits).
  Records `enrichment_applied_at` for idempotency.
- `scripts/medusa_create_toys_category.py` — Creates 16 top-level Medusa product categories
  matching the AI vocab (Toys, Playground Equipment, Kids Furniture, Arts & Crafts,
  Educational Manipulatives, Music Instruments, Role Play, Sports & Outdoor, Infant & Toddler,
  Water Play, Sand Play, Climbing, Ride-Ons, Books & Media, Safety & Accessories, Other),
  then links each Wisdom product to its inferred category.

#### PDP changes (leka-website — separate repo)

- `catalogs/src/app/[brand]/[handle]/product-detail.tsx` — accept both `meta.materials[]` and
  legacy singular `meta.material`; render new spec rows `Volume`, `Indoor/Outdoor`, `Subcategory`;
  suppress `EN Standard`, `Fall Height`, `Safety Zone` for OEM brands (`source_brand_internal`
  in {wisdom, vinci, vortex}) which don't carry EU certifications. Materials displayed
  title-cased. (Lives in eukrit/leka-website; tracked/committed there separately.)

#### Verification (smoke test, 9 representative SKUs)

| SKU | Title | → Category |
|---|---|---|
| A4-497100 | Dino Rocker™ | toys |
| GP1-12004 | Giraffe Ride-on | toys |
| G1-SG018 | Smart Car | toys |
| SR-21004 | Pony Spring Rider | playground_equipment |
| KB1-0111-V01 | Small Dress Up Trolley | kids_furniture |
| H3-DMM004 | Tambourine | music_instruments |
| B2-2006 | Blow Lotto | educational_manipulatives |
| E10-B04 | Rabbit 45Pcs | educational_manipulatives |
| K4-20420 | Flower Matching Game | educational_manipulatives |

Average confidence on smoke set: 0.89.

#### Full-run results

| Stage | Outcome | Duration |
|---|---|---|
| Enrich (Gemini 2.5 Flash) | 5,061 ok, 0 errors | 3.1 h |
| Apply to Medusa | 4,571 applied + 490 skipped (idempotent re-run), 0 errors | 56 min |
| Category create | 16 top-level categories ensured | 1 min |
| Category link | 5,055 linked + 6 already, 0 errors | 31 min |

#### Confidence distribution (full pass)

- ≥ 0.85: **4,145** (81.9%)
- 0.70 – 0.85: 828 (16.4%)
- 0.50 – 0.70: 88 (1.7%)
- < 0.50: 0

#### Final per-category counts (live Medusa, Leka Project SC)

| Category | Count | Category | Count |
|---|---|---|---|
| Playground Equipment | 1,523 | Music Instruments | 70 |
| Kids Furniture | 977 | Sand Play | 70 |
| Educational Manipulatives | 845 | Water Play | 44 |
| Arts & Crafts | 495 | Safety & Accessories | 43 |
| Role Play | 472 | Sports & Outdoor | 41 |
| **Toys** | **300** | Ride-Ons | 25 |
| Infant & Toddler | 121 | Other | 15 |
| | | Climbing | 10 |
| | | Books & Media | 4 |

#### Two PDP query bugs found + fixed during verification (leka-website)

1. **Medusa v2 `+categories` shorthand returns `[]`** on the Store API — nested
   paths must be explicit. PDP query updated to
   `+categories.id,+categories.name,+categories.handle` (plus `+collection.id,
   +collection.title,+tags.id,+tags.value`). The `categories: Array<...>` type
   gained a `handle` field.
2. **Breadcrumb prefers Medusa category over legacy `series_name`** — Dino Rocker
   now shows `Leka Project / Toys / SKU` with the Toys node linking to
   `/leka-project?category=toys`.

#### Verified on `leka-project-qruge2f7` (Dino Rocker™)

```
title:        Dino Rocker™
description:  A vibrant red plastic push-car designed for toddlers, featuring
              a functional steering wheel and a convenient parent push handle ...
dims:         L57 × W33 × H69 cm
materials:    [plastic]
specs:        {age_group: "1-3 yrs", num_users: "1",
               indoor_outdoor: "both", subcategory: "push-car"}
category_inferred: toys
admin categories:  Other, Toys           (confidence 0.90)
```

#### Apply-pipeline fixes shipped during the run

- `scripts/apply_wisdom_enrichment.py` — added `PYTHONUNBUFFERED=1` to the run
  invocation (Python full-buffers stdout when piped through `grep`, so progress
  logs were invisible until process exit on the first kill-shot bg).
- `scripts/medusa_create_toys_category.py` — `ensure_category` now matches by
  handle ONLY (matching by name was picking up legacy `leka-project-outdoor-*`
  subcategories named "Climbing"/"Sand Play"/"Water Play"/"Other" and blocking
  creation of the clean top-level handle). Link payload now uses Medusa v2's
  `categories: [{id}]` shape, not the rejected `category_ids: [...]`.

---

## [2.36.0] - 2026-05-29

### Added — `archimedes-water-play` brand: Wenzhou Daosen pricelist parsed

New brand folder `archimedes-water-play-catalog/` for the Wenzhou Daosen
(温州道森游乐戏水) factory pricelist — 34 children's water-play SKUs (Chinese
names + raw dimensions + CNY prices). Vendor contact 桂书龙 (13676763303),
Yongjia/Wenzhou. Brand name comes from SKU AWP033 阿基米德取水器
("Archimedes water collector"), the signature item in the catalog.

- Parser: `archimedes-water-play-catalog/import_pricelist.py` reads the
  single sheet `儿童戏水`, slugs SKUs as `AWP001`..`AWP034`, parses each
  dimension cell into structured fields (length/width/height + kind:
  `lwh`/`two-dim`/`diameter`/`length`/`custom`) while preserving the raw
  string. **Mixed units in source (cm vs. mm) — no CBM normalization
  attempted; landed-pricing pass deferred.**
- CSV: `archimedes-water-play-catalog/data/pricelist_2026-05-29_parsed.csv`
  (34 rows, UTF-8 BOM for Excel-friendly Chinese).
- Firestore target: `vendors/archimedes-water-play/pricelists/2026-05-29`
  in the `vendors` database (same shape as `vendors/rampline/pricelists/...`).
  Run `python archimedes-water-play-catalog/import_pricelist.py` once
  `LEKA_FIRESTORE_ACCESS_TOKEN` or ADC is configured.
- Source XLS archived at
  `archimedes-water-play-catalog/data/source/daosen_pricelist_2026-05-29.xls`.

Price range: ¥560 (手摇取水) → ¥16,700 (月亮自行车, 直径200×70×225).

> Renumbered from 2.35.0 at merge: 2.35.0 was already taken by the checkout fix
> (below). Audit/parse-only — landed pricing + Medusa sync are a follow-up pass.

### Files changed
- `archimedes-water-play-catalog/import_pricelist.py` (new)
- `archimedes-water-play-catalog/data/pricelist_2026-05-29_parsed.csv` (new)
- `archimedes-water-play-catalog/data/source/daosen_pricelist_2026-05-29.xls` (new)
- `CHANGELOG.md`, `VERSION` → 2.36.0

---

## [2.35.0] - 2026-05-29

### Fixed — "We couldn't submit your order" on `catalogs.leka.studio/checkout`

The Submit Order step on every catalog brand returned the generic frontend
error banner. Root cause: the storefront (eukrit/leka-website/catalogs) calls
`sdk.store.cart.complete(cartId, ...)` → `POST /store/carts/:id/complete`,
which on the backend is served by Medusa's stock `completeCartWorkflow`.
That workflow validates the cart has shipping methods + a payment collection
with an authorized session. Leka catalogs are a B2B "send to proposal" flow
with no shipping providers and no payment providers configured — so every
checkout failed cart validation before any order was created.

A separate custom route, `POST /store/proposal-builder/convert-cart`
(introduced in v2.29.0), already did the right thing for this flow, but the
storefront never called it.

#### `medusa-backend/src/api/store/carts/[id]/complete/route.ts` (new)

Overrides Medusa's stock cart-complete route. Pulls the cart, builds a draft
order via `createOrderWorkflow` with `status: "draft"` and
`metadata.proposal_builder: true`, then returns the same response shape the
storefront SDK expects: `{ type: "order", order: { id, display_id, ... } }`.
No storefront change required.

Defensive bits learned from upstream Medusa source:

- `items[].title` is required by `validateLineItemPricesStep`; we fall back
  to `product_title` / `variant_sku` / `"Item"` so a cart whose line items
  carry a null title (rare but possible) still completes.
- `quantity` and `unit_price` are coerced via `Number()` to guard against
  BigNumber serialization edge cases.
- `region_id` and `currency_code` are forwarded as-is; if either is stale
  (e.g. a cart cached before the SGD region went live in v2.33.0) the
  workflow's `findOneOrAnyRegionStep` resolves to "any" region rather than
  throwing.
- Errors are surfaced as `400` with `{ message, type }` so the storefront's
  `err.response.data.message` path shows the real reason (e.g. "variant_xxx
  out of stock") instead of the generic banner.

The existing `proposal-created.ts` subscriber already filters on
`metadata.proposal_builder === true` to post the new draft to
`#leka-medusa-proposal`, so the operator handoff is unchanged.

#### Files changed
- `medusa-backend/src/api/store/carts/[id]/complete/route.ts` (new)
- `VERSION` → 2.35.0

---

## [2.34.0] - 2026-05-25

### Fixed — Zero blank product cards on `catalogs.leka.studio/leka-project`

The "Leka Project" storefront (Medusa SC `sc_01KNKTHC0B7KFEDSZ3NNM49JQW`,
formerly Wisdom) was rendering blank cards for **2,226 of 5,062 products
(44%)**. Diagnosis: those products had `images: []` and `null` thumbnail in
Medusa because the original Wisdom import deliberately left them blank — every
one mapped to a `products_wisdom` Firestore doc that also had empty `images[]`
and `image_verified: False` / `None`. The v2.17.0 image proxy + URL rewrite are
correct; only 1 product had a true 404 URL.

Empirically established (and now permanently checkpointed in Firestore
`image_backfill_verify/`):

- **539** imageless products had a hosted candidate image in
  `gs://ai-agents-go-vendors/leka-project/<code>_*` but all were flagged
  `image_verified: False`. Visual spot-checks confirmed real mismatches
  (e.g. item "Car Wash Splash Center" whose hosted image is actually a felt-
  faces toy).
- **1,687** had no hosted candidate at all.
- Slack `#vendor-wisdom-playground` (`C090A90K2N6`) is a project/quotation
  channel — not an item-code-keyed image library. No automated bulk source.

#### `scripts/backfill_leka_project_images.py` (new)

Four-phase, idempotent, resumable. Mirrors the auth + checkpoint conventions
of `scripts/strip_wisdom_logos.py` and the Medusa-write pattern of
`scripts/rewrite_wisdom_image_urls.py`.

- `--verify`: for each of the 539 candidates, downloads the representative
  image (`catalog/<code>_img0` preferred, else lexicographically first), calls
  `gemini-2.5-flash` at Vertex `location=global` with `{title, image}` and a
  structured JSON schema `{matches: bool, confidence: number, depicted: str}`.
  Accepts only when `matches == True and confidence >= 0.70`. Checkpoints each
  decision in Firestore `image_backfill_verify/{sha1(code)}`. Concurrency 4 to
  respect the global-location quota documented in v2.17.0.
- `--make-placeholder`: renders a 1024×1024 Leka Design System PNG with Pillow
  (cream `#FFF9E6` background, navy `#182557` "Leka Project" wordmark, purple
  `#8003FF` "Image coming soon" subtitle, amber underline accent, navy rounded
  card stroke). Uploads to
  `gs://ai-agents-go-vendors/leka-project/_placeholder/leka-coming-soon.png`
  and keeps a provenance copy at `docs/assets/leka-coming-soon.png`. Proxy URL:
  `https://catalogs.leka.studio/api/i/leka-project/_placeholder/leka-coming-soon.png`.
- `--attach [--dry-run]`: admin auth via Secret Manager `medusa-admin-email` /
  `medusa-admin-password`, then `POST /admin/products/{id}` with the resolved
  `images[]` + `thumbnail`. Verified codes get all bucket objects with that
  leading token attached (catalog/ first, then verified/ + spatial_v2/) and
  `metadata.image_status = "backfilled"`. Everything else gets the placeholder
  URL and `metadata.image_status = "placeholder"`.
- `--audit`: re-walks the Store API for the SC and asserts zero products
  remain with empty images + null thumbnail.

#### Run results (2026-05-25)

- Verify: 539/539 done in ~9 min, **67 accept / 472 reject**. The strict
  reject behavior is intentional — every reject sampled was a genuine
  mismatch (e.g. "Viking Toys Tractor" image showing water-play towers).
- Placeholder: 25,427-byte PNG uploaded; proxy returns `200 image/png`.
- Attach: 2,226/2,226 in 25.8 min (~1.4/s sequential admin POSTs), **67
  backfilled with verified real photos + 2,159 placeholder, 0 errors**. The
  stray `test-swing` test product (1 product whose existing URL was the
  one true 404) also re-pointed to the placeholder.
- Audit: **0 blanks** across all 5,062 products in the SC.

#### Reversibility

`metadata.image_status` flags every touched product (`backfilled` or
`placeholder`), so a future real-image pass can target placeholders without
re-touching backfills. Original Wisdom blobs remain untouched at
`gs://ai-agents-go-vendors/wisdom/`. Firestore `image_backfill_verify/`
preserves every per-code decision (matches, confidence, depicted phrase) for
audit and re-runs.

### Cost

≈ $5 Vertex AI (gemini-2.5-flash, 539 vision calls @ ~$0.01 each). No
incremental Cloud Run / Cloud SQL / GCS storage cost worth measuring (one
25 KB PNG, 0 net new image blobs).

### Files changed

- `scripts/backfill_leka_project_images.py` (new — phases A–D)
- `docs/assets/leka-coming-soon.png` (new — provenance copy)
- `requirements.txt` — pinned `google-genai` (was imported by
  `strip_wisdom_logos.py` but unpinned)
- New GCS object: `gs://ai-agents-go-vendors/leka-project/_placeholder/leka-coming-soon.png`
- New Firestore collection: `image_backfill_verify/` (539 docs)
- `CHANGELOG.md`, `VERSION` → 2.34.0
- `docs/build-summary.html`, `docs/hub.html` regenerated
- `.claude/PROGRESS.md` updated

---

## [2.33.0] - 2026-05-25

### Added — Singapore SGD Medusa region + pricing summary HTML

- **Medusa Singapore SGD region** (`reg_01KSEBH1EAK9RWAYEW87QY8NWS`) created via
  admin API. `sg` (Singapore) removed from Asia-Pacific USD region
  (`reg_01KNKVD0TNN5G0HG3CSTF7JGWN`) and re-assigned to new Singapore region.
  All brands' `retail_sgd` prices (already in Firestore from v2.31.0 backfill)
  synced to Medusa via `sync_brand_prices_to_medusa.py --brand all --write`.
- **`docs/summaries/pricing-config-master.md`** updated to v2.33.0: corrected all
  v2.29.0 → v2.31.0 references, added Rampline airfreight fix details (v2.32.0,
  `FAMILY_DESC_TO_SLUG`, 32/127 SKUs), added Medusa regions section with all 4
  region IDs including new Singapore SGD, updated version history.
- **`docs/summaries/pricing-config-master.html`** (NEW): full visual HTML reference
  of the pricing structure using Leka Design System (Manrope font, navy/purple
  palette). Includes brand cards, pipeline diagram, formula blocks, tier table,
  region cards, and version history table. Served via gateway.

---

## [2.32.0] - 2026-05-24

### Fixed — Rampline weight scraper + airfreight routing for 32/127 SKUs

- `scripts/scrape-rampline.ts`: fixed weight extraction — Rampline publishes specs
  in `<p><br>` blocks, not `<ul><li>`. Now parses both; takes max weight across all
  variant lines per page (conservative airfreight estimate).
  Products with weight data: Rampit 40kg, Rampit TWIN 60kg, Jumpstone 20kg,
  Rampit Storm 50kg, BalanceBuddy 43kg, Fungi 33kg, Playground Loop 160kg.
- `rampline-catalog/import_pricelist.py`: added `FAMILY_DESC_TO_SLUG` table (pricelist
  uses long descriptive family names, not marketing names); `load_dim_index()` now
  keys by handle slug + title slug in addition to WooCommerce SKU; main loop tries
  family-desc lookup when article-SKU lookup misses.
  Result: **32/127 SKUs now use `airfreight_weight` strategy** (was 0), 95 remain on
  `flat_uplift` (Rampball — no published weight, ShockDeck, motor-skill parks).
  Scraped data: `data/scraped/rampline/products.json` (54 products from sitemap).

---

## [2.31.0] - 2026-05-24

### Changed — Pricing formula overhaul: duty fix, TH VAT, independent currencies, CBM routing

#### Task 1 — Pricing config master doc
- Added `docs/summaries/pricing-config-master.md`: complete authoritative reference
  for all FX sources, brand params, tax rules, per-brand formulas, Vinci tier
  floor/cap system with worked examples, shipping-automation integration details,
  and script reference.

#### Task 2 — Fix Wisdom import duty (0%, not 7%)
- `shared/wisdom_pricing.py`: `IMPORT_DUTY_RATE` corrected 0.07 → 0.00. China-origin
  goods qualify under ASEAN-China FTA (Form E); 7% was incorrect.
- `shared/pricing_config.py` schema doc updated: `brands.wisdom.import_duty_rate = 0.0`.
- After this fix, Wisdom retail prices decrease by ~7% (the erroneous duty is removed).
  Re-run `scripts/backfill_sgd_pricing.py --brand wisdom --write` to apply.

#### Task 3 — TH customer VAT: embed 7% into all retail prices
- `shared/landed_pricing.py`: added `TH_CUSTOMER_VAT_RATE = 0.07`. `_resolve_params()`
  now reads `th_customer_vat_rate` from Firestore. `price_row()` applies
  `retail_thb = (landed_thb / (1-gm)) × 1.07`. This is the TH domestic customer VAT
  (distinct from the 7% import VAT already in `landed_thb`).
- `shared/wisdom_pricing.py`: same `TH_CUSTOMER_VAT_RATE` constant and application in
  `compute_wisdom_retail()`.
- `scripts/ingest_designpark_pricelist.py`: applies `th_customer_vat_rate` from config.
- `berliner-catalog/import_pricelist.py`: applies `th_customer_vat_rate`.
- `rampline-catalog/import_pricelist.py`: applies `th_customer_vat_rate`.
- Net effect: all THB retail prices increase by 7% vs pre-VAT. USD and SGD prices are
  unaffected (TH customer VAT is a Thai domestic tax; international prices pre-VAT).

#### Task 4 — Vinci tier floor/cap documented (code unchanged)
- Vinci already routes through `shared.price_row()` → `cost_engine` when CBM available.
- Full tier table and worked examples now documented in pricing-config-master.md.

#### Task 5 — Berliner: CBM routing via shipping-automation
- Berliner already uses `cost_engine` via its own `price_row()` implementation when
  Firestore docs carry dimension data (from prior website scrape). No code change needed.
- `_berliner_params()` now includes `th_customer_vat_rate`.

#### Task 6 — DesignPark: Korea LCL CBM routing
- `scripts/ingest_designpark_pricelist.py`: `price_designpark_row()` now accepts `cbm`
  and `kg` params. When CBM > 0, routes through `cost_engine origin=japan_korea,
  method=lcl` (3,500 THB/CBM). Applies Vinci-style tier clamp. Falls back to
  flat 35% uplift when no CBM data (current pricelist has no dimensions).

#### Task 7 — Wisdom: China LCL CBM routing + tier clamp
- `shared/wisdom_pricing.py`: `compute_wisdom_retail()` now accepts `cbm`, `kg`, `fx`
  params. New `_wisdom_lcl_estimate()` helper calls `cost_engine origin=china,
  method=lcl` (2,800 THB/CBM). When CBM estimate succeeds, applies Vinci-style tier
  clamp. Falls back to flat China CIF ≈ FOB path (duty=0%) when no CBM.
- `compute_wisdom_retail_batch()` now auto-computes CBM from `dimensions` dict if
  present on product docs (packing_factor 0.15).

#### Task 8 — Rampline: airfreight routing when weight available
- `rampline-catalog/import_pricelist.py`: load_dim_index() now also reads `weight_kg`
  from scraped products. Main pricing loop: when weight_kg > 0, calls `cost_engine
  origin=europe, method=air` (120 THB/kg, Profreight Italy→BKK rate, Norway comparable).
  Applies tier clamp. Falls back to LCL tier system when no weight data (current scrape
  has no weight; air routing activates after re-scrape).
- Added `RAMPLINE_SHIPPING_METHOD = "air"` constant and airfreight rate logging.

#### Task 9 — PLP currency selector (THB / USD / SGD)
- `leka-website/catalogs/src/lib/currency.ts` (new): `SupportedCurrency` type,
  `SUPPORTED_CURRENCIES`, `getStoredCurrency()` / `storeCurrency()` (localStorage),
  `pickPrice()` (currency-aware Medusa variant price picker), `formatPrice()`.
- `leka-website/catalogs/src/components/currency-selector.tsx` (new): pill-shaped
  THB/USD/SGD selector matching Leka DS (Manrope, #8003FF, 9999px pill radius, 8px
  button radius, `0px 2px 8px rgba(24,37,87,0.08)` shadow).
- `leka-website/catalogs/src/components/product-card.tsx`: accepts `currency` prop;
  uses `pickPrice()` + `formatPrice()` for currency-aware price display.
- `leka-website/catalogs/src/app/[brand]/catalog-content.tsx`: adds `currency` state
  (hydrated from localStorage after mount to avoid SSR mismatch); shows
  `CurrencySelector` in header when `brand.hasPricing`; passes `currency` to
  every `ProductCard`.

#### Task 10 — Independent retail calculations per currency
- `shared/landed_pricing.py` `price_row()`: `retail_usd` and `retail_sgd` now derived
  from `landed_thb / FX` (not from `retail_thb / FX`) — independent from the TH
  customer VAT applied to `retail_thb`. International prices are pre-TH-VAT.
- `shared/wisdom_pricing.py`: same independent derivation.
- `scripts/ingest_designpark_pricelist.py`: same independent derivation.
- `berliner-catalog/import_pricelist.py`: same independent derivation.
- `rampline-catalog/import_pricelist.py`: same independent derivation.

**Files changed:**
- `shared/landed_pricing.py`
- `shared/wisdom_pricing.py`
- `shared/pricing_config.py` (schema comment update)
- `scripts/ingest_designpark_pricelist.py`
- `berliner-catalog/import_pricelist.py`
- `rampline-catalog/import_pricelist.py`
- `docs/summaries/pricing-config-master.md` (new)
- `leka-website/catalogs/src/lib/currency.ts` (new)
- `leka-website/catalogs/src/components/currency-selector.tsx` (new)
- `leka-website/catalogs/src/components/product-card.tsx`
- `leka-website/catalogs/src/app/[brand]/catalog-content.tsx`

---


---

## [2.30.0] - 2026-05-23

### Changed — Playground Mound Modeler extracted to dedicated repo

The `mound-modeler/` module (developed in a worktree off this repo from
2026-04 to 2026-05-17) has been extracted to its own repo and Cloud Run
service:

- **Repo:** [eukrit/leka-mound](https://github.com/eukrit/leka-mound) (private, branch `main`)
- **Cloud Run service:** `leka-mound` (asia-southeast1, replaces the `/mound/` blueprint mount on `leka-product-catalogs` Cloud Run)
- **Gateway slug:** `leka-mound` (kind=cloud_run, visibility=admin)
- **Legacy slug:** `leka-mound-modeler` deprecated 2026-05-23; still points at the existing `leka-product-catalogs` Cloud Run revision (which carries the historical /mound/ blueprint). Scheduled for removal on 2026-06-23.

### Vinci catalog dependency

The new `leka-mound` service fetches Vinci product data at runtime from
`https://leka-product-catalogs-538978391890.asia-southeast1.run.app/vinciplay/data/products_all.json`.
Bundled snapshot in `leka-mound/data/vinci_products.bundled.json` is the
offline fallback. Refresh cadence: 1h in-memory cache. `/health` surfaces
the current source as `remote` / `bundled` / `remote_stale`.

### Firestore designs

`mound_designs` collection stays in this project's Firestore database
(`leka-product-catalogs`). The new service uses a cross-database client
so existing saved-design URLs (`?id=m-XXXX`) still resolve.

### Note on the running Cloud Run revision

`leka-product-catalogs` Cloud Run revision `00014-mw2` was built from the
worktree (not from main) and includes the mound blueprint at `/mound/`.
A redeploy from `main` would drop the blueprint and break the legacy
`leka-mound-modeler` gateway slug. Plan: redeploy from main only AFTER
2026-06-23 when the legacy slug is removed.

### Pre-history

All mound-modeler development before extraction is preserved in this
repo's git history under the worktree branch
`claude/determined-yalow-d2e28e`. See `eukrit/leka-mound/BUILD_LOG.md`
for v0.2.0 (the extraction).

---

## [2.29.0] - 2026-05-22

### Added — Proposal Builder backend endpoints (sibling to leka-projects #29)

Two new HTTP routes + one subscriber so the `catalogs.leka.studio` storefront's "Send to Proposal" button (sibling PR in `eukrit/leka-website`) can convert a customer cart into a Medusa Draft Order, and so the Python `proposal_engine` adapter in `eukrit/leka-projects` (v1.48.0) can fetch that draft order pre-joined with every expansion it needs.

Plan: `~/.claude/plans/based-on-the-latest-tingly-coral.md` §D.

**New routes:**

- `POST /store/proposal-builder/convert-cart`
  - **Auth:** store-side (publishable API key + optional customer session).
  - **Body:** `{ cart_id, project_id?, project_name?, site_location?, project_details?, metadata? }`.
  - **Flow:** retrieves the cart, runs `createOrderWorkflow` from `@medusajs/medusa/core-flows` with `status: "draft"`, stamps `metadata.proposal_builder: true` on the order + every line item plus the project context. Copies cart shipping/billing address through. Returns `{ draft_order_id, display_id, status, message }`.
  - **What happens to the cart:** left intact on the server (storefront clears its localStorage cart-id on success).
  - **File:** `medusa-backend/src/api/store/proposal-builder/convert-cart/route.ts`.

- `GET /admin/draft-orders/:id/proposal-export`
  - **Auth:** admin (JWT, or a secret admin API key from the Medusa admin UI). The proposal engine authenticates with the secret key via **HTTP Basic** — key as username, empty password (`Authorization: Basic base64("<key>:")`); key lives in GCP Secret Manager as `medusa-admin-api-key-proposal-engine`. (Corrected in 2.50.1 — earlier notes mistakenly said `x-medusa-access-token`, which 401s.)
  - **Returns:** the draft order with every expansion the Python adapter needs (items → variant → product → images, region, addresses) in a single HTTP call, wrapped in a legacy-`cart`-shaped envelope so the adapter doesn't have to dual-handle v1/v2 order shapes.
  - **Why custom:** the BoQ adapter contract is stable in `proposal_engine` (plan §C3); pinning the wire shape here means future BoQ schema changes don't require redeploying Cloud Run.
  - **File:** `medusa-backend/src/api/admin/draft-orders/[id]/proposal-export/route.ts`.

**New subscriber:**

- `src/subscribers/proposal-created.ts` — listens on `order.placed`, filters `metadata.proposal_builder === true`, posts a Slack alert to `#leka-medusa-proposal` via the data-comms Slack Router (Rule 16) with the `draft_order_id`, total, project_id/name/site, and a one-liner instruction to paste the ID into `projects/<id>/config.yaml` and run `python -m proposal_engine render ...`. Best-effort (no-throws) so the cart conversion never fails on notification glitches.

**Verification:**

- `npm run build` → green (backend compiled in 19.85s, admin frontend in 59.31s; no TypeScript errors).
- Manual smoke (post-deploy):
  ```
  curl -X POST https://catalogs.leka.studio/api/store/proposal-builder/convert-cart \
    -H "Content-Type: application/json" \
    -H "x-publishable-api-key: $LEKA_PUBLISHABLE_KEY" \
    -d '{"cart_id":"cart_xxx","project_id":"dulwich-singapore","project_name":"Test"}'
  ```
  Expect `201` with `draft_order_id`.

**Not in this PR (sibling work):**

- `eukrit/leka-projects` v1.48.0 — the Python adapter that consumes `/admin/draft-orders/:id/proposal-export` (PR #29, merged).
- `eukrit/leka-website` — the storefront "Send to Proposal" button that POSTs to `/store/proposal-builder/convert-cart`.
- One-shot: `gcloud secrets create medusa-admin-api-key-proposal-engine --replication-policy=automatic` + paste the admin key issued in Medusa admin UI.
- Variant metadata backfill (`supplier`, `supplier_url`, `dimensions`, `age_range`, `diecut_white_gcs`) on Wisdom / Vinci Play / Weplay products so the proposal engine cards have full data — separate follow-up; until then bare products render with default zone/category + sales retags in admin.

---

## [2.28.0] - 2026-05-22

### Added — SGD retail across 5 brands + recompute onto current config

Implements "local currency per country": Thailand checks out in THB,
Singapore in SGD, everywhere else USD. SGD retail prices were missing on
every brand except Eurotramp; this pass computes them for Wisdom, Vinci,
Berliner, DesignPark, and Rampline straight from each brand's original
pricelist FOB through the canonical landed-cost pipeline (user direction
2026-05-22: "always refer to original pricelist and use pricing calculation
to THB/SGD/USD as target").

#### Tax treatment (already in `pricing_config/canonical`, confirmed)
- **TH** — `th_customer_vat_rate = 0`: retail is VAT-inclusive; the 7% import
  VAT is already inside `landed_thb`. No extra customer-VAT line.
- **SG** — `sg_nubo_gst_registered = false`: SG sale is treated as a
  zero-rated export, so **no GST is added** at catalog price. The formula
  `retail_sgd = retail_pre_tax_thb / (THB/SGD)` flips to add 9% automatically
  once Nubo registers and the flag is set true.

#### Pipeline changes (SGD added to the formula)
- `shared/landed_pricing.py` — `PricedRow.retail_sgd`; `price_row()` computes
  it with the Nubo GST gate. New `SG_CUSTOMER_GST_RATE` / `SG_NUBO_GST_REGISTERED`
  fallbacks; `_resolve_params()` reads the SG keys from Firestore config.
- `shared/wisdom_pricing.py` — `retail_sgd` + `sgd_thb` on `WisdomPricedRow`;
  `get_sgd_thb()` live-FX helper; `pricing_metadata()` emits SGD.
- `scripts/ingest_designpark_pricelist.py` — `price_designpark_row()` emits
  `retail_sgd`.
- `vinci/berliner/rampline import_pricelist.py` — persist `retail_sgd`; Berliner
  derives the EXW cost basis from `list_eur × (1 - exw_discount)` (config-driven).

#### Recompute = adds SGD AND corrects stale config drift
Recomputing from FOB at the current config also fixed prices that predated
config changes and were never backfilled:
- **Vinci -7.8%** — stored prices used 40% GM; config moved to 35% on 2026-05-14.
- **Berliner +0.4%→+17.3%** — stored prices predated the 2026-05-14 7% Thai
  VAT layer (small items floored either way; large items show the added VAT).
- DesignPark/Rampline ~0% drift; Wisdom had no retail at all (FOB-only).

Trade terms re-verified against the `vendors` DB before writing: Berliner
`eur_fob` = `list_eur × 0.85` (EXW -15%, no double discount); Vinci/DesignPark/
Wisdom are discount-free FOB; Vinci `eur_fob_2026` == `eur_fob`; Wisdom
`fob_usd` covers all priceable docs.

#### `scripts/backfill_sgd_pricing.py` (new)
Recomputes the landed→retail cascade per brand from the original-pricelist FOB
captured on each Firestore doc and writes `pricing.retail_{thb,usd,eur,sgd}`
back to `vendors/{slug}/products` (Rampline → its `pricelists/<date>` audit
doc). Dry-run by default; dumps a pre-write backup CSV per brand
(`scripts/backfill_backups/`, gitignored) and stamps `fx_snapshot`,
`fx_source`, `retail_basis`, `calculated_at` for audit. **Written:** Vinci
1,234 · Berliner 728 · DesignPark 178 · Wisdom 4,809 · Rampline 127 (audit).

#### `scripts/sync_brand_prices_to_medusa.py` (new)
Update-only multi-currency price push. Indexes ALL Medusa products by variant
sku / `metadata.legacy_sku` / handle and matches vendor docs by
item_code → handle → doc-id, so it **never creates products** — avoiding the
duplicate hazard of the handle-based `sync_vendors_to_medusa.py` (Berliner uses
descriptive handles with item-code SKUs; Wisdom is rebranded "Leka Project"
with `LP-` SKUs + `legacy_sku`). Match rates: Vinci 1,234/1,234, Berliner
728/728, DesignPark 178/178, Wisdom 4,800/4,809 (9 `CQ14-QL-*(n)` sub-variants
absent in Medusa).

#### Deferred (not in this pass)
- **SGD region NOT created** — per user, hold the `sg` region switch until the
  whole ~9k catalog has SGD; SG keeps checking out in USD until then. No
  storefront change needed (checkout currency follows `cart.region`).
- **Rampline → Medusa** stays deferred (per-variant migration not done); SGD is
  in the audit doc only.
- **4soft / Weplay / Vortex** have no usable FOB/retail source in the vendors DB
  and were out of scope.

---

## [2.27.0] - 2026-05-21

### Added — B2B project context in order-placed notifications

The `order.placed` subscriber (`medusa-backend/src/subscribers/order-placed.ts`)
now reads the B2B project fields the storefront sets on the cart/order metadata
(`project_name`, `project_details`, `site_location`) and surfaces them in both
the Slack alert (#leka-medusa-order) and the confirmation email:

- **Slack:** adds a Project / Site-location fields block and a Project-details
  section when present (rendered between the customer block and the items list).
- **Email:** adds a cream-highlighted project block above the line-item table.

Both are conditional — orders without project metadata are unchanged. Pairs with
leka-website catalogs v0.17.0 (Submit Order flow).

---

## [2.26.0] - 2026-05-18

### Added — Weplay quotation AQ1251030077 USD pricing sync

Ingested the 2025-11-05 Weplay quotation (`AQ1251030077`, dated
Oct. 30, 2025, FOB Taiwan, USD) into `vendors/weplay/products/*`.

#### `scripts/ingest_weplay_quotation_aq1251030077.py` (new)
Parses the 7-page text-layer PDF with `pdfplumber`, line regex on
`SKU DESCRIPTION PRICE / UNIT PACK CBM GW`. Uses the same
`SKU_TOKEN_RE = ([A-Z]{2}[0-9]{4,})` (no word boundaries) as
`scripts/ingest_weplay_local_catalogs.py` so it matches tokens inside
larger item codes (e.g. `KM1003` inside `6800KM1003`).

Source-priority gating preserved: name/description only written when
the target doc has zero provenance (`source_url_en/cached/flipbook/
pdf_ocr/local`) AND is in a draft state. Otherwise the write is
audit-only — never clobbers richer sources.

Always-written fields (merge=True):
  - `pricing.quote_2025_usd`              — FOB Taiwan price
  - `pricing.quote_aq1251030077_at`       — `"2025-10-30"`
  - `pricing.quote_aq1251030077_unit`     — `PC | SET | PAC | DZN`
  - `quotation_refs`                      — `ArrayUnion(["AQ1251030077"])`

#### Run results
  - 167 quotation rows parsed
  - 151 unique SKU tokens
  - 189 Firestore docs matched (some tokens have variant docs)
  - 0 no-doc-match
  - 189 audit-only writes (all matched docs already had names from
    richer scrape sources — `name`/`description`/`source_url_local`
    correctly skipped per the priority gate)

#### Audit-only by design
USD `quote_*` fields are kept separate from any landed-cost or retail
`retail_*` keys consumed by `sync_vendors_to_medusa.py`, so no Medusa
re-sync is required from this commit.

---

## [2.25.0] - 2026-05-17

### Removed — 38 duplicate Weplay products (Medusa 200 → 162)

Inspection of the live Medusa Weplay SC surfaced **34 SKU tokens with
>1 doc**, producing **62 active duplicate products** on
`catalogs.leka.studio/weplay`. Each was a separate scrape-pass artifact
showing the same product as multiple cards:

  - `KM2802`: 11 docs all named "Soft Gym (7 pcs)"
  - `KC0002`: 4 docs all named "Brick Me" (6800KC0002.1-090, KC0002,
    KC0002.1, WE-KC0002)
  - `KC2003`: 3 "Fun with Curves" (kc2003, kc2003-00b, we-kc2003)
  - `KP1001`: 3 "Seesaw (A)"
  - `KM1003`: 2 "Pile Balance Up" (6800km1003, km1003)
  - `KM2016`: 2 "Over The Mountain"
  - `KT0017`: 2 "Squishy Tactile Shell"
  - `KC0004`: 2 "Q-blocks (64 pcs)"
  - And 18 more groups

#### `scripts/merge_weplay_duplicates.py` (new)
Groups docs by `(sku_token, normalized_name)`. Within each group picks
a canonical doc using priority `active+images > active > has_images >
shortest doc_id`. For non-canonical docs:
  - Sets `status = "merged_duplicate"`
  - Sets `merged_into = <canonical_doc_id>`
  - Sets `merged_canonical_sku` for audit
  - DELETEs the corresponding Medusa product (if found by handle)

Run: 26 dedup groups identified, **40 Firestore docs marked merged**,
**38 Medusa products deleted** (2 didn't have matching handles —
likely never synced). **Medusa Weplay catalog: 200 → 162 products.**

Idempotent. Doesn't touch tokens where docs have DIFFERENT names
(those are likely real variants or AI-misinferred SKUs needing
human review — see HTML report).

#### `scripts/generate_weplay_review_html.py` (new)
Static HTML page at `docs/weplay-review.html` (95KB) for the user
to review:

1. **AI-inferred drafts tab** — all 103 docs stamped by v2.15.1's
   `stamp_weplay_ai_inferred.py`. Grouped by category (balance,
   construction, motor-skill, sensory, etc.), each card shows
   SKU + doc_id + name + description + AI notes (the Anthropic
   Vision pipeline's audit trail like "Product identified as
   Weplay X based on visual appearance").

2. **Variant groups tab** — every SKU token that still has >1 doc
   after the dedup pass (mostly mixed-name groups that need
   human eye). Each group shows all docs side-by-side with status
   badge + thumbnail.

Searchable + tabbed. Two-color borders distinguish AI-inferred
(purple) from variant-group cards (red).

Served at `https://gateway.goco.bz/leka-product-catalogs/weplay-review.html`
(after deploy) and from local docs/ folder. Hub regenerated.

### Composite catalog state
- **`catalogs.leka.studio/weplay`: 162 product cards** (was 200 with
  dupes, now de-duped)
- 103 AI-inferred drafts still draft, now visible in HTML review for
  human decisions
- 8 multi-doc variant groups remaining (mixed names — need review,
  visible in HTML)

### Files changed
- `scripts/merge_weplay_duplicates.py` (new)
- `scripts/generate_weplay_review_html.py` (new)
- `docs/weplay-review.html` (new)
- `docs/hub.html` (regenerated)
- `CHANGELOG.md`

---

## [2.24.0] - 2026-05-17

### Changed — TH retail = VAT-inclusive by default + Vinci → Vinci Play rename

Per user direction:
- `global.th_customer_vat_rate` default `0.07` → **`0.0`**. Retail price
  is always quoted VAT-inclusive in Thailand; the 7% Thai import VAT is
  already folded into `landed_thb` so no additional customer-VAT line
  is needed. With this change, `retail_th_thb == retail_pre_tax_thb`.
- `brands.vinci.source_pricelist_url` changed to the renamed
  Google Drive folder
  `https://drive.google.com/drive/folders/1ZiRZknbz0XlE9RMIbDwe9MC1oXegMyfl`
  (label: "Vinci Play master folder (Google Drive)"). Old local
  Windows path was browser-broken; this URL opens cleanly.

### Synced in this commit
- `src/main.py` `_empty_config()` matches the live Firestore state.
- `scripts/seed_pricing_config.py` extended to seed all v2.21.0
  schema additions (TH/SG tax fields + per-brand source URLs) so
  `--force` re-seed no longer regresses them.
- Live Firestore was patched directly via the deployed
  `POST /api/pricing-config` (audit footer now shows
  `eukrit@gmail.com (via claude)` at 2026-05-17T08:50:05Z).

### Companion — `vendors` repo
Drive folder rename `My Drive/Partners Playground/Vinci/Vinci Play Prices`
→ `My Drive/Partners Playground/Vinci Play/Vinci Play Prices`. Three
scripts in `vendors/vinci-play-catalog/scripts/` hardcoded the old path
and were updated in the same change-set:
`import_pricelist.py`, `enrich_schema.py`, `run_enrichment_pipeline.py`.
Cloud Build job `vinci-pricelist-enrich` is unaffected — it resolves
the Drive folder by ID via the `vinci-play-pricelist-folder-id` Secret
Manager secret (folder ID didn't change, only the display name).

> *Note: bumped from the originally-prepared v2.21.1 to v2.24.0 to stay
> above the v2.22.x / v2.23.x rebrand work that landed on `main` in
> parallel.*

## [2.23.9] - 2026-05-16

### Added — 5 themed collections for Leka Project (auto-generated)

Wisdom never had a "series" concept (unlike Vinci or Berliner), so the
storefront's collection filter was disabled for Leka Project. This adds
5 curated themed collections by mapping each product's top-level
category to the first matching collection from a priority list.

Created collections (handle prefix `leka-project-`):
- `leka-project-furniture-collection`     — 1,261 products (from `furniture`)
- `leka-project-outdoor-and-nature-play`  — 618 products  (from `outdoor`, `nature_play`, `water_play`)
- `leka-project-active-play`              — 1,278 products (from `playground`, `balance`, `climbing`, `sports`)
- `leka-project-early-years-collection`   — 83 products   (from `early_years`)
- `leka-project-creative-and-loose-parts` — 130 products  (from `creative`, `loose_parts`)

**3,370 of 5,062 products (67%) assigned**, 0 errors, elapsed 20m 25s.
The remaining 1,692 products in the catch-all `other` category stay
uncollected — discoverable via category and search only. Future curation
can claim them.

Medusa v2 only supports one collection per product (`collection_id`
is singular), so priority order matters: Furniture first (most specific),
then Outdoor & Nature, Active Play, Early Years, Creative & Loose Parts.

### Storefront coordination
- Pairs with leka-website v0.10.0 which flips
  `BRANDS["leka-project"].hasCollections: true` and sets
  `collectionPrefix: "leka-project-"` so the existing filter UI picks
  them up without any rendering changes.

### Added
- `scripts/create_leka_project_collections.py` — idempotent; `--revert`
  clears `collection_id` on every Leka Project product (does not delete
  the empty collections).

### Files changed
- `scripts/create_leka_project_collections.py` (new)
- `CHANGELOG.md`, `VERSION`

---

## [2.23.8] - 2026-05-16

### Changed — Renamed 80 `wisdom-*` Medusa product categories to `leka-project-*`

Final cleanup for the Wisdom → Leka Project rebrand (v2.17.0). Product
categories were left behind in that pass: 80 subcategory handles like
`wisdom-furniture-cabinet`, `wisdom-balance-house`, etc. continued to
surface in storefront URLs as `?subcategory=wisdom-...`, leaking the
upstream supplier identity. The category *names* ("Furniture", "Climbing",
etc.) were already clean — only the handles needed updating.

- 80 / 80 categories renamed via Medusa Admin API in 26 seconds.
- Old handle preserved in `metadata.legacy_handle` for revert.
- Verified live: Store API returns 0 `wisdom-*` handles to the Leka Project
  publishable key, 76 `leka-project-*` subcategories present and visible
  on `catalogs.leka.studio/leka-project`.

### Added
- `scripts/rename_wisdom_categories.py` — idempotent rename + `--revert`.

### Files changed
- `scripts/rename_wisdom_categories.py` (new)
- `CHANGELOG.md`, `VERSION`

---

## [2.23.7] - 2026-05-16

### Added — Wisdom / Leka Project Medusa price refresh tooling

New bulk updater that pushes the canonical FOB → CIF → duty + VAT → landed
→ retail formula (already in `shared/wisdom_pricing.py`) to Firestore
`products_wisdom` documents AND the corresponding Medusa variants in the
Leka Project sales channel.

Key wrinkle this handles: products were rebranded from Wisdom to Leka
Project in May 2026, so Medusa SKUs are now `LP-XXXXXXXX` while Wisdom
item codes survive in `variants[].metadata.legacy_sku`. The updater
indexes the sales channel once by `legacy_sku` and then matches each
Firestore row in O(1).

### Files

- `shared/medusa_importer.py` — added 4 methods:
  - `get_product_with_variants(handle)` — fetch product including variants
  - `get_variant_by_sku(sku)` — current-SKU lookup with legacy handle fallback
  - `build_legacy_sku_index(sales_channel_id)` — O(N) page through SC,
    O(1) lookup keyed by `metadata.legacy_sku`
  - `update_variant_prices(product_id, variant_id, prices)` — replace
    variant price list (e.g. set THB retail alongside USD FOB)
- `wisdom-catalog/update_pricing.py` **(new)** — Firestore + Medusa bulk
  updater. Supports `--dry-run`, `--skip-medusa`, `--usd-thb` overrides.
  Writes `pricing.{landed_thb,retail_thb,retail_usd,duty_thb,vat_thb,
  usd_thb,import_duty_rate,thai_vat_rate,gross_margin,price_date}` to
  Firestore and `{usd: FOB, thb: retail}` prices to each Leka Project
  variant.

### Usage

```powershell
python wisdom-catalog/update_pricing.py --dry-run                  # preview
python wisdom-catalog/update_pricing.py --usd-thb 35.20            # live
python wisdom-catalog/update_pricing.py --skip-medusa              # FS only
```

Effective multiplier on FOB-USD at USD/THB 35.0: `35 × 1.07 × 1.07 × 2.0 ≈ 80.14` THB/USD.

---

## [2.23.6] - 2026-05-16

### Improved — DesignPark follow-ups (image coverage, Modern Igloo, Slack)

Tightens the v2.20.0 / v2.23.5 DesignPark pipeline along the three open
follow-ups. Net live result: **87 active products** (up from 15, +480 %)
and **87 / 191 published in Medusa** (up from 15).

#### 1. Asset matcher overhaul (`scripts/ingest_designpark_assets.py`)

The original SKU regex covered only 6 prefixes (`SDM|PTC|PTM|DPM|DPF|DPS`)
which missed the majority of pricelist SKUs. New strategy:

- **Generic regex** widened to all pricelist prefixes:
  `SDM, PTC, PTM, SM, BOA, BTA, BKA, BGA, UTM, DPM, DPF, DPS, DP`.
- **Known-SKU substring matcher** (`find_sku_in_text`) — `load_product_index()`
  now exports a longest-first SKU list; `match_product()` searches filenames
  (and Slack message context) against the live set, tolerant of
  spaces/dashes/underscores between SKU segments. This is what unlocks
  `SM12 - 04B - Upright Cycle EMERALD GREEN.jpg` and
  `BTA12-06 금광.jpg` matches that the regex alone couldn't reach.
- **Theme alias table** (`THEME_ALIASES`) — manual map from the 2024 CAD
  bundle theme slugs (`twin-tower`, `hunter-s-hut`, …) to the 2023 manifest
  product slugs (`twin-star`, `hut-in-the-forest`, …). Plus a 2-token
  Jaccard-style fallback for partial overlap.
- **Result**: 109 matched → **288 matched** (+179 joins, +165 %).

#### 2. Modern Igloo sheet handling (`scripts/ingest_designpark_pricelist.py`)

The 12th pricelist sheet uses a 4-column layout (No / Category /
Description / Unit Price) with no MODEL NO column, which the original
parser skipped. New fallback path: synthesize
`item_code = "DP-<SHEET-SLUG>-<DESC-SLUG>"` and filter out the
trailing 1)/2)/3) footer rows. **Result**: +1 product.

#### 3. Slack ingest live (`scripts/ingest_designpark_slack.py`)

Replaces the v2.20.0 manifest-driven scaffold with a direct Slack API
client that pages `files.list?channel=C0AESCDCZRQ` and fetches
`conversations.history` for per-file message context. Auth via
`slack-bot-token` from Secret Manager. Channel state (2026-02-13 →
2026-05-16): 3 files, all PDFs, all brochures (no per-product photos
yet). Run yield: 3 PDFs uploaded to GCS, attached to
`vendors/designpark.brochures[]` (vendor-level — multi-product catalogs).

#### 4. Status promotion (`scripts/promote_designpark_published.py`)

`sync_vendors_to_medusa.py::_build_update_payload` intentionally omits
`status` so manual Medusa Admin curation isn't overwritten on every sync.
This new idempotent helper closes the loop: for every product with
`status="active"` in Firestore that's still `draft` in Medusa, POST
`{status: "published"}`. This run: **72 promoted** + 15 already published
= **87 published** total.

#### Files

- modified: `scripts/ingest_designpark_assets.py`
- modified: `scripts/ingest_designpark_pricelist.py`
- added: `scripts/ingest_designpark_slack.py`
- added: `scripts/promote_designpark_published.py`
- modified: `VERSION` → `2.23.6`

#### Live final state (verified via Medusa Admin API)

- Total in `Design Park` SC: **191** products.
- Status: **87 published**, **104 draft**.
- 178 priced (USD + THB + EUR); 13 themes / no-FOB rows carry no `retail_*`.
- GCS blobs: 518 (no new uploads this run — re-ingest path is fully idempotent).
- Slack brochures attached at vendor level: 3.

#### Remaining gaps (smaller than before)

1. **230 unmatched assets** (down from 411) — mostly Korean-language
   drawings and loose CAD. Would need OCR-on-DWG or a manual mapping pass.
2. **104 draft products** — components/themes without imagery. When the
   partner sends more photos (Slack drop or Drive update), re-running B2 +
   E1 + sync + this version's promote helper picks them up automatically.

---

## [2.23.5] - 2026-05-16

### Deployed — DesignPark v2.20.0 apply run (9th brand live in Medusa)

Executed the v2.20.0 scaffolding against live Firestore + GCS + Medusa.

#### Live state

- **Medusa Sales Channel:** `Design Park` → `sc_01KRRK0N4ET8QZHX6QB3KZ84YD`.
  Registered in `scripts/sync_vendors_to_medusa.py::BRAND_SALES_CHANNELS`.
- **Firestore `vendors/designpark` root doc:** written with `origin_route=japan_korea`,
  `currency_native=USD`, `fob_port="Busan, South Korea"`, `duty_rate_thai=0.10`.
- **Firestore `vendors/designpark/products`:** **190 docs** (211 pricelist rows
  collapsed to 190 unique handles; duplicate `MODEL NO` entries across sheets
  resolved by last-write-wins on merge). 178 priced via the USD-FOB →
  THB-landed → retail-USD/THB/EUR formula (formula_version `designpark-v1-2026-05-15`);
  12 themes carry `status=draft_no_images` and no `pricing.retail_*` (quoted
  per project, not catalog-priced).
- **GCS `gs://ai-agents-go-vendors/designpark/media/`:** **518 blobs uploaded**
  (PE images + DWG drawings). UBLA + PAP. Served via storefront proxy at
  `https://catalogs.leka.studio/api/i/designpark/media/<sha>.<ext>`.
- **Firestore `vendors/designpark/attachments/`:** 518 attachment docs.
- **Image-to-product joins:** **109 matches** (15 products with ≥1 image now
  `status=active`, 175 remain `draft_no_images`). Coverage is intentionally
  low for v1 — see Follow-ups #1.
- **Descriptions:** **97 backfills** from 4 catalog PDFs (2024-05-30 ENG,
  2023-09-14 ENG 2022, D.PARK_Catalog_EN, DesignPark-Catalogue). 100
  text-extractable pages processed, 41 image-only pages skipped.
- **Medusa Admin verified:** `GET /admin/products?sales_channel_id[]=sc_01KRRK0N4ET8QZHX6QB3KZ84YD&limit=5`
  returned `count=190` with multi-currency prices on every variant.

#### Sample verification (live data, FX 2026-05-16 USD=33.29, EUR=38.70 THB)

| Handle | FOB USD | Retail USD | Retail THB | Retail EUR |
|---|---:|---:|---:|---:|
| `designpark-3p090-40b0300a-00` | $455 | $1,112.27 | ฿37,028.31 | €956.71 |
| `designpark-3p090-40b0600a-00` | $650 | $1,588.95 | ฿52,897.57 | €1,366.73 |
| `designpark-5p090-58a30a00-00` | $100 | $244.45 | ฿8,138.09 | €210.27 |

#### Run order executed

```
py scripts/bootstrap_designpark.py --apply
py scripts/ingest_designpark_pricelist.py --apply --dump-csv=docs/designpark-pricelist-2026-05-16.csv
py scripts/ingest_designpark_assets.py --apply       # 518 uploads, 109 matched
py scripts/ingest_designpark_catalog_pdfs.py --apply # 97 description writes
py scripts/shape_designpark_to_medusa_schema.py --apply
py scripts/sync_vendors_to_medusa.py --brand=designpark   # 190 created, 0 errors
```

Total wall-clock: ~5 min (asset upload dominates).

#### Files

- modified: `scripts/sync_vendors_to_medusa.py` — `BRAND_SALES_CHANNELS["designpark"] = "sc_01KRRK0N4ET8QZHX6QB3KZ84YD"`
- added (audit): `docs/designpark-pricelist-2026-05-16.csv` (211-row pricelist audit dump)
- modified: `VERSION` → `2.23.5`

#### Follow-ups (not in this entry)

1. **Image-join coverage (109/518 matched).** Most unmatched assets are DWG
   drawings whose filenames carry no SKU token (CAD bundle uses
   `<N>_<theme>.dwg` naming, theme zips use line names). Two fixes:
   (a) tighten the SKU regex to also accept the pricelist's own SKU shapes
   (`5W092-…`, `5P091-…`, `3P090-…`); (b) reconcile the 2024 CAD-bundle
   theme list with the 2023 theme manifest (different theme names —
   e.g. CAD says `Twin Tower`, manifest says `Twin star`).
2. **Modern Igloo sheet.** 12th pricelist sheet uses a non-standard header
   and was skipped (11 rows lost). Easy patch.
3. **Slack `#vendor-design-park` ingest.** Phase C was deferred at v2.20.0;
   not in this deploy entry.
4. **Status promotion.** 175 products remain `draft_no_images`. They sync
   to Medusa as `draft` (correct). After image-join coverage improves, run
   `shape_designpark_to_medusa_schema.py --apply` again and re-sync — they
   will be promoted to `active` → `published`.

## [2.23.4] - 2026-05-16

### Added — Rampline specifications enrichment

New `rampline-catalog/enrich_specifications.py` reads
`vendors/rampline-catalog/parsed/products.json` and pushes
storefront-useful product specs to Medusa via product metadata. Winner-
takes-all per product on a richness score (presence of raw dimensions,
certifications, downloads, notes; tiebreak on description length).

### Fields written to `metadata`

- `installed_dimensions` — `{raw, length, width, height, unit}`. **NOT
  packing CBM** — rampline.com only publishes installed footprint (e.g.
  "Approx. 8 x 10 m", "Area: 46 m²"). Sufficient for storefront product
  pages.
- `installed_area_raw` — captured separately when the raw line says
  "Area: NN m²" (Trip, Twist, Dynamic, Grip, Speed).
- `certifications` — joined string of EN-standard certs (e.g. "EN 1176").
- `downloads_json` — JSON-encoded list of `{type, url, filename}` for
  Rampline-supplied DWG/PDF reference docs. Many point at public Drive
  folders Rampline themselves host.
- `downloads_count` — convenience count for storefront badges.
- `crawl_notes` — free-text "notes" field from the crawl (often the
  equipment-list "Area: NN m². Equipment: …" lines from PDPs).

### Run results (2026-05-16)

| Stage | Counts |
|---|---|
| Dry-run | 28 ENRICH_SPECS planned · 0 skipped |
| Apply | **28 ENRICH_SPECS applied · 0 errors** |

| Field | Products updated |
|---|---|
| `installed_dimensions` | 18 |
| `installed_area_raw` | 5 (Trip, Twist, Dynamic, Grip, Speed) |
| `certifications` | 7 |
| `downloads_json` + count | 14 |
| `crawl_notes` | 26 |

### Why this is NOT landed-cost CBM

The plan's item B asked for landed-cost refinement using crawled tech-
sheet PDFs (replace the 35 % flat uplift). Investigation: the crawled
`docs/` bucket contains 6 CAD `.zip` files + 1 installation manual — no
dimensional packing data. The 2025 NOK pricelist PDF in the Drive folder
contains diameters and installed heights, but no packing CBM. The
crawled `products.json` specifications.dimensions field stores installed
footprint, not box size. **Real CBM still requires supplier-supplied
packing lists from Rampline.** See `MANUAL_TASKS.md` for what to ask for.

## [2.23.3] - 2026-05-16

### Added — Rampline brand-CI enrichment → Sales Channel metadata

New `rampline-catalog/enrich_brand_ci.py` reads
`vendors/rampline-catalog/parsed/brand_ci.json` (palette + logos extracted
by step3) and writes a canonical `brand_ci` token block to the Rampline
Sales Channel (`sc_01KNQAA448RY0YPR51FNPM2TVA`) metadata in Medusa. The
storefront can now render Rampline-branded product pages using these
tokens instead of the generic Leka theme.

### Tokens written (live on Medusa, 2026-05-16)

| Token | Value |
|---|---|
| `primary_color` | `#B5BC00` (Rampline green) |
| `secondary_color` | `#2D5346` |
| `accent_color` | `#0073AA` |
| `text_color` | `#313131` |
| `background_color` | `#E6E6E6` |
| `surface_color` | `#EEEEEE` |
| `neutral_color` | `#DDDDDD` |
| `primary_logo_url` | `https://catalogs.leka.studio/api/i/rampline/design-system/logos/<sha>.svg` |
| `fonts` | `[]` (typography extraction was a Playwright miss; static CSS only had font-family rules that didn't parse cleanly — to be revisited if/when step3 re-renders with the fixed Playwright timeout) |
| `source` | `vendors/rampline/brand_ci/latest` |

Idempotent: re-runs are no-ops when tokens are unchanged.

## [2.23.2] - 2026-05-16

### Added — Playwright fallback for Rampline image enrichment

Follows v2.23.1. The static crawl missed product photos on 11 PDPs
because rampline.com lazy-loads its 360 viewer / gallery images via JS,
and those URLs (`rampline.com/wp-content/uploads/360-uploads/...`) never
appeared in the static HTML. The carousel-only candidates were correctly
filtered out as sibling products, leaving those 11 with 0 images.

New `rampline-catalog/enrich_images_playwright.py`:
- Opens each target product page in headless Chromium
  (`wait_until="domcontentloaded"` + best-effort `networkidle` 20 s) and
  scrolls 4× to trigger lazy-load.
- Reads `document.querySelectorAll('img')` → `src` + `currentSrc` +
  `srcset` after JS hydration.
- Whitelist: `rampline.imgix.net` + `rampline.com/wp-content/uploads/`.
  Same name-token filter as v2.23.1 keeps sibling-carousel images out.
- PATCHes Medusa product with new images + thumbnail (when missing).

### Run results (2026-05-16)

| Stage | Counts |
|---|---|
| Dry-run | 11 ADD_IMAGES, 1 image each |
| Apply | **11 ADD_IMAGES applied · 11 thumbnails set · 0 errors** |

Products enriched (all picked up the rampline.com 360-viewer reference image):
`rampline-take-5`, `rampline-monkey-business`, `rampline-junior-power-ii`,
`rampline-junior-power`, `rampline-jane-jump`, `rampline-hunting-high-and-low`,
`rampline-fearless`, `rampline-fast-and-curious`, `rampline-crouching-tiger`,
`rampline-cliffhanger`, `rampline-classic-jump`.

Combined post-v2.23 totals: 28 Rampline products now have crawl-derived
images on Medusa (3 from v2.23.1 static crawl + 11 from v2.23.2 Playwright +
14 already had images from earlier work). The remaining 34 Medusa-only
products (Rampit, BalanceBuddy, Jumpstone, …) have no rampline.com
counterpart so they still need manual or pricelist-supplied artwork.

## [2.23.1] - 2026-05-16

### Added — Rampline image enrichment from website crawl

Follows v2.23.0 metadata enrichment. New `rampline-catalog/enrich_images.py`
reads `vendors/rampline-catalog/source-files/_manifest.json` + per-page
HTML, parses each Medusa product's source_url page for `<img>` tags, and
attaches new photos to Medusa.

### Image resolution paths

1. **Crawled (preferred):** image is in `vendors/rampline` manifest → use
   GCS proxy URL `https://catalogs.leka.studio/api/i/rampline/media/<sha>.<ext>`
   (served by `leka-website/catalogs/src/app/api/i/[...path]/route.ts` from
   the private `ai-agents-go-vendors` bucket).
2. **External whitelist (fallback):** image is on `rampline.imgix.net` →
   link directly. The crawler skipped imgix because it's off-host; the
   imgix CDN is publicly cached and stable, so direct linking is fine.

### Carousel filter (key correctness fix)

Initial dry-run pulled sibling-product photos from rampline.com's "you
might also like" carousel onto wrong products (e.g. `rampline-take-5`
getting PulseZone + FastandCurious shots). Filter now requires each
candidate image's filename to share at least one token with the Medusa
product handle (or its dehyphenated variant for CamelCase imgix names).
Result: 28 → 3 ADD_IMAGES, all genuinely matching.

### Run results (2026-05-16)

| Stage | Counts |
|---|---|
| Dry-run | 3 ADD_IMAGES · 25 IMAGES_UPTODATE · 0 skipped |
| Apply | **3 ADD_IMAGES applied · 0 errors** · 17 new images total |

| Product | Existing → New |
|---|---|
| `rampline-floating-bench` | 6 → 14 (+8 imgix product photos) |
| `rampline-shockdeck` | 18 → 26 (+8 imgix product photos) |
| `rampline-trip` | 1 → 2 (+1 Trip_Produktbilde) |

The other 25 products with crawl metadata are `IMAGES_UPTODATE`: either
they already have images from earlier work, OR the carousel filter
screened out all candidates (their PDPs only showed sibling-park photos,
not their own). To enrich those further we'd need either (a) a Playwright
re-render of step3 to capture lazy-loaded photos, or (b) a more aggressive
image-mining pass over the rampline.com sitemap.

Idempotent: images are added by union (never replaces). Re-runs are
no-ops.

## [2.23.0] - 2026-05-16

### Added — Rampline enrichment bridge: `vendors/rampline/*` → Medusa

Per the 2026-05-16 architecture statement ("`leka-product-catalogs` is
canonical; `vendors/*` mirrors external sources and ENRICHES the canonical
layer"), this commit wires the rampline.com website crawl output into the
Medusa product catalog.

### What shipped

- `rampline-catalog/enrich_from_vendors.py` (NEW, 360 lines) — reads
  `vendors/rampline-catalog/parsed/products.json` (91 crawled products
  from rampline.com), matches each to a Medusa product on the Rampline
  sales channel by URL/title slug similarity (winner-takes-all per Medusa
  product), and upserts:
    - `metadata.source_url` — canonical rampline.com PDP URL
    - `metadata.crawled_at` — first-write timestamp
    - `metadata.crawl_sha` — SHA-256 of the source HTML
    - `metadata.crawl_category`, `metadata.crawl_subcategory`
    - `metadata.crawl_variant_skus` — comma-joined sibling SKUs from the
      same PDP (preserves the surface-variant breakdown for traceability)
  Description is preserved if Medusa's existing value is ≥80 chars (the
  rich descriptions migrated from earlier work stay intact); only short
  pricelist-title stubs would be overwritten.
- Three run modes: `--report-only` (reconciliation CSV), `--dry-run`,
  `--apply`. Audit logs land in `rampline-catalog/data/build_runs/` with
  the same shape as `build_variants.py` + `sync_variant_prices.py`.

### Run results (2026-05-16)

| Stage | File | Counts |
|---|---|---|
| Reconciliation | `reconciliation_2026-05-16T11-28-24Z.csv` | 125 rows: 90 matched · 1 crawl-only (`slakklinesystem`, no URL) · 34 medusa-only |
| Dry-run | `enrichment_dryrun_2026-05-16T11-30-39Z.json` | 28 ENRICH planned (winner-takes-all collapses 90 → 28 unique Medusa products) |
| Apply | `enrichment_applied_2026-05-16T11-31-42Z.json` | **28 ENRICH applied · 0 errors** |

The 34 medusa-only entries are genuinely absent from the crawl: products
like Rampit, BalanceBuddy, Jumpstone, Fungi are referenced inside other
PDPs on rampline.com but do not have their own standalone PDP pages, so
the crawl could not extract them as discrete products. Not a matcher
defect.

### Spot-check (live Medusa, post-apply)

- `rampline-shockdeck` ← `shock-absorber`: `source_url` ✓, `crawl_sha` ✓,
  `crawl_variant_skus` lists 3 sibling components.
- `rampline-trip` ← `trip-for-shockdeck`: `source_url` https://rampline.com/en/product/trip/,
  `crawl_variant_skus` covers 3 surface variants.
- `rampline-classic-jump` ← `24536`: `crawl_variant_skus` lists 3 article codes.

### Out of scope (deferred to future versions)

- Image enrichment: the crawl captured 239 media artifacts under
  `gs://ai-agents-go-vendors/rampline/media/`. v2.22.3 just landed the
  image-sync fix in `sync_vendors_to_medusa.py`. Wiring crawl media →
  Medusa images is the natural follow-up.
- Brand-CI enrichment (`vendors/rampline/brand_ci/latest` → Medusa
  collection metadata or storefront theme tokens).
- Landed-cost refinement using crawled tech-sheet PDFs for per-SKU CBM.

## [2.22.3] - 2026-05-16

### Fixed — `sync_vendors_to_medusa.py` UPDATE path now syncs images

Bug found while verifying the Eurotramp v1.11.2 image enrichment landed
in Medusa. After uploading 404 product images to GCS and writing
`images[]` to 105 Firestore docs, the storefront still showed the 📦
placeholder for those products. Root cause: `_build_update_payload()`
only emitted `title`, `description`, and `metadata` — it never touched
`images` or `thumbnail`, so any product that already existed in Medusa
(the UPDATE path) had its Firestore images silently dropped on every
sync. Only the CREATE path included images.

### Changes (`scripts/sync_vendors_to_medusa.py`)

- `_build_update_payload()` gains an `existing_image_urls` kwarg. When
  the caller passes it (the set of URLs Medusa already has), the payload
  appends any Firestore URLs not already present (union semantics, so
  Medusa's existing image ids — including reverse-imported ones — are
  preserved). Also writes `thumbnail` when the product has none.
- `metadata` now carries `dimensions` and `gtin` so the v1.11.3
  structured-data backfill propagates to Medusa without a separate sync.
- `_find_product_by_handle()` fetches `thumbnail` + `images.url` so the
  caller can pass them into the update payload.
- Call site in `sync_brand()` builds `existing_img_urls` from the lookup
  response and passes it through.

Idempotent: re-running the sync with no new Firestore images is a no-op
on the image axis (everything already in `existing_image_urls`).

### Outcome

After this fix, `sync_vendors_to_medusa.py --brand=eurotramp` should
push the 404 images uploaded in [eukrit/vendors#12](https://github.com/eukrit/vendors/pull/12)
to Medusa, and the storefront PDPs for the 105 enriched SKUs will
finally render real product photos instead of the placeholder.

## [2.22.2] - 2026-05-16

### Changed — Re-priced Rampline at v2.20.1 pricing constants (30% GM, 7% VAT)

Re-ran the landed-cost + retail pipeline against the Rampline-specific
constants (`GROSS_MARGIN=0.30`, `DUTY_RATE_NON_CHINA=0.10`,
`THAI_VAT_RATE=0.07`) introduced in v2.20.1, refreshed the Firestore
audit doc, and pushed the new prices to all 127 Medusa variants on
the Rampline sales channel.

Also flipped the 8 new Rampball/Jumpstone size sub-products
`draft → published` so they're now visible on the storefront.

#### Pricing-config note

Firestore `pricing_config/canonical` is not yet seeded — the run used
`PRICING_CONFIG_DISABLE=1` to skip the live cfg lookup and resolve to
the module-level fallbacks in
`rampline-catalog/import_pricelist.py` and
`shared/landed_pricing.py`. Once `scripts/seed_pricing_config.py`
populates the Firestore doc, this caveat goes away and the import
script reads the cfg automatically.

#### Price delta vs v2.22.1

Net effect of 0.40 → 0.30 GM (plus today's FX): roughly
**-15 % on retail across the board**, modulated by minor
NOK→EUR drift (0.09277 → 0.09236 today).

| SKU | Family | THB v2.22.1 | THB v2.22.2 | Δ |
|---|---|---:|---:|---:|
| `RB35` | Rampball 35 (wet pour) | 133,471 | **113,648** | -14.85 % |
| `SD 02` | ShockDeck U-piece | 786 | **669** | -14.89 % |
| `BP 15 LF` | Marathon Play (loose fills) | 9,710,485 | **9,731,783** | +0.22 % (FX drift > GM cut for clamped tiers) |

#### Status changes

| Handle | Before | After |
|---|---|---|
| `rampline-rampball-{35,50,50r,70r}` | draft | **published** |
| `rampline-jumpstone-en-{27,50,3,5}` | draft | **published** |

#### Verification

```
Audit doc: vendors/rampline/pricelists/2026-05-13
  calculated_at: 2026-05-16T08:46:12  (refreshed)
  gross_margin: 0.30
  row_count: 127

sync_variant_prices.py --apply
  SET_VARIANT_PRICES: 127
  errors: 0
  unmatched audit codes: 0

8 sub-products status flipped draft → published, 0 NOT FOUND
```

#### Files

- REGENERATED: `rampline-catalog/data/pricelist_2026-05-13_landed.csv`
  (overwritten with 30 % GM numbers).
- NEW: `rampline-catalog/data/build_runs/prices_dryrun_2026-05-16T08-47-52Z.json`,
  `prices_applied_2026-05-16T08-48-43Z.json`.

## [2.22.1] - 2026-05-16

### Added — Rampline variant prices pushed to Medusa (THB / USD / EUR)

127 / 127 Medusa variants on the Rampline sales channel now carry
retail prices in three currencies, sourced from the
`vendors/rampline/pricelists/2026-05-13` Firestore audit doc.

#### Pipeline

`rampline-catalog/sync_variant_prices.py`:
1. Reads the audit doc via Firestore REST (uses
   `LEKA_FIRESTORE_ACCESS_TOKEN` env or ADC fallback — no SA key on disk).
2. Indexes Rampline variants by `metadata.article_code` (set during the
   v2.22.0 variant creation) → falls back to `variants.sku`.
3. For each pricelist row, computes the price delta vs current variant
   state and emits one of `SET_VARIANT_PRICES` / `PRICES_UPTODATE`.
4. Pushes per-variant prices via `POST /admin/products/{pid}/variants/{vid}`,
   stamping each variant with provenance metadata
   (`prices_synced_at`, `prices_synced_from`, `prices_formula_version`).
5. Writes a full audit log under
   `rampline-catalog/data/build_runs/prices_*.json`.

#### Currencies + carve-outs

- **Pushed**: `thb`, `usd`, `eur` (storefront-facing).
- **Not pushed**: `nok`. Wholesale net stays in `variant.metadata.net_nok`
  to avoid confusing customers with supplier currency.
- 8 Rampball/Jumpstone size sub-products remain `status=draft` — flip to
  `published` after a final sanity check.

#### Caveat (intentional)

Prices use the v2.19.0 formula constants from the 2026-05-13 audit doc
(`gross_margin=0.40`, no separate Thai VAT layer). The post-v2.20.1
pricing-config (per-brand GMs + 7% Thai VAT) supersedes this; once the
config is locked, re-run `rampline-catalog/import_pricelist.py` to
refresh the audit doc, then re-run `sync_variant_prices.py` — it's
idempotent and only POSTs deltas.

#### Spot-check

| SKU | Family | Retail THB | Retail USD | Retail EUR |
|---|---|---:|---:|---:|
| RB35 | Rampball 35 (wet pour) | 133,471 | 4,039 | 3,441 |
| SD 02 | ShockDeck U-piece | 786 | 24 | 20 |
| BP 15 LF | Marathon Play (loose fills) | 9,710,485 | 293,837 | 250,350 |

#### Verification

```
Total variants on Rampline channel: 149  (127 real + 22 placeholder)
Variants with prices_synced_at metadata: 127
SET_VARIANT_PRICES actions: 127
PRICES_UPTODATE: 0
errors: 0
unmatched audit codes (no Medusa variant): 0
```

#### Files

- NEW: `rampline-catalog/sync_variant_prices.py` (Medusa price-push
  script with `--dry-run` / `--apply` / `--limit-family`).
- NEW: `rampline-catalog/data/build_runs/prices_dryrun_*.json`,
  `prices_applied_*.json` (full audit trail).
- REGENERATED: `docs/build-summary.html`, `docs/architecture.html`,
  `docs/hub.html` (v2.22.x pickup).

## [2.22.0] - 2026-05-16

### Added — Rampline pricelist → Medusa variants

127 article codes from the 2025 NOK pricelist now live as Medusa
variants across 40 Rampline sub-products. Default placeholder variants
(keyed on the WooCommerce post IDs from the original `rampline.com`
scrape) are removed from every product that received real variants.

#### Structure (per user decision 2026-05-16)

- **Size-as-product** for clean Size × Surface families:
  - `rampline-rampball` → 4 new size sub-products `-35`, `-50`, `-50r`,
    `-70r` (4 surface variants each = 16 variants).
  - `rampline-jumpstone-en` → 4 new size sub-products `-27`, `-50`,
    `-3`, `-5` (4 surface variants each = 16 variants).
- **Single-product-with-options** for multi-axis / service families
  (`balancebuddy-en`, `balancebuddy-wave`, `fungi-eng`, `rampit`,
  `rampit-hopper`, `rampit-swing`, `rampit-storm-en`, `rampbow`,
  `rampline-slackline`, `floating-bench`, `shockdeck`). Axes per
  family: Length × Style, Surface, Size, Component × Surface, Type, or
  synthetic Type (Medusa v2 forbids option-less products).
- **Group B park bundles** — each of 21 SHOCKDECK-priced parks
  (Kangaroo, Marathon Play, …) gains 3-surface variants on top of the
  existing product.

#### Counts

- Products: 54 → **62** (8 new Rampball/Jumpstone size sub-products,
  `status=draft`).
- Variants: **149** total (127 from pricelist + 22 untouched
  placeholders on legacy parks / unpriced equipment / family parents).
- Cleanup: 24 placeholder defaults deleted, 25 "Default" options
  removed.
- Reconciliation: 0 pricelist SKUs missing, 0 unexpected real SKUs.

#### Out of scope (intentional)

- 17 legacy parks not in the 2025 pricelist (ABILITY, AGILE, BOUNCE,
  …, TWIST) — pre-2025 lineup, kept as-is.
- 3 unpriced equipment products (Spare parts ×2, Playground Loop
  trampoline) — kept as-is.
- Variants carry full audit `metadata` (`article_code`, `family`,
  `family_discount`, `net_nok`, `recommended_nok`, `description`,
  `pricelist_date`, `source`) but **no prices** — pricing handled
  separately via the Firestore-backed pricing-config flow (v2.20.1) +
  a follow-up sync script.

#### Files

- NEW: `rampline-catalog/build_variants.py` (Medusa write script,
  `--dry-run` / `--apply` / `--limit-family`).
- NEW: `rampline-catalog/data/mapping/generate_mapping_drafts.py`
  (parser + scaffold generator).
- NEW: `rampline-catalog/data/mapping/family_mapping_draft.csv`
  (40 sub-product rows).
- NEW: `rampline-catalog/data/mapping/variant_scaffold_draft.csv`
  (127 article codes, full option breakdown).
- NEW: `rampline-catalog/data/mapping/medusa_snapshot_2026-05-14.json`
  (read-only Medusa state at planning time).
- NEW: `rampline-catalog/data/build_runs/*.json` (dry-run + applied
  action logs, full audit trail).
- NEW: `docs/summaries/rampline-variants.html` (Leka-styled summary).

#### Verification

```
Total Rampline products: 62  (was 54 + 8 new size sub-products)
Total variants: 149  (127 from pricelist + 22 untouched placeholders)
Pricelist SKUs missing from Medusa: 0
Unexpected non-placeholder SKUs in Medusa: 0
```

#### Next

- Set per-currency prices (THB/USD/EUR/NOK) on the 127 new variants
  via a sync_vendors_to_medusa extension reading
  `vendors/rampline/pricelists/<date>`.
- Flip Rampball/Jumpstone size sub-products `draft` → `published`
  once prices land.
- Re-run the landed-cost computation against the post-v2.20.1 pricing
  config (0.30 GM + duty/VAT layers) once Rampline cfg is locked.
- Parse Rampline tech-sheet PDFs for per-SKU dimensions so the
  landed-cost engine uses real CBM rather than the 35% flat uplift.

## [2.21.0] - 2026-05-16

### Added — Cost cascade dashboard with TH/SG destination pricing

The pricing-config editor at `/forms/pricing-config` now shows the full
FOB → Landed → Retail cascade for one product per logistics tier per
brand, live FX, and side-by-side TH-VAT-inclusive vs SG-via-Nubo
retail prices. Schema additions are backward-compatible.

#### New global config fields
- `th_customer_vat_rate` (default `0.07`) — added to retail base for
  TH-destination sales. The import 7% VAT inside `landed_thb` remains;
  this is an additional sales VAT charged to the customer.
- `sg_customer_gst_rate` (default `0.09`) — applied on SG-destination
  retail **only when** `sg_nubo_gst_registered` is true.
- `sg_nubo_gst_registered` (default `false`) — checkbox. Nubo is not
  yet GST-registered in Singapore; the dashboard ships with this off
  so SG retail is GST-free until that registration completes.

#### New per-brand config fields
- `source_pricelist_url` — file path or URL for the EXW/FOB pricelist.
  Defaults:
  - `vinci`: 2026-05-11 xlsx in Eukrit's Drive (Partners Playground/…)
  - `berliner`: `berliner-catalog/data/pricelist_2026-01-01.csv`
  - `rampline`: Rampline 2025 NOK pricelist (Google Drive)
  - `wisdom`: `wisdom-catalog/data/` (Excel catalogs)
- `source_pricelist_label` — display name for the link in the UI.

#### Live cost cascade
- `GET /api/pricing-context` — new endpoint returning:
  - `fx`: live USD/EUR/SGD vs THB from frankfurter.app (ECB-backed,
    no key), cached 1h server-side, with hardcoded fallback if the
    feed fails.
  - `brands`: for each brand, 1 example product per logistics tier
    (4 examples × 4 brands = 16). For Vinci/Berliner, examples come
    from `vendors/<brand>/products` with stored pricing. For Rampline,
    from `vendors/rampline/pricelists/<date>` variants. For Wisdom,
    from per-product fob_usd. Cascade recomputed against current
    Firestore config so config changes flow through.
- Each cascade row shows: source FOB (native ccy), THB FOB, logistics
  uplift, duty, import VAT, landed, retail-pre-tax (÷ (1 − GM)),
  retail TH (VAT-inclusive), retail SG (SGD).

#### UI
- `docs/forms/pricing-config.html` — major rewrite:
  - Live FX strip in the header (USD/EUR/SGD per THB).
  - All rate fields now display as **percentages** (`7`, not `0.07`),
    stored as decimals.
  - New "Cost cascade — live examples" card under the config form,
    one table per brand.
  - New "Source pricelist" URL + label per brand (clickable; flagged
    if the value is a local Windows path the browser can't open).
  - "Refresh FX + examples" button.
  - Inline formula card explaining the math.
- `src/main.py` VERSION `0.6.1` → `0.7.1`.

#### Formula recap (visible in the dashboard)

```
landed_thb         = (FOB × EUR/THB × unmatched_landed_uplift)
                   + (CIF × duty_rate)
                   + ((CIF + duty) × thai_vat_rate)
retail_pre_tax_thb = landed_thb / (1 − gross_margin)
retail_th_thb      = retail_pre_tax_thb × (1 + th_customer_vat_rate)
retail_sg_thb      = retail_pre_tax_thb × (1 + sg_customer_gst_rate)   (if Nubo GST-registered)
                   = retail_pre_tax_thb                                 (otherwise)
retail_sg_sgd      = retail_sg_thb / (THB/SGD)
```

Wisdom (China-origin) skips the EU-logistics uplift + tier clamp; uses
`brands.wisdom.import_duty_rate` instead of `global.duty_rate_non_china`.

#### Build sequence
1. `a7a41738` SUCCESS (2m1s) — v0.7.0 first cut. Rampline examples
   came back empty.
2. *(diagnosed)* — variant key was `article_code`, not `article`;
   `eur_fob` was pre-computed (no NOK→EUR multiply needed).
3. `bwp6k17ne` — fixed variant field names. Rampline still 0 — caused
   by `order_by("__name__")` returning empty on the named DB.
4. v0.7.1 — switched to `stream() + Python sort by doc id`. All four
   brands now return 4 examples.

#### Smoke output (2026-05-16, live FX EUR=37.99 SGD=25.52 USD=32.67)

```
berliner | tier0 (EUR ≤ 500)  | EUR 163   → landed ฿9,487   → retail_TH ฿13,535  → retail_SG SGD 496
berliner | tier3 (EUR > 10k)  | EUR 10117 → landed ฿519,137 → retail_TH ฿740,635 → retail_SG SGD 27,120
vinci    | tier0              | EUR 116   → landed ฿7,933   → retail_TH ฿13,059  → retail_SG SGD 478
vinci    | tier3              | EUR 10184 → landed ฿614,812 → retail_TH ฿1.01M   → retail_SG SGD 37,059
rampline | tier0              | NOK 73    → landed ฿462     → retail_TH ฿706     → retail_SG SGD 26
rampline | tier3              | NOK 113833 → landed ฿637,529 → retail_TH ฿974,508 → retail_SG SGD 35,683
wisdom   | tier0              | USD 3     → landed ฿120     → retail_TH ฿257     → retail_SG SGD 9
wisdom   | tier3              | USD 11640 → landed ฿435,382 → retail_TH ฿931,717 → retail_SG SGD 34,117
```

#### Notes for the user to verify
- The 7% Thai customer VAT is **stacked on top** of the import VAT
  (per your direction). If the convention is actually that retail
  already absorbs the import VAT and only the 7% customer VAT is
  shown to the buyer, set `th_customer_vat_rate = 0` and the formula
  collapses to `retail_th = retail_pre_tax`.
- Nubo SG GST: dashboard ships with the flag OFF. Flip when Nubo is
  registered and the 9% multiplier kicks in automatically.
- Source pricelist links: Vinci's default is a local Windows path that
  browsers can't open. Replace with the Drive share URL once you have
  it (the field is right above the link).
- Wisdom values look low because `wisdom-b2-2255` has a `fob_usd` of
  $3 — that's likely a SKU with a misparsed unit price (catalog default
  is per-piece, not per-pack). Catalog data, not formula bug.

## [2.20.3] - 2026-05-16

### Fixed — pricing-config form Load failed HTTP 404

The editor page loaded but `fetch("/api/pricing-config")` 404'd because
the gateway strips the `/leka-product-catalogs` prefix on the way to the
backend, and the browser resolved the absolute path against the gateway
host (`https://gateway.goco.bz/api/pricing-config`) instead of the
project-prefixed path. Two follow-ups from v2.20.2:

- `docs/forms/pricing-config.html` — added `API_URL` derived from
  `location.pathname` so the same HTML works whether served via
  `gateway.goco.bz/leka-product-catalogs/forms/pricing-config` or
  directly from local Flask. Footer "← Hub" link is now path-relative
  (`../`) instead of hardcoded `/leka-product-catalogs/`.
- `src/main.py` — `VERSION` 0.6.0 → 0.6.1 for traceability.

Also adds a separate gateway-side change merged in PR
[go-access-gateway#6](https://github.com/eukrit/go-access-gateway/pull/6) —
script sync for `register-all-projects.sh` (live registry was already
patched via Firestore REST when the user hit the v2.20.2
`not_found_in_repo` error).

### Build
- Cloud Build `aaa11d4c` SUCCESS (1m48s). Image
  `gateway:3eac0a2-dirty` deployed as new revision of
  `leka-catalogs-gateway`. `/health` returns `0.6.1`.

## [2.20.2] - 2026-05-16

### Deployed — pricing-config UI live at gateway

Followed the v2.20.1 deploy plan and pushed a new revision of the
existing `leka-catalogs-gateway` Cloud Run service (asia-southeast1).
The page that previously returned the gateway's `not_found_in_repo` 404
now resolves because the v0.5.0 revision didn't have the
`/forms/pricing-config` route — the new revision (image
`gateway:3d640e7`) does.

#### Decisions
- **Reused `leka-catalogs-gateway`** instead of creating a separate
  `leka-catalogs-admin` service. The access-gateway already proxies
  `https://gateway.goco.bz/leka-product-catalogs/...` to it, and that's
  what the user actually calls.
- **Kept `--allow-unauthenticated`** on the service. Tightening to
  invoker-only requires a coordinated change in `go-access-gateway`
  routing so it mints an ID token before proxying — out of scope for
  this deploy. The form's POST handler already trusts the gateway's
  forwarded `X-Goog-Authenticated-User-Email` for the audit trail.

#### Changes
- `cloudbuild-admin.yaml` — retargeted to `_SERVICE: leka-catalogs-gateway`
  + image `_IMAGE: gateway`. Removed `--no-allow-unauthenticated` flip.
- `.gcloudignore` — root `Dockerfile` build context needs `src/`,
  `shared/`, `docs/forms/`, and `vinci-catalog/web-app/public/`. Removed
  the wholesale `docs`, `shared`, `scripts`, `/src`, `/vinci-catalog`
  exclusions (gitignore semantics — can't re-include children of an
  excluded parent); added narrow per-file exclusions for the heavy
  non-runtime parts that we don't need in the image.
- `.dockerignore` — same fix on the Docker side: removed `docs/` and
  `shared/`, added narrow exclusions for non-runtime docs files.

#### Build sequence (today)
1. Cloud Build `4b7964fa` — FAIL: `$SHORT_SHA` empty on manual submit.
   Fix: pass `--substitutions=SHORT_SHA=$(git rev-parse --short HEAD)`.
2. Cloud Build `708f2b37` — FAIL: `COPY shared/` not found
   (`.gcloudignore` excluded `shared`). Fix: see above.
3. Cloud Build `e65c0c30` — FAIL: `COPY docs/forms/` not found
   (gitignore parent-dir rule defeated `!/docs/forms/**`). Fix: removed
   the blanket `docs` exclusion.
4. Cloud Build `a2642143` — **SUCCESS** (2m1s). Image
   `asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs/gateway:3d640e7`
   deployed as revision `leka-catalogs-gateway-00002-?`.

#### Smoke test (direct Cloud Run URL)
- `GET /health` → `{"version":"0.6.0", ...}` ✅ (was `0.5.0`)
- `GET /api/pricing-config` → 200 with the seed (5 globals, 4 brands,
  4 tiers) ✅
- `GET /forms/pricing-config` → 200, 13.9 KB of HTML ✅

Gateway URL `https://gateway.goco.bz/leka-product-catalogs/forms/pricing-config`
returned the Google sign-in flow on unauthenticated curl — IAP working
as expected. Authenticated browser sessions get the editor.

### Outstanding (not blocking the editor)
- `pricing_config/canonical` Firestore doc doesn't exist yet. The form
  serves `_empty_config()` defaults until either:
  - The user clicks **Save changes** in the editor (writes the doc with
    their email as `updated_by`), or
  - `python scripts/seed_pricing_config.py` is run locally (writes the
    doc with `scripts/seed_pricing_config.py` as `updated_by`).
- `--no-allow-unauthenticated` tightening — see Decisions above.

## [2.20.1] - 2026-05-15

### Added — Firestore-backed pricing config + gateway-fronted editor UI

Pricing parameters are no longer scattered Python module-level constants
edited via PR. They now live in **`pricing_config/canonical`** in the
`leka-product-catalogs` Firestore database and are editable through a
form behind the access gateway.

#### Reader side
- `shared/pricing_config.py` (new) — process-cached Firestore loader.
  `get_pricing_config(brand)` merges global keys with per-brand overrides;
  returns `{}` when Firestore unreachable so module-level constants act
  as fallbacks. `PRICING_CONFIG_DISABLE=1` short-circuits in CI/tests.
- `shared/landed_pricing.py` — `price_row()` gains `brand: str = "vinci"`
  kwarg; pulls GROSS_MARGIN, DUTY_RATE_NON_CHINA, THAI_VAT_RATE,
  UNMATCHED_LANDED_UPLIFT, and LOGISTICS_TIERS from the live cfg.
- `shared/wisdom_pricing.py` — `compute_wisdom_retail()` and
  `pricing_metadata()` consult the live cfg via `_params()`.
- `vinci-catalog/import_pricelist.py` — passes `brand="vinci"` into
  `price_row()`; metadata writes use `_vinci_gross_margin()` (live).
- `berliner-catalog/import_pricelist.py` — `_berliner_params()` returns
  live cfg merged with Berliner's local fallbacks; both `price_row()` and
  `write_firestore()` consume it.
- `rampline-catalog/import_pricelist.py` — passes `brand="rampline"`
  into `price_row()`; `_rampline_params()` covers the post-call retail
  re-derivation.

#### Writer side
- `src/main.py` — adds `/forms/pricing-config`, `GET /api/pricing-config`,
  `POST /api/pricing-config`. Auth boundary is the gateway IAP; we trust
  `X-Goog-Authenticated-User-Email` / `X-Goco-User-Email` for the audit
  field. Range-validates payloads (catches "35" entered as percent vs
  "0.35"). `VERSION` bumped 0.5.0 → 0.6.0.
- `docs/forms/pricing-config.html` — Manrope + Leka palette editor with
  brand pills, logistics-tier table, save/reload buttons, audit footer
  ("Last edited by … at …"), and a raw-JSON debug pane.
- `Dockerfile` — installs `google-cloud-firestore`, copies `shared/` and
  `docs/forms/` so the Flask service can serve the editor.
- `cloudbuild-admin.yaml` (new) — manual-trigger build that deploys the
  Flask service as Cloud Run service `leka-catalogs-admin`,
  `--no-allow-unauthenticated`, ready for the gateway invoker-binding.

#### Seed
- `scripts/seed_pricing_config.py` — one-shot. Reads current module-level
  constants from shared + brand scripts and writes them to
  `pricing_config/canonical`. `--force` to overwrite, `--dry-run` to print.

#### Hub
- `hub.config.json` — `pricing-config.html` added to
  `classification_hints`. `live.enabled` stays `false` until the
  Cloud Run admin service is deployed and gateway-routed.

### Verification
- `PRICING_CONFIG_DISABLE=1 python -c "..."` confirms the fallback path
  resolves to module defaults (Vinci 0.35 GM, non-China duty 0.10, etc.).
- Flask test_client smoke: GET returns seed (5 globals, 4 brands, 4
  tiers); bad payload (`thai_vat_rate=7`) → 400; valid payload → 500
  with sanitized Firestore error (expected — local ADC expired).
- Form route serves the 13.5 KB HTML editor.

### Deploy plan (one-time, manual)
```bash
gcloud builds submit --config=cloudbuild-admin.yaml
gcloud run services add-iam-policy-binding leka-catalogs-admin \
  --region=asia-southeast1 \
  --member="serviceAccount:go-access-gateway@ai-agents-go.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
python scripts/seed_pricing_config.py
# Then in go-access-gateway/registry, point project_id "leka-product-catalogs"
# at this Cloud Run URL and flip hub.config.json hub.live.enabled to true.
```

### Outcome
- The 2026-05-14 pricing canonicalization (commits `e0c5c75` + `4316d8f`)
  is now live-editable. Next tweak is one form save + one re-run of
  `<brand>/import_pricelist.py` — no PR required.
- Closes the Rules 2 + 4 gap from the v1.32.0 sibling work
  (CHANGELOG + build-summary were left stale by `e0c5c75` + `4316d8f`).

## [2.20.0] - 2026-05-15

### Added — DesignPark onboarding (9th brand, full Gen-3 pipeline scaffolding)

DesignPark (DESIGN PARK Co., Ltd., South Korea — playground, water play,
outdoor fitness, themed installations) onboarded via the same
`vendors/<slug>` → `sync_vendors_to_medusa.py` path the other 8 brands use.
This version lands the **code + dry-run validation**; the actual
`--apply` runs against live Firestore / GCS / Medusa are gated on
credentials and follow as a v2.20.1 deploy entry.

### Pipeline

1. **`scripts/bootstrap_designpark.py`** — creates the Medusa Sales Channel
   "Design Park" via `MedusaImporter.get_or_create_sales_channel`, then
   merge-writes `vendors/designpark` root doc to Firestore DB `vendors`
   (origin_route=`japan_korea`, currency_native=USD, FOB port=Busan,
   duty_rate_thai=0.10 — non-China per landed_pricing rule).
2. **`scripts/ingest_designpark_pricelist.py`** — parses
   `Design Park Pricelist D'Park Price List (USD-2024).xlsx` (12 sheets,
   178 component SKUs across Slides & Tubes, Fitness Premium/Universal/
   Elderly/SMART/Senior/CrossFit, Speed Racers, Play Dry/GRC/Aquatic)
   plus the 33-theme manifest at
   `2024-03-18 D'Park 2D CAD & Images/2023 Theme dry&waterplay list ... .xlsx`.
   211 product docs written to `vendors/designpark/products`.
3. **USD FOB → THB landed → retail (THB/USD/EUR)** — same formula spine as
   Vinci/Rampline, but currency-agnostic per row: cost_engine origin =
   `japan_korea` (LCL Busan → Bangkok), DUTY_RATE_NON_CHINA=10%,
   THAI_VAT_RATE=7%, UNMATCHED_LANDED_UPLIFT=1.35x (no CBM data in the
   pricelist; tightens when B2 supplies DWG-derived dimensions),
   GROSS_MARGIN=0.35. Formula version stamped `designpark-v1-2026-05-15`.
4. **`scripts/ingest_designpark_assets.py`** — discovers 620 assets across
   four sources: CAD bundle (66 numbered `<N>_<theme>.{jpg,dwg}` files),
   `Catalogs GO/DesignPark/IMAGE/*.zip` (197 images across 11 line zips),
   `Catalogs GO/DesignPark/DRAWING/*.zip` (337 DWGs across 10 zips),
   `Suppliers GO/DesignPark/*.zip` (16 per-SKU drops). Uploads to
   `gs://ai-agents-go-vendors/designpark/media/<sha>.<ext>` (UBLA, PAP),
   serves via `https://catalogs.leka.studio/api/i/designpark/media/<sha>.<ext>`,
   joins to products by SKU regex (SDM/PTC/PTM/DPM/DPF/DPS) or theme-name
   slug match.
5. **`scripts/ingest_designpark_catalog_pdfs.py`** — pdfplumber-extracts
   text from the 2024 ENG catalog (and 2022 fallback); backfills empty
   `description` fields by matching SKU tokens / product names against
   the product index. Image-only pages are reported but skipped (Gemini
   Vision OCR path deferred to follow-up if needed).
6. **`scripts/shape_designpark_to_medusa_schema.py`** — finalizes invariants
   (`handle`, `images[]` deduped by sha, `thumbnail`, `status` promoted to
   `active` when ≥1 image attached else `draft_no_images`).
7. **`scripts/sync_vendors_to_medusa.py`** — added `designpark` placeholder
   to `BRAND_SALES_CHANNELS`; the bootstrap script provides the `sc_…` id.

### Phase C deferred

Slack `#vendor-design-park` ingest deferred to v2.20.1 — depends on Slack
OAuth setup not yet in place for this brand. Plan placeholder lives at
`~/.claude/plans/inspect-new-vendor-scraping-stateful-octopus.md` §C1.
Website scrape (originally Phase D) skipped per plan §7 decision #1.

### Dry-run output (2026-05-15)

```
ingest_designpark_pricelist.py --dry-run
  FX: USD=33.0119 THB/USD, EUR=38.5735 THB/EUR
  parsed 11/12 component sheets (Modern Igloo header non-standard, skipped)
  parsed 33 themes
  built 211 product docs
  sample: PE SINGLE SLIDE 900 — fob_usd=$375 → retail_usd=$916.70

ingest_designpark_assets.py --dry-run
  total assets discovered: 620
  by kind:   {'image': 389, 'drawing': 211}
  by source: {'cad-bundle': 66, 'image-zips': 197, 'drawing-zips': 337, 'suppliers': 16}
  has sku:   78 / no sku: 522 (theme/line match)
```

### Files

- new: `scripts/bootstrap_designpark.py`
- new: `scripts/ingest_designpark_pricelist.py`
- new: `scripts/ingest_designpark_assets.py`
- new: `scripts/ingest_designpark_catalog_pdfs.py`
- new: `scripts/shape_designpark_to_medusa_schema.py`
- modified: `scripts/sync_vendors_to_medusa.py` — `BRAND_SALES_CHANNELS` entry placeholder.
- modified: `VERSION` → `2.20.0`

### Apply sequence (for v2.20.1 deploy)

```
py scripts/bootstrap_designpark.py --apply                      # SC + root doc
py scripts/ingest_designpark_pricelist.py --apply               # 211 products
py scripts/ingest_designpark_assets.py --apply                  # GCS uploads + image[] join
py scripts/ingest_designpark_catalog_pdfs.py --apply            # descriptions
py scripts/shape_designpark_to_medusa_schema.py --apply         # status promote
# Update BRAND_SALES_CHANNELS["designpark"] with sc_ id printed by bootstrap.
py scripts/sync_vendors_to_medusa.py --brand=designpark --dry-run
py scripts/sync_vendors_to_medusa.py --brand=designpark
```

## [2.19.0] - 2026-05-13

### Added — Rampline pricelist → landed cost + retail (Firestore audit)

Rampline's 2025 NOK pricelist (Google Drive, 31 KB, 127 article codes
across 13 product families) now flows through the same landed-cost +
40 % GM retail formula as Vinci Play, with results audited in Firestore
at `vendors/rampline/pricelists/2026-05-13`.

### Pipeline

1. `rampline-catalog/import_pricelist.py` fetches/reads the xlsx,
   parses section headers (each carries the wholesale discount), reads
   the **Net price 2025** column as EXW (NOK).
2. NOK → EUR via `open.er-api.com` (live ECB-backed, fallback
   `frankfurter.app`, then hardcoded 0.087). Today: 0.09277 EUR/NOK.
3. EUR FOB → THB landed via `shared/landed_pricing.py` (shipping-automation
   `estimate_landed_cost` LCL Europe → Laem Chabang, Baltic-rate
   calibrated).
4. Tiered logistics clamp (80 / 60 / 45 / 35 % floor by FOB band).
5. Retail THB = landed / 0.60 (40 % GM); USD/EUR at live FX.

### Output

- CSV: `rampline-catalog/data/pricelist_2026-05-13_landed.csv` (127 rows).
- Firestore: `vendors/rampline/pricelists/2026-05-13` — single audit doc
  with `variants` map keyed by sanitized article code, plus
  `fx_snapshot`, `nok_eur_rate`, `baltic_rate_snapshot`, `logistics_tiers`.

### Spot-check

| SKU | NOK net | EUR FOB | Landed THB | Retail USD |
|---|---:|---:|---:|---:|
| SD 02 (SHOCKDECK smallest) | 73 | 6 | 442 | $22 |
| RB35 (Rampball wet-pour) | 13,910 | 1,290 | 80,083 | $4,039 |
| BP 15 LF (SHOCKDECK largest) | 1,199,380 | 111,259 | 5,826,041 | $293,820 |

94/127 SKUs hit the floor clamp (small parts dominated by fixed
shipping costs), 33/127 within band, 0 capped. Realized GM uniformly 40 %.

### Shared module

Lifted the Vinci landed-cost + retail formula into
`shared/landed_pricing.py` so both brands share one canonical
implementation. `vinci-catalog/import_pricelist.py` refactored
(427 → 219 lines) — zero behaviour change.

### Medusa push — DEFERRED

Rampline's 54 Medusa products each have a single "Default" variant
keyed on the WooCommerce numeric ID. The pricelist's 127 article
codes are variant-level SKUs that don't yet exist in Medusa. Creating
per-article variants is a separate migration (also needs new products
for SHOCKDECK / climbing pole / balance arch families). For now we
only audit landed + retail in Firestore.

### Files

- NEW: `shared/landed_pricing.py`,
  `rampline-catalog/import_pricelist.py`,
  `rampline-catalog/data/source/rampline_pricelist_2025_fetched-2026-05-13.xlsx`,
  `rampline-catalog/data/pricelist_2026-05-13_landed.csv`,
  `docs/rampline.html`.
- CHANGED: `vinci-catalog/import_pricelist.py`, `CHANGELOG.md`, `VERSION`.

### Next

- Decide whether to create per-article Medusa variants (127 new
  variants across 13 families) — needs family-name → Medusa-product
  map and probably new products for SHOCKDECK / climbing pole /
  balance arch.
- Source per-SKU dimensions (Rampline tech-sheet PDFs are scraped but
  not parsed yet). Would shift most rows off the flat-uplift branch.

## [2.18.4] - 2026-05-13

### Fixed — Medusa admin UI silent-crash (start from `.medusa/server`, not `/app`)

Root cause of the v2.18.2/2.18.3 silent-exit-on-start when
`DISABLE_ADMIN=false`:

Medusa v2's `medusa build` outputs the admin UI assets to
`.medusa/server/public/admin/`. At runtime, the admin loader
(`@medusajs/medusa/src/loaders/admin.ts:90`) looks for
`<cwd>/.medusa/admin/index.html` — i.e. it assumes the CLI is being run
from inside `.medusa/server`, not from the project root. Our `start.sh`
was running `medusa start` from `/app`, so the loader looked for
`/app/.medusa/admin/index.html` (doesn't exist) and crashed.

The crash output never reached Cloud Logging because the medusa CLI
catches the error and exits before its logger has flushed — only
"Server is ready" + the error message appear, and only when started
from the right cwd. We caught this by spinning up the image inside
Cloud Build with verbose stdout capture and a wide `find .medusa`,
which surfaced both the build output location (`.medusa/server/public/admin/`)
and the loader's expectation (`.medusa/admin/`).

### Changes

- **`medusa-backend/start.sh`** — `cd /app/.medusa/server` before
  `exec node /app/node_modules/.bin/medusa start`. The CLI is resolved
  via the parent `/app/node_modules` so we don't need a second
  `npm install` inside `.medusa/server`.
- **`cloudbuild.yaml`** — restored `DISABLE_ADMIN=false` in the deploy
  step's `--set-env-vars` (was reverted to `true` in v2.18.3 as a
  hotfix when we couldn't isolate the crash).

After Cloud Build picks this up, the admin UI lives at
https://catalogs.leka.studio/app . Login with `admin@leka.studio` +
the password in Secret Manager (`medusa-admin-password`).

### Debug artefact

`cloudbuild-debug-admin.yaml` (new) — pulls the production image and
runs `medusa start` inside Cloud Build with stdout/stderr captured,
useful for surfacing silent crashes that Cloud Run obscures. Keep
around for future debugging.

## [2.18.3] - 2026-05-13

### Reverted — `DISABLE_ADMIN=false` in cloudbuild (Medusa start silent-crash on Cloud Run)

v2.18.2 set `DISABLE_ADMIN=false` so the admin UI would be served at
`https://catalogs.leka.studio/app`. After two rebuilds and three Cloud
Run revisions (`00015`, `00016`, `00017`), the container failed every
startup probe with no usable error: stdout shows `medusa start` printing
its banner then exit(1) with nothing else on stdout / stderr / Cloud
Logging. Revision `00018-mcq` is the working state — same new image
(`medusa-backend:01addb0`), same MEDUSA_BACKEND_URL baked in, but
`DISABLE_ADMIN=true` so the API stays healthy.

This commit reverts the `DISABLE_ADMIN` default in `cloudbuild.yaml` back
to `true` so the next Cloud Build doesn't break the service. Everything
else from v2.18.1+2 stays:

- `MEDUSA_ADMIN_PASSWORD` from Secret Manager (Rule 12 fix).
- `MEDUSA_BACKEND_URL=https://catalogs.leka.studio` baked + at runtime
  (harmless with admin disabled; ready for when admin is re-enabled).
- `ADMIN_CORS` / `AUTH_CORS` include `catalogs.leka.studio` (also
  harmless; future-proofs the storefront).
- `cloudbuild.yaml` deploy `--set-env-vars` keeps the `^|^` delimiter so
  comma-bearing values (AUTH_CORS) deploy cleanly.

The `catalogs.leka.studio/admin/*` + `/auth/*` Next.js rewrites in
[eukrit/leka-website](https://github.com/eukrit/leka-website) v0.8.8
**do work** — the admin API + login are reachable through the catalogs
domain. Only the admin UI HTML at `/app` is unavailable on Cloud Run.

### Workaround

Run the admin UI locally against prod credentials:

```powershell
cd medusa-backend
# .env: DATABASE_URL / REDIS_URL / COOKIE_SECRET / JWT_SECRET copied
# from Secret Manager (or use ADC via gcloud secrets versions access)
npx medusa develop
# Open http://localhost:9000/app
```

`medusa develop` builds + serves the admin in dev mode and bypasses the
production startup issue.

### Follow-up

The silent `medusa start` exit needs local repro to surface stack
traces. Likely candidates: missing admin asset, NODE_ENV=production +
admin combination in this Medusa version, or a config validation that
fails without printing. Out of scope for tonight; tracked for next
session.

## [2.18.2] - 2026-05-13

### Changed — Wire Medusa admin to catalogs.leka.studio/app

- **`cloudbuild.yaml`**:
  - `--build-arg=MEDUSA_BACKEND_URL=https://catalogs.leka.studio` — admin
    bundle now calls its API on the catalogs domain, not the raw Cloud Run
    URL. Combined with the storefront's Next.js rewrites, every admin
    request stays on one origin (no CORS).
  - `--set-env-vars` switched to `^|^` delimiter syntax. The previous
    `\,` escape inside `AUTH_CORS` was being rejected by gcloud as
    `Bad syntax for dict arg: [https://leka-medusa-backend-...]`, which is
    why v2.18.1's build step succeeded but the deploy step silently
    failed (the bash wrapper echoed "Deployed..." regardless of exit
    code). The new `^|^` delimiter lets values contain literal commas.
  - `ADMIN_CORS` and `AUTH_CORS` both now include
    `https://catalogs.leka.studio` (plus the Cloud Run direct URL for
    fall-back during DNS / domain-mapping cutover).

### Companion change

[eukrit/leka-website](https://github.com/eukrit/leka-website)
`catalogs/next.config.js` — new `rewrites()`:
```
/app           → ${MEDUSA}/app
/app/:path*    → ${MEDUSA}/app/:path*
/admin/:path*  → ${MEDUSA}/admin/:path*
/auth/:path*   → ${MEDUSA}/auth/:path*
```
After both deploys land, the admin lives at
https://catalogs.leka.studio/app (HTML+assets) and the bundle's API
calls (`/admin/*`, `/auth/*`) hit the same origin via the rewrites.

## [2.18.1] - 2026-05-13

### Changed — Medusa admin UI enabled + admin password moved to Secret Manager (Rule 12 fix)

- **Dockerfile (`medusa-backend/Dockerfile`):** add `ARG MEDUSA_BACKEND_URL`
  + `ENV MEDUSA_BACKEND_URL` before `npm run build` so the admin UI bundle is
  built with the production backend URL hard-coded into its API client.
- **`cloudbuild.yaml` (build step):** pass
  `--build-arg=MEDUSA_BACKEND_URL=https://leka-medusa-backend-538978391890.asia-southeast1.run.app`
  so the bundle that lands in the image points at the live Cloud Run URL.
- **`cloudbuild.yaml` (deploy step):**
  - `--set-secrets` adds `MEDUSA_ADMIN_PASSWORD=medusa-admin-password:latest`
    (previously plain text — visible to anyone with `run.services.get`,
    Rule 12 violation).
  - `--set-env-vars` adds `NODE_ENV=production`, `DISABLE_ADMIN=false`
    (was `true` — admin UI now served at `/app`), and
    `MEDUSA_ADMIN_EMAIL=admin@leka.studio` so the deploy matches what the
    earlier out-of-band `gcloud run services update` runs had to set
    manually.

### Other

- Granted `roles/secretmanager.secretAccessor` to the runtime SA
  `538978391890-compute@developer.gserviceaccount.com` on the
  `medusa-admin-password` secret (so the new revision can resolve the
  secret binding at start).
- Revision `leka-medusa-backend-00014-w4s` already has the secret binding
  + Rule-12 fix live; this commit makes that state reproducible from
  Cloud Build and unlocks the admin UI on the next image rebuild.

## [2.18.0] - 2026-05-13

### Added — EPDM/Infill pricer + new shared product categories

Converted the live "EPDM 2024 / Pricelist" Google Sheet
(`1wXGZoseE4PWEiY14BmtrYaHkkCJJEPyLQnUte7qUGrg`, tab `Pricelist`) into a
configurable HTML pricer and a Firestore product catalog so other projects can
query Critical Fall Height (CFH) without ever opening the spreadsheet.

(Originally landed locally as v2.10.0 commit `2d96cd0`, lost to a
`git reset --hard origin/main` that brought in v2.14–v2.16, re-applied as
v2.17.0 then renumbered to **v2.18.0** to clear the version collision with
the remote-side Wisdom → Leka Project rebrand that also took v2.17.0.)

- **`scripts/sync_epdm_pricelist.py`** — pulls the sheet via the Sheets API
  (SA `claude@ai-agents-go`), re-implements the formula chain locally
  (`H = G·C`, `J = H·I`, `L = J·K`, `P = (J+L)·(1+O)·N`, `R = P·Q`,
  `V = P·(V₃/12)·U`, `AD = H·AB·AC`, `AE = W of SBR-Shreded[thk=D]`,
  `W = P+R+T+V+AD+AE`, `Y = W/(1−X)`, `Quote = CEIL(Y/(1−Z), step)`),
  and writes (a) `docs/forms/data/epdm-pricelist.json` plus (b) one Firestore
  doc per row. Two-pass compute handles the AE backing lookup for layered
  EPDM/TPV. **Quote parity vs the sheet: 10/10 spot-checked rows match
  exactly** (SBR Granule, Sand Infill, Rubber Infill, SBR Shreded, EPDM Miroad,
  EPDM Eurosia Non-UV, EPDM Eurosia UV, TPV UV).
- **`scripts/import_categories_shared.py`** — writes two new
  brand-agnostic category docs (`product_categories/epdm`,
  `product_categories/infill`) in the `leka-product-catalogs` database,
  parallel to the existing per-brand `product_categories_{brand}` ones.
  `brand: null` marks them shared.
- **Firestore** (`leka-product-catalogs` database):
  - `products_epdm` — 53 docs (SBR Granule + SBR Shreded + EPDM Miroad +
    EPDM Eurosia Non-UV/UV + EPDM Custom Graphic + TPV UV)
  - `products_infill` — 5 docs (Sand 16/30 + 20/40 + SBR 4/7 kg/sqm + TPE 4 kg/sqm)
  - Each doc carries `cfh_m: number` at top level so other projects can ask
    "given fall height ≥ X m, which thickness/SBR/system is the cheapest
    compliant option?" via
    `db.collection("products_epdm").where("cfh_m", ">=", X)
       .order_by("cfh_m").order_by("pricing.quote_thb_per_sqm").limit(1)`.
- **`docs/forms/epdm-pricer.html`** — single-file static page, Leka Design
  System styled (Manrope, `#8003FF`, 16px cards, navy header, amber CFH
  badge). Left pane: product picker + per-row inputs. Right pane: global
  params + live cost breakdown ending in the boxed final Quote. Pure
  client-side JS mirrors the same 2-pass calc so changing globals re-flows
  every backing lookup. Served via gateway at
  `https://gateway.goco.bz/leka-product-catalogs/forms/epdm-pricer`
  (private, sign-in-gated per Rule 14).
- **`firestore/firestore.indexes.json`** — three new composite indexes:
  `products_epdm(status, cfh_m, pricing.quote_thb_per_sqm)`,
  `products_epdm(system, cfh_m, thickness_mm)`,
  `products_infill(system, pricing.quote_thb_per_sqm)`. All deployed.
- **`hub.config.json`** — classification hint so the pricer lands under
  Forms on the regenerated `docs/hub.html`.

### CFH lookup contract for downstream projects

Database: `leka-product-catalogs` · Collection: `products_epdm` ·
Query: `where status==active and cfh_m >= <required>` ordered by
`cfh_m ASC, pricing.quote_thb_per_sqm ASC`. Smoke-tested live:
`cfh_m >= 1.5` returns `EPDM Blk 50/0` (1.6 m, 5,155 THB/sqm) and
`EPDM E 10/40` (1.6 m, 3,195 THB/sqm) — cheapest Eurosia Non-UV option.

### Files
- NEW `scripts/sync_epdm_pricelist.py`
- NEW `scripts/import_categories_shared.py`
- NEW `docs/forms/epdm-pricer.html`
- NEW `docs/forms/data/epdm-pricelist.json` (58 products + defaults + source)
- MOD `firestore/firestore.indexes.json` (+3 composites)
- MOD `hub.config.json` (classification_hints)
- MOD `PROJECT_INDEX.md` (CFH lookup contract section)
- REGEN `docs/hub.html`, `docs/build-summary.html`, `docs/architecture.html`
- BUMP `VERSION` 2.17.0 → 2.18.0

## [2.17.0] - 2026-05-13

### Changed — Wisdom → Leka Project rebrand (customer-facing)

Customers now see the formerly-Wisdom vendor's 5,062 products as the in-house
"Leka Project" brand. The upstream supplier identity is hidden behind Leka's
own house brand across every customer-visible surface in Medusa.

### Medusa data changes (live, scripted, idempotent)

- **Sales channel `sc_01KNKTHC0B7KFEDSZ3NNM49JQW`**: name `"Wisdom"` →
  `"Leka Project"`; description updated. ID unchanged so the publishable key
  binding and storefront env vars stay valid.
- **Publishable API key `apk_01KNKTHXDJ344T8V131SKJPNEK`**: title
  `"Wisdom Storefront"` → `"Leka Project Storefront"` (token unchanged — no
  storefront re-deploy required).
- **5,061 products** got fresh opaque handles `leka-project-{nanoid8}` and
  fresh opaque variant SKUs `LP-{NANOID8}`. Old handle preserved in
  `metadata.legacy_handle`; old SKU in `variant.metadata.legacy_sku` for
  procurement / quotation cross-reference. One stray `test-swing` product
  was skipped (not a real Wisdom product).
- **32 titles + 32 descriptions** had embedded "Wisdom" / "WISDOM" /
  "Wisdom Toys" strings stripped.
- **6,228 product image URLs + 2,835 thumbnails** rewritten from
  `https://catalogs.leka.studio/api/i/wisdom/...` →
  `https://catalogs.leka.studio/api/i/leka-project/...`.

### Image bucket (Gemini-cleaned)

- New cleaned-image prefix `gs://ai-agents-go-vendors/leka-project/` populated
  by `scripts/strip_wisdom_logos.py`. Originals kept untouched at
  `gs://ai-agents-go-vendors/wisdom/` for audit + rollback.
- **Pass-1 (logo detection):** 37,975 / 37,976 images classified via Gemini
  2.5 Flash. **814 images contain Wisdom branding** (2.14%); 37,161 are clean.
  Per-image checkpoint persisted in Firestore `image_logo_scan/{sha1(path)}`.
- **Pass-2 (logo removal):** 814 hits fed to Gemini 2.5 Flash Image
  (Nano Banana Pro) at `location=global`. Final counts after error mop-up:
  ~625 OK / ~185 manual_review / ~5 hard errors. QA-failed edits routed to
  `gs://ai-agents-go-vendors/manual_review/` for human follow-up. Per-image
  state in Firestore `image_logo_edit/{sha1(path)}`.
- **Bulk copy:** 37,161 no-logo blobs server-side-copied to `leka-project/`
  in 4.5 minutes (zero Gemini cost).
- **Cost:** ≈ $5 Flash + ≈ $30 Nano Banana Pro = ~$35 in Vertex AI.

### Storefront-side coordination (next: leka-website)

- The leka-website image proxy at `catalogs/src/app/api/i/[...path]/route.ts`
  is already prefix-agnostic (`/api/i/<vendor>/...` →
  `gs://ai-agents-go-vendors/<vendor>/...`), so the new
  `/api/i/leka-project/...` URLs resolve with **zero code changes**.
- Outstanding for leka-website (separate PR): rename the `wisdom` brand-route
  to `leka-project`, swap the brand registry entry, replace the logo asset,
  and 301 the old `/catalogs/wisdom/*` URLs. The redirect map for product
  handles ships with this commit at `migration/wisdom-handle-redirects.json`
  (5,061 entries) for storefront middleware to consume.

### Added — three new scripts

- `scripts/strip_wisdom_logos.py` — three-phase pipeline (`--scan-only`,
  `--edit-only`, `--copy-only`). Idempotent + resumable via Firestore
  checkpoints. Tolerant JSON parser, exponential-backoff retry on 429/5xx,
  schema flattened to avoid Vertex `Nested arrays are not allowed` rejection.
- `scripts/rebrand_wisdom_to_leka_project.py` — orchestrates SC rename,
  publishable-key rename, product handle/SKU regeneration. `--dry-run` and
  `--revert` supported. Writes `migration/wisdom-handle-redirects.json`.
- `scripts/rewrite_wisdom_image_urls.py` — flips Medusa product
  `images[].url` and `thumbnail` from `/api/i/wisdom/...` to
  `/api/i/leka-project/...`. Idempotent.

### Notable lessons learned

- Gemini Flash schema with nested arrays (`bboxes: array of array of number`)
  hits a hard `400 Nested arrays are not allowed` server-side validator. Use
  array of objects or a flat numeric array instead.
- Gemini image-edit refuses prompts that name a third-party trademark
  ("remove the Wisdom logo" → policy refusal). Brand-neutral framing
  ("remove overlay text and small graphics, preserve product") works.
- Vertex `gemini-2.5-flash` at `location=global` has tight quota
  (~5 RPM-effective with bursts). Concurrency above 4 reliably trips
  RESOURCE_EXHAUSTED storms.

### Files changed
- `scripts/strip_wisdom_logos.py` (new)
- `scripts/rebrand_wisdom_to_leka_project.py` (new)
- `scripts/rewrite_wisdom_image_urls.py` (new)
- `migration/wisdom-handle-redirects.json` (new, force-tracked)
- `CHANGELOG.md`, `VERSION`

### Outcome

Live Medusa Production: 5,061 Wisdom products rebranded to Leka Project on
2026-05-13. Storefront images resolve via the existing image proxy.
~185 manual_review + ~5 hard-error images need human inpainting follow-up
(<0.5% of catalog).

---

## [2.16.0] - 2026-05-13

### Added — Multi-currency variant pricing + Firestore-driven variants in `sync_vendors_to_medusa.py`

Extended the cross-brand Medusa sync to read 4-currency pricing (USD/THB/EUR/SGD)
and Firestore-declared `variants[]` arrays, used by the new Eurotramp 2025
pricelist pipeline in [eukrit/vendors](https://github.com/eukrit/vendors)
`eurotramp-catalog/scripts/` (BUILD_LOG `[1.10.1]`).

- `_build_prices()` (new) — emits a Medusa `prices[]` array from
  `pricing.retail_{usd,thb,eur,sgd}` in minor units. Falls back to legacy
  `pricing.fob_usd` (USD-only) so previously-seeded brands still work.
- `_update_variant_prices()` (renamed from `_update_variant_price`) — PATCHes
  all currencies in a single body, reusing existing `price.id` per
  `currency_code` so price rows aren't orphaned. Endpoint corrected to
  Medusa v2: `POST /admin/products/{product_id}/variants/{variant_id}`.
- `_build_create_payload()` — when a Firestore doc carries `variants[]`,
  emits one option (`variant_option` field, e.g. `Coating`) + one Medusa
  variant per entry with per-variant `prices[]`. Single-variant docs
  unchanged (Default/Default).
- `_ensure_variants()` (new) — for existing Medusa products, upserts any
  `variants[]` entries that aren't on the product yet; skips with a log
  when the product was created with the legacy `Default` option only
  (needs one-off admin migration to add the new option).
- `_find_product_by_handle()` — now returns `options.{id,title,values.value}`,
  `variants.{title,sku,options.value,options.option_id}`, and
  `variants.prices.{id,currency_code,amount}`.

Live run on Eurotramp (sales channel `sc_01KNQAA3Y72W17B7CP2VQ93T3M`):
**187 products · 105 created · 187 updated · 123 priced · 0 errors**.
Spot-check `eurotramp-kids-tramp-playground`: USD $3,572.10 / THB ฿118,047.75
/ EUR €3,043.43 / SGD $4,544.84.

One-off store config: PATCHed `store.supported_currencies` to add `sgd`
(was `eur, thb, usd`).

- **Files modified:** `scripts/sync_vendors_to_medusa.py`, `CHANGELOG.md`.
- **Backwards compat:** brands without `pricing.retail_*` (vortex, wisdom,
  vinci, berliner) keep USD-only pricing via the legacy `pricing.fob_usd`
  path. No re-run required.

## [2.15.1] - 2026-05-13

### Changed — Berliner gross margin 40 % → 25 %

Berliner-specific markup retune. `GROSS_MARGIN = 0.25` in
`berliner-catalog/import_pricelist.py` (Vinci keeps its 40 %). Re-ran the
landed-cost importer (801 Firestore docs refreshed) and re-pushed prices to
Medusa. All Berliner retail prices scaled by ×0.80 (= 0.60 / 0.75).

### Fixed — `push_pricelist_to_medusa.py` name-only lookup

The first GM-25 re-push CREATEd 405 duplicate products (handles `*-3`/`*-4`)
because the original script only looked up rows by `item_code`. Name-only
pricelist rows (no SKU) bypassed the match path and re-CREATEd instead of
UPDATEing the v2.15.0 originals.

- Fixed by using the CSV row's `handle` (already uniquified by parser with
  `-2`/`-3` suffixes on name collisions) as the synthetic SKU lookup key —
  matches the SKU that `create_product` writes for name-only rows
  (`variant.sku = sku or handle`), so subsequent runs round-trip as
  UPDATEs.
- Added `berliner-catalog/delete_duplicate_products.py` to clean up the
  damage. Filter is **time-windowed by `--since` against `created_at`** so
  real product SKU-style handles like `berliner-spaceball-l-02` (Spaceball
  L.02, created during initial scrape) are not matched. Deleted 405 dupes
  with 0 errors.
- Final re-push: 722 updated + 6 created + 73 skipped + 0 errors.

Sample: LU.001.001 retail THB 2,546,873 → **2,037,498** / USD 77,068 →
**61,654** / EUR 65,662 → **52,529**. Solar Explorer THB 52,312 → **41,849**.
944 total Berliner products in Medusa SC.

## [2.15.0] - 2026-05-13

### Added — Berliner Seilfabrik pricelist load (Compendium 11, 2026)

First Berliner data load. Parses the 2026 Compendium 11 EN-Ausland pricelist PDF
(11 pages, 801 SKUs/lines) and pushes products + THB/USD/EUR retail prices
through the same landed-cost pipeline Vinci uses. Trade terms are EXW; our EXW
cost is 15 % off the published list, then the Vinci EU-LCL cost engine
(Baltic-rate calibrated, tier-clamped, 40 % GM) produces THB landed and retail.

**New code**
- `berliner-catalog/parse_pricelist.py` — PyMuPDF `find_tables()` extraction.
  Detects 4- and 5-column schemas (some tables drop the leading "Page" col).
  Synthesizes handles from item code; falls back to slugified name when an
  accessory row has no SKU. Disambiguates collisions with a counter suffix.
- `berliner-catalog/import_pricelist.py` — mirrors
  `vinci-catalog/import_pricelist.py`. Reads pricelist CSV, applies 15 % EXW
  discount, computes landed THB via the shared
  `shipping-automation/mcp-server/cost_engine`, applies the standard Vinci
  `LOGISTICS_TIERS` floor/cap, marks up to 40 % GM, and upserts
  `vendors/berliner/products/{handle}` in Firestore. Reads existing dimensions
  if a prior website scrape populated them; otherwise every row takes the
  `flat_uplift` path. `GOOGLE_APPLICATION_CREDENTIALS` is read from env (no
  hardcoded SA path).

**New artifacts**
- `berliner-catalog/data/pricelist_2026-01-01.csv` — parsed PDF
- `berliner-catalog/data/pricelist_2026-01-01_landed.csv` — landed cost
- `berliner-catalog/DEPLOYMENT_LOG.md` — initial load
- `docs/berliner.html` — Leka-styled summary page

**Counts**
- 801 rows: 380 priced+SKU, 348 priced/name-only, 16 SKU on-request, 57
  name-only on-request
- 728 `flat_uplift` + 73 `n/a` (on-request) — 0 dim-matched (no scrape yet)
- Firestore: 801 docs under `vendors/berliner/products`
- Medusa: 801 rows reconciled with the existing Berliner sales channel
  (`sc_01KNQAA3QDYHP15Y9K4PPRMDF0`, ~498 pre-scrape products): **349 updated**
  + **440 created** + **12 skipped** + **0 errors**. On-request rows pushed as
  `draft` with no price; priced rows carry THB+USD+EUR retail.

**Mismatch discovery**: the generic `scripts/sync_vendors_to_medusa.py` couldn't
be used as-is because the prior Berliner scrape used `berliner-<slug(name)>`
handles (e.g. `berliner-swingo-02`) while our pricelist parser produced
`berliner-<slug(item_code)>` (e.g. `berliner-90-160-141`). Lookup by handle
missed every existing product, then CREATE collided on the duplicate SKU.
`push_pricelist_to_medusa.py` solves this by paginating the SC, building a
SKU → variant map, and routing each row to UPDATE-by-SKU or CREATE-with-
slug-of-name.

**Sample math (verified)**
- berliner-lu-001-001 (LevelUp.01.1) list EUR 34,333 → EXW EUR 29,183 (×0.85)
  → THB FOB 1,131,931 → landed THB 1,528,124 (flat_uplift) → tier-band cap
  (EUR≥10 k → 35-80 % logistics, clamp inactive) → retail THB 2,546,873 / USD
  77,068 / EUR 65,662 (÷0.60 GM)

## [2.14.1] - 2026-05-13

### Fixed — Vinci series filter (badges + `/vinci/series/<slug>` page) returned 0 products

**Symptom:** On `catalogs.leka.studio/vinci`, clicking any series badge emptied the
product grid; deep-linking to `/vinci/series/<slug>` also rendered 0 products.
Berliner / 4soft / Vortex were unaffected.

**Root cause:** All 1,096 Vinci products had `collection_id = null` on the Medusa
backend, while their `metadata.series_slug` / `metadata.series_name` were
populated and the 27 Vinci collections (`pcol_…`) themselves still existed. An
earlier Vinci re-import wrote products under a flattened handle scheme
(`vinci-{item_code}` instead of `vinci-{series_slug}-{item_code}`) and dropped
the `collection_id` field — the badges queried `?collection_id=pcol_…` and got
0 matches. Probed via the four brands' publishable keys: Berliner / 4soft /
Vortex returned 100% `collection.id` populated; Vinci returned 0/100.

**Fix:**
- Added `MedusaImporter.set_product_collection(product_id, collection_id)` —
  one-line wrapper around `POST /admin/products/:id` to set the collection link.
- New script `vinci-catalog/relink_collections.py` — paginates all products in
  the Vinci Sales Channel via Admin API, reads `metadata.series_slug`,
  get-or-creates the matching collection (idempotent), and PATCHes each product
  with the correct `collection_id`. Run with `--dry-run` first.

**Result:** 1,096 / 1,096 products relinked, 0 errors. Verified post-fix:
- `ACTIVE` (pcol_01KNKVFBG2WD4GHG6GRR86QSFF) → 11 products
- `ROBINIA` (pcol_01KNKVHCSNDZGHQWAFVJVTR49F) → 255 products
- All 27 Vinci series filters now functional.

### Verified — all four collection-bearing brands

| Brand | Own collections | Sample filter | Products |
|---|---|---|---|
| Vinci Play | 27 | `workout` | 54 |
| Berliner Seilfabrik | 18 | `berliner-univers` | 1 |
| 4soft | 3 | `4soft-tunnels-furniture` | 48 |
| Vortex Aquatics | 8 | `vortex-uncategorized` | 272 |

### Files changed
- `shared/medusa_importer.py` — `set_product_collection` helper
- `vinci-catalog/relink_collections.py` — new one-off relink script
- `CHANGELOG.md`

### Storefront note
No `leka-website/catalogs/` changes were needed; the storefront's
`collection_id` filter call (`catalog-content.tsx:141`,
`series/[slug]/page.tsx:36`) was already correct. The fix is
backend-data-only.

---

## [2.15.1] - 2026-05-13

### Documented — the "remaining 103 uncovered drafts" are AI-Vision-inferred, not orphans

The v2.15.0 followup report flagged "~91 real-SKU drafts still uncovered" as
needing another image source or hand curation. Investigation surfaced the
real story: those 103 docs were created by the **upstream Anthropic-Vision
scrape pipeline** (well before this session) and already contain full
English `name`, `description`, and `category` fields. They look "uncovered"
only because they predate v2.13.0's source-priority guards and lack a
`source_url_*` field.

Examples of what's actually in these docs (sampled):
- `AT0002` "Tactile Path - Nature" — full description, balance category
- `ED0001` "Edusante Trike" — full description, motor-skill category
- `KB0001` "Jumbo Blocks" — full description, construction category
- `KB0007` "Translucent Honeycomb" — full description, sensory category
- `KC0015` "Log & Roll", `KC0016` "Tai Chi Ball", `KC0018` "Step 'n' Stones",
  `KC0019` "Wavy Tactile Path", `KC0021` "Tactile Board", `KC0022`
  "Tactile Stepping Stone" — all with rich descriptions

The docs even carry an audit trail in their `notes` field:
"Product identified as Weplay X (SKU) based on visual appearance.
Specifications are not available in the image."

#### `scripts/stamp_weplay_ai_inferred.py` (new)
Stamps these 103 docs with explicit lineage:
  - `source_ai_inferred = True`
  - `source_ai_pipeline = "anthropic_vision_v1"`
  - `source_ai_sha = <existing source_sha>`

Doesn't change `status` (kept as draft — SKU assignments are AI-inferred
and may not match the real catalog), `name`, or `description`. Just makes
the lineage visible so future enrichment passes know to treat these as
"covered with caveat".

By prefix: KC=55, KM=20, KP=13, KB=4, KS=4, KT=2, AT=1, ED=1, KF=1,
KY=1, WJ=1.

#### Why they stay drafts
The AI inference IS plausible and the descriptions read well, but:
1. SKU may not match Weplay's actual catalog (e.g. `KC0010` was AI-tagged
   "Tai Chi Ball", but Vision OCR of the 2025 catalog also tagged
   `KC0016` as "Tai Chi Ball" — same product, different inferred SKUs).
2. No images attached — would render as placeholder cards on storefront.

To promote any of these to active in a future pass would require:
1. Cross-referencing the inferred SKU against the catalog OCR data
   (`scripts/ocr_weplay_local_pdfs.py` dump) for confirmation.
2. Image attachment (likely from `source_sha` page lookup).
3. Probably a manual review step.

Out of scope here. The stamp + documentation is enough to prevent future
"~91 uncovered" reports and clarify the gap.

### Composite catalog state (unchanged from v2.15.0)
`catalogs.leka.studio/weplay`: still **200 active product cards**. The
103 AI-inferred drafts remain drafts — high-quality candidates for a
future manual review pass.

### Files changed
- `scripts/stamp_weplay_ai_inferred.py` (new)
- `CHANGELOG.md`

---

## [2.15.0] - 2026-05-13

### Added — Weplay catalog 149 → 200 via Vision OCR of image-only catalog PDFs

Two new scripts that close the last open growth path: Gemini-Vision-OCR
of the four image-only PDFs in the local Drive folder that v2.14.0
skipped (`2025-2026`, `2020-2021`, `2022-2023`, `New Products 2021-2023`,
totaling 330 pages, ≤135 chars/page text-extractable).

#### `scripts/ocr_weplay_local_pdfs.py` (new)
PyMuPDF renders each PDF page to a 180-DPI JPG; Gemini 2.5 Flash extracts
`{sku, name_en, description_en, age_range}` per visible product card.
Resumable via JSON checkpoint dump every 5 pages. Same writeback safety
as flipbook: only writes when no `source_url_*` is set.

**Run:** 330 pages processed, **198 unique SKU tokens** extracted,
148 with rich descriptions (>30 chars), 174 with age ranges. Source
attribution: 2025 (516 mentions), 2022-2023 (381), 2020-2021 (314),
New Products (9 — mostly section dividers).

Writeback: 162 matched to existing docs → 153 already covered →
**9 new draft writes** (KC0007 Icy Ice Building Set, KC0008 Forever
Up-Down, KC0009 Infinite Loop, KC0010 Tai Chi Ball, KC0011 Putt Putt
Balance Board, KC0013 Tai-Chi Balance Board, etc).

#### `scripts/create_weplay_pdf_only_docs.py` (new)
For the 77 SKUs the OCR found that DON'T have any Firestore product
yet, create new docs with `status="draft_no_images"`, EN name +
description from OCR, category inferred from SKU prefix
(`PREFIX_CATEGORY` map: KB=balance, KM=motor-skill, KT=sensory,
KP=construction, KC=construction, KE=classroom-furniture,
KF=ball-play, EM=motor-skill).

Notable additions: KT7001-KT7006 (Helix Balance Path, Jungle Trial,
Coral Adventure, Rainbow River Stones, Wavy Tactile Path, Tactile
Curve Path), KC0012 (Maze Balance Board), KM4001 (Team Walker),
KT0001 (Stepping Stones), KT0004 (Tactile Straight Path).

URL-safe handle slugifier added (`re.sub(r"[^a-z0-9._-]+", "-")`)
after first sync attempt rejected `kt3310-(l)` / `ke0311...(l)..(s)`
handles with `Invalid product handle` errors.

#### Bug fixed — `shape_weplay_to_medusa_schema.py` was clobbering data
The original shaping script (v2.8.4) wrote `name = product_name or sku`
unconditionally, then `images = []` when no URL-encoded SKU folder match
existed. Re-running it after EN content + thumb-image ingest had landed
**clobbered** the EN names back to Chinese product_name and **nuked**
the thumb images on the 36 promoted-via-thumb drafts.

Detected via spot-check after running shape post-PDF-OCR. Recovered by
re-running scrape_weplay_en + scrape_weplay_cached + ingest_weplay_images
(all idempotent). Patched the shape script to be safe by default:
  - `name` only set if doc has no existing `name` (so EN scraper writes
    win on re-run).
  - `images` only set when this run finds attachments AND doc has no
    existing `images[]` (preserves thumbs).
  - `status` only flipped TO active — never demoted by this script.

The recovery turned out to be a net win: re-running the cached scrape
caught additional drafts the prior pass had missed, raising the
post-recovery active count from the pre-shape 149 to **200**.

#### Vision rank rerun + thumbnail sync
After the catalog grew to 200, vision_rank_weplay_images.py picked up
the previously-unscored ~460 images plus all the new actives:
**+462 scored, +74 reordered, +71 primary photo changes**. Cumulative
across all session runs: ~1,060 images scored.

`sync_weplay_thumbnails.py` pushed the 71 thumbnail changes + 70+ image
order updates to Medusa. End-state dry-run: 200/200 in sync, 0 changes
needed, 0 errors.

#### Final composite catalog
- **`catalogs.leka.studio/weplay`: 200 active product cards** (was 149
  in v2.14.0, +34% jump)
- All 200 carry English names + descriptions (sourced from `.tw?lang=en`
  live, GCS-cached HTML, 2025 flipbook OCR, OR 2020/2022/2025 PDF
  Vision OCR)
- 71 lifestyle/kids-using primary photos picked by Gemini Vision
- Provenance fields per product: `source_url_en`, `source_url_cached`,
  `source_url_flipbook`, `source_url_local`, `source_url_pdf_ocr`

#### Reversed prior conclusion (v2.14.0)
v2.14.0 concluded that `KC0007`–`KC0030` were "scrape artifacts" because
none of the text-extractable sources had them. Vision OCR proved them
**real Weplay products** (Icy Ice Building Set, Tai Chi Ball, Infinite
Loop, etc.) just hidden inside image-only PDFs. The previous
"definitive answer" was definitively wrong.

### Files changed
- `scripts/ocr_weplay_local_pdfs.py` (new)
- `scripts/create_weplay_pdf_only_docs.py` (new)
- `scripts/shape_weplay_to_medusa_schema.py` (safety patch)
- `CHANGELOG.md`

### Remaining (small)
- ~91 Firestore draft tokens still uncovered (real-SKU `item_code`
  with no source). Need another image-only catalog edition or hand
  curation. Many likely color variants (e.g. `KC0013-B`) that match
  the parent SKU's URL pattern but have separate Firestore docs.

---

## [2.14.0] - 2026-05-12

### Investigated — local Google-Drive Weplay catalogs (closes upstream-data debate)

Mined `C:\Users\Eukrit\My Drive\Catalogs GO\WePlay Catalogs\` (5 PDF
catalogs 2020–2026, 2 Excel pricelists, 2 quotation PDFs). Built
`scripts/ingest_weplay_local_catalogs.py` to parse all text-extractable
sources and merge into Firestore using the same source-priority writeback
as the cached and flipbook scripts.

#### Result
113 unique SKUs found across local sources → 100 already had richer
source data (live/cached/flipbook) → only **1 truly new write**
(KP4003 "Weplay Twinkle Stones" — pulled from the 2021 Powen pricelist).

#### Definitive finding on the "uncovered drafts"
Of the 113 draft products with extractable SKU tokens that had no
catalog source attached:
  - **112 are scrape artifacts** — synthetic SKUs like `KC0007`–`KC0030`
    that don't exist in ANY of the five PDF catalogs (2020-2026), the
    Excel pricelists, or the 2020 quotations. Real Weplay numbering
    jumps from `KC0001`–`KC0006` directly to `KC1801`/`KC2001`/`KC2802`,
    so the entire `KC0007`–`KC0030` range is upstream pipeline noise.
  - **1 (KP4003)** is real but discontinued, recovered from 2021
    pricelist.

These 112 ghost SKUs should be archived/deleted as a future cleanup —
they're polluting the `vendors/weplay/products/*` collection but will
never become real products.

#### 40 catalog-only SKUs (legitimate gap)
Local catalogs surfaced 40 real SKUs we don't have Firestore docs for:
EM5501–EM5531 (Edusante line), KC1801/KC2008/KC2009 (Creative Mat /
Puzzle Fun), KC2803–KC2805, KE0014/KE0015 (Cot), KE0311/KE0312 (Modern
Ball Chair), KF0005 (Tricky Fish), KM4001/KM5514, KP0002 (Circular
Balancing Board), and others. These could become new active products
in a future pass — they have names + sometimes prices, just need image
sources matched.

#### Image-only PDFs skipped
2025 (95p), 2020-2021 (83p), 2022-2023 (91p), and New Products 2021-2023
(61p) PDFs have ≤135 chars/page (image-only). Vision OCR via Gemini
would cost ~$30-50 across 330+ pages — deferred unless the 40
catalog-only SKUs warrant it.

### Files changed
- `scripts/ingest_weplay_local_catalogs.py` (new)
- `CHANGELOG.md`

### Composite catalog state on `catalogs.leka.studio/weplay`
- **149 active products** (no change from v2.13.0 — local sources
  largely overlap)
- 1 more product with EN content (KP4003, still draft until image
  ingest)
- Catalog growth path is now exhausted from automated EN sources;
  further growth requires (a) bulk-creating Firestore docs for the 40
  catalog-only SKUs + sourcing their images, or (b) Vision OCR on the
  330+ image-only catalog pages.

---

## [2.13.0] - 2026-05-12

### Added — Weplay coverage closes follow-ups: catalog 136 → 149 + cached/flipbook fallback sources

Three small follow-up scripts that close out the v2.12.0 out-of-scope items
(missing actives, unreachable drafts, unscored vision images).

#### `scripts/scrape_weplay_cached.py` (new)
Mines `gs://ai-agents-go-vendors/weplay/pages/*.html` (1,453 pages from
the original scrape) for English product detail content the live
crawler missed. Same parser as `scrape_weplay_en.py`; only writes when
the doc lacks both `source_url_en` and `source_url_cached`.

**Result:** 597 cached HTML pages parsed → 181 unique SKUs → 31 new
Firestore writes. Recovered EN content for 4 of the 9 originally-missing
actives (KB1303 Gym Ball, KB1307 Gym Roll, KC3001 Learning Cube, KC3004
Stepping Shape) plus 27 more drafts. After re-running the existing
ingest pipeline + Medusa sync: **+13 new active products promoted**.
Catalog grew **136 → 149**.

The remaining 5 missing actives (KC0001, KP1001, KP1002, KP1003, KT0003)
aren't in any cached page — likely never crawled.

#### `scripts/ocr_weplay_flipbook.py` (new)
OCRs the 188-page Weplay EN 2025 Flash flipbook (one high-res JPG per
page at `weplay.com.tw/download/EN/Catalog/2025/files/mobile/N.jpg`)
via Gemini 2.5 Flash. Per-page prompt asks for every product card on
the page as `{sku, name_en, description_en, age_range}`.

**Result:** 257 SKUs extracted, 251 matched to Firestore docs, 248
already had richer source data (live or cached) and were skipped, **3
new writes** (KM1004 Balance Rocking Ice, KM1006 Honey Hills, KM1007
Coral Adventure). 103 catalog SKUs found with no matching Firestore
doc — could become new products in a future pass. Cost ~$2-3.

The 116 originally-uncovered drafts are mostly OLDER products
(`KB0001`, `KC0007` style) discontinued before the 2025 catalog — the
flipbook doesn't help them. They'd need an older catalog edition or
hand-curation.

#### Vision rerun (no new script — `vision_rank_weplay_images.py --apply` again)
Second pass picked up the ~460 images Gemini 429'd on first run.
**+110 images scored, +15 reordered, +8 primary changes.** Cumulative
totals across the two passes: 600 images scored, 82 products
reordered, 66 new card thumbnails.

### Composite outcome
- `catalogs.leka.studio/weplay`: **149 product cards** (was 136 in v2.12.0)
- Provenance fields per product: `source_url_en` (live), `source_url_cached`
  (GCS HTML), `source_url_flipbook` (page N OCR) — explicit lineage
- Drafts left: 113 with real-SKU `item_code` not in any source we tried
  (mostly KB0001-style discontinued products)

### Files changed
- `scripts/scrape_weplay_cached.py` (new)
- `scripts/ocr_weplay_flipbook.py` (new)
- `CHANGELOG.md`

---

## [2.12.0] - 2026-05-12
## [2.9.1] - 2026-05-10

### Verified — backend pipeline green end-to-end

Manually submitted `cloudbuild.yaml` against `medusa-backend/` to validate the
v2.8.5 db-migrate fix had actually been exercised — it had not, because no
Cloud Build trigger exists for this repo (the storefront's build was driven
manually too). Build [`5628a71c-3485-47dd-bf29-4eb99fdeefa4`](https://console.cloud.google.com/cloud-build/builds;region=asia-southeast1/5628a71c-3485-47dd-bf29-4eb99fdeefa4?project=538978391890):
4m3s, **SUCCESS** through all four steps (build / push / db-migrate / deploy).
Backend image `medusa-backend:fixmigratetest` is now serving on Cloud Run
service `leka-medusa-backend`. Storefront at `https://catalogs.leka.studio/`
continues to call this backend — no client-visible change.

### Added
- **Cloud Build trigger `deploy-leka-medusa-backend`** — watches `main` branch
  on `eukrit/leka-product-catalogs`, build config `cloudbuild.yaml`, included
  files `medusa-backend/**` + `cloudbuild.yaml`. So future backend changes
  auto-deploy the same way the storefront now does. Service account
  `claude@ai-agents-go.iam.gserviceaccount.com` runs the build.

### Out of scope (still TODO)
- `medusa-backend/Dockerfile` — Medusa v2 `.medusa/server` structure mismatch.
  The fact that builds pass and the runtime works suggests the mismatch is
  cosmetic / partial; flagged as a separate task to clean up the layered
  COPY in stage 2 and confirm `.medusa/server` is the canonical location.
- Wisdom palette audit (lives in `eukrit/leka-website`).

---

## [2.9.0] - 2026-05-10

### Removed — Next.js storefront migrated to `eukrit/leka-website`

The multi-brand storefront moved to the leka-website repo on 2026-05-10 (commit
`1cf31cf`, leka-website v0.7.0). It now ships from `catalogs/` in that repo,
deploys to a new Cloud Run service `leka-catalogs`, and serves
`https://catalogs.leka.studio/` (verified live, all 4 brand routes 200, TLS
provisioned). The old service `leka-medusa-storefront` is cold-scaled
(`min=0, max=1`) for 24h rollback safety; full deletion follows once the new
stack is validated.

This repo now owns only the Medusa v2 backend (`medusa-backend/`) and the
data-prep / vendor-shaping scripts. Backend → Storefront contract unchanged:
storefront still calls `https://leka-medusa-backend-538978391890.asia-southeast1.run.app`
via per-brand publishable keys (which moved to leka-website's
`cloudbuild-catalogs.yaml`).

### Removed
- `medusa-storefront/` — full Next.js app, public assets, configs, Dockerfile.
- `cloudbuild-storefront.yaml`, `cloudbuild-storefront-only.yaml` — orphan pipelines.
- `cloudbuild.yaml` Steps 5–7 (build-storefront, push-storefront, deploy-storefront)
  + the `medusa-storefront` images output. Backend pipeline (Steps 1–4) is unchanged.

### Out of scope (still TODO in this repo)
- `medusa-backend/Dockerfile` — Medusa v2 `.medusa/server` structure mismatch.
- `cloudbuild.yaml` `db-migrate` step — currently broken; backend deploys remain
  red until this is fixed (independent of the storefront migration).
- Wisdom palette audit (referenced by leka-website, not this repo).

## [2.8.5] - 2026-05-10

### Fixed — Cloud Build `db-migrate` step (Missing script error since v2.8.3)
- v2.8.3 changed step 3 from `npx medusa db:migrate` to `npm run db:migrate` but didn't account for entrypoint-override behavior: when Cloud Build runs a step with a custom `entrypoint`, the container CWD is `/workspace` (the host workspace mount), NOT the image's WORKDIR (`/app`). So `npm run db:migrate` ran in `/workspace` where no `package.json` exists → `npm error Missing script: "db:migrate"`.
- Every build since 4e31de5 failed at this step, including the `feat(weplay)` merge (build `66cfff32`).
- Fix: switch to `entrypoint: bash` + `args: ['-c', 'cd /app && npm run db:migrate']` so CWD is explicitly set inside the container before npm runs.

### Files changed
- `cloudbuild.yaml`

---

## [2.8.4] - 2026-05-10

### Added — Weplay catalog live (path 1B: imaged subset)
- Created Medusa Sales Channel **Weplay** (`sc_01KR6Z0VBSXWYZDVGF30EAP0EQ`) + publishable key `pk_2b18dd5670830702993445fe43f4269a406baab0b20f85cad15d43b9b9a9efbb`. Linked the key to the SC.
- Imported **100 Weplay products** (KC/KM/KT/KB/KP series) into the new SC. All published, all with images, no USD prices (Weplay catalog policy).
- Storefront URL: `https://catalogs.leka.studio/weplay` (live after CI/CD deploy).

### Fixed — `sync_vendors_to_medusa.py` two real bugs found during the Weplay run
- **`prices` field omission rejected by Medusa v2** — when `pricing.fob_usd` was missing, the script omitted `variant.prices` entirely, and Medusa returned `{"type":"invalid_data","message":"Invalid request: Field 'variants, 0, prices' is required"}` for all 100 products. Fix: always send `prices: []` when no FOB price exists. (This bug presumably affects Berliner / Eurotramp / 4soft re-syncs too — they all use the same code path. Tested: 100/100 success after fix.)
- **`--skip-no-images` flag** — additive opt-in flag that filters out products with empty `images[]` before sync. Used for Weplay path 1B to ship only the 100 products with confirmed photos and skip the 1,095 `draft_no_images` records left for path 2.

### Added — `scripts/shape_weplay_to_medusa_schema.py`
- Converts the upstream Weplay scrape's per-product schema (`product_name`, `sku`, no `handle`, no `images[]`) into the schema `sync_vendors_to_medusa.py` expects (`name`, `item_code`, `handle`, `images[]`, `status`).
- Image join: indexes `vendors/weplay/attachments/*` by URL-encoded SKU folder pattern (`/Products/<XX>/<SKU>/`); joins each product whose `sku` contains a matching token. Only ~8% of attachments carry the URL-encoded SKU and ~8.4% (100/1,195) of products end up with images. The remaining 1,095 products are written back with `status="draft_no_images"` so the sync filter can skip them. **Path 2 follow-up will source images for the rest** (likely via re-running the upstream `/Products/<prefix>/<SKU>/` crawl with full coverage rather than relying on the partial scrape).
- Image URL form is the storefront proxy: `https://catalogs.leka.studio/api/i/weplay/media/<sha>.<ext>` — served by `medusa-storefront/src/app/api/i/[...path]/route.ts`, no public GCS bucket exposure.
- Backfilled the `vendors/weplay` root doc with `name`, `slug`, `country`, `legal_name`, `website`, `status`, `sales_channel_id`, `publishable_key_id`, `publishable_key_token`.

### Wired
- `scripts/sync_vendors_to_medusa.py` — added `"weplay": "sc_01KR6Z0VBSXWYZDVGF30EAP0EQ"` to `BRAND_SALES_CHANNELS`.
- `medusa-storefront/src/lib/medusa-client.ts` — Weplay `productCount: 0 → 100`; `hasCollections: true → false` (no `collectionPrefix` exists for Weplay; matches Eurotramp pattern).
- `cloudbuild.yaml`, `cloudbuild-storefront-only.yaml`, `medusa-storefront/cloudbuild-storefront.yaml` — added `NEXT_PUBLIC_WEPLAY_PUBLISHABLE_KEY` build-arg so the storefront bundle resolves the key (avoids the Vortex-style "missing key" bug from v2.7.x).

### Outcome
100/100 products created in Medusa under the Weplay SC. Verified via admin API (`/admin/products?sales_channel_id[]=...`) — all published, all with thumbnail + images + category metadata. Storefront deploy follows via the auto Cloud Build trigger on push.

### Known gap (path 2 follow-up)
1,095 Weplay products are sitting in Firestore with `status="draft_no_images"`. They have valid descriptions, SKUs, categories — they're missing only the photo references. The upstream scrape captured 4,770 photo blobs but only 381 have URL-encoded SKU paths; the other 4,389 have opaque scrambled filenames with no product link. Resolving requires either a fuller re-crawl of `https://www.weplay.com.tw/UserFiles/images/Products/<XX>/<SKU>/` or a Vision-based image→description matching pass. Tracked in `docs/WEPLAY_PATH2_FOLLOWUP.md`.

---

## [2.8.3] - 2026-05-09

### Fixed — Cloud Build `db-migrate` step (npx could not resolve `medusa` bin)
- `cloudbuild.yaml` Step 3: `entrypoint: npx; args: [medusa, db:migrate]` → `entrypoint: npm; args: [run, db:migrate]`. After [2.8.2] unblocked the worker, the next pipeline run got further: build/push backend SUCCESS in ~3 min, but `db-migrate` failed with `npm error could not determine executable to run`. The Medusa v2 production image apparently doesn't expose `medusa` directly via `npx`, but the `db:migrate` script in `package.json` works. The Dockerfile already uses `npm run build` for the same reason.

---

## [2.8.2] - 2026-05-09

### Fixed — Cloud Build pipeline (10+ consecutive timeouts since 2026-05-05)
- `cloudbuild.yaml`: bumped `options.machineType` from `E2_MEDIUM` (1 vCPU / 4 GB) to `E2_HIGHCPU_8` (8 vCPU / 8 GB). Every push from 2026-05-05 onward was timing out at Step #0 `build-medusa-backend` → `Step 4/25 RUN npm ci`. Root cause: the 19,145-line Medusa v2 lockfile (`@medusajs/framework`, `@medusajs/medusa`, `@medusajs/admin-sdk`, `@medusajs/medusa-cli` and their transitive deps) plus `medusa build` plus a parallel Next.js docker build cannot fit inside a 1 vCPU / 4 GB worker before the 1 hr step deadline. Build log signature was deprecation warnings streaming with no error, then `context deadline exceeded` — pure CPU/memory thrashing, not a network or code issue.
- `medusa-backend/Dockerfile`: `RUN npm ci` → `RUN npm ci --prefer-offline --no-audit --no-fund`. Skips post-install audit + funding HTTP calls and prefers cache hits, typically saves 30–60 s on `npm ci` wall-clock.
- Net effect: PR #11 (verified brand-CI palettes + photo-first cards + Vortex logo contrast) and the 9 prior pushes were all built but never deployed to `catalogs.leka.studio`. This commit is what unblocks the trigger for all of them.

---

## [2.8.1] - 2026-05-09

### Added — Weplay onboarding (8th brand)
- Verified Weplay palette in Chrome at weplay.com.tw on 2026-05-09 via computed-style histogram across 3,000 elements: `#C7161E` red (126 hits, dominant), `#F0831E` orange (34), `#FED52B` yellow (5). Updated `brand-ci.ts` evidence + tagline ("We play, we learn — for the future.").
- Fixed `medusa-client.ts` `BrandConfig` for Weplay: `color` was the placeholder `#0099cc` cyan — corrected to verified `#C7161E` red. `hasCollections` flipped to `true` so collection filters render once products are imported.
- Wired Weplay into `scripts/sync_vendors_to_medusa.py` via a new `_resolve_sales_channel(slug)` helper: hardcoded slugs in `BRAND_SALES_CHANNELS` win, missing slugs fall back to env `LEKA_<SLUG>_SALES_CHANNEL_ID`. Lets a new brand import without an extra commit — set `LEKA_WEPLAY_SALES_CHANNEL_ID=sc_...` after creating the channel in Medusa Admin, then promote the value into the dict.

---

## [2.8.0] - 2026-05-08

### Reverted — `vendor-themes.ts` regression
Commit `70f0dcd` ("vendor-specific design systems for 6 brands") removed `brand-ci.ts` and replaced it with a parallel `vendor-themes.ts` system carrying fabricated palettes (Berliner navy+orange, Eurotramp red, Rampline lime+black, etc.). That code never deployed — live `catalogs.leka.studio` was still serving the v2.6.0 brand-CI lineage. Reverted in full so main now matches what's actually in production.

### Re-added on top of the revert (clean additions)
- `medusa-storefront/src/lib/image-scoring.ts` — `scoreImage` / `pickPrimaryImage` / `sortImagesByScore` penalize drawings/CAD/certs and reward photos so cards lead with the most marketable image.
- `medusa-storefront/public/placeholder-product.svg` — graceful fallback when an image URL fails.
- Wired `pickPrimaryImage` into `product-card.tsx` (with `onError` swap to the placeholder); `sortImagesByScore` into `product-detail.tsx` so the gallery's default-selected image is the best photo.

### Fixed — Card series-badge overlay
- Removed the `absolute top-2 left-2 badge` overlay on the product image; the series/collection name now lives next to the SKU in the card body with `truncate max-w-[60%]`. Long names no longer wrap onto the photo.

### Fixed — Vortex logo contrast on live PLP
- `medusa-storefront/public/brands/vortex/logo.svg`: added `fill="#FFFFFF"` so the wordmark renders white on the `#153CBA` blue header wrapper. The previous SVG had no `fill`, which defaulted to black on the dark blue background.

### Fixed — `brand-ci.ts` palettes vs verified vendor stylesheets
Re-audited every vendor's production CSS on 2026-05-08 and corrected the live brand themes. Confidence + evidence cited per brand inline.

| Brand | Old (was) | New (verified, in CSS) |
|---|---|---|
| Vinci | `#970260` magenta + `#182557` navy | `#8A3492` purple + `#FBBE2F` yellow + `#E9592C` orange |
| Berliner | `#00827A` teal (light) primary | `#00534F` (dark) primary, `#00827A` secondary, `#E6F3F2` accent |
| Eurotramp | `#0062AF` + `#6B9950` (wrong green) | `#0062AF` + `#63727F` slate + `#C80000` red accent |
| Rampline | `#182557` navy + `#970260` magenta | `#B5BC00` lime + `#2D5346` forest, paper `#F2F2EE` |
| 4soft | `#FFA900` amber primary (wrong) | `#0089CF` blue + `#CF0026` red + `#F99D1C` orange |
| Vortex | `#153CBA` + `#FFE000` yellow secondary | `#153CBA` + `#FF33D4` hot-pink secondary, yellow demoted to accent |
| WePlay | `#0099CC` cyan primary (wrong) | `#C7161E` red + `#F0831E` orange + `#FED52B` yellow |
| Wisdom | `#FCB822` amber + `#1D3A8A` navy (swapped) | `#1F4A83` navy + `#FBBE2F` amber — verified in Chrome at wisdomplaygroundsint.com (the actual vendor; not wisdomtoys.cn) |

### Added — `bodyVar` + `accent` on `BrandCI`
- `BrandPalette.accent?` for the third pop color most vendors carry (Eurotramp red, Vortex pink, Vinci orange, etc.) — exposed as `--brand-accent` and `bg-brand-accent` Tailwind utility.
- `BrandFonts.bodyVar` for vendors whose body font differs from heading (Vinci: Montserrat heading + Open Sans body; 4soft: Nunito + Lato; Vortex: Work Sans + Nunito) — exposed as `--brand-body` and `font-body`.
- New next/font imports: `Roboto_Condensed` (Eurotramp), `Work_Sans` (Vortex).

### Removed
- `docs/vendor-ds-preview.html` — was a static mockup of the abandoned `vendor-themes.ts` system, misleading anyone reviewing the storefront.

### Files changed
- `medusa-storefront/src/lib/brand-ci.ts` — verified palettes, evidence comments, `accent` + `bodyVar` fields
- `medusa-storefront/src/app/layout.tsx` — add Roboto_Condensed + Work_Sans fonts
- `medusa-storefront/src/app/[brand]/layout.tsx` — wire `--brand-accent` + `--brand-body`
- `medusa-storefront/tailwind.config.ts` — add `brand.accent` color + `font-body` family
- `medusa-storefront/src/components/product-card.tsx` — image scoring, onError fallback, series moved to body
- `medusa-storefront/src/app/[brand]/[handle]/product-detail.tsx` — gallery default uses `sortImagesByScore`
- `medusa-storefront/src/lib/image-scoring.ts` (new)
- `medusa-storefront/public/placeholder-product.svg` (new)
- `medusa-storefront/public/brands/vortex/logo.svg` — `fill="#FFFFFF"`
- `docs/vendor-ds-preview.html` (deleted)

### Outcome
TypeScript clean (`tsc --noEmit`). Live deployment lineage preserved; `main` once again represents what users see.

---

## [2.7.0] - 2026-05-07

### Added — Wisdom catalog Category → Sub-category selector + price/material filters

- **Storefront FilterBar** ([medusa-storefront/src/components/filter-bar.tsx](medusa-storefront/src/components/filter-bar.tsx)): top-level `<select>` now drives a dependent Sub-category `<select>`, populated from each parent's `category_children`. Hidden when no brand category has subcategories so Vinci/Berliner/4soft/Vortex/Eurotramp/Rampline render unchanged.
- **Wisdom-only filters**: USD min/max price range + Material dropdown (Wood, Rubber wood, Plastic, Metal, Fabric, Foam — bucketed from messy `metadata.material` strings via regex). Gated by a new `BrandConfig.hasMaterialFilter` flag in [medusa-storefront/src/lib/medusa-client.ts](medusa-storefront/src/lib/medusa-client.ts) (set on Wisdom only).
- **CatalogContent** ([medusa-storefront/src/app/[brand]/catalog-content.tsx](medusa-storefront/src/app/[brand]/catalog-content.tsx)): loads categories with `parent_category_id` and builds a `{id, name, handle, children[]}` tree. Subcategory selection short-circuits the parent on the Medusa `category_id` query. Filter state mirrored to the URL (`?q=&category=&subcategory=&material=&min_price=&max_price=`) so deep-links and Reset both work.
- **Backend support** ([shared/medusa_importer.py](shared/medusa_importer.py)): `get_or_create_category()` now takes optional `parent_category_id`; new `add_categories_to_product()` and `_patch()` helpers for product-category linking.
- **One-shot importer** ([wisdom-catalog/import_subcategories_to_medusa.py](wisdom-catalog/import_subcategories_to_medusa.py)): reads the same Excel that `import_to_medusa.py` ingests, derives `(category, subcategory)` via `shared/category_mapper.py`, ensures child categories exist under each parent (handle: `wisdom-<cat>-<sub>`), and PATCHes each Wisdom product to add the child category id alongside the parent. Idempotent + `--dry-run`. Dry-run on the deployed backend reported **80 child categories / 1,321 product links**; real run completed successfully.

### Files changed
- `medusa-storefront/src/components/filter-bar.tsx`
- `medusa-storefront/src/app/[brand]/catalog-content.tsx`
- `medusa-storefront/src/lib/medusa-client.ts`
- `shared/medusa_importer.py`
- `wisdom-catalog/import_subcategories_to_medusa.py` (new)

### Outcome
- Wisdom shoppers can now drill Furniture → Cabinet / Table / Chair / Shelf / Bed / Desk / Bench / Fence / Kitchen / House / Play-structure (and similar leaves under Playground, Outdoor, Nature Play, etc.), narrow by material, and clamp by USD price.
- Other six brand catalogs untouched at the UI level — sub-category dropdown stays hidden when no parent has children.

---

## [2.6.0] - 2026-05-07

### Added — Per-brand corporate identity (logos, palettes, fonts) on storefront

Each brand catalog page now renders the vendor's real corporate identity instead of a generic letter-badge.

- **Logos** — scraped from each vendor's public homepage and stored under `medusa-storefront/public/brands/<slug>/`:
  - Wisdom, Berliner, Eurotramp, Rampline, Vortex, WePlay → real logos
  - Vinci → white logo on brand-magenta background wrapper
  - 4soft → no public logo asset; falls back to letter badge styled with brand primary
- **Palettes** — full 4-color palette (`primary`, `secondary`, `ink`, `paper`) per brand, exposed as CSS variables (`--brand-primary` etc.) set at the brand layout root. Tailwind exposes them as `bg-brand-primary`, `text-brand-ink`, etc.
- **Fonts** — Manrope stays for body text across all brands; headings now use a brand-specific Google Font loaded once via `next/font/google`:
  Wisdom→Poppins, Vinci→Montserrat, Berliner→Roboto, Eurotramp→Open Sans, Rampline→Lato, 4soft→Nunito (verified from 4soft.cz CSS), Vortex→Inter, WePlay→Nunito.
- **Favicons** — each `/[brand]` page sets its own browser-tab icon via `generateMetadata`.
- **WePlay (8th brand stub)** — added as a `BrandConfig` entry with `productCount: 0`. No Sales Channel yet, so the route renders a "Catalog coming soon" placeholder using the brand CI. `NEXT_PUBLIC_WEPLAY_PUBLISHABLE_KEY` placeholder added to `env.example`. Sales Channel + product import is a follow-up task.
- **Components updated** — `SeriesBadges` and `ProductCard` now use `var(--brand-primary)` / `var(--brand-secondary)` instead of hardcoded `badge-purple` / `badge-navy` / `badge-amber` classes; series filters and price labels match the brand.

**Files changed**:
- NEW `medusa-storefront/src/lib/brand-ci.ts` — typed CI registry for 8 brands
- NEW `medusa-storefront/public/brands/<slug>/{logo.*, favicon.*}` — 8 brand asset folders
- `medusa-storefront/src/app/layout.tsx` — load 7 brand fonts, attach CSS variable classes to `<html>`
- `medusa-storefront/src/app/[brand]/layout.tsx` — `<Image>` logo, brand CSS-var injection, `font-heading` on brand name
- `medusa-storefront/src/app/[brand]/page.tsx` — per-brand favicon
- `medusa-storefront/src/app/[brand]/catalog-content.tsx` — WePlay-style "coming soon" branch for stub brands
- `medusa-storefront/src/components/series-badges.tsx` — brand-primary active state, drops hardcoded `BADGE_COLORS` array
- `medusa-storefront/src/components/product-card.tsx` — series/NEW badges + price use brand palette
- `medusa-storefront/src/lib/medusa-client.ts` — `weplay` entry added to `BRANDS`
- `medusa-storefront/tailwind.config.ts` — `colors.brand.*` and `fontFamily.heading` mapped to CSS vars
- `medusa-storefront/tsconfig.json` — `types: ["node"]` added to scope @types resolution (parent-root @types/caseless was breaking the build)
- `medusa-storefront/env.example` — Vortex and WePlay publishable-key placeholders

**Outcome**: clean `npm run build` (Next 15.5 / TS strict). Each `/[slug]` route is now visually distinct on a per-vendor basis. Letter-badge fallback keeps the page rendering even if a logo asset is missing.

## [2.5.2] - 2026-05-07

### Fixed — Cross-brand series badges showing on wrong brand pages

**Root cause**: `medusa.store.collection.list()` returns all 56 collections globally regardless of the publishable API key's sales channel scope. Every brand with `hasCollections: true` was displaying all 56 collection badges from all vendors.

- **Symptom**: Berliner Seilfabrik page showed Vinci series (Active, Arena, Castillo, etc.) alongside its own Berliner series — and vice versa for all 4 collection brands.
- **Root cause**: Medusa's store collections API does not filter by sales channel — it returns all collections in the database regardless of which publishable key is used in the request header.
- **Fix**: Added `collectionPrefix?: string` to `BrandConfig` interface and set a per-brand prefix. After the API fetch, collections are filtered client-side:
  - `berliner-*` → Berliner Seilfabrik (15 collections → 18 after handle audit)
  - `4soft-*` → 4soft (3 collections)
  - `vortex-*` → Vortex Aquatics (8 collections)
  - `undefined` (Vinci) → all handles that do NOT start with any other vendor's prefix (27 Vinci collections)
- **Files changed**: `medusa-storefront/src/lib/medusa-client.ts`, `medusa-storefront/src/app/[brand]/catalog-content.tsx`
- **Deployed**: Cloud Build `25da4b21`, storefront revision `accae83`

### Verified (post-fix browser audit — all collection brands passing)
| Brand | Series shown | Correct |
|-------|-------------|---------|
| Vinci Play | 27 (Vinci-only handles) | ✓ |
| Berliner Seilfabrik | 18 (all "Berliner *") | ✓ |
| 4soft | 3 (4soft Tunnels & Furniture, 3D Elements, 2D Graphics) | ✓ |
| Vortex Aquatics | 8 (all "Vortex — *") | ✓ |

---

## [2.5.1] - 2026-05-07

### Fixed — CORS misconfiguration blocking all brand catalogs + Vortex missing key

**Root cause: all brand catalog pages showed "No products found"** due to two independent bugs found during a full frontend status audit.

#### Bug 1 — STORE_CORS pointed to raw Cloud Run URL (critical, global)
- **Symptom**: Every brand page returned 0 products. Browser console: `TypeError: Failed to fetch`. `no-cors` mode returned opaque response confirming CORS — not network — was failing.
- **Root cause**: `STORE_CORS` env var on `leka-medusa-backend` was set to `https://leka-medusa-storefront-538978391890.asia-southeast1.run.app` (the raw Cloud Run URL from initial deploy), not the custom domain `https://catalogs.leka.studio`. The backend was never redeployed after the custom domain was configured. Preflight OPTIONS returned empty `Access-Control-Allow-Origin`.
- **Fix**: `gcloud run services update leka-medusa-backend --update-env-vars STORE_CORS=https://catalogs.leka.studio,AUTH_CORS=...` — new revision `00012-6sh`. CORS now returns `Access-Control-Allow-Origin: https://catalogs.leka.studio`.
- **Also note**: `cloudbuild.yaml` backend deploy step already had the correct `STORE_CORS=https://catalogs.leka.studio` — the stale value was from a pre-custom-domain manual deploy.

#### Bug 2 — NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY missing from storefront build
- **Symptom**: Vortex catalog specifically showed 0 products (would have been visible after Bug 1 was fixed).
- **Root cause**: `NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY` build-arg was missing from both `cloudbuild.yaml` and `cloudbuild-storefront-only.yaml`. The key resolved to `""` in the bundle, so the Medusa store API rejected the auth.
- **Fix**: Added `--build-arg NEXT_PUBLIC_VORTEX_PUBLISHABLE_KEY=pk_df5eb6c3d0032c6baebe18bec7b3be1cdb024ba5efd3833cac2b8517432c56dc` (retrieved from Medusa Admin API) to both Cloud Build files. Redeployed storefront (Cloud Build `fa376c2b`, revision `00011-mkn`).
- **Files changed**: `cloudbuild.yaml`, `cloudbuild-storefront-only.yaml`

### Verified (post-fix browser audit — all passing)
| Brand | Products | Images | Status |
|-------|----------|--------|--------|
| Wisdom | 5,062 | ✓ (GCS proxy, ~8s warm-up) | ✓ |
| Vinci Play | 1,096 | ✓ (external CDN) | ✓ |
| Berliner Seilfabrik | 466 | ✓ (GCS proxy) | ✓ |
| Eurotramp | 80 | ✓ (GCS proxy) | ✓ |
| Rampline | 54 | ✓ (GCS proxy) | ✓ |
| 4soft | 391 | ✓ (GCS proxy) | ✓ |
| Vortex Aquatics | 521 | ✓ (GCS proxy) | ✓ |

### Known issues (not blocking)
- **Cross-brand series badges**: Brands with `hasCollections: true` (Vinci, Berliner, 4soft, Vortex) all show the same 56 series badges from ALL brands. Medusa's `store/collections` API returns all collections regardless of the publishable key's sales channel scope. Fix: scope collections to the sales channel in Medusa, or filter client-side by handle prefix.
- **Vortex product count 521 vs 272**: Vortex Sales Channel appears to include products from multiple brands. Needs sales channel audit in Medusa Admin.
- **Image warm-up latency**: `/_next/image` optimization on 512Mi Cloud Run takes ~5–8s for first-load batches of 48 large (2560×2560) images. Consider bumping storefront memory to 1Gi or pre-warming.

## [2.5.0] - 2026-05-05

### Added — Phase 4: image bucket migration + private-via-proxy serving

Product images for the 6 GCS-resident leka brands moved from the public `gs://ai-agents-go-documents/product-images/<slug>/` to a project-prefixed, **private** bucket `gs://ai-agents-go-vendors/<slug>/`. Public access prevention stays enabled on the new bucket; the Cloud Run storefront fronts it via a Next.js image proxy. Vinci images stay external (zamowienia.vinci-play.pl).

- **GCS copy** — 5.30 GB across wisdom (2.29 GB), berliner (1.97 GB), vortex (953 MB), rampline (57 MB), eurotramp (17 MB), 4soft (8 MB), copied with `gcloud storage cp -r`. Slug-based folder names for consistency with existing `durasein/`, `gumtec/`, `zelk/` etc.
- **Image proxy** [medusa-storefront/src/app/api/i/[...path]/route.ts](medusa-storefront/src/app/api/i/[...path]/route.ts) — Next 15 route handler. Reads private GCS via the Cloud Run runtime SA (`538978391890-compute@developer.gserviceaccount.com`, ADC token from metadata server, cached until ~5 min before expiry). Streams response with `Cache-Control: public, max-age=86400, immutable`. Preserves raw URL path so encoding (single vs double `%20`) survives end-to-end. Allowed in [next.config.js](medusa-storefront/next.config.js).
- **URL rewriter** [scripts/rewrite_image_urls_to_vendors_bucket.py](scripts/rewrite_image_urls_to_vendors_bucket.py) — sweeps `vendors/{slug}/products` (Firestore DB `vendors`) AND Medusa Admin API for each brand's sales channel, rewriting `images[].url` (and Medusa `thumbnail`) from old-bucket public URLs to proxy URLs. Idempotent; supports `--target-base` so the same script can target direct GCS or the storefront proxy. Running counts:
  - 4soft: 780 + 780 (firestore + medusa) = 1,560 URLs
  - eurotramp: 1,326 + 1,326 = 2,652 URLs (79 external images preserved)
  - rampline: 127 + 127 = 254 URLs
  - vortex: 0 + 1,949 = 1,949 URLs (Firestore subcollection empty by design)
  - berliner: 3,969 + 3,969 = 7,938 URLs (8 external preserved)
  - wisdom: 5,910 + 5,900 = 11,810 URLs (first pass) + 328 + 328 = 656 URLs (verified/ mop-up) = 12,466 URLs
  - **Grand total: 26,819 URLs rewritten across both stores, 0 errors, 0 unknown hosts, 0 `no_match` remaining.**
  - Plus 582 4soft GCS objects renamed (`%20` → space).
- **Cloud Build** — added [cloudbuild-storefront-only.yaml](cloudbuild-storefront-only.yaml) for storefront-only deploys when the backend hasn't changed (skips medusa-backend build + db-migrate). [cloudbuild.yaml](cloudbuild.yaml) hardcoded `_AR_REPO` project to `ai-agents-go` because `$PROJECT_ID` was not recursively expanding inside the substitution.
- **.gcloudignore** added to keep `gcloud builds submit` archives small (807 KiB vs. 500+ MB unfiltered).

### Fixed (same release)

- **4soft literal `%20` filenames**: long-standing image rendering bug. The catalog scrape had uploaded 582 objects with literal `%20` characters in their GCS object names (so single-encoded URLs in Medusa decoded to spaces at GCS and 404'd). One-shot rename via [scripts/rename_4soft_literal_pct20.py](scripts/rename_4soft_literal_pct20.py) replaces literal `%20` with real spaces in every affected object name. After rename, every existing single-encoded Medusa URL resolves correctly. 582 files renamed in 13 sec, 0 errors.
- **Wisdom 328 `no_match`**: traced to a `verified/` sibling folder under `gs://ai-agents-go-documents/product-images/` (not under `wisdom/`), used by ~200 wisdom products for quality-curated catalog imagery. Copied to `gs://ai-agents-go-vendors/wisdom/verified/` (2,253 files / 19 MB) and extended the rewriter with a `BRAND_EXTRA_PREFIXES` map so `verified/` is recognized as a wisdom-owned alt prefix.

### Known issues

- (none currently — both above resolved)
- Phase 5 (archive + delete `leka-product-catalogs` Firestore DB) is gated on a 2-week green canary on `vortex-daily-refresh`.
- `scripts/seed_medusa_api.py:16-17` still hardcodes admin password (Rule 12 violation, pre-existing).

## [2.4.0] - 2026-05-04

### Added — Migration to vendors-rooted Firestore architecture (Phases 0-3)

Source-of-truth product data moved from `leka-product-catalogs` Firestore database (flat `products_{brand}` layout) to the `vendors` database (`vendors/{slug}/products` hierarchical layout owned by the `vendors` project). Plan: `~/.claude/plans/inspect-our-project-database-wise-feigenbaum.md`.

- [migration/vendors_target_schema.md](migration/vendors_target_schema.md) — target schema, slug registry, leka→vendors mapping rules.
- [scripts/migrate_leka_to_vendors.py](scripts/migrate_leka_to_vendors.py) — Phase 1 one-shot. Reads `products_{brand}`, `product_categories_{brand}`, brand-filtered `quotations`; writes `vendors/{slug}/products|product_categories|quotations` and the vendor root doc. **Run live**: wisdom (5,071 products), vinci (1,113 products + 6 categories), vortex (0 products in leka — already canonical in vendors). Total: 6,184 products migrated.
- [scripts/reverse_import_medusa_to_vendors.py](scripts/reverse_import_medusa_to_vendors.py) — Phase 2 one-shot. For brands that had no Firestore source (berliner / eurotramp / rampline / 4soft), reads them back from Leka Medusa Admin API and writes to `vendors/{slug}/products`. **Run live**: berliner (466), eurotramp (80), rampline (54), 4soft (391). Total: 991.
- [scripts/sync_vendors_to_medusa.py](scripts/sync_vendors_to_medusa.py) — Phase 3 generalized sync. Reads `vendors/{slug}/products` and upserts into Medusa via Admin API (handle lookup → create/update → variant USD price). Replaces (does not yet remove) the brand-specific TS scrapers and `seed_medusa_api.py`. Smoke-tested with `--brand=rampline --limit=5 --dry-run`: 5/5 UPDATE, 0 errors. Vortex sync continues to run via the existing `vortex-refresh` Cloud Run Job.

### Pending

- Phase 4: live sync run + storefront smoke test on a sampled product per brand.
- Phase 5: archive leka Firestore DB to `migration/leka-firestore-archive/` and delete the database after a 2-week green-sync window.

## [2.3.0] - 2026-04-21

### Added — Vortex Aquatics brand (272 products · 1,949 images mirrored)

- New brand folder [vortex-catalog/](vortex-catalog/) mirrors the vinci-catalog pattern
- **Scraper** [vortex-catalog/scrape_catalog.py](vortex-catalog/scrape_catalog.py) — hybrid WP REST + HTML approach against www.vortex-intl.com
- **Image mirror** [vortex-catalog/mirror_images_to_gcs.py](vortex-catalog/mirror_images_to_gcs.py) — uploads images to `gs://ai-agents-go-documents/product-images/vortex/catalog/`
- **Medusa importer** [vortex-catalog/import_to_medusa.py](vortex-catalog/import_to_medusa.py) — creates "Vortex Aquatics" Sales Channel + publishable API key, category `water_play`, 7 collections (one per product-type)
- **Static web-app** [vortex-catalog/web-app/](vortex-catalog/web-app/) — Flask + vanilla JS catalog browser, deploys to Cloud Run service `vortex-catalog`
- **Design System** [vortex-catalog/DESIGN_SYSTEM.md](vortex-catalog/DESIGN_SYSTEM.md) — tokens derived from live vortex-intl.com theme CSS (primary `#153cba`, accent `#ff33d4`, water `#6ed4fc`, Nunito + Work Sans)
- **Vortex logo** — SVG extracted from the live theme sprite, stored at [vortex-catalog/web-app/public/assets/vortex-logo.svg](vortex-catalog/web-app/public/assets/vortex-logo.svg)
- **Gmail outreach draft** — saved in user's Drafts addressed to Vicky Denisova (current Vortex account manager) requesting the 2026 pricelist & latest catalogs

### Changed

- [shared/medusa_importer.py](shared/medusa_importer.py) — added `get_or_create_sales_channel()`, `create_publishable_api_key()`, and optional `sales_channel_ids` kwarg to `create_product()` so future brand importers can attach products to a dedicated Sales Channel at create time.

## [2.2.0] - 2026-04-09

### Added — Vendor Product Catalogs (991 products, 4 brands)
- Scraped and uploaded 4 vendor catalogs to Medusa:
  - Berliner Seilfabrik (466 products) — rope play equipment, Germany
  - Eurotramp (80 products) — trampolines, Germany
  - Rampline (54 products) — motor skill equipment, Norway
  - 4soft (391 products) — EPDM surfaces, Czech Republic
- Created Sales Channels + publishable API keys per vendor
- Added vendor brand pages to storefront (6 brands total)
- Fixed 15 failed product uploads (SKU deduplication, handle sanitization)
- Bulk-published all 991 vendor products
- GCS image re-hosting script (`scripts/rehost-images-to-gcs.ts`)
- Vendor scraper scripts: `scripts/scrape-{berliner,eurotramp,rampline,4soft}.ts`
- Unified upload script: `scripts/upload-vendors-to-medusa.ts`

### Changed
- Updated product card and detail page to handle vendor metadata format
- Added vendor CDN image domains to Next.js config
- Updated cloudbuild.yaml with all 6 vendor publishable API keys
- Applied SEO metadata (generateMetadata) to brand and product pages
- Wired up quotation accept/reject workflow

## [2.1.1] - 2026-04-07

### Added — Product Data Seeded
- Exported 6,219 documents from Firestore (5,071 Wisdom + 1,113 Vinci + categories + quotations)
- Seeded 6,151 products via Medusa Admin API (5,056 Wisdom + 1,095 Vinci)
- Created Admin API seed script (`scripts/seed_medusa_api.py`) for remote seeding
- Created Sales Channels: Wisdom, Vinci Play (with publishable API keys)
- Created Region: Asia-Pacific (USD, 5 countries)
- Created admin user (admin@leka.studio)
- Rebuilt storefront with API keys baked in via Docker build args

## [2.1.0] - 2026-04-07

### Deployed — GCP Infrastructure & Cloud Run Services
- Cloud SQL PostgreSQL: `areda-medusa` / `leka_medusa` (asia-southeast1)
- Memorystore Redis: `leka-medusa-redis` (10.225.88.67:6379)
- VPC Connector: `leka-connector` (10.8.0.0/28)
- Secret Manager: 4 secrets (database-url, redis-url, cookie-secret, jwt-secret)
- **Medusa Backend**: https://leka-medusa-backend-538978391890.asia-southeast1.run.app
- **Next.js Storefront**: https://leka-medusa-storefront-538978391890.asia-southeast1.run.app

### Fixed — Docker Build & Deployment Issues
- Added ts-node + typescript as production dependencies (Medusa CLI needs them at runtime)
- Fixed medusa-config.ts: use module:nodenext for ts-node compatibility, export default
- Removed custom modules array from config (Medusa v2.13 includes all modules by default)
- Added @medusajs/admin-sdk peer dependency for draft-order admin UI
- Compiled medusa-config.ts to .js via ts.transpileModule for runtime fallback
- Added start.sh with db:migrate before server start
- Fixed CRLF line endings with .gitattributes + sed in Dockerfile
- Switched from Cloud SQL Unix socket to public IP (Unix socket URL format incompatible with MikroORM)
- Added DISABLE_ADMIN env var to skip admin UI when build output missing

## [2.0.1] - 2026-04-07

### Added — Sprint 1: Cart Flow, Filters, i18n, Loading States
- Cart state management (`lib/cart.ts`) with localStorage persistence per brand
- Slide-out cart drawer component with quantity controls
- Add-to-cart handler on product detail page with loading/success feedback
- Age group filter dropdown (Vinci-specific, matching current site)
- Product/series count stats in catalog header
- Download count icon on product cards
- "NEW" badge on product cards from tags
- Loading skeleton for catalog page
- 404 pages (brand-scoped and root)
- Locale switcher component (EN/TH/CN) with i18n library
- Mobile-responsive header with cart drawer
- Region setup (Asia-Pacific, USD, 5 countries) in seed script
- Manual fulfillment and payment provider setup in seed script
- Publishable API key generation per sales channel

## [2.0.0] - 2026-04-06

Renamed from [1.0.0].

## [1.0.0] - 2026-04-06

### Changed — Medusa Commerce v2 Migration
- **Backend**: Migrated from Python/Flask/Firestore to Medusa Commerce v2 (TypeScript/Node.js/PostgreSQL)
- **Frontend**: Migrated from vanilla JS static app to Next.js 15 with Tailwind CSS
- **Database**: Migrated from Firestore to Cloud SQL PostgreSQL 15
- **Architecture**: Products now managed via Medusa Admin API with Sales Channels per brand

### Added
- `medusa-backend/` — Medusa v2 backend with custom API routes for specifications and downloads
- `medusa-storefront/` — Next.js storefront with Leka Design System (Tailwind)
- Full e-commerce: cart, checkout, customer accounts, order management
- Multi-brand via Medusa Sales Channels (Wisdom, Vinci Play)
- Product detail pages (replaces modal) with image gallery, specs, downloads, certifications
- Customer authentication (login, register, order history)
- `scripts/export_firestore_to_json.py` — Firestore data export for migration
- `medusa-backend/src/scripts/seed-from-firestore.ts` — Medusa seed script
- `shared/medusa_importer.py` — Medusa Admin API import helper
- `wisdom-catalog/import_to_medusa.py` — Wisdom Excel → Medusa importer
- `vinci-catalog/import_to_medusa.py` — Vinci JSON → Medusa importer
- Updated `cloudbuild.yaml` for multi-service build (backend + storefront)

### Deprecated
- `src/main.py` (Flask gateway) — replaced by Medusa backend
- `*/import_to_firestore.py` — replaced by `*/import_to_medusa.py`
- `vinci-catalog/web-app/` — replaced by `medusa-storefront/`
- Firestore collections — data migrated to PostgreSQL

## [0.5.0] - 2026-04-01

### Added — Full Vinci Play Catalog (1,172 products)
- Full website scrape of all 29 Vinci Play series (1,172 products)
- Firestore import to `products_vinci` collection with category index
- Brand registration in `brands/vinci`
- Redeployed web app with complete product data

### Fixed
- Service account credential path case mismatch (eukri → Eukrit)

## [0.4.0] - 2026-04-01

### Added — Vinci Play Web App & Cloud Run Deployment
- Web app with Leka Design System for browsing Vinci Play products
- Dockerfile and Cloud Build config for containerized deployment
- Cloud Run service `vinci-catalog` at https://vinci-catalog-538978391890.asia-southeast1.run.app
- Artifact Registry repo `leka-product-catalogs` in asia-southeast1
- 47 Spring series products with static JSON data
- `.dockerignore` and deploy instructions

## [0.3.0] - 2026-03-30

### Added — Vinci Play Brand
- `vinci-catalog/` brand folder with complete scraping and import pipeline
- `scrape_catalog.py` — full website scraper for vinci-play.com (29 series, ~1,000+ products)
  - Extracts: product info, specifications, images, drawings, downloads, certifications
  - Supports `--resume` for checkpoint/resume and `--series` for single-series scraping
  - Rate-limited with retry logic for reliability
- `import_to_firestore.py` — imports scraped JSON to `products_vinci` collection
  - Supports `--dry-run` for preview mode
- `firestore_schema.json` — Vinci-specific schema documentation
- `DEPLOYMENT_LOG.md` — brand-specific deployment tracking
- Firestore composite indexes for `products_vinci`
- Added `requests` and `beautifulsoup4` to requirements.txt

## [0.2.0] - 2026-03-30

### Added
- Multi-brand data architecture with separate Firestore collections per brand (`products_{brand}`)
- `shared/` module with reusable utilities: `base_importer.py`, `category_mapper.py`, `image_pipeline.py`
- Brand registry collection (`brands`) in Firestore
- Per-brand category collections (`product_categories_{brand}`)
- `status` field (active/discontinued/draft) on all products
- `brand` field on products and quotations
- `tags` array field for free-form product tagging
- `description_th` field for Thai product names

### Changed
- Wisdom importer now writes to `products_wisdom` collection (was `products`)
- Firestore rules updated for wildcard brand collections
- Composite indexes added for `products_wisdom`
- Root service (`src/main.py`) now reads from Firestore `brands` collection
- Version bumped to 0.2.0

## [0.1.0] - 2026-03-30

### Added
- Initial project structure from goco-project-template
- Python 3.11 runtime with Flask health endpoint
- Cloud Build pipeline (cloudbuild.yaml) for CI/CD
- Dockerfile for Cloud Run deployment
- verify.sh post-build verification script
- Leka Design System configuration
- Wisdom brand catalog (5,071 products) — migrated from product-catalogs repo
- Firestore rules and composite indexes
- Multi-brand architecture with per-brand subfolders
