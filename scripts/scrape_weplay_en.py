"""Re-scrape Weplay product catalog in English from www.weplay.com.tw using
the `?lang=en` URL parameter that returns full English product detail HTML.

Background
----------
The original scrape (e-weplay.com.tw, Chinese) populated
`vendors/weplay/products/*` with `product_name` (Chinese) and partial fields,
plus 4,770 photo attachments with no SKU linkage. Weplay's parent site
www.weplay.com.tw, however, exposes the SAME product detail pages in
English when you append `&lang=en` to the REQUEST_ID URL — and these pages
return clean structured HTML with:

  - <title>Product Name in English</title>
  - <span class="ftit">Item No.</span><span class="ftxt">XX9999</span>
  - <span class="ftit">Age</span><span class="ftxt">3y+</span>
  - <span class="ftit">Maximum Load</span><span class="ftxt">60 KG</span>
  - <span class="ftit">Product Weight</span><span class="ftxt">…</span>
  - <img src=".../UserFiles/images/Products/XX/SKU/…">
  - product description paragraphs

This script BFS-crawls the EN catalog and writes one JSON record per SKU.

What it writes back to Firestore (--apply)
-----------------------------------------
For each EN-scraped SKU that maps to a `vendors/weplay/products/<doc_id>`
(via `item_code` containing the SKU token), MERGE these fields:

  name              <- EN product title (replaces Chinese product_name's role)
  name_zh           <- preserved current product_name
  description       <- EN description paragraph
  description_zh    <- preserved current description
  specs             <- {ageRange, maxLoad, productWeight, ...} dict
  source_url_en     <- the weplay.com.tw EN URL (provenance)
  images            <- existing `images[]` ∪ new EN-page `/Products/XX/SKU/`
                      photos (URL-encoded already, dedup by sha-fragment)
  status            <- bumped to "active" iff post-merge images is non-empty
                      AND name is non-empty (else stays draft_no_images)

Idempotent. Re-running upserts the same fields (set semantics on images).

Usage
-----
    py scripts/scrape_weplay_en.py --crawl                       # crawl only
    py scripts/scrape_weplay_en.py --crawl --limit-pages=50      # smoke
    py scripts/scrape_weplay_en.py --apply                       # crawl+write
    py scripts/scrape_weplay_en.py --apply --dump=out.json       # save audit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import deque
from html import unescape
from typing import Iterable

import requests
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
log = logging.getLogger("scrape_weplay_en")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
PROXY_BASE = "https://catalogs.leka.studio/api/i/weplay"

ROOT_URL = "https://www.weplay.com.tw/mod/product/?lang=en"
DETAIL_BASE = "https://www.weplay.com.tw/mod/product/index.php"

# -- HTML parsing patterns
TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
HREF_RE = re.compile(
    r'href="(https?://www\.weplay\.com\.tw/mod/product/[^"]*REQUEST_ID=[^"]+)"',
    re.IGNORECASE,
)
# Each spec field: <span class="ftit">Label</span><span class="ftxt">Value</span>
SPEC_FIELD_RE = re.compile(
    r'<span\s+class="ftit"[^>]*>([^<]+)</span>\s*<span\s+class="ftxt"[^>]*>([^<]*)</span>',
    re.IGNORECASE,
)
ITEM_NO_RE = re.compile(
    r'<span\s+class="ftit"[^>]*>\s*Item\s*No\.?\s*</span>\s*'
    r'<span\s+class="ftxt"[^>]*>\s*([A-Z0-9._-]+)\s*</span>',
    re.IGNORECASE,
)
# NOTE: no `\b` boundaries — Weplay's full item codes look like `6800KC0002.1-090`,
# and `\b[A-Z]{2}[0-9]{4,}\b` doesn't match `KC0002` inside that because there's
# no word boundary between `0` and `K` (both word chars). The shorter form works
# everywhere we need.
SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")
IMG_RE = re.compile(
    r'<img[^>]*src="([^"]+\.(?:jpg|jpeg|png|webp))"', re.IGNORECASE
)
PRODUCTS_IMG_RE = re.compile(
    r"https?://[^\"]+/UserFiles/images/Products/[A-Z0-9]{2}/[A-Z0-9._-]+/[^\"]+",
    re.IGNORECASE,
)
# Weplay product detail page structure (verified 2026-05-12):
#   <div class="pdesc fold-desc"> Product Feature <br> <real description> </div>
#   <div class="pdesc fold-desc"> Specification   <br> <components/dims> </div>
# Both blocks have nested <div>s, so a greedy regex would over-capture and a
# non-greedy one would under-capture. Easiest reliable approach: find the
# "Product Feature" anchor and capture text up to the next pdesc block.
PRODUCT_FEATURE_RE = re.compile(
    r"Product\s*Feature(.*?)(?=<div\s+class=\"[^\"]*pdesc|<script|<footer|</body)",
    re.IGNORECASE | re.DOTALL,
)
SPEC_BLOCK_RE = re.compile(
    r"Specification(.*?)(?=<script|<footer|</body)",
    re.IGNORECASE | re.DOTALL,
)
META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
P_TAG_TEXT_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
TAG_STRIP_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def _clean_text(s: str) -> str:
    return WHITESPACE_RE.sub(" ", unescape(TAG_STRIP_RE.sub(" ", s))).strip()


def _normalize_url(u: str) -> str:
    """HTML-decode and strip session/tracking params we don't care about."""
    u = unescape(u)
    return u


# -------- Crawl --------------------------------------------------------------

def crawl(limit_pages: int | None = None, polite_ms: int = 400) -> dict:
    """BFS the EN product graph. Returns {sku: detail_dict, ...}."""
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LekaCatalogBot/1.0)"})

    visited: set[str] = set()
    queue: deque[str] = deque([ROOT_URL])
    detail_results: dict[str, dict] = {}
    pages_fetched = 0

    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        if limit_pages and pages_fetched >= limit_pages:
            log.info("hit page limit %d, stopping crawl", limit_pages)
            break

        try:
            r = sess.get(url, timeout=20)
        except requests.RequestException as e:
            log.warning("FETCH ERR %s: %s", url, e)
            continue
        pages_fetched += 1
        if r.status_code != 200:
            log.warning("status %d %s", r.status_code, url)
            continue
        time.sleep(polite_ms / 1000.0)

        body = r.text
        # Discover more REQUEST_ID URLs (lang=en)
        new_urls = 0
        for m in HREF_RE.finditer(body):
            cand = _normalize_url(m.group(1))
            if "lang=en" not in cand:
                cand = cand + ("&" if "?" in cand else "?") + "lang=en"
            if cand not in visited:
                queue.append(cand)
                new_urls += 1

        # Detail page? — must have "Item No." span
        item_m = ITEM_NO_RE.search(body)
        if not item_m:
            if pages_fetched % 20 == 0:
                log.info("crawl progress: pages=%d, queue=%d, details=%d",
                         pages_fetched, len(queue), len(detail_results))
            continue

        sku = item_m.group(1).upper().strip()
        # Token from sku for join key (KM1003 from 6800KM1003 etc.)
        token_m = SKU_TOKEN_RE.search(sku)
        token = token_m.group(1) if token_m else sku

        # Parse title
        t = TITLE_RE.search(body)
        raw_title = t.group(1) if t else ""
        # Trim "- Weplay : we play-we learn" suffix
        en_name = re.sub(r"\s*-\s*Weplay\s*:\s*we play-we learn\s*$", "", raw_title).strip()
        en_name = re.sub(r"^\s*Weplay\s+", "", en_name)  # drop "Weplay " prefix

        # Specs — collect every <ftit>/<ftxt> pair (skip the Item No. one)
        specs: dict[str, str] = {}
        for label, value in SPEC_FIELD_RE.findall(body):
            label_clean = _clean_text(label)
            value_clean = _clean_text(value)
            if not label_clean or not value_clean:
                continue
            if label_clean.lower().startswith("item"):
                continue  # already captured
            # Normalize to camelCase-ish keys
            key = re.sub(r"[^a-z0-9]+", "_", label_clean.lower()).strip("_")
            specs[key] = value_clean

        # Description — anchor on "Product Feature" header inside the pdesc
        # block; falls back to <meta description> only as last resort (which
        # is the same generic boilerplate on every page so we want to avoid).
        description = ""
        feat_m = PRODUCT_FEATURE_RE.search(body)
        if feat_m:
            description = _clean_text(feat_m.group(1))
        if len(description) < 30:
            meta_m = META_DESC_RE.search(body)
            if meta_m:
                description = _clean_text(meta_m.group(1))

        # Spec block — components, dimensions, country of origin (separate
        # from the Item No./Age/Weight key-value spec fields above).
        spec_block = ""
        spec_m = SPEC_BLOCK_RE.search(body)
        if spec_m:
            spec_block = _clean_text(spec_m.group(1))
            # Trim init scripts that often follow the block content
            spec_block = re.sub(
                r"\s*\$\(function\(\).*$|\s*Back\s*$", "", spec_block
            ).strip()

        # Images — collect /Products/XX/SKU/ URLs (high-res) and any other product imgs
        img_urls = sorted({_normalize_url(u) for u in PRODUCTS_IMG_RE.findall(body)})
        # Also include other <img src> URLs from detail body but only if they look like product photos
        all_imgs = [_normalize_url(u) for u in IMG_RE.findall(body)]
        for u in all_imgs:
            if "/Products/" in u or "/public/files/product/" in u:
                if u not in img_urls:
                    img_urls.append(u)

        existing = detail_results.get(sku)
        if existing:
            # merge image lists, keep first-seen URL
            existing["image_urls"] = sorted(set(existing["image_urls"]) | set(img_urls))
            existing["source_urls"].append(url)
            continue

        detail_results[sku] = {
            "sku": sku,
            "sku_token": token,
            "name_en": en_name,
            "description_en": description,
            "spec_block_en": spec_block,
            "specs": specs,
            "image_urls": img_urls,
            "source_urls": [url],
        }

        if len(detail_results) % 25 == 0:
            log.info("crawled %d details (pages=%d, queue=%d, +%d new urls this page)",
                     len(detail_results), pages_fetched, len(queue), new_urls)

    log.info("crawl done: %d pages fetched, %d unique detail SKUs found",
             pages_fetched, len(detail_results))
    return detail_results


# -------- Firestore writeback ------------------------------------------------

def _proxy_url_for(att_doc_id: str, ext: str) -> str:
    return f"{PROXY_BASE}/media/{att_doc_id}.{ext}"


def writeback(detail_results: dict, dry_run: bool) -> dict:
    """Merge EN content into vendors/weplay/products/* by sku-token match."""
    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")

    # Build sku-token -> list of doc snapshots
    token_to_docs: dict[str, list[firestore.DocumentSnapshot]] = {}
    for snap in coll.stream():
        d = snap.to_dict() or {}
        sku = (d.get("item_code") or "").upper()
        m = SKU_TOKEN_RE.search(sku)
        if not m:
            continue
        token_to_docs.setdefault(m.group(1), []).append(snap)
    log.info("indexed %d Firestore docs by SKU token", sum(len(v) for v in token_to_docs.values()))

    counters = {
        "scraped_skus": len(detail_results),
        "matched_to_doc": 0,
        "promoted_to_active": 0,
        "no_doc_match": 0,
        "no_images_after_merge": 0,
    }
    sample_promotions: list[str] = []
    sample_no_match: list[str] = []
    batch = db.batch()
    batch_n = 0
    BATCH_SIZE = 300

    for sku, det in detail_results.items():
        token = det.get("sku_token") or sku
        targets = token_to_docs.get(token, [])
        if not targets:
            counters["no_doc_match"] += 1
            if len(sample_no_match) < 10:
                sample_no_match.append(f"{sku} (token={token}) name={det.get('name_en')!r}")
            continue
        for snap in targets:
            counters["matched_to_doc"] += 1
            d = snap.to_dict() or {}

            # Detect whether the original product_name is Chinese (preserve it
            # as name_zh only in that case to avoid mis-labeling EN strings).
            orig_name = d.get("product_name") or ""
            is_chinese = bool(re.search(r"[一-鿿]", orig_name))

            # description: the upstream pipeline wrote Anthropic-generated EN
            # descriptions to `description`. We preserve that as
            # description_orig (audit/rollback) and overwrite with the new
            # authoritative EN text from the catalog.
            payload = {
                "name": det.get("name_en") or d.get("name"),
                "description": det.get("description_en") or d.get("description"),
                "specs": det.get("specs") or {},
                "spec_block": det.get("spec_block_en") or "",
                "source_url_en": det.get("source_urls", [None])[0],
                "source_image_urls_en": det.get("image_urls", []),
                "description_orig": d.get("description"),
            }
            if is_chinese:
                payload["name_zh"] = orig_name

            # Image policy: EN-page URLs are upstream weplay.com.tw — they
            # aren't in our private bucket so the proxy can't serve them.
            # We DON'T touch images[] here. A separate ingest pass will
            # download new images to GCS and attach via proxy URL. As a
            # consequence, drafts (status=draft_no_images, images=[]) keep
            # their draft status even though they now have EN name + desc.
            existing_images = d.get("images") or []
            has_images = bool(existing_images)
            if has_images and payload["name"]:
                payload["status"] = "active"
                if d.get("status") != "active":
                    counters["promoted_to_active"] += 1
                    if len(sample_promotions) < 5:
                        sample_promotions.append(f"{snap.id}  sku={sku}  name={payload['name'][:60]!r}")
            elif not has_images:
                counters["no_images_after_merge"] += 1

            if not dry_run:
                batch.set(snap.reference, payload, merge=True)
                batch_n += 1
                if batch_n >= BATCH_SIZE:
                    batch.commit()
                    log.info("committed batch (%d docs)", batch_n)
                    batch = db.batch()
                    batch_n = 0

    if not dry_run and batch_n:
        batch.commit()
        log.info("committed final batch (%d docs)", batch_n)

    log.info("writeback summary: %s", counters)
    if sample_promotions:
        log.info("sample promotions: %s", sample_promotions)
    if sample_no_match:
        log.info("sample no-doc-match: %s", sample_no_match[:5])
    return counters


# -------- CLI ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--crawl", action="store_true", help="Crawl only, no writeback.")
    mode.add_argument("--apply", action="store_true",
                      help="Crawl + Firestore merge writeback.")
    mode.add_argument("--load", type=str,
                      help="Skip crawl; load JSON dump and writeback.")
    ap.add_argument("--limit-pages", type=int, default=None,
                    help="Cap on total pages fetched (smoke test).")
    ap.add_argument("--dump", type=str, default=None,
                    help="Path to write JSON dump of crawl result.")
    ap.add_argument("--polite-ms", type=int, default=400,
                    help="Sleep between fetches in ms (default 400).")
    ap.add_argument("--dry-run", action="store_true",
                    help="With --apply, skip Firestore writes.")
    args = ap.parse_args()

    if args.load:
        log.info("loading crawl dump from %s", args.load)
        with open(args.load, "r", encoding="utf-8") as f:
            dump = json.load(f)
        results = dump if isinstance(dump, dict) else {d["sku"]: d for d in dump}
        log.info("loaded %d details", len(results))
        writeback(results, dry_run=args.dry_run)
        return 0

    log.info("=== scrape_weplay_en mode=%s limit_pages=%s polite_ms=%d ===",
             "APPLY" if args.apply else "CRAWL",
             args.limit_pages, args.polite_ms)
    results = crawl(limit_pages=args.limit_pages, polite_ms=args.polite_ms)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        log.info("dumped %d results to %s", len(results), args.dump)
    if args.apply:
        writeback(results, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
