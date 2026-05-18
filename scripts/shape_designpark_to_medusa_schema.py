"""Phase E1: finalize `vendors/designpark/products` for Medusa sync.

Read every product doc; ensure these invariants hold so
`sync_vendors_to_medusa.py --brand=designpark` can consume them:

  - `handle`     non-empty, slug-shaped (set by ingest_designpark_pricelist.py).
  - `name`       non-empty (already guaranteed).
  - `item_code`  non-empty (already guaranteed).
  - `images[]`   list of `{url, sha, ext}` dicts (set by ingest_designpark_assets.py).
  - `status`     "active" when len(images) >= 1, else "draft_no_images".
                 Themes with no pricing AND no images stay "draft_no_images".

Idempotent — merge writes only.

Usage:
    py scripts/shape_designpark_to_medusa_schema.py --dry-run
    py scripts/shape_designpark_to_medusa_schema.py --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_LOCAL_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for cand in _LOCAL_SA_CANDIDATES:
        if os.path.exists(cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

from google.cloud import firestore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("shape_designpark_to_medusa_schema")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "designpark"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run

    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    n_total, n_promoted, n_kept_draft, n_fixed_handle, n_dropped_dupe_img = 0, 0, 0, 0, 0
    status_after = Counter()

    for snap in coll.stream():
        n_total += 1
        d = snap.to_dict() or {}
        handle = d.get("handle") or snap.id
        images = d.get("images") or []
        # Dedup by sha.
        seen_sha: set[str] = set()
        clean_images: list[dict] = []
        for img in images:
            if isinstance(img, str):
                clean_images.append({"url": img})
                continue
            sha = img.get("sha")
            if sha and sha in seen_sha:
                n_dropped_dupe_img += 1
                continue
            if sha:
                seen_sha.add(sha)
            clean_images.append(img)
        new_status = "active" if clean_images else "draft_no_images"
        before_status = d.get("status") or "draft_no_images"
        if new_status != before_status:
            if new_status == "active":
                n_promoted += 1
            else:
                n_kept_draft += 1
        status_after[new_status] += 1

        update: dict = {"status": new_status, "images": clean_images}
        # Ensure handle exists.
        if not d.get("handle"):
            update["handle"] = snap.id
            n_fixed_handle += 1
        # Add thumbnail convenience field — first image url.
        if clean_images:
            first = clean_images[0]
            update["thumbnail"] = first.get("url") if isinstance(first, dict) else first

        if not dry:
            coll.document(snap.id).set(update, merge=True)

    log.info("%s: total=%d promoted_to_active=%d kept_draft=%d "
             "fixed_handle=%d dropped_dupe_imgs=%d  status_after=%s",
             "[DRY]" if dry else "wrote",
             n_total, n_promoted, n_kept_draft,
             n_fixed_handle, n_dropped_dupe_img, dict(status_after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
