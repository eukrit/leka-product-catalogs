"""Stamp `metadata.brand_slug` on every Medusa collection + re-prefix Vinci handles.

## Why

Medusa v2 collections are GLOBAL — `GET /store/collections` returns every
collection regardless of the publishable key's sales channel. The storefront
(leka-website `catalogs/`) historically filtered them client-side by HANDLE
PREFIX (`berliner-`, `4soft-`, `vortex-`, `leka-project-`). Vinci's collections
were created with BARE handles (`robinia`, `wooden`, ...), so Vinci used a
negative "blocklist" filter — which leaked every unprefixed collection
(Eurotramp legacy/orphan collections) onto the Vinci PLP.

This script makes collection→brand association ROBUST so the storefront can
filter on `collection.metadata.brand_slug === brand.slug` instead of handles:

  1. For every collection, infer its brand from the majority `brand_slug` of the
     products assigned to it (products carry `metadata.brand_slug`).
  2. Collections with ZERO products are true orphans → tagged `brand_slug="_orphan"`
     (matches no brand, so they disappear from every PLP) and logged for review.
  3. Stamp `metadata.brand_slug` (shallow-merge — Medusa metadata update merges;
     send the full merged object; clear a key by sending "").
  4. Re-prefix Vinci collection handles to `vinci-*` for cross-brand consistency
     (handle is now cosmetic; metadata.brand_slug is load-bearing). Collection
     IDs are NEVER changed, so product↔collection links survive untouched.

Idempotent: re-running skips collections already tagged with the correct
brand_slug and handles already prefixed.

## Credentials
Admin login via env (from GCP Secret Manager — do NOT hardcode a key path):
    LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD

## Usage
    python scripts/backfill_collection_brand_slug.py --dry-run
    python scripts/backfill_collection_brand_slug.py
    python scripts/backfill_collection_brand_slug.py --revert   # strip vinci- prefix + clear brand_slug
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
log = logging.getLogger("backfill_collection_brand_slug")

BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
TIMEOUT = 60
VINCI_PREFIX = "vinci-"
ORPHAN = "_orphan"
# Sample size for inferring a collection's brand from its products.
BRAND_SAMPLE = 50

# Brand is taken from the authoritative brand-module link (product.brand.name),
# which is always present — unlike metadata.brand_slug, which only the vendor
# upload script (eurotramp/berliner/4soft) stamps. Map the brand NAME to the
# storefront slug (must match leka-website catalogs/src/lib/medusa-client.ts).
# NOTE: `GET /admin/products?fields=id,metadata` returns an EMPTY products array
# for some collections (a Medusa serialization quirk); requesting a nested field
# like `brand.name` returns them correctly — so always query brand.name here.
NAME_TO_SLUG = {
    "Leka Project": "leka-project",
    "Vinci Play": "vinci",
    "Berliner Seilfabrik": "berliner",
    "Eurotramp": "eurotramp",
    "Rampline": "rampline",
    "4soft": "4soft",
    "Vortex Aquatics": "vortex",
    "Weplay": "weplay",
    "Design Park": "designpark",
}


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


def _iter_collections(tok: str, page: int = 100):
    offset = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/collections", headers=_hdr(tok),
                         params={"limit": page, "offset": offset,
                                 "fields": "id,title,handle,metadata"},
                         timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json().get("collections", [])
        if not batch:
            return
        for c in batch:
            yield c
        if len(batch) < page:
            return
        offset += page


def _infer_brand(tok: str, collection_id: str) -> tuple[str, int]:
    """Return (brand_slug, product_count). Brand = majority brand-module link
    (product.brand.name) mapped via NAME_TO_SLUG. ORPHAN if the collection has
    no products or no recognizable brand."""
    r = requests.get(f"{BACKEND}/admin/products", headers=_hdr(tok),
                     params={"collection_id": collection_id, "limit": BRAND_SAMPLE,
                             "fields": "id,brand.name"},
                     timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    products = body.get("products", [])
    count = body.get("count", len(products))
    if not products:
        return ORPHAN, count
    votes = Counter(
        (p.get("brand") or {}).get("name")
        for p in products
        if (p.get("brand") or {}).get("name")
    )
    if not votes:
        return ORPHAN, count
    top_name = votes.most_common(1)[0][0]
    slug = NAME_TO_SLUG.get(top_name)
    if not slug:
        log.warning("  unmapped brand name %r (collection %s) — tagging orphan",
                    top_name, collection_id)
        return ORPHAN, count
    return slug, count


def _update_collection(tok: str, cid: str, payload: dict) -> None:
    r = requests.post(f"{BACKEND}/admin/collections/{cid}", headers=_hdr(tok),
                      json=payload, timeout=TIMEOUT)
    r.raise_for_status()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true",
                    help="Strip vinci- prefix from Vinci handles and clear metadata.brand_slug.")
    args = ap.parse_args()

    tok = _auth()
    log.info("Authenticated against %s", BACKEND)

    collections = list(_iter_collections(tok))
    log.info("Fetched %d collections", len(collections))

    counts = Counter()
    rename_map: dict[str, str] = {}  # old_handle -> new_handle (for deep-link reference)
    per_brand = Counter()

    for c in collections:
        cid, handle, meta = c["id"], c.get("handle", ""), (c.get("metadata") or {})
        counts["processed"] += 1

        # ---- REVERT path ------------------------------------------------------
        if args.revert:
            payload: dict = {}
            if handle.startswith(VINCI_PREFIX):
                payload["handle"] = handle[len(VINCI_PREFIX):]
            if meta.get("brand_slug"):
                # Medusa metadata update is a shallow-merge; "" clears the key.
                payload["metadata"] = {**meta, "brand_slug": ""}
            if not payload:
                continue
            if args.dry_run:
                log.info("  [dry-run] REVERT %s -> %s", handle, payload.get("handle", handle))
                counts["reverted"] += 1
                continue
            _update_collection(tok, cid, payload)
            counts["reverted"] += 1
            time.sleep(0.05)
            continue

        # ---- FORWARD path -----------------------------------------------------
        brand, pcount = _infer_brand(tok, cid)
        per_brand[brand] += 1
        if brand == ORPHAN:
            log.warning("  ORPHAN (0 products): %s '%s' (%s)", handle, c.get("title"), cid)

        payload = {}
        # Stamp brand_slug if missing or wrong.
        if meta.get("brand_slug") != brand:
            payload["metadata"] = {**meta, "brand_slug": brand}
        # Re-prefix Vinci handles only.
        new_handle = handle
        if brand == "vinci" and handle and not handle.startswith(VINCI_PREFIX):
            new_handle = f"{VINCI_PREFIX}{handle}"
            payload["handle"] = new_handle
            rename_map[handle] = new_handle

        if not payload:
            counts["already_ok"] += 1
            continue

        if args.dry_run:
            log.info("  [dry-run] %-40s brand=%-12s handle: %s -> %s (products=%s)",
                     cid, brand, handle, new_handle, pcount)
            counts["would_update"] += 1
            continue

        _update_collection(tok, cid, payload)
        counts["updated"] += 1
        log.info("  updated %-40s brand=%-12s %s -> %s", cid, brand, handle, new_handle)
        time.sleep(0.05)

    log.info("Done: %s", dict(counts))
    if not args.revert:
        log.info("Brand distribution: %s", dict(per_brand))
    if rename_map:
        log.info("Vinci handle renames (old -> new), %d total:", len(rename_map))
        for old, new in sorted(rename_map.items()):
            log.info("  %s -> %s", old, new)


if __name__ == "__main__":
    main()
