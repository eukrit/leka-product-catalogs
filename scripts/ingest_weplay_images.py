"""Ingest Weplay product images from www.weplay.com.tw EN detail pages
into our private GCS bucket, attach via the storefront proxy URL.

For each `vendors/weplay/products/<doc>` whose `source_image_urls_en` is
non-empty (set by `scrape_weplay_en.py`), download each upstream URL once,
sha256-hash it, upload to `gs://ai-agents-go-vendors/weplay/media/<sha>.<ext>`,
and append `{url: <proxy>, sha: <sha>}` to the product's `images[]` array.
After ingest, products with `status = "draft_no_images"` AND ≥1 image
attached are promoted to `status = "active"`.

Idempotent on two levels:
  - GCS: skip upload when the sha-named blob already exists.
  - Firestore: dedupe `images[]` by `url`.

Image source priority (one product can yield several URLs from EN crawl):
  1. `https://www.weplay.com.tw/UserFiles/images/Products/<XX>/<SKU>/...jpg`
     — high-res lifestyle/marketing photos. Preferred.
  2. `https://www.weplay.com.tw/public/files/product/thumb/Bxxxx.jpg`
     — small thumbnails. Used when no high-res URLs are available
     (typical for newer SKUs, e.g. KP4007, KT0017).

Usage:
    py scripts/ingest_weplay_images.py --dry-run
    py scripts/ingest_weplay_images.py --apply
    py scripts/ingest_weplay_images.py --apply --limit-products=20    # smoke
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import mimetypes
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests
from google.cloud import firestore, storage

_DEFAULT_SA = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
_FALLBACK_ADC = (
    r"C:\Users\Eukrit\AppData\Roaming\gcloud\legacy_credentials"
    r"\codex-chatgpt@ai-agents-go.iam.gserviceaccount.com\adc.json"
)
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ or not os.path.exists(
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
):
    if os.path.exists(_DEFAULT_SA):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _DEFAULT_SA
    elif os.path.exists(_FALLBACK_ADC):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _FALLBACK_ADC
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("ingest_weplay_images")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
BUCKET = "ai-agents-go-vendors"
GCS_PREFIX = "weplay/media"
PROXY_BASE = "https://catalogs.leka.studio/api/i/weplay/media"

# Sort: high-res first, then thumbs.
def _url_priority(u: str) -> int:
    if "/UserFiles/images/Products/" in u:
        return 0
    if "/public/files/product/thumb/" in u:
        return 2
    if "/public/files/product/" in u:
        return 1
    return 3


def _ext_for(url: str, content_type: str | None) -> str:
    """Pick file extension from URL path, fallback to content-type."""
    path = urlparse(url).path
    m = re.search(r"\.(jpg|jpeg|png|webp|gif)(?:\?|$)", path, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    if content_type:
        guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
        if guessed:
            return guessed.lstrip(".").lower()
    return "jpg"


def _existing_images_set(images: list) -> set[str]:
    """Return set of urls in images[] (which may be dicts or strings)."""
    out: set[str] = set()
    for img in images or []:
        if isinstance(img, dict) and img.get("url"):
            out.add(img["url"])
        elif isinstance(img, str):
            out.add(img)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit-products", type=int, default=None,
                    help="Only process first N products (smoke test).")
    ap.add_argument("--polite-ms", type=int, default=200,
                    help="Sleep between fetches in ms (default 200).")
    ap.add_argument("--enrich-actives", action="store_true",
                    help="Also ingest images for products that already have "
                         "images[]. Default: skip (we only fill empty drafts).")
    args = ap.parse_args()

    write = bool(args.apply)
    log.info("=== ingest_weplay_images mode=%s limit=%s polite_ms=%d ===",
             "WRITE" if write else "DRY-RUN", args.limit_products, args.polite_ms)

    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")

    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LekaCatalogBot/1.0)"})
    gcs = storage.Client(project=PROJECT)
    bucket = gcs.bucket(BUCKET)

    # Cache of GCS blob existence (sha -> bool) to avoid re-stat per product
    blob_exists_cache: dict[str, bool] = {}

    def gcs_blob_path(sha: str, ext: str) -> str:
        return f"{GCS_PREFIX}/{sha}.{ext}"

    counters = {
        "products_scanned": 0,
        "products_with_source_urls": 0,
        "products_skipped_already_have_images": 0,
        "products_updated": 0,
        "promoted_to_active": 0,
        "urls_attempted": 0,
        "urls_uploaded": 0,
        "urls_already_in_gcs": 0,
        "urls_failed_fetch": 0,
        "urls_already_in_images": 0,
    }
    sample_promotions: list[str] = []

    docs = list(coll.stream())
    if args.limit_products:
        docs = [d for d in docs if (d.to_dict() or {}).get("source_image_urls_en")]
        docs = docs[: args.limit_products]
    log.info("scanning %d product docs", len(docs))

    batch = db.batch()
    batch_n = 0
    BATCH_SIZE = 200

    for doc in docs:
        counters["products_scanned"] += 1
        d = doc.to_dict() or {}
        source_urls = d.get("source_image_urls_en") or []
        if not source_urls:
            continue
        counters["products_with_source_urls"] += 1

        # Sort by priority: high-res first
        source_urls = sorted(set(source_urls), key=lambda u: (_url_priority(u), u))

        existing_images = list(d.get("images") or [])
        if existing_images and not args.enrich_actives:
            counters["products_skipped_already_have_images"] += 1
            continue
        existing_urls = _existing_images_set(existing_images)
        new_image_entries: list[dict] = []

        for upstream_url in source_urls:
            counters["urls_attempted"] += 1
            try:
                # HEAD first to get content-type cheaply; some servers don't
                # support HEAD on these paths so fall back to streaming GET.
                ct = None
                content = None
                resp = sess.get(upstream_url, timeout=15, stream=False)
                if resp.status_code != 200:
                    log.warning("  fetch %d %s", resp.status_code, upstream_url)
                    counters["urls_failed_fetch"] += 1
                    continue
                content = resp.content
                ct = resp.headers.get("content-type")
            except requests.RequestException as e:
                log.warning("  fetch ERR %s: %s", upstream_url, e)
                counters["urls_failed_fetch"] += 1
                continue

            if not content or len(content) < 100:
                log.warning("  too small (%d bytes) %s", len(content) if content else 0, upstream_url)
                counters["urls_failed_fetch"] += 1
                continue

            sha = hashlib.sha256(content).hexdigest()
            ext = _ext_for(upstream_url, ct)
            blob_path = gcs_blob_path(sha, ext)
            proxy_url = f"{PROXY_BASE}/{sha}.{ext}"

            if proxy_url in existing_urls:
                counters["urls_already_in_images"] += 1
                continue

            # GCS: upload if not present
            already = blob_exists_cache.get(sha)
            blob = bucket.blob(blob_path)
            if already is None:
                already = blob.exists()
                blob_exists_cache[sha] = already
            if already:
                counters["urls_already_in_gcs"] += 1
            else:
                if write:
                    blob.upload_from_string(content, content_type=ct or f"image/{ext}")
                blob_exists_cache[sha] = True
                counters["urls_uploaded"] += 1

            new_image_entries.append({"url": proxy_url, "sha": sha})
            existing_urls.add(proxy_url)

            time.sleep(args.polite_ms / 1000.0)

        if not new_image_entries:
            continue

        merged_images = existing_images + new_image_entries
        payload = {"images": merged_images}

        # Promote to active iff we now have ≥1 image AND we have a name
        is_currently_draft = d.get("status") == "draft_no_images"
        had_no_images = not existing_images
        if had_no_images and merged_images and (d.get("name") or "").strip():
            payload["status"] = "active"
            if is_currently_draft:
                counters["promoted_to_active"] += 1
                if len(sample_promotions) < 10:
                    sample_promotions.append(
                        f"{doc.id}  +{len(new_image_entries)} imgs  name={d.get('name')!r}"
                    )

        counters["products_updated"] += 1
        if write:
            batch.set(doc.reference, payload, merge=True)
            batch_n += 1
            if batch_n >= BATCH_SIZE:
                batch.commit()
                log.info("  committed batch (%d docs)", batch_n)
                batch = db.batch()
                batch_n = 0

        if counters["products_updated"] % 10 == 0:
            log.info("progress: scanned=%d, updated=%d, urls_uploaded=%d, urls_skipped_in_gcs=%d, promoted=%d",
                     counters["products_scanned"],
                     counters["products_updated"],
                     counters["urls_uploaded"],
                     counters["urls_already_in_gcs"],
                     counters["promoted_to_active"])

    if write and batch_n:
        batch.commit()
        log.info("committed final batch (%d docs)", batch_n)

    log.info("=== summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    if sample_promotions:
        log.info("sample promotions:")
        for s in sample_promotions:
            log.info("  %s", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
