"""Backfill 4soft.cz scraped detail (dimensions + images) into vendors/4soft/products.

Context (v2.39.0): PR #63 (v2.38.0) priced all 2,410 pricelist SKUs but wrote NO
dimensions, so every landed cost used the flat-35%-uplift + tier-floor
approximation. 4soft.cz only publishes ~400 products (the rest of the 2,410 are
colour/size variants with no individual web page), so we can only recover dims
and images for the ~400 on-web SKUs.

This script reads data/scraped/4soft/products.json and writes, by handle:
  * dimensions{length_cm,width_cm,height_cm,diameter_cm,area_m2}  — when the
    scrape carries a full L/W/H, so import_pricelist.py switches that SKU from
    flat_uplift → dims_scaled CBM landed cost.
  * images[]  — own scraped web images, only when the Firestore doc has none
    (never clobbers the existing medusa_reverse_import images on the 377 matched).

Base-design image borrowing (3D scope only, opt-in via --borrow-base-images):
  Many 3D colour variants (e.g. "MINI Tunnel - red" T1-01A-01) have no web page
  but share a base design (T1-01A) that IS on the web. We attach the base
  design's image to the variant, flagged source="4soft_web_base_design" +
  representative=True, so the draft reviewer knows it's the base colour. URLs use
  the storefront proxy with the base product's handle:
  https://catalogs.leka.studio/api/i/4soft/<base-handle>/<filename>

Usage:
    # auth: GOOGLE_APPLICATION_CREDENTIALS → ai-agents-go SA key (already set)
    python foursoft-catalog/backfill_scraped_details.py --dry-run
    python foursoft-catalog/backfill_scraped_details.py            # dims + own images
    python foursoft-catalog/backfill_scraped_details.py --borrow-base-images --scope 3D
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "foursoft-catalog" / "data"
PRICELIST_CSV = DATA_DIR / "pricelist_2025-03-01.csv"
SCRAPED_JSON = REPO_ROOT / "data" / "scraped" / "4soft" / "products.json"

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "4soft"
PROXY_BASE = "https://catalogs.leka.studio/api/i/4soft"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("foursoft_backfill")


def norm(code: str) -> str:
    return (code or "").strip().upper()


def handle_for(code: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")
    return f"4soft-{slug}"


def base_code(code: str) -> str:
    """Design family = code without the trailing colour segment.
    T1-01A-01 → T1-01A ; M3-12B-53UV → M3-12B ; short codes unchanged."""
    parts = norm(code).split("-")
    return "-".join(parts[:2]) if len(parts) >= 3 else norm(code)


def has_full_dims(d: dict) -> bool:
    return bool(d.get("length_cm") and d.get("width_cm") and d.get("height_cm"))


def proxy_url(handle: str, raw_url: str) -> str:
    filename = os.path.basename(urlparse(raw_url).path)
    return f"{PROXY_BASE}/{handle}/{filename}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--borrow-base-images", action="store_true",
                    help="Attach base-design images to colour variants (scope-filtered).")
    ap.add_argument("--scope", default="3D",
                    help="Dimension scope for base-image borrowing (default 3D). 'all' = no filter.")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
        raise RuntimeError("Set GOOGLE_APPLICATION_CREDENTIALS to the ai-agents-go SA key.")

    scraped = json.loads(SCRAPED_JSON.read_text(encoding="utf-8"))
    pricelist = list(csv.DictReader(PRICELIST_CSV.open(encoding="utf-8")))
    dim_by_code = {norm(r["code"]): r["dimension"] for r in pricelist}
    pl_codes = set(dim_by_code)

    scr_by_code: dict[str, dict] = {}
    base_img_index: dict[str, tuple[str, list[str]]] = {}  # base → (base_handle, image_urls)
    for s in scraped:
        c = norm(s.get("sku"))
        if not c:
            continue
        scr_by_code[c] = s
        imgs = [u for u in (s.get("image_urls") or []) if u]
        if imgs:
            base_img_index.setdefault(base_code(c), (s["handle"], imgs))

    from google.cloud import firestore  # type: ignore
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document(SLUG).collection("products")

    # Bulk-read existing docs once (avoid 2,410 individual gets).
    log.info("streaming existing vendors/4soft/products …")
    existing_by_id = {d.id: (d.to_dict() or {}) for d in coll.stream()}
    log.info("loaded %d existing docs", len(existing_by_id))

    n_dims = n_own_img = n_borrow_img = n_docs = 0
    batch = db.batch()
    batch_n = 0

    # Iterate over pricelist codes (the canonical SKU set).
    rows = pricelist if not args.limit else pricelist[: args.limit]
    for r in rows:
        code = norm(r["code"])
        handle = handle_for(r["code"])
        update: dict = {}

        scr = scr_by_code.get(code)
        # 1) dimensions from own scrape
        if scr and has_full_dims(scr.get("dimensions") or {}):
            d = scr["dimensions"]
            update["dimensions"] = {
                "length_cm": float(d["length_cm"]),
                "width_cm": float(d["width_cm"]),
                "height_cm": float(d["height_cm"]),
                "diameter_cm": float(d.get("diameter_cm") or 0),
                "area_m2": float(d.get("area_m2") or 0),
                "source": "4soft_web",
            }
            n_dims += 1

        # 2) own images — only when doc currently has none (don't clobber reverse-import)
        existing = existing_by_id.get(handle, {})
        existing_imgs = existing.get("images") or []
        if scr and not existing_imgs:
            own = [u for u in (scr.get("image_urls") or []) if u]
            if own:
                update["images"] = [
                    {"url": proxy_url(handle, u), "is_primary": (i == 0),
                     "source": "4soft_web"}
                    for i, u in enumerate(own)
                ]
                n_own_img += 1

        # 3) borrowed base-design image (scope-filtered) for variants with no image
        if (args.borrow_base_images and not existing_imgs and "images" not in update
                and (args.scope == "all" or dim_by_code.get(code) == args.scope)):
            b = base_code(code)
            hit = base_img_index.get(b)
            if hit and code not in scr_by_code:  # only true colour variants, not the base itself
                base_handle, base_imgs = hit
                update["images"] = [
                    {"url": proxy_url(base_handle, base_imgs[0]),
                     "is_primary": True, "source": "4soft_web_base_design",
                     "representative": True, "base_design": b}
                ]
                n_borrow_img += 1

        if not update:
            continue
        n_docs += 1
        if args.dry_run:
            if n_docs <= 12:
                log.info("[dry] %s %s", handle, {k: (v if k != "images" else f"{len(v)} img({v[0]['source']})") for k, v in update.items()})
            continue
        batch.set(coll.document(handle), update, merge=True)
        batch_n += 1
        if batch_n >= 400:
            batch.commit(); batch = db.batch(); batch_n = 0

    if not args.dry_run and batch_n:
        batch.commit()

    log.info("docs updated=%d | dims=%d | own_images=%d | borrowed_base_images=%d (scope=%s)%s",
             n_docs, n_dims, n_own_img, n_borrow_img, args.scope,
             "  [DRY RUN — Firestore untouched]" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
