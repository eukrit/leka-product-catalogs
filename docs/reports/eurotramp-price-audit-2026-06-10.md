# Eurotramp full price audit — Medusa live vs 2026 (1E) price list

**Date:** 2026-06-10 · **Brand:** Eurotramp (`sc_01KNQAA3Y72W17B7CP2VQ93T3M`)
**Tool:** [`scripts/audit_eurotramp_prices.py`](../../scripts/audit_eurotramp_prices.py) (read-only, reusable)
**Source of truth:** Firestore `ai-agents-go` / DB `vendors` / `vendors/eurotramp/products` (`pricing.*`, `price_date: 2026-06-07`)
**Backend:** `leka-medusa-backend-538978391890.asia-southeast1.run.app`

## Scope

This is the broad follow-up to PR #134 / CHANGELOG **v2.83.0**, which fixed only the
**28 SKUs that hard-errored as create-collisions**. Here we reconcile **every**
Eurotramp variant's live Medusa price (THB/USD/EUR/SGD) against the per-SKU 2026
price list, to confirm no variant is left on stale pricing.

The audit pages the entire Medusa catalog (14,110 variants / 32,713 keys) and
matches **by exact variant SKU → `metadata.legacy_sku` → product handle**, reusing
the exact `_match_key` logic of `sync_brand_prices_to_medusa.py`, sales-channel
scoped to Eurotramp. So the "matched" set here is precisely the set the writer
would touch.

## Result — fully converged, 0 stale

| Bucket | Count |
|---|---|
| Firestore eurotramp docs | 707 (683 priced) |
| Medusa variants on Eurotramp SC | 744 |
| **Matched** (Firestore→Medusa) | **683** |
| (a) **STALE** — live ≠ 2026, needs update | **0** |
| (b) ORPHAN — Medusa variant, no priced FS doc | 67 |
| (c) MISSING — priced FS doc, no Medusa variant | 0 |
| (d) CROSS-BRAND — resolves only to another brand's channel | 0 |
| OK (already at 2026 price, all 4 currencies within 1 minor unit) | 683 |
| 28-fix regression check | 28/28 OK |

**Every one of the 683 priced Firestore SKUs is matched to a Medusa variant and is
already at its exact 2026 (1E) price in all four currencies.** The 28 collision
SKUs fixed in v2.83.0 all held. There were therefore **no stale (bucket a)
variants to write** — the "apply" step is a verified no-op. Independent
confirmations: `_verify_eurotramp_collisions.py` → `ok=28 bad=0`;
`sync_brand_prices_to_medusa.py --brand eurotramp --dry-run` → `matched 683/683
(100%), unmatched=0, guarded=0`.

A redundant `--write` was deliberately **not** run: the audit already proves 0
drift by reading live prices, and writing 683 already-correct variants would add
churn and re-expose the known `eurotramp-kids-tramp-track-playground` 503-hang for
zero benefit.

## Bucket (b) — 67 orphan variants (flagged, NOT repriced)

These are Medusa variants on the Eurotramp channel whose SKU is **not** a single
priced 2026 Firestore doc. The per-SKU 2026 price list defines no single price for
them, so they are out of scope for "reconcile against the price list." They split
cleanly into three expected, benign classes — **none is a 2026-listed SKU sitting
on a wrong price**:

1. **Composite "Impact Protection" variants (32)** — SKUs of the form
   `BASE+OPTION` (e.g. `97044+E97448`, `ET-97100+E97041`, `97500B+E97544`) on the
   Kids-Tramp / Kids-Tramp-Track / Wehrfritz umbrella products. These are
   Medusa-synthesised base+option combinations; their live price is **not** a
   simple base+option sum of two Firestore docs (verified — the combination price
   follows a separate model), so there is no single 2026 doc to match. The
   standalone option SKUs they reference (`E97441/448/641/648/841/848/941/948`,
   etc.) *are* in the 2026 list and were verified correct.
2. **"B"-suffix / bare-number umbrella variants (~12)** — e.g. `97000`, `97000B`,
   `97500B`, `97010B`, `97610B`, `94700B`. The umbrella product carries these as
   sibling variants of the canonical `ET-####` Firestore SKU; Firestore has no
   `####B` doc. The non-B siblings (`97000`, `97500`, `97010`, `97610`) already
   carry the canonical doc's exact price; the `B` siblings are distinct
   configurations with their own (higher) live prices and no 1:1 list entry.
3. **Unpriced ET-#### parents / spec-only products (~23)** — e.g. `ET-03150`
   (Premium series parent), `ET-04000`, `ET-26200`, `ET-38000`, `ET-40000`,
   `ET-70000`, `ET-83000`, `ET-85000`, `ET-90000`, `ET-97507/508`, and the
   `ET-03150-eurotramp-*` model rows. The matching Firestore doc exists but is
   **unpriced** (no `retail_*`), so there is no 2026 price to apply.

**Follow-up (optional, out of scope here):** if these orphan variants should be
sellable at list prices, the fix is upstream in `eukrit/vendors` — either add
priced 2026 docs for the `B`/composite configurations, or confirm the parents are
intentionally spec-only. No storefront change is warranted from the price-list
reconciliation alone.

## Reproduce

```bash
export LEKA_MEDUSA_ADMIN_EMAIL=$(gcloud secrets versions access latest --secret=leka-medusa-admin-email --project=ai-agents-go)
export LEKA_MEDUSA_ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=leka-medusa-admin-password --project=ai-agents-go)
python scripts/audit_eurotramp_prices.py --json out/eurotramp_audit.json   # read-only
```

Exit code is non-zero only if a stale variant or a 28-fix regression appears.
