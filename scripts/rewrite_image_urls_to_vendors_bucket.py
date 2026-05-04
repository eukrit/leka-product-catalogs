"""Rewrite product image URLs from `gs://ai-agents-go-documents/product-images/<leka_slug>/`
to `gs://ai-agents-go-vendors/<vendor_folder>/...` across:

  1. Firestore DB `vendors` -> `vendors/{slug}/products/*` -> `images[].url`
  2. Medusa Admin API products on each brand's sales channel -> `images[].url` + `thumbnail`

Phase 4 of the leka -> vendors migration. Vinci is excluded (its image URLs already
point at zamowienia.vinci-play.pl and stay external).

The slug -> folder mapping in BRAND_FOLDER_MAP MUST be confirmed against
`gcloud storage ls gs://ai-agents-go-vendors/` before live use. The script
verifies each target folder exists at startup and aborts otherwise.

Usage:
    python scripts/rewrite_image_urls_to_vendors_bucket.py --brand=rampline --dry-run
    python scripts/rewrite_image_urls_to_vendors_bucket.py --brand=rampline
    python scripts/rewrite_image_urls_to_vendors_bucket.py --brand=all --target=firestore
    python scripts/rewrite_image_urls_to_vendors_bucket.py --brand=wisdom --target=medusa

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD (only required when
target includes medusa).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from google.cloud import firestore, storage

_LOCAL_SA = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.exists(_LOCAL_SA):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _LOCAL_SA
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("rewrite_image_urls")

PROJECT = "ai-agents-go"
SRC_DB = "vendors"
OLD_BUCKET = "ai-agents-go-documents"
OLD_PREFIX = "product-images"
NEW_BUCKET = "ai-agents-go-vendors"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
TIMEOUT = 60
TOKEN_REFRESH_EVERY = 400
MEDUSA_PAGE = 100

# slug -> Medusa Sales Channel id (mirror of sync_vendors_to_medusa.py).
BRAND_SALES_CHANNELS: dict[str, str] = {
    "wisdom":    "sc_01KNKTHC0B7KFEDSZ3NNM49JQW",
    "vortex":    "sc_01KPRY1T8HZJ57020JPZVGAKZK",
    "berliner":  "sc_01KNQAA3QDYHP15Y9K4PPRMDF0",
    "eurotramp": "sc_01KNQAA3Y72W17B7CP2VQ93T3M",
    "rampline":  "sc_01KNQAA448RY0YPR51FNPM2TVA",
    "4soft":     "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y",
}

# Leka product-images/<slug>/ -> ai-agents-go-vendors/<folder>/.
# CONFIRM these against `gcloud storage ls gs://ai-agents-go-vendors/` before live use.
# The startup check fails loudly if any target folder is absent.
BRAND_FOLDER_MAP: dict[str, str] = {
    "wisdom":    "wisdom-playground",
    "vortex":    "vortex-aquatics",
    "berliner":  "berliner-seilfabrik",
    "eurotramp": "eurotramp",
    "rampline":  "rampline",
    "4soft":     "4soft",
}


def verify_target_folders(brands: list[str]) -> None:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(NEW_BUCKET)
    missing = []
    for slug in brands:
        folder = BRAND_FOLDER_MAP[slug]
        blobs = list(client.list_blobs(bucket, prefix=f"{folder}/", max_results=1))
        if not blobs:
            missing.append(f"{slug} -> gs://{NEW_BUCKET}/{folder}/")
    if missing:
        raise SystemExit(
            "ABORT: target folders missing or empty in gs://%s/:\n  %s\n"
            "Run `gcloud storage ls gs://%s/` and update BRAND_FOLDER_MAP."
            % (NEW_BUCKET, "\n  ".join(missing), NEW_BUCKET)
        )


def rewrite_url(url: str, slug: str) -> tuple[str, str]:
    """Return (new_url, status). status in {rewritten, already_new, external, unknown_host, no_match}."""
    if not url:
        return url, "no_match"
    parts = urlsplit(url)
    if parts.netloc != "storage.googleapis.com":
        if "googleusercontent.com" in parts.netloc:
            return url, "unknown_host"
        return url, "external"
    path = parts.path.lstrip("/")
    if path.startswith(f"{NEW_BUCKET}/"):
        return url, "already_new"
    expected_prefix = f"{OLD_BUCKET}/{OLD_PREFIX}/{slug}/"
    if not path.startswith(expected_prefix):
        return url, "no_match"
    folder = BRAND_FOLDER_MAP[slug]
    tail = path[len(expected_prefix):]
    new_path = f"/{NEW_BUCKET}/{folder}/{tail}"
    return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment)), "rewritten"


def _bump(counters: dict, key: str) -> None:
    counters[key] = counters.get(key, 0) + 1


def rewrite_firestore(slug: str, dry_run: bool, limit: int | None) -> dict:
    db = firestore.Client(project=PROJECT, database=SRC_DB)
    coll = db.collection("vendors").document(slug).collection("products")
    docs = list(coll.stream())
    if limit:
        docs = docs[:limit]
    log.info("[firestore/%s] %d products to scan", slug, len(docs))

    counters = {"docs_scanned": 0, "docs_changed": 0, "urls_rewritten": 0,
                "urls_already_new": 0, "urls_external": 0, "urls_unknown_host": 0,
                "urls_no_match": 0}
    samples: list[tuple[str, str]] = []

    for doc in docs:
        counters["docs_scanned"] += 1
        data = doc.to_dict() or {}
        images = data.get("images") or []
        if not images:
            continue
        new_images = []
        changed = False
        for img in images:
            if not isinstance(img, dict):
                new_images.append(img)
                continue
            old = img.get("url")
            new_url, status = rewrite_url(old, slug)
            _bump(counters, {
                "rewritten": "urls_rewritten",
                "already_new": "urls_already_new",
                "external": "urls_external",
                "unknown_host": "urls_unknown_host",
                "no_match": "urls_no_match",
            }[status])
            if status == "rewritten":
                changed = True
                if len(samples) < 10:
                    samples.append((old, new_url))
                merged = dict(img)
                merged["url"] = new_url
                new_images.append(merged)
            else:
                new_images.append(img)
        if changed:
            counters["docs_changed"] += 1
            if not dry_run:
                coll.document(doc.id).set({"images": new_images}, merge=True)

    if samples:
        log.info("[firestore/%s] sample rewrites:", slug)
        for old, new in samples:
            log.info("    %s\n -> %s", old, new)
    log.info("[firestore/%s] counters: %s", slug, counters)
    return counters


def _admin_login() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        raise RuntimeError("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.")
    r = requests.post(
        f"{BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["token"]


def _hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def rewrite_medusa(slug: str, dry_run: bool, limit: int | None) -> dict:
    sc_id = BRAND_SALES_CHANNELS[slug]
    token = _admin_login()
    counters = {"products_scanned": 0, "products_changed": 0, "urls_rewritten": 0,
                "urls_already_new": 0, "urls_external": 0, "urls_unknown_host": 0,
                "urls_no_match": 0, "errors": 0}
    samples: list[tuple[str, str]] = []
    offset = 0
    processed = 0

    while True:
        r = requests.get(
            f"{BACKEND}/admin/products",
            params={"sales_channel_id[]": sc_id, "limit": MEDUSA_PAGE, "offset": offset,
                    "fields": "id,handle,thumbnail,images.id,images.url"},
            headers=_hdrs(token),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
        products = body.get("products", [])
        if not products:
            break
        for p in products:
            counters["products_scanned"] += 1
            processed += 1
            if processed % TOKEN_REFRESH_EVERY == 0:
                token = _admin_login()
            images = p.get("images") or []
            new_urls: list[str] = []
            changed = False
            for img in images:
                old = img.get("url")
                new_url, status = rewrite_url(old, slug)
                _bump(counters, {
                    "rewritten": "urls_rewritten",
                    "already_new": "urls_already_new",
                    "external": "urls_external",
                    "unknown_host": "urls_unknown_host",
                    "no_match": "urls_no_match",
                }[status])
                if status == "rewritten":
                    changed = True
                    if len(samples) < 10:
                        samples.append((old, new_url))
                    new_urls.append(new_url)
                else:
                    new_urls.append(old)
            new_thumb, thumb_status = rewrite_url(p.get("thumbnail"), slug)
            if thumb_status == "rewritten":
                changed = True
            if changed:
                counters["products_changed"] += 1
                if not dry_run:
                    payload = {"images": [{"url": u} for u in new_urls if u]}
                    if thumb_status == "rewritten":
                        payload["thumbnail"] = new_thumb
                    upd = requests.post(
                        f"{BACKEND}/admin/products/{p['id']}",
                        json=payload,
                        headers=_hdrs(token),
                        timeout=TIMEOUT,
                    )
                    if upd.status_code >= 400:
                        log.warning("[medusa/%s] %s update failed: %s %s",
                                    slug, p.get("handle"), upd.status_code, upd.text[:200])
                        counters["errors"] += 1
            if limit and processed >= limit:
                break
        if limit and processed >= limit:
            break
        if len(products) < MEDUSA_PAGE:
            break
        offset += MEDUSA_PAGE

    if samples:
        log.info("[medusa/%s] sample rewrites:", slug)
        for old, new in samples:
            log.info("    %s\n -> %s", old, new)
    log.info("[medusa/%s] counters: %s", slug, counters)
    return counters


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True,
                    help="Brand slug or 'all' (one of: %s, all)" % ", ".join(BRAND_FOLDER_MAP))
    ap.add_argument("--target", choices=("firestore", "medusa", "both"), default="both")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    brands = list(BRAND_FOLDER_MAP) if args.brand == "all" else [args.brand]
    for b in brands:
        if b not in BRAND_FOLDER_MAP:
            log.error("unknown brand: %s (valid: %s, all)", b, ", ".join(BRAND_FOLDER_MAP))
            return 2

    log.info("=== rewrite_image_urls_to_vendors_bucket mode=%s target=%s brands=%s ===",
             "DRY-RUN" if args.dry_run else "WRITE", args.target, brands)

    verify_target_folders(brands)

    grand_unknown = 0
    grand_rewritten = 0
    for slug in brands:
        if args.target in ("firestore", "both"):
            c = rewrite_firestore(slug, args.dry_run, args.limit)
            grand_unknown += c["urls_unknown_host"]
            grand_rewritten += c["urls_rewritten"]
        if args.target in ("medusa", "both"):
            c = rewrite_medusa(slug, args.dry_run, args.limit)
            grand_unknown += c["urls_unknown_host"]
            grand_rewritten += c["urls_rewritten"]
        time.sleep(1)

    log.info("=== grand: rewritten=%d unknown_host=%d ===", grand_rewritten, grand_unknown)
    if grand_unknown > 0:
        log.error("Encountered %d URLs on unknown hosts (e.g. *.googleusercontent.com). "
                  "Inspect before re-running without --dry-run.", grand_unknown)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
