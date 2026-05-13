"""Rewrite Medusa product image URLs from /api/i/wisdom/... to /api/i/leka-project/...

After A9 (Gemini logo removal) populated gs://ai-agents-go-vendors/leka-project/
with cleaned images at the same relative paths as gs://...wisdom/, the storefront
proxy serves both prefixes from the same Cloud Run service. This script flips
every Medusa product's thumbnail and images[].url so the storefront fetches the
cleaned versions.

Idempotent: skips when URL already starts with /api/i/leka-project/.

Usage:
    python scripts/rewrite_wisdom_image_urls.py --dry-run
    python scripts/rewrite_wisdom_image_urls.py --limit=10
    python scripts/rewrite_wisdom_image_urls.py
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import re
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("rewrite_image_urls")

BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
WISDOM_SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"  # now the "Leka Project" SC
OLD_SEGMENT = "/api/i/wisdom/"
NEW_SEGMENT = "/api/i/leka-project/"
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


def _retry(method: str, url: str, tok: str, **kw) -> requests.Response:
    delays = [2, 5, 15, 45]
    last_err: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            r = requests.request(method, url, headers=_hdr(tok), timeout=TIMEOUT, **kw)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
            return r
        except (requests.RequestException, requests.HTTPError) as e:
            last_err = e
            if attempt == len(delays):
                break
            time.sleep(delays[attempt] + random.random() * 2)
    raise last_err if last_err else RuntimeError("retry loop fell through")


def _flip(u: str | None) -> str | None:
    if not u:
        return u
    if NEW_SEGMENT in u:
        return u
    return u.replace(OLD_SEGMENT, NEW_SEGMENT)


def _iter_products(tok: str, sc_id: str, limit_per_page: int = 100):
    offset = 0
    while True:
        r = _retry("GET", f"{BACKEND}/admin/products", tok,
                   params={"sales_channel_id[]": sc_id, "limit": limit_per_page, "offset": offset,
                           "fields": "id,handle,thumbnail,images.id,images.url"})
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            yield p
        if len(batch) < limit_per_page:
            return
        offset += limit_per_page


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    tok = _auth()
    log.info("Authenticated against %s", BACKEND)
    log.info("Rewriting %s -> %s for SC %s", OLD_SEGMENT, NEW_SEGMENT, WISDOM_SC_ID)

    counts = {"products": 0, "products_updated": 0, "images_flipped": 0,
              "thumbnails_flipped": 0, "skipped_clean": 0, "errors": 0}
    started = time.time()

    for prod in _iter_products(tok, WISDOM_SC_ID):
        counts["products"] += 1
        pid = prod["id"]
        old_thumb = prod.get("thumbnail")
        new_thumb = _flip(old_thumb)
        old_images = prod.get("images") or []
        new_images = []
        flips = 0
        for img in old_images:
            old_u = img.get("url")
            new_u = _flip(old_u)
            if new_u != old_u:
                flips += 1
            new_images.append({"url": new_u})

        thumb_flipped = new_thumb != old_thumb

        if not flips and not thumb_flipped:
            counts["skipped_clean"] += 1
            continue

        if args.dry_run:
            log.info("  [dry-run] %s (%s): %d images flip, thumb=%s",
                     pid, prod.get("handle"), flips, thumb_flipped)
            counts["images_flipped"] += flips
            if thumb_flipped: counts["thumbnails_flipped"] += 1
            counts["products_updated"] += 1
        else:
            payload: dict = {}
            if flips:
                payload["images"] = new_images
            if thumb_flipped:
                payload["thumbnail"] = new_thumb
            try:
                r = _retry("POST", f"{BACKEND}/admin/products/{pid}", tok, json=payload)
                r.raise_for_status()
                counts["images_flipped"] += flips
                if thumb_flipped: counts["thumbnails_flipped"] += 1
                counts["products_updated"] += 1
            except Exception as e:
                log.error("  %s update failed: %s", pid, str(e)[:200])
                counts["errors"] += 1

        if counts["products"] % 200 == 0:
            rate = counts["products"] / max(time.time() - started, 0.001)
            log.info("  %d processed (%.1f/s) — %s", counts["products"], rate, counts)

        if args.limit and counts["products_updated"] >= args.limit:
            log.info("--limit=%d reached.", args.limit)
            break

    elapsed = time.time() - started
    log.info("Done in %.1fs: %s", elapsed, counts)


if __name__ == "__main__":
    main()
