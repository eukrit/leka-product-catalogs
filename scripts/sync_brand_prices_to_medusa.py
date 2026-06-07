"""Update-only multi-currency price push (THB/USD/EUR/SGD) to Leka Medusa.

Pushes retail prices from vendors/{slug}/products[].pricing onto the EXISTING
Medusa variants of a brand's sales channel — matching by variant SKU, then
metadata.legacy_sku, then product handle. It NEVER creates products, so it is
safe for brands whose vendor handles don't line up with Medusa (Berliner uses
descriptive handles with item-code SKUs; Wisdom was rebranded to "Leka Project"
with LP- SKUs + legacy_sku metadata). This avoids the duplicate-product hazard
of the handle-based sync_vendors_to_medusa.py.

Prices come straight from vendors/{slug}/products (already computed at one
consistent FX snapshot by scripts/backfill_sgd_pricing.py), keeping Firestore
and Medusa coherent.

Sales-channel scoping (the cross-brand-clobber fix):
    The Medusa index is built ONCE for the whole catalog, but every indexed
    variant is tagged with the set of sales-channel ids of its product. A
    `--brand X` run only ever writes to a variant that lives on brand X's own
    sales channel (SC[X]). When two brands share an identical SKU — e.g.
    Rampline "Kids Tramp" articles (97010B, E97047, E31120, E21898B …) collide
    with Eurotramp SKUs — the channel tag disambiguates them, so a Rampline run
    can no longer overwrite the Eurotramp variant (or vice versa). A vendor doc
    whose SKU resolves ONLY to another brand's DEDICATED channel is skipped and
    logged under the cross-brand guard rather than silently clobbering.
    Products that no other brand claims — no sales channel at all, or only the
    shared aggregate channels ("Leka Catalogs", "Default", "Proposal") that the
    unified storefront uses — remain matchable so their prices still land (many
    brand products live only on "Leka Catalogs").

Usage:
    python scripts/sync_brand_prices_to_medusa.py --brand berliner --dry-run
    python scripts/sync_brand_prices_to_medusa.py --brand rampline --dry-run
    python scripts/sync_brand_prices_to_medusa.py --brand all --write
    python scripts/sync_brand_prices_to_medusa.py --brand eurotramp --write \
        --scope-file data/curated/eurotramp_performance_line.json

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("sync_brand_prices")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"

# slug → sales channel id. Full mirror of
# scripts/sync_vendors_to_medusa.py::BRAND_SALES_CHANNELS — keep in sync. The
# channel id is now load-bearing: a `--brand X` run only writes variants on
# SC[X], so every brand that can be priced MUST appear here (rampline/weplay
# were previously absent, which let the global index clobber across brands).
SC: dict[str, str] = {
    "vinci":      "sc_01KNKTHC77716EPCE3E2BKAMQP",
    "berliner":   "sc_01KNQAA3QDYHP15Y9K4PPRMDF0",
    "designpark": "sc_01KRRK0N4ET8QZHX6QB3KZ84YD",
    "wisdom":     "sc_01KNKTHC0B7KFEDSZ3NNM49JQW",  # rebranded "Leka Project"
    "vortex":     "sc_01KPRY1T8HZJ57020JPZVGAKZK",  # Vortex Aquatics (VOR-… SKUs)
    "eurotramp":  "sc_01KNQAA3Y72W17B7CP2VQ93T3M",  # shares SKUs with Rampline
    "rampline":   "sc_01KNQAA448RY0YPR51FNPM2TVA",  # "Kids Tramp" ⇄ Eurotramp collisions
    "4soft":      "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y",  # 4soft EPDM graphics (v2.40.0)
    "weplay":     "sc_01KR6Z0VBSXWYZDVGF30EAP0EQ",
    # Archimedes Water Play SC created v2.40.0. Price sync is a no-op until the
    # 34 AWP### products are created in Medusa (catalog creation is a follow-up).
    "archimedes-water-play": "sc_01KSSP39K5DVH9TT2TMXCREHFV",
}
_CCY = (("retail_thb", "thb"), ("retail_usd", "usd"),
        ("retail_eur", "eur"), ("retail_sgd", "sgd"))


def _firestore():
    from google.cloud import firestore
    return firestore.Client(project=PROJECT, database=VENDORS_DB)


def _prices(p: dict) -> list[dict]:
    out = []
    for key, ccy in _CCY:
        v = p.get(key)
        if v:
            out.append({"amount": int(round(v * 100)), "currency_code": ccy})
    return out


def _index_all(client) -> dict[str, list[dict]]:
    """Index ALL Medusa products by sku, legacy_sku, and handle.

    Returns ``{key: [candidate, …]}`` where each candidate is
    ``{"pid": product_id, "vid": variant_id, "scs": frozenset(sales_channel_ids)}``.

    Unlike the old first-wins ``setdefault`` index, a key now keeps EVERY
    matching variant. That is what makes cross-brand SKU collisions resolvable:
    when Rampline and Eurotramp both expose SKU ``97010B`` the key holds both
    candidates, and ``_match_key`` picks the one on the requesting brand's
    sales channel. Each candidate carries its product's ``sales_channels.id``
    set so a ``--brand X`` run can refuse to write outside SC[X]. Products with
    no sales channel keep an empty ``scs`` and stay matchable as a fallback."""
    idx: dict[str, list[dict]] = defaultdict(list)

    def _add(key: str, cand: dict) -> None:
        key = (key or "").strip()
        if not key:
            return
        bucket = idx[key]
        # De-dupe: the same variant can arrive via sku and sku.upper().
        if not any(c["pid"] == cand["pid"] and c["vid"] == cand["vid"] for c in bucket):
            bucket.append(cand)

    offset, limit = 0, 200
    while True:
        resp = client._get("/admin/products", {
            "limit": limit, "offset": offset,
            "fields": "id,handle,sales_channels.id,variants.id,variants.sku,variants.metadata",
        })
        batch = resp.get("products", [])
        if not batch:
            break
        for p in batch:
            pid, handle = p["id"], p.get("handle")
            scs = frozenset(
                sc["id"] for sc in (p.get("sales_channels") or []) if sc.get("id")
            )
            vs = p.get("variants") or []
            for v in vs:
                cand = {"pid": pid, "vid": v["id"], "scs": scs}
                sku = (v.get("sku") or "").strip()
                legacy = str((v.get("metadata") or {}).get("legacy_sku") or "").strip()
                if sku:
                    _add(sku, cand)
                    _add(sku.upper(), cand)
                if legacy:
                    _add(legacy, cand)
            if handle and vs:
                _add(handle, {"pid": pid, "vid": vs[0]["id"], "scs": scs})
        if len(batch) < limit:
            break
        offset += limit
    return dict(idx)


def _match_key(dd: dict, idx: dict, brand_sc: str,
               other_brand_channels: frozenset[str]) -> tuple[dict | None, dict | None]:
    """Resolve a vendor doc to a Medusa variant safe to price for this brand.

    Tries item_code → sku/legacy_sku, then handle / doc-id → product handle
    (e.g. Vinci doc id "0101-1" == Medusa handle). For each key, in order:
      1. prefer a candidate on ``brand_sc`` (the brand's own dedicated channel);
      2. else accept a candidate NOT claimed by any other brand — i.e. one whose
         channels are a subset of the shared/aggregate channels (Leka Catalogs,
         Default, Proposal) or none at all. Many brand products live only on the
         "Leka Catalogs" aggregate channel; pricing those is not a clobber;
      3. else remember it as a foreign-only hit — the SKU/handle exists, but only
         on OTHER brands' DEDICATED channels (the real cross-brand collision,
         e.g. Rampline "Kids Tramp" SKUs resolving to Eurotramp variants) — and
         keep trying the remaining keys.

    ``other_brand_channels`` is ``set(SC.values()) - {brand_sc}`` — the dedicated
    channels owned by every OTHER brand. A candidate is "claimed by another
    brand" iff its channel set intersects that.

    Returns ``(candidate | None, guard | None)``. ``guard`` is set only when no
    key produced an acceptable match but at least one resolved to another
    brand's dedicated channel — the caller logs these as the cross-brand guard."""
    foreign: dict | None = None
    for key in (dd.get("item_code"), dd.get("handle"), dd.get("_id")):
        if not key:
            continue
        cands = idx.get(str(key).strip())
        if not cands:
            continue
        on_brand = [c for c in cands if brand_sc in c["scs"]]
        if on_brand:
            return on_brand[0], None
        # Not on this brand's channel — accept only if no OTHER brand claims it.
        unclaimed = [c for c in cands if not (c["scs"] & other_brand_channels)]
        if unclaimed:
            return unclaimed[0], None
        if foreign is None:
            foreign = {
                "key": str(key).strip(),
                "channels": sorted({sc for c in cands for sc in c["scs"]}),
            }
    return None, foreign


def run_brand(client, slug: str, write: bool, limit: int | None, idx: dict,
              scope: set[str] | None = None) -> dict:
    brand_sc = SC[slug]
    other_brand_channels = frozenset(SC.values()) - {brand_sc}
    db = _firestore()
    docs = list(db.collection("vendors").document(slug).collection("products").stream())
    rows = []
    for d in docs:
        dd = d.to_dict() or {}
        dd["_id"] = d.id
        if scope is not None and not ({dd.get("handle"), dd.get("item_code"), dd["_id"]} & scope):
            continue
        p = dd.get("pricing") or {}
        if _prices(p):
            rows.append(dd)
    if scope is not None:
        log.info("[%s] scope filter active: %d docs in scope", slug, len(rows))
    if limit:
        rows = rows[:limit]
    log.info("[%s] %d priced vendor docs", slug, len(rows))

    matched, missing, guarded = [], [], []
    for dd in rows:
        hit, guard = _match_key(dd, idx, brand_sc, other_brand_channels)
        if hit:
            matched.append((dd, (hit["pid"], hit["vid"])))
        else:
            missing.append((dd, None))
            if guard:
                guarded.append((dd, guard))
    log.info("[%s] match %d / %d (%.1f%%); unmatched=%d", slug,
             len(matched), len(rows), 100.0 * len(matched) / max(1, len(rows)), len(missing))
    if guarded:
        log.warning(
            "[%s] CROSS-BRAND GUARD: %d vendor doc(s) matched a SKU/handle that "
            "exists ONLY on other brands' channels — skipped to avoid clobber. "
            "sample: %s", slug, len(guarded),
            [{"code": g[0].get("item_code") or g[0]["_id"],
              "on_channels": g[1]["channels"]} for g in guarded[:5]],
        )
    if missing[:5]:
        log.info("[%s] sample unmatched: %s", slug,
                 [m[0].get("item_code") or m[0]["_id"] for m in missing[:5]])

    if not write:
        for dd, hit in matched[:4]:
            log.info("  [dry] %s → %s", dd.get("item_code") or dd["_id"], _prices(dd["pricing"]))
        return {"brand": slug, "matched": len(matched), "updated": 0,
                "unmatched": len(missing), "guarded": len(guarded)}

    updated = errors = 0
    for i, (dd, (pid, vid)) in enumerate(matched, 1):
        try:
            client.update_variant_prices(pid, vid, _prices(dd["pricing"]))
            updated += 1
        except Exception as e:
            errors += 1
            log.warning("[%s] price update failed %s: %s", slug,
                        dd.get("item_code") or dd["_id"], str(e)[:140])
        if i % 200 == 0:
            log.info("  [%s] …%d/%d (errors=%d)", slug, i, len(matched), errors)
            time.sleep(0.2)
    log.info("[%s] done: updated=%d errors=%d unmatched=%d guarded=%d",
             slug, updated, errors, len(missing), len(guarded))
    return {"brand": slug, "matched": len(matched), "updated": updated,
            "unmatched": len(missing), "guarded": len(guarded)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True, help="one of %s, or 'all'" % ", ".join(SC))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--scope-file", default=None,
                    help="JSON list of handles/item_codes to restrict the push to "
                         "(e.g. data/curated/eurotramp_performance_line.json).")
    args = ap.parse_args()

    scope: set[str] | None = None
    if args.scope_file:
        import json
        raw = json.loads(Path(args.scope_file).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "groups" in raw:
            raw = [h for v in raw["groups"].values() for h in v]
        scope = set(raw)
        log.info("scope-file: %d keys", len(scope))
    brands = list(SC) if args.brand == "all" else [args.brand]
    for b in brands:
        if b not in SC:
            log.error("unknown brand %s", b)
            return 2

    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    client = MedusaImporter(base_url=BACKEND)

    log.info("Indexing all Medusa products (by sku/legacy_sku/handle, tagged with sales channel)…")
    idx = _index_all(client)
    log.info("Indexed %d keys", len(idx))

    summary = [run_brand(client, b, args.write, args.limit, idx, scope) for b in brands]
    print("\n=== summary ===")
    for s in summary:
        print(f"  {s['brand']:11} matched={s['matched']:5} updated={s['updated']:5} "
              f"unmatched={s['unmatched']:5} guarded={s.get('guarded', 0):5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
