"""
Mirror Vortex product images from vortex-intl.com to GCS.

Downloads each image URL, uploads to:
  gs://ai-agents-go-documents/product-images/vortex/catalog/<slug>/<filename>

Rewrites each product's images[] with `gcs_url` (public HTTPS) while keeping
`url` as the original source for provenance. Idempotent — skips blobs that
already exist.

Usage:
    python vortex-catalog/mirror_images_to_gcs.py
    python vortex-catalog/mirror_images_to_gcs.py --dry-run
    python vortex-catalog/mirror_images_to_gcs.py --limit 10
"""
import os
import sys
import json
import time
import logging
import argparse
import hashlib
from urllib.parse import urlparse

import requests
from google.cloud import storage

BUCKET_NAME = "ai-agents-go-documents"
GCS_PREFIX = "product-images/vortex/catalog"
DATA_PATH = os.path.join(os.path.dirname(__file__), "web-app", "public", "data", "products_all.json")

THROTTLE = 0.25  # seconds between downloads

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("vortex-mirror")


def sanitize_filename(url):
    """Extract a safe filename from a URL, adding short hash if needed."""
    path = urlparse(url).path
    name = os.path.basename(path) or "image.jpg"
    # Add short hash to avoid collisions when same filename appears in different subdirs
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    stem, ext = os.path.splitext(name)
    return f"{stem[:60]}-{h}{ext}"


def mirror_image(bucket, src_url, dest_blob_path, dry_run=False):
    """Download src_url, upload to GCS. Returns public URL."""
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{dest_blob_path}"
    if dry_run:
        return public_url

    blob = bucket.blob(dest_blob_path)
    if blob.exists():
        return public_url

    try:
        r = requests.get(src_url, timeout=45, stream=True)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "image/jpeg")
        blob.upload_from_string(r.content, content_type=content_type)
        return public_url
    except requests.RequestException as e:
        log.warning(f"    download failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", default=DATA_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not os.path.exists(args.data_file):
        log.error(f"Data file not found: {args.data_file}")
        log.error("Run scrape_catalog.py first.")
        sys.exit(1)

    with open(args.data_file, encoding="utf-8") as f:
        products = json.load(f)

    if args.limit:
        products = products[: args.limit]

    log.info(f"Loaded {len(products)} products")

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    total_images = 0
    mirrored = 0
    failed = 0
    start = time.time()

    for idx, p in enumerate(products):
        slug = p.get("slug") or f"product-{p.get('id')}"
        images = p.get("images", [])
        if not images:
            continue
        log.info(f"[{idx+1}/{len(products)}] {slug} — {len(images)} images")

        for img in images:
            src = img.get("url")
            if not src:
                continue
            filename = sanitize_filename(src)
            dest = f"{GCS_PREFIX}/{slug}/{filename}"
            total_images += 1

            public = mirror_image(bucket, src, dest, dry_run=args.dry_run)
            if public:
                img["gcs_url"] = public
                mirrored += 1
            else:
                failed += 1

            if not args.dry_run:
                time.sleep(THROTTLE)

    # Write back
    if not args.dry_run:
        with open(args.data_file, "w", encoding="utf-8") as f:
            json.dump(products, f, indent=2, ensure_ascii=False)
        log.info(f"Updated {args.data_file} with gcs_url fields")

    elapsed = time.time() - start
    log.info(f"DONE: {mirrored}/{total_images} mirrored, {failed} failed in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
