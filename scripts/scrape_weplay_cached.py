"""Mine `gs://ai-agents-go-vendors/weplay/pages/*.html` for English product
detail content that the live crawler (`scrape_weplay_en.py`) missed.

Background
----------
`scrape_weplay_en.py` walks the live `weplay.com.tw/mod/product/?lang=en`
nav and pulled 100 SKUs (covering 58 actives + 31 promotable drafts). The
remaining 9 actives + 112 real-SKU drafts weren't reachable via the
live nav — but the original scrape pipeline DID fetch many of them once
and cached the HTML to GCS. Same parsing rules (Item No. span, Product
Feature header, /Products/XX/SKU/ image URLs) apply.

This script reads every cached HTML, picks out the ones that are detail
pages (Item No. marker), parses them, and writes results back to
Firestore using the same merge logic as the live scraper.

Idempotent. Pure local read — no network fetches.

Usage:
    py scripts/scrape_weplay_cached.py --dry-run
    py scripts/scrape_weplay_cached.py --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from html import unescape
from urllib.parse import urlparse

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
log = logging.getLogger("scrape_weplay_cached")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
BUCKET = "ai-agents-go-vendors"
PAGES_PREFIX = "weplay/pages/"

# --- HTML parsing patterns (kept in sync with scrape_weplay_en.py) ---
TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
SPEC_FIELD_RE = re.compile(
    r'<span\s+class="ftit"[^>]*>([^<]+)</span>\s*<span\s+class="ftxt"[^>]*>([^<]*)</span>',
    re.IGNORECASE,
)
ITEM_NO_RE = re.compile(
    r'<span\s+class="ftit"[^>]*>\s*Item\s*No\.?\s*</span>\s*'
    r'<span\s+class="ftxt"[^>]*>\s*([A-Z0-9._-]+)\s*</span>',
    re.IGNORECASE,
)
SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")  # no \b — see scrape_weplay_en.py for why
PRODUCT_FEATURE_RE = re.compile(
    r"Product\s*Feature(.*?)(?=<div\s+class=\"[^\"]*pdesc|<script|<footer|</body)",
    re.IGNORECASE | re.DOTALL,
)
SPEC_BLOCK_RE = re.compile(
    r"Specification(.*?)(?=<script|<footer|</body)", re.IGNORECASE | re.DOTALL,
)
META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
PRODUCTS_IMG_RE = re.compile(
    r"https?://[^\"]+/UserFiles/images/Products/[A-Z0-9]{2}/[A-Z0-9._-]+/[^\"]+",
    re.IGNORECASE,
)
IMG_RE = re.compile(r'<img[^>]*src="([^"]+\.(?:jpg|jpeg|png|webp))"', re.IGNORECASE)
TAG_STRIP_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _clean(s: str) -> str:
    return WS_RE.sub(" ", unescape(TAG_STRIP_RE.sub(" ", s))).strip()


def parse_detail(body: str) -> dict | None:
    """Return the same dict shape as scrape_weplay_en.py's detail_results
    entries, or None if the page isn't an English product detail page."""
    item_m = ITEM_NO_RE.search(body)
    if not item_m:
        return None
    sku = item_m.group(1).upper().strip()

    # Skip pages whose title is Chinese — we want EN only
    title = TITLE_RE.search(body)
    raw_title = title.group(1) if title else ""
    if re.search(r"[一-鿿]", raw_title):
        return None

    en_name = re.sub(r"\s*-\s*Weplay\s*:\s*we play-we learn\s*$", "", raw_title).strip()
    en_name = re.sub(r"^\s*Weplay\s+", "", en_name)

    specs: dict[str, str] = {}
    for label, value in SPEC_FIELD_RE.findall(body):
        lb = _clean(label); vv = _clean(value)
        if not lb or not vv or lb.lower().startswith("item"):
            continue
        key = re.sub(r"[^a-z0-9]+", "_", lb.lower()).strip("_")
        specs[key] = vv

    description = ""
    feat = PRODUCT_FEATURE_RE.search(body)
    if feat:
        description = _clean(feat.group(1))
    if len(description) < 30:
        meta_m = META_DESC_RE.search(body)
        if meta_m:
            description = _clean(meta_m.group(1))

    spec_block = ""
    spec_m = SPEC_BLOCK_RE.search(body)
    if spec_m:
        spec_block = _clean(spec_m.group(1))
        spec_block = re.sub(r"\s*\$\(function\(\).*$|\s*Back\s*$", "", spec_block).strip()

    img_urls = sorted({u for u in PRODUCTS_IMG_RE.findall(body)})
    for u in IMG_RE.findall(body):
        if "/Products/" in u or "/public/files/product/" in u:
            if u not in img_urls:
                img_urls.append(u)

    token_m = SKU_TOKEN_RE.search(sku)
    return {
        "sku": sku,
        "sku_token": token_m.group(1) if token_m else sku,
        "name_en": en_name,
        "description_en": description,
        "spec_block_en": spec_block,
        "specs": specs,
        "image_urls": img_urls,
        "source_urls": [],  # filled by caller
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit-pages", type=int, default=None,
                    help="Only scan first N cached HTML pages (smoke test).")
    args = ap.parse_args()
    write = bool(args.apply)
    log.info("=== scrape_weplay_cached mode=%s limit=%s ===",
             "WRITE" if write else "DRY-RUN", args.limit_pages)

    gcs = storage.Client(project=PROJECT)
    bucket = gcs.bucket(BUCKET)

    blobs = list(bucket.list_blobs(prefix=PAGES_PREFIX))
    if args.limit_pages:
        blobs = blobs[: args.limit_pages]
    log.info("scanning %d cached HTML pages", len(blobs))

    # Parse: dedupe by SKU; merge image URLs across multiple cached pages.
    detail_results: dict[str, dict] = {}
    n_detail = 0
    for blob in blobs:
        body = blob.download_as_text()
        det = parse_detail(body)
        if not det:
            continue
        n_detail += 1
        existing = detail_results.get(det["sku"])
        if existing:
            existing["image_urls"] = sorted(set(existing["image_urls"]) | set(det["image_urls"]))
            existing["source_urls"].append(blob.name)
            # Keep richer description if longer
            if len(det["description_en"]) > len(existing["description_en"]):
                existing["description_en"] = det["description_en"]
            for k, v in det["specs"].items():
                existing["specs"].setdefault(k, v)
            continue
        det["source_urls"] = [blob.name]
        detail_results[det["sku"]] = det

    log.info("parsed: %d cached detail blobs -> %d unique SKUs",
             n_detail, len(detail_results))

    # Cross-reference with Firestore
    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    token_to_docs: dict[str, list[firestore.DocumentSnapshot]] = {}
    for snap in coll.stream():
        d = snap.to_dict() or {}
        sku = (d.get("item_code") or "").upper()
        m = SKU_TOKEN_RE.search(sku)
        if not m:
            continue
        token_to_docs.setdefault(m.group(1), []).append(snap)
    log.info("indexed %d Firestore docs by SKU token",
             sum(len(v) for v in token_to_docs.values()))

    counters = {
        "scraped_skus": len(detail_results),
        "matched_to_doc": 0,
        "skipped_already_has_en": 0,
        "writes": 0,
        "promoted_to_active": 0,
        "no_doc_match": 0,
    }
    sample_writes = []
    sample_no_match = []
    batch = db.batch()
    batch_n = 0
    BATCH = 200

    for sku, det in detail_results.items():
        token = det["sku_token"]
        targets = token_to_docs.get(token, [])
        if not targets:
            counters["no_doc_match"] += 1
            if len(sample_no_match) < 8:
                sample_no_match.append(f"{sku} name={det['name_en']!r}")
            continue
        for snap in targets:
            counters["matched_to_doc"] += 1
            d = snap.to_dict() or {}
            # Only write when this doc DOESN'T already have the EN data the
            # live crawler set. Avoid clobbering richer live data with
            # stale cached versions.
            already_has_en = bool(d.get("source_url_en"))
            if already_has_en:
                counters["skipped_already_has_en"] += 1
                continue

            orig_name = d.get("product_name") or ""
            is_chinese_orig = bool(re.search(r"[一-鿿]", orig_name))

            payload = {
                "name": det["name_en"] or d.get("name"),
                "description": det["description_en"] or d.get("description"),
                "specs": det["specs"] or {},
                "spec_block": det["spec_block_en"] or "",
                "source_url_cached": det["source_urls"][0] if det["source_urls"] else None,
                "source_image_urls_en": det["image_urls"],
                "description_orig": d.get("description"),
            }
            if is_chinese_orig:
                payload["name_zh"] = orig_name

            # Only promote to active if doc already has images[]
            if (d.get("images") or []) and payload["name"] and d.get("status") != "active":
                payload["status"] = "active"
                counters["promoted_to_active"] += 1

            counters["writes"] += 1
            if len(sample_writes) < 8:
                sample_writes.append(
                    f"{snap.id}  sku={sku}  name={payload['name'][:50]!r}"
                )

            if write:
                batch.set(snap.reference, payload, merge=True)
                batch_n += 1
                if batch_n >= BATCH:
                    batch.commit()
                    log.info("  committed batch (%d docs)", batch_n)
                    batch = db.batch()
                    batch_n = 0

    if write and batch_n:
        batch.commit()
        log.info("  committed final batch (%d docs)", batch_n)

    log.info("=== summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    if sample_writes:
        log.info("sample writes:")
        for s in sample_writes:
            log.info("  %s", s)
    if sample_no_match:
        log.info("sample no-doc-match: %s", sample_no_match)
    return 0


if __name__ == "__main__":
    sys.exit(main())
