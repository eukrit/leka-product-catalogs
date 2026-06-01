"""
enrich_medusa_from_po_images.py — Enrich Medusa (Leka Project) products with the
clean single-product photos extracted from the 2026-06-01 Dulwich Wisdom PO.

Pipeline (run the first two once, this script consumes their output):
  1. python wisdom-catalog/extract_po_images.py        -> exports/po_images_raw/<code>.<ext> + manifest.json
  2. powershell -File wisdom-catalog/convert_po_emf.ps1 -> exports/po_images_png/<code>.png
  3. python wisdom-catalog/enrich_medusa_from_po_images.py --write

This script:
  * Uploads each <code>.png to gs://ai-agents-go-vendors/leka-project/po-20260601/<code>.png
    (the PRIVATE proxy bucket — served via https://catalogs.leka.studio/api/i/leka-project/...;
    never make_public, never use a raw storage.googleapis.com URL).
  * Resolves each code to its Medusa product via the Leka Project legacy_sku index.
  * Adds the PO photo to the product's image gallery (full-replace semantics, so
    we re-send existing images + the new one, deduped).
  * Sets the PO photo as the hero/thumbnail ONLY when the current hero is a
    placeholder or a 2025-catalog crop (spatial_v2 / _wisdom_2025_ / catalog/_imgN);
    curated `_notionr2_` heroes are kept. (--hero-all overrides to always set hero.)

Auth: GOOGLE_APPLICATION_CREDENTIALS for GCS; Medusa via MEDUSA_ADMIN_API_KEY or
LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD (Secret Manager medusa-admin-email/-password).

Usage:
    python wisdom-catalog/enrich_medusa_from_po_images.py --dry-run
    python wisdom-catalog/enrich_medusa_from_po_images.py --write
    python wisdom-catalog/enrich_medusa_from_po_images.py --write --hero-all
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PNG_DIR = REPO_ROOT / "wisdom-catalog" / "exports" / "po_images_png"

GCP_PROJECT = "ai-agents-go"
GCS_BUCKET = "ai-agents-go-vendors"          # the proxy-served catalog-image bucket
GCS_PREFIX = "leka-project/po-20260601"      # objects under leka-project/ are served by /api/i/
PROXY_BASE = "https://catalogs.leka.studio/api/i"
MEDUSA_BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
LEKA_PROJECT_SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"

# Heroes we are happy to replace with a clean PO studio shot.
CROP_MARKERS = ("/spatial_v2/", "_wisdom_2025_")
PLACEHOLDER_MARKERS = ("_placeholder/", "coming")
_CATALOG_IMGN = re.compile(r"/catalog/.*_img\d", re.I)


def _norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def _credentials_path() -> str | None:
    for p in (
        r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
        r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
    ):
        if os.path.exists(p):
            return p
    return None


def hero_is_replaceable(thumb: str | None) -> bool:
    """True if the current hero is a placeholder or a 2025-catalog crop."""
    if not thumb:
        return True
    t = thumb.lower()
    if any(m in t for m in PLACEHOLDER_MARKERS):
        return True
    if any(m in t for m in CROP_MARKERS):
        return True
    if _CATALOG_IMGN.search(t):
        return True
    return False


def upload_to_gcs(code: str, local: Path, dry_run: bool) -> str:
    """Upload <code>.png to the proxy bucket; return the proxy URL."""
    object_path = f"{GCS_PREFIX}/{code}.png"
    proxy_url = f"{PROXY_BASE}/{object_path}"
    if dry_run:
        return proxy_url
    from google.cloud import storage
    client = storage.Client(project=GCP_PROJECT)
    blob = client.bucket(GCS_BUCKET).blob(object_path)
    blob.upload_from_filename(str(local), content_type="image/png")
    # Bucket is UBLA + private — DO NOT make_public; the proxy streams it.
    return proxy_url


def index_sc(client) -> dict[str, dict]:
    """norm(sku|legacy_sku) -> product dict (id, thumbnail, images)."""
    idx: dict[str, dict] = {}
    off = 0
    while True:
        r = client._get("/admin/products", {
            "limit": 200, "offset": off, "sales_channel_id[]": LEKA_PROJECT_SC_ID,
            "fields": "id,thumbnail,handle,images.url,variants.sku,variants.metadata"})
        b = r.get("products", [])
        if not b:
            break
        for p in b:
            for v in p.get("variants") or []:
                for k in (v.get("sku"), (v.get("metadata") or {}).get("legacy_sku")):
                    if k:
                        idx.setdefault(_norm(k), p)
        if len(b) < 200:
            break
        off += 200
    return idx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--hero-all", action="store_true",
                    help="Set the PO photo as hero on every product (default: only gaps/crops)")
    ap.add_argument("--png-dir", default=str(PNG_DIR))
    args = ap.parse_args()
    dry = args.dry_run

    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        cred = _credentials_path()
        if cred:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred

    png_dir = Path(args.png_dir)
    pngs = sorted(png_dir.glob("*.png"))
    if not pngs:
        print(f"No PNGs in {png_dir} — run extract_po_images.py + convert_po_emf.ps1 first.")
        return 1
    print(f"PO photos to apply: {len(pngs)}  (mode: {'DRY-RUN' if dry else 'WRITE'}"
          f"{', hero-all' if args.hero_all else ''})\n")

    os.environ.setdefault("MEDUSA_BACKEND_URL", MEDUSA_BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", os.environ.get("MEDUSA_ADMIN_EMAIL", ""))
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", os.environ.get("MEDUSA_ADMIN_PASSWORD", ""))
    from shared.medusa_importer import MedusaImporter
    client = MedusaImporter(base_url=MEDUSA_BACKEND)

    print("Indexing Leka Project sales channel…")
    idx = index_sc(client)
    print(f"  indexed {len(idx)} keys\n")

    hero_set = gallery_only = not_found = errors = 0
    for png in pngs:
        code = png.stem
        p = idx.get(_norm(code))
        if not p:
            print(f"  NOT-IN-SC  {code}")
            not_found += 1
            continue

        proxy_url = upload_to_gcs(code, png, dry)
        cur_thumb = p.get("thumbnail")
        existing = [i.get("url") for i in (p.get("images") or []) if i.get("url")]
        make_hero = args.hero_all or hero_is_replaceable(cur_thumb)

        if make_hero:
            gallery = [proxy_url] + [u for u in existing if u != proxy_url]
            new_thumb = proxy_url
            hero_set += 1
            action = "HERO+gallery"
        else:
            gallery = existing + ([proxy_url] if proxy_url not in existing else [])
            new_thumb = cur_thumb
            gallery_only += 1
            action = "gallery-only (keep curated hero)"

        print(f"  {code:18s} {action}")
        if not dry:
            try:
                client.update_product_images(p["id"], new_thumb, gallery)
                time.sleep(0.05)
            except Exception as e:
                print(f"     ! Medusa error: {e}")
                errors += 1

    print(f"\n{'[dry] ' if dry else ''}Done. hero-set={hero_set}  gallery-only={gallery_only}  "
          f"not-in-SC={not_found}  errors={errors}")
    if dry:
        print("Re-run with --write to upload to GCS + patch Medusa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
