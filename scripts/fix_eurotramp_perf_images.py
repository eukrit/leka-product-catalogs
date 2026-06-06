"""Targeted hero-image + gallery cleanup for the Eurotramp performance line.

The generic fix_eurotramp_thumbnails.py conservatively skips products whose
gallery has no handle-overlapping photo. This script handles the remaining
competition-line gaps explicitly:

  * REPOINT — promote a real photo already in the product's gallery to thumbnail.
  * UPLOAD  — rehost a real product photo from the local scrape
              (data/scraped/eurotramp/images/) to GCS, add it to images[] and
              set it as the thumbnail.
  * For every scoped product it also DE-CLUTTERS the gallery: real photos first
    (by photo_rank), demoting tiny spare-part previews / merchant logos / badges
    / certs to the end (never dropped).

True upstream gaps (no real photo anywhere) are left untouched and reported.

Rollback metadata: metadata.previous_thumbnail / previous_images / images_fixed_at.
Read-only unless --write. Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.

Usage:
    python scripts/fix_eurotramp_perf_images.py --dry-run
    python scripts/fix_eurotramp_perf_images.py --write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.reclassify_eurotramp_images import classify          # noqa: E402
from scripts.fix_eurotramp_thumbnails import photo_rank, fn_of    # noqa: E402
from scripts.rehost_missing_eurotramp_photos import (             # noqa: E402
    GCS_BUCKET, GCS_PREFIX, PROXY_BASE, upload_via_sdk,
)

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SC_EUROTRAMP = "sc_01KNQAA3Y72W17B7CP2VQ93T3M"
SCOPE_FILE = REPO_ROOT / "data" / "curated" / "eurotramp_performance_line.json"
SCRAPE_IMAGES = REPO_ROOT / "data" / "scraped" / "eurotramp" / "images"

# Promote an existing in-gallery photo (filename) to the thumbnail.
REPOINT = {
    "eurotramp-hdts": "preview-hdts003-transportcase-hdts_ab34f7302e_680x378.jpg",
    "eurotramp-set-of-landing-mats-dmt": "preview-26101-landingmatcover_9bd4331aaa_680x378.jpg",
}
# Rehost a real product photo from the scrape and set it as thumbnail.
UPLOAD = {
    "eurotramp-bungee-longe": "34550-preview-bungeelonge_0151fb8b81_680x378.jpg",
    "eurotramp-spieth-ground-safety-mat": "28330---spieth-ground-safety-mats_cbb2542addd8f8060_680x378.jpg",
    "eurotramp-booster-board-freestyle": "61000f-boosterboardfreestyle_0ef7bd78c0_200x112.jpg",
    "eurotramp-trampoline-set-stationary": "98001k-trampolinesetstationary_92aff79ec2_200x112.jpg",
}


def load_scope() -> list[str]:
    data = json.loads(SCOPE_FILE.read_text(encoding="utf-8"))
    return [h for v in data["groups"].values() for h in v]


# Definitely-not-a-photo classes + the FIG/patented badges the classifier
# leaves as 'unknown'. Everything else (incl. unconventional real-photo names
# like preview-23005-…, 27300f-…, hdts003-…) is treated as a real photo, so we
# never replace a correct thumbnail we merely failed to recognise.
JUNK_CLASSES = {"merchant", "feature-badge", "cert", "placeholder", "symbol", "vector"}
EXTRA_BADGES = ("figapproved", "patented", "all-seasonuse", "water-resistant",
                "uv-lightresistant", "cold-resistant", "madeingermany")


def is_junk(url: str) -> bool:
    fn = fn_of(url).lower()
    if classify(fn) in JUNK_CLASSES:
        return True
    return any(b in fn for b in EXTRA_BADGES)


def is_real_photo(url: str) -> bool:
    return bool(url) and not is_junk(url)


def medusa_session() -> tuple[requests.Session, dict]:
    s = requests.Session()
    tok = s.post(BACKEND + "/auth/user/emailpass", json={
        "email": os.environ["LEKA_MEDUSA_ADMIN_EMAIL"],
        "password": os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]}, timeout=30).json()["token"]
    return s, {"Authorization": "Bearer " + tok}


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()
    write = args.write

    scope = load_scope()
    s, H = medusa_session()
    gcs = None
    if write and UPLOAD:
        from google.cloud import storage
        gcs = storage.Client(project="ai-agents-go")

    # fetch scoped products
    prods: dict[str, dict] = {}
    off = 0
    while True:
        r = s.get(BACKEND + "/admin/products", headers=H, params={
            "limit": 100, "offset": off, "sales_channel_id[]": SC_EUROTRAMP,
            "fields": "id,handle,thumbnail,images.url,metadata.previous_thumbnail"}, timeout=60).json()
        b = r.get("products", [])
        for p in b:
            prods[p["handle"]] = p
        off += 100
        if len(b) < 100:
            break

    changed = flagged = 0
    for h in scope:
        p = prods.get(h)
        if not p:
            print(f"  {h:55} -- MISSING"); continue
        cur_thumb = p.get("thumbnail") or ""
        urls = [i["url"] for i in (p.get("images") or [])]

        new_thumb = None
        action = ""
        if h in UPLOAD:
            fn = UPLOAD[h]
            local = SCRAPE_IMAGES / fn
            proxy = f"{PROXY_BASE}/{GCS_PREFIX}/{h}/{fn}"
            if not local.is_file():
                print(f"  {h:55} -- UPLOAD source missing: {fn}"); flagged += 1; continue
            if write:
                upload_via_sdk(gcs, GCS_BUCKET, local, f"{GCS_PREFIX}/{h}/{fn}", False)
            if proxy not in urls:
                urls.append(proxy)
            new_thumb = proxy
            action = "upload+thumb"
        elif h in REPOINT:
            target = REPOINT[h]
            new_thumb = next((u for u in urls if fn_of(u) == target), None)
            action = "repoint" if new_thumb else "repoint-MISS"
        else:
            if is_real_photo(cur_thumb):
                new_thumb = cur_thumb
                action = "keep"
            else:
                cands = [u for u in urls if is_real_photo(u)]
                if cands:
                    new_thumb = max(cands, key=photo_rank)
                    action = "auto-repoint"

        if not new_thumb:
            print(f"  {h:55} -- FLAG (no real photo)  thumb={fn_of(cur_thumb)}")
            flagged += 1
            continue

        # de-clutter: real photos first (photo_rank desc), junk after; thumb first.
        reals = sorted([u for u in urls if is_real_photo(u)], key=photo_rank, reverse=True)
        junk = [u for u in urls if not is_real_photo(u)]
        ordered = ([new_thumb] if new_thumb in urls else [new_thumb]) + \
                  [u for u in reals if u != new_thumb] + junk
        # dedupe preserving order
        seen = set(); ordered = [u for u in ordered if not (u in seen or seen.add(u))]

        reorder_changed = ordered != urls
        thumb_changed = new_thumb != cur_thumb
        if not (reorder_changed or thumb_changed):
            print(f"  {h:55} ok ({action}, already clean)")
            continue
        changed += 1
        print(f"  {h:55} {action:13} thumb={fn_of(new_thumb)[:42]}  imgs {len(urls)}->{len(ordered)}")

        if write:
            md = p.get("metadata") or {}
            payload = {
                "thumbnail": new_thumb,
                "images": [{"url": u} for u in ordered],
                "metadata": {
                    "previous_thumbnail": md.get("previous_thumbnail") or cur_thumb,
                    "previous_images": urls,
                    "images_fixed_at": "2026-06-06",
                },
            }
            rr = s.post(BACKEND + f"/admin/products/{p['id']}", headers=H, json=payload, timeout=60)
            rr.raise_for_status()

    print(f"\nchanged={changed}  flagged={flagged}  scope={len(scope)}")
    if not write:
        print("DRY-RUN — no writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
