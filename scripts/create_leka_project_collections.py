"""Create themed Leka Project collections + assign products by category.

After the Wisdom → Leka Project rebrand (v2.17.0 + v2.23.8), the Leka Project
sales channel has ~5,062 products spread across 12 top-level categories.
Wisdom never had a "series" concept (unlike Vinci or Berliner), so the
storefront's collection filter is disabled (`hasCollections: false`).

This script generates 5 curated themed collections by mapping each product's
top-level category to the first matching collection from a priority list.
Medusa v2 only supports one collection per product (single `collection_id`),
so the priority order matters.

Themed collections (with their feeding categories):
  furniture-collection             ← furniture
  outdoor-and-nature-play          ← outdoor, nature_play, water_play
  active-play                      ← playground, balance, climbing, sports
  early-years-collection           ← early_years
  creative-and-loose-parts         ← creative, loose_parts

Products in `other` (~1,691) get no collection assignment — they remain
discoverable via category and search only. Future curation can add a
`other-and-misc` collection or hand-curate from there.

Idempotent: skips products that already have any leka-project-* collection.

Usage:
    python scripts/create_leka_project_collections.py --dry-run
    python scripts/create_leka_project_collections.py
    python scripts/create_leka_project_collections.py --revert
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import Counter

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("create_leka_collections")

BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
LP_SC = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
TIMEOUT = 60
PREFIX = "leka-project-"

# Priority-ordered. First match wins (Medusa: one collection per product).
THEMED_COLLECTIONS = [
    {
        "title": "Furniture",
        "handle": f"{PREFIX}furniture-collection",
        "categories": ["furniture"],
    },
    {
        "title": "Outdoor & Nature Play",
        "handle": f"{PREFIX}outdoor-and-nature-play",
        "categories": ["outdoor", "nature_play", "water_play"],
    },
    {
        "title": "Active Play",
        "handle": f"{PREFIX}active-play",
        "categories": ["playground", "balance", "climbing", "sports"],
    },
    {
        "title": "Early Years",
        "handle": f"{PREFIX}early-years-collection",
        "categories": ["early_years"],
    },
    {
        "title": "Creative & Loose Parts",
        "handle": f"{PREFIX}creative-and-loose-parts",
        "categories": ["creative", "loose_parts"],
    },
]


def _auth() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        log.error("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD."); sys.exit(2)
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("token") or r.json().get("access_token")


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _get_or_create_collection(tok: str, title: str, handle: str, dry_run: bool) -> str | None:
    r = requests.get(f"{BACKEND}/admin/collections", headers=_hdr(tok),
                     params={"handle": [handle], "limit": 1}, timeout=TIMEOUT)
    r.raise_for_status()
    existing = r.json().get("collections", [])
    if existing:
        log.info("  collection exists: %s (%s)", handle, existing[0]["id"])
        return existing[0]["id"]
    if dry_run:
        log.info("  [dry-run] would CREATE collection %s '%s'", handle, title)
        return None
    r = requests.post(f"{BACKEND}/admin/collections", headers=_hdr(tok),
                      json={"title": title, "handle": handle,
                            "metadata": {"brand": "leka-project", "source": "auto-themed-v1"}},
                      timeout=TIMEOUT)
    r.raise_for_status()
    cid = r.json()["collection"]["id"]
    log.info("  collection CREATED: %s (%s)", handle, cid)
    return cid


def _iter_products(tok: str, sc_id: str, page: int = 100):
    offset = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/products", headers=_hdr(tok),
                         params={"sales_channel_id[]": sc_id, "limit": page, "offset": offset,
                                 "fields": "id,handle,collection_id,categories.handle"},
                         timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            yield p
        if len(batch) < page:
            return
        offset += page


def _pick_collection(product: dict, cat_to_collection: dict[str, str]) -> str | None:
    """Pick the first themed-collection match in priority order."""
    cats = {c["handle"] for c in (product.get("categories") or [])}
    for theme in THEMED_COLLECTIONS:
        for ch in theme["categories"]:
            if ch in cats:
                return cat_to_collection[ch]
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true",
                    help="Set collection_id=null on every Leka Project product; do NOT delete collections.")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    tok = _auth()
    log.info("Authenticated against %s", BACKEND)

    if args.revert:
        log.info("REVERT: clearing collection_id on Leka Project products")
        counts = {"processed": 0, "cleared": 0, "errors": 0}
        for p in _iter_products(tok, LP_SC):
            counts["processed"] += 1
            if not p.get("collection_id"):
                continue
            if args.dry_run:
                log.info("  [dry-run] clear %s", p["id"])
                counts["cleared"] += 1
                continue
            try:
                r = requests.post(f"{BACKEND}/admin/products/{p['id']}", headers=_hdr(tok),
                                  json={"collection_id": None}, timeout=TIMEOUT)
                r.raise_for_status()
                counts["cleared"] += 1
            except Exception as e:
                log.error("  %s: %s", p["id"], str(e)[:200])
                counts["errors"] += 1
            if args.limit and counts["cleared"] >= args.limit:
                break
        log.info("REVERT done: %s", counts)
        return

    # Forward path: create collections, assign products.
    log.info("Creating %d themed collections ...", len(THEMED_COLLECTIONS))
    cat_to_collection: dict[str, str] = {}
    collection_titles: dict[str, str] = {}
    for theme in THEMED_COLLECTIONS:
        cid = _get_or_create_collection(tok, theme["title"], theme["handle"], args.dry_run)
        # In dry-run, use the handle as a stub id so we can still preview
        # the per-collection distribution. Real ids are needed only for writes.
        effective_id = cid or f"<dry-run:{theme['handle']}>"
        for ch in theme["categories"]:
            cat_to_collection[ch] = effective_id
        collection_titles[effective_id] = theme["title"]
    log.info("Category -> Collection mapping built: %d categories cover %d collections",
             len(cat_to_collection), len(set(cat_to_collection.values())))

    log.info("Assigning products to collections (priority order) ...")
    counts = {"processed": 0, "assigned": 0, "skipped_already_set": 0,
              "skipped_no_match": 0, "errors": 0}
    per_collection = Counter()
    started = time.time()
    for p in _iter_products(tok, LP_SC):
        counts["processed"] += 1
        if p.get("collection_id"):
            counts["skipped_already_set"] += 1
            continue
        cid = _pick_collection(p, cat_to_collection)
        if not cid:
            counts["skipped_no_match"] += 1
            continue
        if args.dry_run:
            per_collection[collection_titles.get(cid, cid)] += 1
            counts["assigned"] += 1
        else:
            try:
                r = requests.post(f"{BACKEND}/admin/products/{p['id']}", headers=_hdr(tok),
                                  json={"collection_id": cid}, timeout=TIMEOUT)
                r.raise_for_status()
                per_collection[collection_titles.get(cid, cid)] += 1
                counts["assigned"] += 1
            except Exception as e:
                log.error("  %s assign failed: %s", p["id"], str(e)[:200])
                counts["errors"] += 1
        if counts["assigned"] % 200 == 0 and counts["assigned"] > 0:
            log.info("  %d assigned ...", counts["assigned"])
        if args.limit and counts["assigned"] >= args.limit:
            break

    log.info("Done in %.1fs: %s", time.time() - started, counts)
    log.info("Per-collection distribution:")
    for title, n in per_collection.most_common():
        log.info("  %-30s %d", title, n)


if __name__ == "__main__":
    main()
