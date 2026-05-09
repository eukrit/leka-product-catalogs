"""Shape `vendors/weplay/products` docs into the schema that
`sync_vendors_to_medusa.py` expects, and attach images via URL-pattern join.

Background
----------
The Weplay ingest (Phase 1) wrote products with a different field layout than
the other 7 brands and never linked photos to product docs. The sync script
needs `handle`, `name`, `item_code`, `status`, `images[]`. This pass
reshapes each product doc in place (merge writes — no field deletion):

    handle      <- slugified doc.id (already slug-shaped)
    name        <- product_name
    item_code   <- sku
    status      <- "active" if image-match else "draft_no_images"
    images[]    <- [{url, sha}] from URL-pattern attachment join

It also backfills the `vendors/weplay` root doc with the Medusa-ready fields
(`name, slug, country, legal_name, website, status`) — `sales_channel_id` is
written separately after the SC is created in Medusa Admin.

Image join
----------
The Weplay scrape stored 4,770 photos in `vendors/weplay/attachments/*` with
no product cross-reference. ~8% (381) have URL-encoded SKU folders in their
`source_urls` like `.../Products/KM/KM1802/...jpg`. We index those, then
match each product's `sku` token (e.g. `6800KM1802.1-090` -> `KM1802`) to a
folder. Coverage is ~100/1,195 products (8.4%); the rest get no images and
ship as `draft_no_images` so the sync can filter them out.

Image URL form is the storefront proxy:
    https://catalogs.leka.studio/api/i/weplay/media/<sha>.<ext>
served by `medusa-storefront/src/app/api/i/[...path]/route.ts`.

Usage
-----
    py scripts/shape_weplay_to_medusa_schema.py --dry-run            # show stats
    py scripts/shape_weplay_to_medusa_schema.py --apply               # write
    py scripts/shape_weplay_to_medusa_schema.py --apply --limit=20    # smoke
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import Counter, defaultdict

from google.cloud import firestore

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
log = logging.getLogger("shape_weplay")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
PROXY_BASE = "https://catalogs.leka.studio/api/i/weplay"

# Match `/Products/<2-char prefix>/<SKU folder>/` in a Weplay scraped image URL.
URL_RE = re.compile(r"/Products/([A-Z0-9]{2})/([A-Z0-9._-]+?)/", re.IGNORECASE)
# Extract SKU token from product `sku` field (e.g. `6800KM1802.1-090` -> `KM1802`).
SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")

# Vendor root doc Medusa-ready fields. Source: Weplay = Strong Gain Enterprise Co., Ltd.
VENDOR_ROOT_BACKFILL = {
    "name": "Weplay",
    "slug": "weplay",
    "country": "Taiwan",
    "legal_name": "Strong Gain Enterprise Co., Ltd.",
    "website": "https://www.weplay.com.tw/",
    "status": "active",
}


def build_attachment_index(db: firestore.Client) -> dict[str, list[dict]]:
    """Map URL-encoded SKU folder (uppercase) -> list of {sha, ext, url}."""
    log.info("indexing vendors/weplay/attachments by URL-encoded SKU folder")
    index: dict[str, list[dict]] = defaultdict(list)
    n = n_with_token = 0
    for doc in db.collection("vendors").document(SLUG).collection("attachments").stream():
        n += 1
        d = doc.to_dict() or {}
        if d.get("file_type") != "photo":
            continue
        ext = (d.get("ext") or "").lower()
        if ext in {"gif", "svg"}:
            continue  # decorations / icons
        sha = d.get("sha")
        if not sha:
            continue
        for url in d.get("source_urls") or []:
            m = URL_RE.search(url)
            if m:
                token = m.group(2).upper()
                index[token].append({
                    "sha": sha,
                    "ext": ext,
                    "url": f"{PROXY_BASE}/media/{sha}.{ext}",
                })
                n_with_token += 1
                break  # one token per attachment is enough
    log.info("indexed %d attachments (%d had URL-encoded SKU); %d unique SKU folders",
             n, n_with_token, len(index))
    return index


def shape_product(p: dict, doc_id: str, attachment_index: dict[str, list[dict]]) -> tuple[dict, bool]:
    """Return (merge_payload, has_images)."""
    sku = (p.get("sku") or "").strip()
    handle = doc_id.lower().replace(".", "-").replace("_", "-")
    name = (p.get("product_name") or "").strip() or sku or handle

    images: list[dict] = []
    if sku:
        m = SKU_TOKEN_RE.search(sku.upper())
        if m:
            token = m.group(1)
            for att in attachment_index.get(token, []):
                images.append({"url": att["url"], "sha": att["sha"]})

    has_images = bool(images)
    payload = {
        "handle": handle,
        "name": name,
        "item_code": sku or None,
        "status": "active" if has_images else "draft_no_images",
        "images": images,
    }
    return payload, has_images


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Write changes (default is dry-run).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Explicit dry-run flag (default).")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-vendor-root", action="store_true",
                    help="Don't backfill the vendors/weplay root doc.")
    args = ap.parse_args()

    if args.dry_run and args.apply:
        log.error("--dry-run and --apply are mutually exclusive")
        return 2
    write = bool(args.apply)
    log.info("=== shape_weplay mode=%s limit=%s ===", "WRITE" if write else "DRY-RUN", args.limit)

    db = firestore.Client(project=PROJECT, database=DB)
    index = build_attachment_index(db)

    coll = db.collection("vendors").document(SLUG).collection("products")
    docs = list(coll.stream())
    if args.limit:
        docs = docs[: args.limit]
    log.info("scanning %d products", len(docs))

    counters = {"total": 0, "with_images": 0, "drafts": 0, "no_sku": 0, "no_name": 0}
    image_count_dist: Counter[int] = Counter()
    samples_with: list[tuple[str, str, int]] = []
    samples_without: list[tuple[str, str]] = []
    batch = db.batch()
    batch_n = 0
    BATCH_SIZE = 400

    for doc in docs:
        counters["total"] += 1
        p = doc.to_dict() or {}
        payload, has_images = shape_product(p, doc.id, index)

        if not p.get("sku"):
            counters["no_sku"] += 1
        if not p.get("product_name"):
            counters["no_name"] += 1
        if has_images:
            counters["with_images"] += 1
            image_count_dist[len(payload["images"])] += 1
            if len(samples_with) < 5:
                samples_with.append((doc.id, payload["item_code"], len(payload["images"])))
        else:
            counters["drafts"] += 1
            if len(samples_without) < 5:
                samples_without.append((doc.id, payload["item_code"] or "—"))

        if write:
            batch.set(coll.document(doc.id), payload, merge=True)
            batch_n += 1
            if batch_n >= BATCH_SIZE:
                batch.commit()
                log.info("  committed batch (%d docs)", batch_n)
                batch = db.batch()
                batch_n = 0

    if write and batch_n:
        batch.commit()
        log.info("  committed final batch (%d docs)", batch_n)

    log.info("=== summary ===")
    log.info("  totals: %s", counters)
    log.info("  image-count distribution: %s", dict(image_count_dist))
    log.info("  sample with-images:    %s", samples_with)
    log.info("  sample without-images: %s", samples_without)

    # Vendor root backfill — keep separate from sales_channel_id (added later).
    if not args.skip_vendor_root:
        root_ref = db.collection("vendors").document(SLUG)
        if write:
            root_ref.set(VENDOR_ROOT_BACKFILL, merge=True)
            log.info("backfilled vendors/weplay root doc with: %s", list(VENDOR_ROOT_BACKFILL))
        else:
            log.info("DRY-RUN: would backfill vendors/weplay root doc: %s", VENDOR_ROOT_BACKFILL)

    return 0


if __name__ == "__main__":
    sys.exit(main())
