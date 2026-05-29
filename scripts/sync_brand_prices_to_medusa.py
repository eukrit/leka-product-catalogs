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

Usage:
    python scripts/sync_brand_prices_to_medusa.py --brand berliner --dry-run
    python scripts/sync_brand_prices_to_medusa.py --brand all --write

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("sync_brand_prices")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"

# slug → sales channel id (from scripts/sync_vendors_to_medusa.py).
SC: dict[str, str] = {
    "vinci":      "sc_01KNKTHC77716EPCE3E2BKAMQP",
    "berliner":   "sc_01KNQAA3QDYHP15Y9K4PPRMDF0",
    "designpark": "sc_01KRRK0N4ET8QZHX6QB3KZ84YD",
    "wisdom":     "sc_01KNKTHC0B7KFEDSZ3NNM49JQW",  # rebranded "Leka Project"
    "vortex":     "sc_01KPRY1T8HZJ57020JPZVGAKZK",  # Vortex Aquatics (VOR-… SKUs)
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


def _index_all(client) -> dict[str, tuple[str, str]]:
    """Index ALL Medusa products by sku, legacy_sku, and handle → (product_id,
    variant_id). Not filtered by sales channel — some products (e.g. stub Vinci
    rows) are attached to no SC but still need prices. Keys are brand-prefixed
    handles / item-code SKUs, so cross-brand collisions don't occur in practice."""
    idx: dict[str, tuple[str, str]] = {}
    offset, limit = 0, 200
    while True:
        resp = client._get("/admin/products", {
            "limit": limit, "offset": offset,
            "fields": "id,handle,variants.id,variants.sku,variants.metadata",
        })
        batch = resp.get("products", [])
        if not batch:
            break
        for p in batch:
            pid, handle = p["id"], p.get("handle")
            vs = p.get("variants") or []
            for v in vs:
                vid = v["id"]
                sku = (v.get("sku") or "").strip()
                legacy = str((v.get("metadata") or {}).get("legacy_sku") or "").strip()
                if sku:
                    idx.setdefault(sku, (pid, vid))
                    idx.setdefault(sku.upper(), (pid, vid))
                if legacy:
                    idx.setdefault(legacy, (pid, vid))
            if handle and vs:
                idx.setdefault(handle, (pid, vs[0]["id"]))
        if len(batch) < limit:
            break
        offset += limit
    return idx


def _match_key(dd: dict, idx: dict) -> tuple[str, str] | None:
    # item_code → variant sku/legacy_sku; handle / doc-id → product handle
    # (e.g. Vinci doc id "vinci-0101-1" == Medusa handle).
    for key in (dd.get("item_code"), dd.get("handle"), dd.get("_id")):
        if key and str(key).strip() in idx:
            return idx[str(key).strip()]
    return None


def run_brand(client, slug: str, write: bool, limit: int | None, idx: dict) -> dict:
    db = _firestore()
    docs = list(db.collection("vendors").document(slug).collection("products").stream())
    rows = []
    for d in docs:
        dd = d.to_dict() or {}
        dd["_id"] = d.id
        p = dd.get("pricing") or {}
        if _prices(p):
            rows.append(dd)
    if limit:
        rows = rows[:limit]
    log.info("[%s] %d priced vendor docs", slug, len(rows))

    matched, missing = [], []
    for dd in rows:
        hit = _match_key(dd, idx)
        (matched if hit else missing).append((dd, hit))
    log.info("[%s] match %d / %d (%.1f%%); unmatched=%d", slug,
             len(matched), len(rows), 100.0 * len(matched) / max(1, len(rows)), len(missing))
    if missing[:5]:
        log.info("[%s] sample unmatched: %s", slug,
                 [m[0].get("item_code") or m[0]["_id"] for m in missing[:5]])

    if not write:
        for dd, hit in matched[:4]:
            log.info("  [dry] %s → %s", dd.get("item_code") or dd["_id"], _prices(dd["pricing"]))
        return {"brand": slug, "matched": len(matched), "updated": 0, "unmatched": len(missing)}

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
    log.info("[%s] done: updated=%d errors=%d unmatched=%d", slug, updated, errors, len(missing))
    return {"brand": slug, "matched": len(matched), "updated": updated, "unmatched": len(missing)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True, help="one of %s, or 'all'" % ", ".join(SC))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
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

    log.info("Indexing all Medusa products (by sku/legacy_sku/handle)…")
    idx = _index_all(client)
    log.info("Indexed %d keys", len(idx))

    summary = [run_brand(client, b, args.write, args.limit, idx) for b in brands]
    print("\n=== summary ===")
    for s in summary:
        print(f"  {s['brand']:11} matched={s['matched']:5} updated={s['updated']:5} unmatched={s['unmatched']:5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
