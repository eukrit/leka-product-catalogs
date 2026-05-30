"""Enrich 4soft products with images extracted from the picture-pricelist PDF.

Pipeline (run after foursoft-catalog/extract_pdf_images.py):
  A. --upload        : push the 989 extracted images to
                       gs://ai-agents-go-vendors/4soft/pdf/<owner-handle>.jpg
                       (the bucket the storefront image proxy reads — see
                       leka-website/catalogs/src/app/api/i/[...path]/route.ts).
  B. --write-firestore: set vendors/4soft/products[].images, resolving each of
                       the 2,410 codes to its own PDF image, else a base-design
                       sibling's image (UV-class matched). Precedence:
                         * keep existing real WEB images (medusa_reverse_import /
                           4soft_web) as primary — they are higher-res than the
                           100px PDF thumbnails (the ~377 web-scraped SKUs);
                         * REPLACE v2.41.0 borrowed base-design web images
                           (source=4soft_web_base_design) with the real PDF image;
                         * ADD a PDF image where the doc had none.
  C. --sync-medusa    : for in-channel products whose primary is now a PDF image
                       (the 3D drafts), set images=[pdf]+thumbnail. Leaves the
                       web-image products untouched.

Image URL form: https://catalogs.leka.studio/api/i/4soft/pdf/<owner-handle>.jpg

Usage:
    # GCS auth via GOOGLE_APPLICATION_CREDENTIALS (set).
    python foursoft-catalog/enrich_pdf_images.py --dry-run
    python foursoft-catalog/enrich_pdf_images.py --upload --write-firestore
    export LEKA_MEDUSA_ADMIN_EMAIL=...; export LEKA_MEDUSA_ADMIN_PASSWORD=...
    python foursoft-catalog/enrich_pdf_images.py --sync-medusa
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = REPO_ROOT / "foursoft-catalog" / "data"
PRICELIST_CSV = DATA_DIR / "pricelist_2025-03-01.csv"
IMG_DIR = DATA_DIR / "pdf_images"
MAP_JSON = DATA_DIR / "pdf_images_map.json"

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
GCS_BUCKET = "ai-agents-go-vendors"           # the proxy's bucket
GCS_PREFIX = "4soft/pdf"
PROXY_BASE = "https://catalogs.leka.studio/api/i/4soft/pdf"
SALES_CHANNEL = "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"

# image sources that are "real web" (keep as primary; don't downgrade to PDF)
REAL_WEB_SOURCES = {"medusa_reverse_import", "4soft_web"}
PDF_SOURCE = "4soft_pdf_pricelist"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("foursoft_enrich_pdf")


def norm(c: str) -> str:
    return (c or "").strip().upper()


def base_code(c: str) -> str:
    p = norm(c).split("-")
    return "-".join(p[:2]) if len(p) >= 3 else norm(c)


def is_uv(c: str) -> bool:
    return norm(c).endswith("UV")


def handle_for(code: str) -> str:
    import re
    return "4soft-" + re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")


def build_resolution() -> tuple[dict, dict]:
    """Returns (code->owner_code, owner_code->handle). owner_code is the code
    whose PDF image represents `code` (own if present, else base sibling)."""
    own = json.loads(MAP_JSON.read_text(encoding="utf-8"))  # code -> {handle,...}
    own_codes = set(own)
    # index base -> list of owner codes (split by UV-class for finish match)
    by_base: dict[str, list[str]] = {}
    for c in own_codes:
        by_base.setdefault(base_code(c), []).append(c)

    pl = [norm(r["code"]) for r in csv.DictReader(PRICELIST_CSV.open(encoding="utf-8"))]
    resolution: dict[str, str] = {}
    for c in pl:
        if c in own_codes:
            resolution[c] = c
            continue
        sibs = by_base.get(base_code(c))
        if not sibs:
            continue
        # prefer a sibling with matching UV-class, else any
        same = [s for s in sibs if is_uv(s) == is_uv(c)]
        resolution[c] = (same or sibs)[0]
    owner_handle = {c: own[c]["handle"] for c in own_codes}
    return resolution, owner_handle


def gcs_upload(owner_handles: set[str], dry: bool) -> int:
    from google.cloud import storage
    cl = storage.Client(project=PROJECT)
    bucket = cl.bucket(GCS_BUCKET)
    n = 0
    for h in sorted(owner_handles):
        f = IMG_DIR / f"{h}.jpg"
        if not f.exists():
            log.warning("missing local image: %s", f); continue
        if dry:
            n += 1; continue
        bucket.blob(f"{GCS_PREFIX}/{h}.jpg").upload_from_filename(
            str(f), content_type="image/jpeg")
        n += 1
        if n % 100 == 0:
            log.info("  uploaded %d/%d", n, len(owner_handles))
    return n


def proxy_url(owner_handle: str) -> str:
    return f"{PROXY_BASE}/{owner_handle}.jpg"


def write_firestore(resolution: dict, owner_handle: dict, dry: bool) -> dict:
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document("4soft").collection("products")
    existing = {d.id: (d.to_dict() or {}) for d in coll.stream()}

    stats = {"pdf_primary": 0, "kept_web": 0, "replaced_borrowed": 0,
             "added": 0, "no_pdf": 0, "pdf_handles": []}
    batch = db.batch(); bn = 0
    pl = [norm(r["code"]) for r in csv.DictReader(PRICELIST_CSV.open(encoding="utf-8"))]
    for code in pl:
        handle = handle_for(code)
        owner = resolution.get(code)
        if not owner:
            stats["no_pdf"] += 1
            continue
        url = proxy_url(owner_handle[owner])
        doc = existing.get(handle, {})
        imgs = doc.get("images") or []
        has_real_web = any((im.get("source") in REAL_WEB_SOURCES) for im in imgs)
        if has_real_web:
            stats["kept_web"] += 1
            continue  # don't downgrade higher-res web image
        had_borrowed = any(im.get("source") == "4soft_web_base_design" for im in imgs)
        new_img = [{
            "url": url, "is_primary": True, "source": PDF_SOURCE,
            "representative": (owner != code),
            "owner_code": owner if owner != code else None,
        }]
        new_img[0] = {k: v for k, v in new_img[0].items() if v is not None}
        stats["pdf_primary"] += 1
        stats["pdf_handles"].append(handle)
        if had_borrowed:
            stats["replaced_borrowed"] += 1
        elif not imgs:
            stats["added"] += 1
        if not dry:
            batch.set(coll.document(handle), {"images": new_img}, merge=True)
            bn += 1
            if bn >= 400:
                batch.commit(); batch = db.batch(); bn = 0
    if not dry and bn:
        batch.commit()
    return stats


def sync_medusa(pdf_handles: list[str], dry: bool) -> dict:
    import requests
    from scripts.sync_vendors_to_medusa import auth, _headers
    token = auth()
    # index handle -> product_id in the 4soft channel
    idx = {}; offset = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/products", params={
            "sales_channel_id[]": SALES_CHANNEL, "limit": 200, "offset": offset,
            "fields": "id,handle"}, headers=_headers(token), timeout=60)
        r.raise_for_status()
        b = r.json().get("products", [])
        for p in b:
            if p.get("handle"):
                idx[p["handle"]] = p["id"]
        if len(b) < 200:
            break
        offset += 200
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document("4soft").collection("products")

    upd = miss = err = 0
    for i, handle in enumerate(pdf_handles, 1):
        pid = idx.get(handle)
        if not pid:
            miss += 1; continue   # not in Medusa (e.g. deferred 2D) — Firestore only
        doc = coll.document(handle).get().to_dict() or {}
        imgs = doc.get("images") or []
        url = imgs[0]["url"] if imgs else None
        if not url:
            continue
        if dry:
            upd += 1; continue
        r = requests.post(f"{BACKEND}/admin/products/{pid}",
                          json={"images": [{"url": url}], "thumbnail": url},
                          headers=_headers(token), timeout=60)
        if r.status_code >= 400:
            log.warning("medusa update %s failed: %s %s", handle, r.status_code, r.text[:160])
            err += 1; continue
        upd += 1
        if i % 100 == 0:
            log.info("  medusa %d/%d (updated=%d miss=%d err=%d)", i, len(pdf_handles), upd, miss, err)
    return {"updated": upd, "not_in_medusa": miss, "errors": err}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--write-firestore", action="store_true")
    ap.add_argument("--sync-medusa", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    do_all = not (args.upload or args.write_firestore or args.sync_medusa)

    resolution, owner_handle = build_resolution()
    owners = {owner_handle[o] for o in set(resolution.values())}
    log.info("resolution: %d codes → image (own+borrowed); %d unique owner images",
             len(resolution), len(owners))

    if args.upload or do_all:
        n = gcs_upload(owners, args.dry_run)
        log.info("GCS upload: %d images %s", n, "(dry)" if args.dry_run else "→ gs://%s/%s/" % (GCS_BUCKET, GCS_PREFIX))

    pdf_handles: list[str] = []
    if args.write_firestore or do_all:
        stats = write_firestore(resolution, owner_handle, args.dry_run)
        pdf_handles = stats.pop("pdf_handles")
        log.info("Firestore: %s %s", stats, "(dry)" if args.dry_run else "")
        (DATA_DIR / "pdf_image_handles.json").write_text(json.dumps(pdf_handles), encoding="utf-8")

    if args.sync_medusa or do_all:
        if not pdf_handles:
            hf = DATA_DIR / "pdf_image_handles.json"
            pdf_handles = json.loads(hf.read_text()) if hf.exists() else []
        s = sync_medusa(pdf_handles, args.dry_run)
        log.info("Medusa sync: %s %s", s, "(dry)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
