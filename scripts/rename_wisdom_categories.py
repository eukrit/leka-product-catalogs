"""Rename Medusa product categories with `wisdom-*` handles to `leka-project-*`.

Per leka-product-catalogs CHANGELOG v2.17.0, the Wisdom vendor was rebranded
to "Leka Project" across products and the sales channel. The product
categories were left behind: 76 subcategory handles still start with
`wisdom-`, which surfaces in storefront URLs as `?subcategory=wisdom-...`
and leaks the supplier identity.

This script renames those handles only. Category names (e.g. "Furniture",
"Climbing") are already clean and untouched.

Idempotent: skips when a category already has a `leka-project-` handle.
Stores legacy handle in `metadata.legacy_handle` for revert.

Usage:
    python scripts/rename_wisdom_categories.py --dry-run
    python scripts/rename_wisdom_categories.py
    python scripts/rename_wisdom_categories.py --revert
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("rename_wisdom_categories")

BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
OLD_PREFIX = "wisdom-"
NEW_PREFIX = "leka-project-"
TIMEOUT = 60


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


def _all_categories(tok: str) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/product-categories", headers=_hdr(tok),
                         params={"limit": 200, "offset": offset,
                                 "fields": "id,name,handle,parent_category_id,metadata"},
                         timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json().get("product_categories", [])
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 200:
            break
        offset += 200
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true",
                    help="Restore the legacy_handle stored in metadata.")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    tok = _auth()
    log.info("Authenticated against %s", BACKEND)

    cats = _all_categories(tok)

    if args.revert:
        targets = [c for c in cats if c.get("handle", "").startswith(NEW_PREFIX)
                   and (c.get("metadata") or {}).get("legacy_handle", "").startswith(OLD_PREFIX)]
        log.info("Revert: %d categories have a legacy_handle to restore.", len(targets))
        counts = {"reverted": 0, "errors": 0}
        for c in targets:
            old = (c.get("metadata") or {}).get("legacy_handle")
            new_md = {k: v for k, v in (c.get("metadata") or {}).items() if k != "legacy_handle"}
            if args.dry_run:
                log.info("  [dry-run] %s -> %s", c["handle"], old)
                continue
            try:
                r = requests.post(f"{BACKEND}/admin/product-categories/{c['id']}",
                                  headers=_hdr(tok),
                                  json={"handle": old, "metadata": new_md},
                                  timeout=TIMEOUT)
                r.raise_for_status()
                counts["reverted"] += 1
            except Exception as e:
                log.error("  %s: %s", c["id"], str(e)[:200])
                counts["errors"] += 1
            if args.limit and counts["reverted"] >= args.limit:
                break
        log.info("Revert done: %s", counts)
        return

    # Forward rename
    targets = [c for c in cats if c.get("handle", "").startswith(OLD_PREFIX)]
    log.info("Found %d categories with `wisdom-*` handles (out of %d total).",
             len(targets), len(cats))

    counts = {"renamed": 0, "skipped_already_done": 0, "errors": 0}
    started = time.time()

    for c in targets:
        old = c["handle"]
        new = NEW_PREFIX + old[len(OLD_PREFIX):]
        # Skip if already done
        md = c.get("metadata") or {}
        if md.get("legacy_handle") == old and c["handle"] == new:
            counts["skipped_already_done"] += 1
            continue

        new_md = dict(md)
        new_md["legacy_handle"] = old
        new_md.setdefault("source_brand_internal", "wisdom")

        if args.dry_run:
            log.info("  [dry-run] %s -> %s (name=%r)", old, new, c["name"])
            counts["renamed"] += 1
        else:
            try:
                r = requests.post(f"{BACKEND}/admin/product-categories/{c['id']}",
                                  headers=_hdr(tok),
                                  json={"handle": new, "metadata": new_md},
                                  timeout=TIMEOUT)
                r.raise_for_status()
                counts["renamed"] += 1
            except Exception as e:
                log.error("  %s rename failed: %s", c["id"], str(e)[:200])
                counts["errors"] += 1

        if counts["renamed"] % 20 == 0:
            log.info("  %d renamed so far ...", counts["renamed"])
        if args.limit and counts["renamed"] >= args.limit:
            break

    elapsed = time.time() - started
    log.info("Done in %.1fs: %s", elapsed, counts)


if __name__ == "__main__":
    main()
