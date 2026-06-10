"""Reconcile the 28 Eurotramp 2026 price-list SKU collisions.

Background
----------
The 2026 Eurotramp (1E) price-list ingest (vendors PR #67) re-priced
`vendors/eurotramp/products` 187 → 707 docs, then pushed to Leka Medusa with
`scripts/sync_vendors_to_medusa.py --brand=eurotramp`. That script matches
Firestore → Medusa by **handle** and CREATEs on a miss. 28 spare-part /
Kids-Tramp-Track SKUs failed with
`400 invalid_data: "Product variant with sku: <SKU> already exists"`.

Root cause: each of these 28 SKUs is already a **variant** of one of 5 existing
multi-variant Eurotramp "umbrella" products (created in the 2025 sync), but the
2026 seed created NEW per-SKU Firestore docs with NEW handles. The vendors model
is 1-doc-per-SKU; Medusa folds them into a handful of multi-variant products —
so handle-matching could never resolve them and tried (and failed) to CREATE.

The 5 umbrellas (all on the Eurotramp sales channel + Leka Catalogs aggregate;
no cross-brand collision):
    eurotramp-bounce-cloud .................. 93001/02/20/21/22/30/31/32
    eurotramp-kids-tramp-track-playground ... 97044/46/48/49/54/56/58/59
    eurotramp-jumping-bed-kids-tramp-track-playground .. E21004/06/08/09
    eurotramp-bonded-impact-protection-kids-tramp-track  E97441/641/841/941
    eurotramp-playpro-rubber-protection-lip-for-kids-tramp-track  E97448/648/848/948

What this script does
---------------------
For each of the 28 SKUs:
  1. Reads the 2026 `pricing.*` (retail_thb/usd/eur/sgd, + legacy fob_usd) from
     the matching `vendors/eurotramp/products` doc (item_code == SKU).
  2. Locates the EXISTING Medusa variant carrying that SKU (paged SKU index).
  3. PATCHes all 4 currency prices onto that variant IN PLACE — matching the
     existing price rows by currency_code so no duplicate price rows are
     orphaned (reuses sync_vendors_to_medusa._update_variant_prices).
  4. (--write) Stamps `medusa_product_id` + `medusa_variant_id` on the Firestore
     doc so future `sync_vendors_to_medusa.py` runs resolve these docs to the
     existing umbrella product (variant-only UPDATE) instead of re-attempting a
     handle CREATE. See the companion patch in sync_vendors_to_medusa.py.

It NEVER creates Medusa products and NEVER touches product-level fields
(title/description/status/options) — it only writes variant prices, so the
multi-variant umbrellas stay intact. It does not change product publication
status (3 of the 5 umbrellas are drafts; left as-is — out of scope).

Usage:
    python scripts/fix_eurotramp_2026_sku_collisions.py --dry-run
    python scripts/fix_eurotramp_2026_sku_collisions.py --write

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD; Firestore via ADC.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import requests
from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Reuse the battle-tested helpers — same price shape as the main sync.
from scripts.sync_vendors_to_medusa import (  # noqa: E402
    BACKEND, TIMEOUT, _build_prices, _headers,
)

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("fix_eurotramp_collisions")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
EUROTRAMP_SC = "sc_01KNQAA3Y72W17B7CP2VQ93T3M"

SKUS = [
    "93001", "93002", "93020", "93021", "93022", "93030", "93031", "93032",
    "97044", "97046", "97048", "97049", "97054", "97056", "97058", "97059",
    "E21004", "E21006", "E21008", "E21009", "E97441", "E97448", "E97641",
    "E97648", "E97841", "E97848", "E97941", "E97948",
]


def _patch_prices_with_retry(token: str, product_id: str, variant_id: str,
                             pricing: dict, existing_prices: list[dict],
                             attempts: int = 5) -> bool:
    """PATCH variant prices with backoff; returns True only on a 2xx.

    The shared sync_vendors_to_medusa._update_variant_prices swallows HTTP
    errors (logs, never raises), and the kids-tramp-track product reliably
    returned transient 503 / read-timeouts under price-recalc load. Here we
    retry on any 5xx or timeout and report real success so the caller's
    error/stamp accounting is accurate. Existing price rows are matched by
    currency_code so we PATCH in place (no orphaned rows)."""
    new_prices = _build_prices(pricing)
    if not new_prices:
        return False
    by_ccy = {(pr.get("currency_code") or "").lower(): pr.get("id")
              for pr in (existing_prices or [])}
    for entry in new_prices:
        eid = by_ccy.get(entry["currency_code"])
        if eid:
            entry["id"] = eid
    url = f"{BACKEND}/admin/products/{product_id}/variants/{variant_id}"
    delay = 3.0
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(url, json={"prices": new_prices},
                              headers=_headers(token), timeout=120)
            if r.status_code < 300:
                return True
            if r.status_code < 500:
                log.warning("variant %s PATCH %s (non-retryable): %s",
                            variant_id, r.status_code, r.text[:160])
                return False
            log.info("variant %s PATCH %s (attempt %d/%d) — retrying in %.0fs",
                     variant_id, r.status_code, attempt, attempts, delay)
        except requests.RequestException as e:
            log.info("variant %s PATCH error (attempt %d/%d): %s — retrying in %.0fs",
                     variant_id, attempt, attempts, str(e)[:120], delay)
        if attempt < attempts:
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    return False


def auth() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        raise RuntimeError("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.")
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["token"]


def build_medusa_sku_index(token: str) -> dict[str, dict]:
    """SKU → {product_id, handle, status, variant_id, on_eurotramp,
    existing_prices:[{id,currency_code,amount}]}. Only keeps the variant that
    carries the SKU; pages the whole catalog so variant SKUs are matched
    reliably (the `q=` admin search does NOT match variant SKUs)."""
    want = set(SKUS)
    idx: dict[str, dict] = {}
    offset, limit, total = 0, 200, 0
    while True:
        r = requests.get(
            f"{BACKEND}/admin/products",
            params={"limit": limit, "offset": offset,
                    "fields": "id,handle,status,sales_channels.id,"
                              "variants.id,variants.sku,"
                              "variants.prices.id,variants.prices.currency_code,"
                              "variants.prices.amount"},
            headers=_headers(token), timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            break
        total += len(batch)
        for p in batch:
            sc_ids = {sc["id"] for sc in (p.get("sales_channels") or []) if sc.get("id")}
            for v in (p.get("variants") or []):
                sku = (v.get("sku") or "").strip()
                if sku in want:
                    idx.setdefault(sku, {
                        "product_id": p["id"],
                        "handle": p.get("handle"),
                        "status": p.get("status"),
                        "variant_id": v["id"],
                        "on_eurotramp": EUROTRAMP_SC in sc_ids,
                        "channel_ids": sorted(sc_ids),
                        "existing_prices": [
                            {"id": pr.get("id"),
                             "currency_code": pr.get("currency_code"),
                             "amount": pr.get("amount")}
                            for pr in (v.get("prices") or [])
                        ],
                    })
        if len(batch) < limit:
            break
        offset += limit
    log.info("paged %d Medusa products; located %d / %d target SKUs",
             total, len(idx), len(SKUS))
    return idx


def build_firestore_pricing(db) -> dict[str, dict]:
    """SKU → {doc_id, name, pricing} from vendors/eurotramp/products (item_code==SKU)."""
    want = set(SKUS)
    out: dict[str, dict] = {}
    for d in db.collection("vendors").document("eurotramp").collection("products").stream():
        dd = d.to_dict() or {}
        code = str(dd.get("item_code") or "").strip()
        if code in want:
            out[code] = {"doc_id": d.id, "name": dd.get("name"),
                         "handle": dd.get("handle"), "pricing": dd.get("pricing") or {}}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--skus", default=None,
                    help="Comma-separated subset of SKUs to process (default: all 28). "
                         "Used to retry a transient-failure subset idempotently.")
    args = ap.parse_args()

    targets = SKUS if not args.skus else [s.strip() for s in args.skus.split(",") if s.strip()]

    token = auth()
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)

    med = build_medusa_sku_index(token)
    fs = build_firestore_pricing(db)

    missing_med = [s for s in targets if s not in med]
    missing_fs = [s for s in targets if s not in fs]
    if missing_med:
        log.error("SKUs not found in Medusa (cannot price): %s", missing_med)
    if missing_fs:
        log.error("SKUs not found in Firestore (no 2026 price): %s", missing_fs)

    priced = skipped = errors = stamped = 0
    fs_writes: list[tuple[str, dict]] = []

    for sku in targets:
        m = med.get(sku)
        f = fs.get(sku)
        if not m or not f:
            skipped += 1
            continue
        if not m["on_eurotramp"]:
            log.warning("[%s] variant is NOT on the Eurotramp channel (%s) — "
                        "skipping to avoid cross-brand clobber", sku, m["channel_ids"])
            skipped += 1
            continue
        new_prices = _build_prices(f["pricing"])
        if not new_prices:
            log.warning("[%s] doc %s has no retail/fob pricing — skipping", sku, f["doc_id"])
            skipped += 1
            continue

        old_minor = {(p.get("currency_code") or "").lower(): p["amount"]
                     for p in m["existing_prices"]}
        new_minor = {e["currency_code"]: e["amount"] for e in new_prices}
        # "Already at target" short-circuit: the variant-price endpoint on the
        # kids-tramp-track product reliably times out (~59s → 503) yet often
        # commits server-side, so a write may have landed on a prior run. If the
        # live price already equals the 2026 target (within 1 minor unit), we
        # skip the (slow, flaky) write and just stamp the mapping. Keeps the
        # script idempotent and avoids hammering the slow product.
        at_target = all(abs(new_minor[c] - old_minor.get(c, -1)) <= 1 for c in new_minor)

        new = {e["currency_code"]: e["amount"] / 100.0 for e in new_prices}
        log.info("[%s] %-52s  %s  THB %s -> %s%s",
                 sku, (f["name"] or "")[:52], m["status"],
                 old_minor.get("thb", 0) / 100.0, new.get("thb"),
                 "  [already at target]" if at_target else "")

        if not args.write:
            priced += 1  # would-price count in dry-run
            continue

        if at_target:
            priced += 1
        else:
            if not _patch_prices_with_retry(token, m["product_id"], m["variant_id"],
                                            f["pricing"], m["existing_prices"]):
                errors += 1
                log.warning("[%s] price PATCH failed after retries", sku)
                continue
            priced += 1
        # Stamp the medusa id mapping once the live price is confirmed correct.
        fs_writes.append((f["doc_id"], {
            "medusa_product_id": m["product_id"],
            "medusa_variant_id": m["variant_id"],
        }))

    # Stamp medusa id mappings so the handle-based sync resolves to UPDATE.
    if args.write and fs_writes:
        coll = db.collection("vendors").document("eurotramp").collection("products")
        batch = db.batch()
        for i, (doc_id, payload) in enumerate(fs_writes, 1):
            batch.set(coll.document(doc_id), payload, merge=True)
            if i % 400 == 0:
                batch.commit()
                batch = db.batch()
        batch.commit()
        stamped = len(fs_writes)

    log.info("=== %s: priced=%d skipped=%d errors=%d stamped=%d ===",
             "WRITE" if args.write else "DRY-RUN", priced, skipped, errors, stamped)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
