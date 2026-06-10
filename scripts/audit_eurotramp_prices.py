"""Comprehensive Eurotramp price audit: Medusa live vs 2026 (1E) Firestore.

Reconciles EVERY Eurotramp variant's live Medusa price (THB/USD/EUR/SGD)
against the 2026 price list stored on each `vendors/eurotramp/products` doc
under `pricing.*`. Read-only — produces a discrepancy report bucketed exactly
as the audit brief requires:

  (a) STALE     — a variant matched to a Firestore doc whose live price differs
                  from the 2026 Firestore price (needs an update);
  (b) ORPHAN    — a Medusa variant on Eurotramp's sales channel whose SKU has
                  NO matching priced Firestore doc (typo / discontinued);
  (c) MISSING   — a Firestore-priced doc that resolves to NO Medusa variant at
                  all (not in the storefront — flag, never auto-create);
  (d) CROSSBRAND— a Firestore doc whose SKU/handle resolves ONLY to another
                  brand's DEDICATED sales channel (must be skipped, logged).

It reuses the EXACT matching logic of sync_brand_prices_to_medusa
(`_index_all` semantics + `_match_key`) so the "matched" set here is precisely
the set of variants `sync_brand_prices_to_medusa.py --brand eurotramp` would
write — making the audit and the writer coherent.

Usage:
    python scripts/audit_eurotramp_prices.py                       # console summary
    python scripts/audit_eurotramp_prices.py --json out/report.json
    python scripts/audit_eurotramp_prices.py --show-ok            # also list OK variants

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD; Firestore via ADC.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.sync_brand_prices_to_medusa import (  # noqa: E402
    BACKEND, PROJECT, SC, VENDORS_DB, _match_key, _prices,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("audit_eurotramp")

BRAND = "eurotramp"
EUROTRAMP_SC = SC[BRAND]
TOL = 1  # minor units (satang/cent)

# The 28 SKUs reconciled by fix_eurotramp_2026_sku_collisions (PR #134 / v2.83.0).
ALREADY_FIXED = {
    "93001", "93002", "93020", "93021", "93022", "93030", "93031", "93032",
    "97044", "97046", "97048", "97049", "97054", "97056", "97058", "97059",
    "E21004", "E21006", "E21008", "E21009", "E97441", "E97448", "E97641",
    "E97648", "E97841", "E97848", "E97941", "E97948",
}


def _firestore():
    from google.cloud import firestore
    return firestore.Client(project=PROJECT, database=VENDORS_DB)


def _client():
    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    return MedusaImporter(base_url=BACKEND)


def index_all_with_prices(client) -> tuple[dict, dict]:
    """Page the whole catalog once.

    Returns:
      idx   — {key: [cand,…]} matching sync_brand_prices._index_all's shape, but
              each cand also carries ``sku`` and ``prices`` ({ccy: amount}).
              _match_key only reads pid/vid/scs, so the extra fields are inert
              for matching but available for the price diff.
      vmap  — {vid: cand} for fast reverse lookup of a matched variant.
    """
    idx: dict[str, list[dict]] = defaultdict(list)
    vmap: dict[str, dict] = {}

    def _add(key, cand):
        key = (key or "").strip()
        if not key:
            return
        bucket = idx[key]
        if not any(c["pid"] == cand["pid"] and c["vid"] == cand["vid"] for c in bucket):
            bucket.append(cand)

    offset, limit = 0, 200
    while True:
        resp = client._get("/admin/products", {
            "limit": limit, "offset": offset,
            "fields": ("id,handle,title,sales_channels.id,variants.id,variants.sku,"
                       "variants.metadata,variants.prices.currency_code,variants.prices.amount"),
        })
        batch = resp.get("products", [])
        if not batch:
            break
        for p in batch:
            pid, handle, title = p["id"], p.get("handle"), p.get("title")
            scs = frozenset(sc["id"] for sc in (p.get("sales_channels") or []) if sc.get("id"))
            vs = p.get("variants") or []
            for v in vs:
                prices = {pr["currency_code"]: pr["amount"] for pr in (v.get("prices") or [])}
                cand = {
                    "pid": pid, "vid": v["id"], "scs": scs,
                    "sku": (v.get("sku") or "").strip(),
                    "legacy": str((v.get("metadata") or {}).get("legacy_sku") or "").strip(),
                    "prices": prices, "handle": handle, "title": title,
                }
                vmap[v["id"]] = cand
                if cand["sku"]:
                    _add(cand["sku"], cand)
                    _add(cand["sku"].upper(), cand)
                if cand["legacy"]:
                    _add(cand["legacy"], cand)
            if handle and vs:
                # handle key points at the first variant (mirrors _index_all)
                first = vmap[vs[0]["id"]]
                _add(handle, first)
        if len(batch) < limit:
            break
        offset += limit
    return dict(idx), vmap


def _diff_prices(expected: list[dict], live: dict) -> dict:
    """Return {ccy: (expected, live_or_None)} for every currency that differs
    by more than TOL (including currencies live is missing entirely)."""
    out = {}
    for pr in expected:
        c, amt = pr["currency_code"], pr["amount"]
        got = live.get(c)
        if got is None or abs(amt - got) > TOL:
            out[c] = (amt, got)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None, help="write the full report to this path")
    ap.add_argument("--show-ok", action="store_true", help="list OK variants too")
    args = ap.parse_args()

    client = _client()
    db = _firestore()

    log.info("Indexing all Medusa products (sku/legacy/handle + live prices)...")
    idx, vmap = index_all_with_prices(client)
    log.info("Indexed %d keys / %d variants", len(idx), len(vmap))

    # All Firestore eurotramp docs (priced + unpriced for completeness counts).
    fs_docs = []
    for d in db.collection("vendors").document(BRAND).collection("products").stream():
        dd = d.to_dict() or {}
        dd["_id"] = d.id
        fs_docs.append(dd)
    fs_priced = [dd for dd in fs_docs if _prices(dd.get("pricing") or {})]
    log.info("Firestore eurotramp: %d docs, %d priced", len(fs_docs), len(fs_priced))

    other_brand_channels = frozenset(SC.values()) - {EUROTRAMP_SC}

    # ---- Direction A: Firestore priced docs → Medusa (mirror the writer) ----
    stale, missing, crossbrand = [], [], []
    ok = []
    matched_vids: set[str] = set()
    for dd in fs_priced:
        sku = str(dd.get("item_code") or "").strip()
        hit, guard = _match_key(dd, idx, EUROTRAMP_SC, other_brand_channels)
        expected = _prices(dd["pricing"])
        if hit:
            cand = vmap[hit["vid"]]
            matched_vids.add(hit["vid"])
            diff = _diff_prices(expected, cand["prices"])
            rec = {
                "sku": sku, "vid": hit["vid"], "pid": hit["pid"],
                "title": cand["title"], "on_eurotramp_sc": EUROTRAMP_SC in cand["scs"],
                "already_fixed": sku in ALREADY_FIXED,
                "expected": {p["currency_code"]: p["amount"] for p in expected},
                "live": cand["prices"], "diff": diff,
                "price_date": (dd.get("pricing") or {}).get("price_date"),
            }
            (stale if diff else ok).append(rec)
        elif guard:
            crossbrand.append({"sku": sku, "key": guard["key"],
                               "on_channels": guard["channels"]})
        else:
            missing.append({"sku": sku, "handle": dd.get("handle"),
                            "title": dd.get("name") or dd.get("title")})

    # ---- Direction B: Eurotramp-SC Medusa variants → Firestore (orphans) ----
    fs_skus = {str(dd.get("item_code") or "").strip() for dd in fs_priced}
    fs_skus |= {s.upper() for s in fs_skus}
    orphans = []
    eurotramp_variant_count = 0
    for vid, cand in vmap.items():
        if EUROTRAMP_SC not in cand["scs"]:
            continue
        eurotramp_variant_count += 1
        sku, legacy = cand["sku"], cand["legacy"]
        if (sku and sku in fs_skus) or (legacy and legacy in fs_skus):
            continue  # has a Firestore priced doc → covered in Direction A
        orphans.append({"sku": sku, "legacy_sku": legacy, "vid": vid,
                        "title": cand["title"], "handle": cand["handle"],
                        "live": cand["prices"]})

    # ---- 28-fix regression check ----
    fixed_status = {s: "absent" for s in ALREADY_FIXED}
    for rec in ok:
        if rec["sku"] in fixed_status:
            fixed_status[rec["sku"]] = "ok"
    for rec in stale:
        if rec["sku"] in fixed_status:
            fixed_status[rec["sku"]] = "STALE"
    fixed_ok = sum(1 for v in fixed_status.values() if v == "ok")
    fixed_bad = [s for s, v in fixed_status.items() if v != "ok"]

    # ---------------------------- report ----------------------------
    print("\n" + "=" * 64)
    print("EUROTRAMP PRICE AUDIT - Medusa live vs 2026 (1E) Firestore")
    print("=" * 64)
    print(f"Firestore eurotramp docs ............ {len(fs_docs)} ({len(fs_priced)} priced)")
    print(f"Medusa variants on Eurotramp SC ..... {eurotramp_variant_count}")
    print(f"Matched (Firestore->Medusa) .......... {len(ok) + len(stale)}")
    print(f"  (a) STALE - needs update .......... {len(stale)}")
    print(f"  (b) ORPHAN - variant, no FS doc ... {len(orphans)}")
    print(f"  (c) MISSING - FS doc, no variant .. {len(missing)}")
    print(f"  (d) CROSSBRAND - skip (other SC) .. {len(crossbrand)}")
    print(f"      OK (already at 2026 price) .... {len(ok)}")
    print(f"  28-fix regression: ok={fixed_ok}/28  bad={fixed_bad or 'none'}")

    def _fmt(rec):
        d = "; ".join(f"{c}: live={l} -> want={e}" for c, (e, l) in rec["diff"].items())
        tag = " [28-fix]" if rec["already_fixed"] else ""
        return f"  {rec['sku']:8} {rec['title'][:42]:42}{tag}  {d}"

    if stale:
        print("\n--- (a) STALE variants (live != 2026) ---")
        for rec in sorted(stale, key=lambda r: r["sku"]):
            print(_fmt(rec))
    if orphans:
        print(f"\n--- (b) ORPHAN Eurotramp variants ({len(orphans)}) ---")
        for o in sorted(orphans, key=lambda r: r["sku"] or ""):
            print(f"  sku={o['sku'] or '-':8} legacy={o['legacy_sku'] or '-':8} {(o['title'] or '')[:40]}")
    if missing:
        print(f"\n--- (c) MISSING from storefront ({len(missing)}) ---")
        for m in sorted(missing, key=lambda r: r["sku"]):
            print(f"  sku={m['sku']:10} {(m['title'] or m['handle'] or '')[:48]}")
    if crossbrand:
        print(f"\n--- (d) CROSS-BRAND (skipped) ({len(crossbrand)}) ---")
        for c in sorted(crossbrand, key=lambda r: r["sku"]):
            print(f"  sku={c['sku']:10} only on={c['on_channels']}")
    if args.show_ok:
        print(f"\n--- OK variants ({len(ok)}) ---")
        for rec in sorted(ok, key=lambda r: r["sku"]):
            print(f"  {rec['sku']:8} {rec['title'][:48]}")

    report = {
        "summary": {
            "fs_docs": len(fs_docs), "fs_priced": len(fs_priced),
            "eurotramp_variants": eurotramp_variant_count,
            "matched": len(ok) + len(stale), "ok": len(ok),
            "stale": len(stale), "orphans": len(orphans),
            "missing": len(missing), "crossbrand": len(crossbrand),
            "fixed_ok": fixed_ok, "fixed_bad": fixed_bad,
        },
        "stale": stale, "orphans": orphans, "missing": missing,
        "crossbrand": crossbrand, "fixed_status": fixed_status,
    }
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("wrote %s", args.json)

    # exit non-zero only when there is fixable drift (stale) or a 28-fix regression
    return 1 if (stale or fixed_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
