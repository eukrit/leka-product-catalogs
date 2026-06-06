"""Reassign Eurotramp products to the correct site categories + family
collections, and unpublish discontinued products.

Source of truth: data/curated/eurotramp_category_map.json
  - categories            : the 13 eurotramp.com nav categories (handle -> name)
  - collections           : cross-cutting family collections (handle -> title)
  - category_overrides    : authoritative handle -> category for main products
  - accessory_handle_regex / accessory_name_patterns : route spare parts
  - collection_rules      : priority-ordered (collection_handle, [handle substrings])
  - discontinued          : handles to set status=draft

Behaviour per product:
  - category : REPLACE the category set with the single resolved category
               (R1 probe confirmed POST /admin/products/:id {categories:[...]}
               is a full-set replace).
  - collection: set collection_id to the first matching family (else leave as-is).
  - status   : set 'draft' if handle is in the discontinued list (never auto-publishes).
  - metadata : stash previous_categories / previous_collection_id / previous_status
               once (idempotent) for rollback.

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD (or MEDUSA_ADMIN_*).

Usage:
    python scripts/reassign_eurotramp_categories.py --dry-run
    python scripts/reassign_eurotramp_categories.py --apply [--limit N]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
CURATED = REPO_ROOT / "data" / "curated" / "eurotramp_category_map.json"

from shared.medusa_importer import MedusaImporter  # noqa: E402

MEDUSA_URL = os.environ.get(
    "MEDUSA_BACKEND_URL",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)


def _env_alias() -> None:
    for a, b in (("LEKA_MEDUSA_ADMIN_EMAIL", "MEDUSA_ADMIN_EMAIL"),
                 ("LEKA_MEDUSA_ADMIN_PASSWORD", "MEDUSA_ADMIN_PASSWORD")):
        if not os.environ.get(b) and os.environ.get(a):
            os.environ[b] = os.environ[a]


def fetch_eurotramp(client: MedusaImporter) -> list[dict]:
    fields = "id,handle,title,status,categories.id,categories.handle,collection.id,collection.handle,metadata"
    out, offset, limit = [], 0, 200
    while True:
        r = client._get("/admin/products", {"limit": limit, "offset": offset, "fields": fields})
        batch = r.get("products", [])
        if not batch:
            break
        for p in batch:
            if (p.get("handle") or "").startswith("eurotramp-"):
                out.append(p)
        offset += limit
    out.sort(key=lambda p: p["handle"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cur = json.loads(CURATED.read_text(encoding="utf-8"))
    categories = cur["categories"]
    collections = cur["collections"]
    overrides = cur["category_overrides"]
    acc_re = re.compile(cur["accessory_handle_regex"])
    name_pats = [p.lower() for p in cur["accessory_name_patterns"]]
    coll_rules = cur["collection_rules"]
    discontinued = set(cur["discontinued"])

    def resolve_category(handle: str, title: str) -> tuple[str, str]:
        if handle in overrides:
            return overrides[handle], "override"
        if acc_re.search(handle):
            return "accessories-spare-parts", "accessory-regex"
        tl = (title or "").lower()
        for pat in name_pats:
            if pat in tl:
                return "accessories-spare-parts", "accessory-name"
        return "accessories-spare-parts", "fallback-unmapped"

    def resolve_collection(handle: str) -> str | None:
        hl = handle.lower()
        for coll_handle, subs in coll_rules:
            if any(s in hl for s in subs):
                return coll_handle
        return None

    _env_alias()
    client = MedusaImporter(base_url=MEDUSA_URL)
    if not client.api_key:
        print("ERROR: no Medusa admin auth.", file=sys.stderr)
        return 2

    # 1) Ensure categories + collections exist (idempotent).
    cat_id: dict[str, str] = {}
    for handle, name in categories.items():
        cat_id[handle] = client.get_or_create_category(name, handle)
    coll_id: dict[str, str] = {}
    for handle, title in collections.items():
        coll_id[handle] = client.get_or_create_collection(title, handle)
    print(f"Categories ensured: {len(cat_id)}; Collections ensured: {len(coll_id)}")

    products = fetch_eurotramp(client)
    print(f"Eurotramp products: {len(products)}")
    if args.limit:
        products = products[: args.limit]

    today = datetime.date.today().isoformat()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    decisions, unmapped = [], []
    n_cat, n_coll, n_status, n_writes, n_fail = 0, 0, 0, 0, 0

    for i, p in enumerate(products, 1):
        h = p["handle"]
        title = p.get("title") or ""
        cur_cats = [c.get("handle") for c in (p.get("categories") or [])]
        cur_coll = (p.get("collection") or {}).get("handle") if isinstance(p.get("collection"), dict) else None
        cur_status = p.get("status")
        meta = dict(p.get("metadata") or {})

        want_cat, reason = resolve_category(h, title)
        want_coll = resolve_collection(h)
        want_status = "draft" if h in discontinued else cur_status

        if reason == "fallback-unmapped":
            unmapped.append(h)

        cat_change = cur_cats != [want_cat]
        coll_change = want_coll is not None and cur_coll != want_coll
        status_change = want_status != cur_status

        rec = {
            "handle": h, "title": title,
            "category": {"from": cur_cats, "to": want_cat, "reason": reason, "change": cat_change},
            "collection": {"from": cur_coll, "to": want_coll, "change": coll_change},
            "status": {"from": cur_status, "to": want_status, "change": status_change},
        }
        decisions.append(rec)

        if not (cat_change or coll_change or status_change):
            continue

        flags = []
        if cat_change:
            flags.append(f"cat {cur_cats}->{want_cat}")
        if coll_change:
            flags.append(f"coll {cur_coll}->{want_coll}")
        if status_change:
            flags.append(f"status {cur_status}->{want_status}")
        print(f"[{i}/{len(products)}] {h}: " + "; ".join(flags))

        if args.dry_run:
            continue

        # Build payload. Stash rollback metadata once.
        payload: dict = {}
        if cat_change:
            payload["categories"] = [{"id": cat_id[want_cat]}]
            meta.setdefault("previous_categories", cur_cats)
            n_cat += 1
        if coll_change:
            payload["collection_id"] = coll_id[want_coll]
            meta.setdefault("previous_collection_id", (p.get("collection") or {}).get("id"))
            n_coll += 1
        if status_change:
            payload["status"] = want_status
            meta.setdefault("previous_status", cur_status)
            n_status += 1
        meta["taxonomy_fixed_at"] = now
        payload["metadata"] = meta

        try:
            client._post(f"/admin/products/{p['id']}", payload)
            n_writes += 1
        except Exception as e:
            n_fail += 1
            rec["error"] = str(e)
            print(f"    ! write failed: {e}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"eurotramp-category-reassign-{today}.json"
    out_path.write_text(json.dumps({
        "generated_at": now,
        "mode": "dry-run" if args.dry_run else "apply",
        "r1_semantics": "replace",
        "totals": {"products": len(products), "writes": n_writes,
                   "cat_changes": n_cat, "coll_changes": n_coll, "status_changes": n_status,
                   "failed": n_fail, "unmapped": len(unmapped)},
        "unmapped": unmapped,
        "decisions": decisions,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # Summary
    from collections import Counter
    cat_dist = Counter(d["category"]["to"] for d in decisions)
    coll_dist = Counter(d["collection"]["to"] for d in decisions if d["collection"]["to"])
    print("\n=== SUMMARY ===")
    print(f"mode: {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print(f"category distribution: {dict(cat_dist)}")
    print(f"collection distribution: {dict(coll_dist)}")
    print(f"unmapped (fallback): {len(unmapped)} {unmapped}")
    print(f"writes: {n_writes} (cat {n_cat}, coll {n_coll}, status {n_status}), failed: {n_fail}")
    print(f"report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
