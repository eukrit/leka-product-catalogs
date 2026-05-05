"""One-shot: rename 4soft GCS objects to replace literal `%20` with space.

The catalog scrape uploaded files with names like
    A1-01A-00%20Circle%2018%20cm%20-%20standard%20colours_WEB_DETAIL.jpg
where `%20` is part of the literal object key. URLs in Medusa are stored
single-encoded (`...A1-01A-00%20Circle...`), which GCS decodes to a space at
fetch time, missing the literal-`%20` object → 404.

Fix: rename each affected object so the literal `%20` becomes a real space.
After renaming, the existing single-encoded URLs in Medusa resolve correctly.

Operates on `gs://ai-agents-go-vendors/4soft/` only. Idempotent (skips objects
that don't contain `%20` in their name).

Usage:
    python scripts/rename_4soft_literal_pct20.py --dry-run
    python scripts/rename_4soft_literal_pct20.py
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed
from google.cloud import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("rename_4soft")

PROJECT = "ai-agents-go"
BUCKET = "ai-agents-go-vendors"
PREFIX = "4soft/"
WORKERS = 16


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    log.info("scanning gs://%s/%s for literal %%20", BUCKET, PREFIX)
    candidates: list[tuple[str, str]] = []
    for blob in client.list_blobs(bucket, prefix=PREFIX):
        if "%20" not in blob.name:
            continue
        new_name = blob.name.replace("%20", " ")
        candidates.append((blob.name, new_name))
    if args.limit:
        candidates = candidates[: args.limit]

    log.info("%d objects to rename", len(candidates))
    if args.dry_run:
        for old, new in candidates[:10]:
            log.info("DRY: %s -> %s", old, new)
        return 0

    renamed = errors = skipped = 0

    def rename_one(pair: tuple[str, str]) -> tuple[bool, str | None]:
        old_name, new_name = pair
        try:
            src_blob = bucket.blob(old_name)
            # Skip if destination already exists (idempotency safeguard).
            if bucket.blob(new_name).exists():
                return False, "dest_exists"
            bucket.rename_blob(src_blob, new_name)
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(rename_one, p): p for p in candidates}
        for i, fut in enumerate(as_completed(futures), 1):
            ok, err = fut.result()
            if ok:
                renamed += 1
            elif err == "dest_exists":
                skipped += 1
            else:
                errors += 1
                log.warning("failed: %s -> %s", futures[fut], err)
            if i % 50 == 0:
                log.info("progress %d/%d (renamed=%d skipped=%d errors=%d)",
                         i, len(candidates), renamed, skipped, errors)

    log.info("DONE renamed=%d skipped=%d errors=%d", renamed, skipped, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
