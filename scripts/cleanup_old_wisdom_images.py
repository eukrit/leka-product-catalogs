"""Post-scrub cleanup of the old Wisdom-named catalog images (follow-up to v2.66.0).

After `scrub_leka_project_wisdom_traces.py` re-hosted every referenced
`…_wisdom_2025_…` image to a neutral `leka-project/catalog2025/…` name and
repointed the products, two bits of housekeeping remain:

  --drop-broken   Remove product image references whose `_wisdom_2025_` GCS
                  source object does NOT exist (dead links the re-host couldn't
                  copy). If the broken object was the thumbnail, repoint the
                  thumbnail to the first surviving image. Idempotent.

  --sweep         Delete the now-unreferenced old GCS objects under
                  leka-project/{spatial_v2,verified}/ whose name contains
                  `_wisdom_2025_`. DESTRUCTIVE — but only deletes an object when
                  BOTH safety invariants hold:
                    (a) no live Medusa product references it, AND
                    (b) a neutral `catalog2025/` copy exists (bytes preserved).
                  Copy-less orphans (never re-hosted) are reported and LEFT
                  in place — deleting them would lose the only bytes.

  --all           --drop-broken then --sweep.

Dry-run by default; pass --write to apply. Auth mirrors the scrub script:
Admin LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD, GCS via ADC / --sa-key.

Usage:
  python scripts/cleanup_old_wisdom_images.py --drop-broken
  python scripts/cleanup_old_wisdom_images.py --sweep
  python scripts/cleanup_old_wisdom_images.py --all --write
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.scrub_leka_project_wisdom_traces import (  # noqa: E402
    BACKEND, GCS_BUCKET, GCS_BRAND_PREFIX, PROXY_ROOT, WISDOM_IMG_TOKEN,
    _admin_token, _retry, _iter_products, neutral_image,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("cleanup_old_wisdom_images")

SWEEP_PREFIXES = (GCS_BRAND_PREFIX + "spatial_v2/", GCS_BRAND_PREFIX + "verified/")
PROD_FIELDS = "id,handle,thumbnail,images.url"


def _src_key_for_url(url: str) -> str | None:
    """The GCS object key a `_wisdom_2025_` proxy URL points at."""
    nm = neutral_image(url)
    return nm[0] if nm else None


# ---------------------------------------------------------------------------
# --drop-broken
# ---------------------------------------------------------------------------
def drop_broken(tok: str, bucket, write: bool) -> dict:
    log.info("drop-broken: scanning for `_wisdom_2025_` images with a missing GCS source ...")
    c = {"products": 0, "broken_imgs": 0, "products_updated": 0, "thumb_repointed": 0, "errors": 0}
    exists_cache: dict[str, bool] = {}

    def src_exists(key: str) -> bool:
        if key not in exists_cache:
            exists_cache[key] = bucket.blob(key).exists()
        return exists_cache[key]

    for p in _iter_products(tok, PROD_FIELDS):
        c["products"] += 1
        urls = [i.get("url") for i in (p.get("images") or [])]
        thumb = p.get("thumbnail")
        broken = set()
        for u in set(urls + [thumb]):
            if u and WISDOM_IMG_TOKEN in u:
                key = _src_key_for_url(u)
                if key and not src_exists(key):
                    broken.add(u)
        if not broken:
            continue
        c["broken_imgs"] += len(broken)
        new_imgs = [u for u in urls if u not in broken]
        new_thumb = thumb
        if thumb in broken:
            new_thumb = new_imgs[0] if new_imgs else None
            c["thumb_repointed"] += 1
        log.info("  %s: drop %d broken img(s)%s", p["handle"], len(broken),
                 " + repoint thumb" if thumb in broken else "")
        if write:
            try:
                _retry("POST", f"{BACKEND}/admin/products/{p['id']}", tok,
                       json={"images": [{"url": u} for u in new_imgs], "thumbnail": new_thumb}).raise_for_status()
                c["products_updated"] += 1
            except Exception as e:
                c["errors"] += 1
                log.error("  update %s: %s", p["handle"], str(e)[:160])
        else:
            c["products_updated"] += 1
    log.info("drop-broken done: %s", c)
    return c


# ---------------------------------------------------------------------------
# --sweep
# ---------------------------------------------------------------------------
def sweep(tok: str, bucket, write: bool) -> dict:
    log.info("sweep: collecting live Medusa references to `_wisdom_2025_` objects ...")
    referenced: set[str] = set()
    for p in _iter_products(tok, PROD_FIELDS):
        for u in [i.get("url") for i in (p.get("images") or [])] + [p.get("thumbnail")]:
            if u and WISDOM_IMG_TOKEN in u:
                key = _src_key_for_url(u)
                if key:
                    referenced.add(key)
    log.info("  %d old object(s) still referenced by a product (will NOT delete).", len(referenced))

    c = {"scanned": 0, "deleted": 0, "skip_referenced": 0, "orphan_no_copy": 0, "errors": 0}
    for prefix in SWEEP_PREFIXES:
        for bl in bucket.list_blobs(prefix=prefix):
            if WISDOM_IMG_TOKEN not in bl.name:
                continue
            c["scanned"] += 1
            if bl.name in referenced:
                c["skip_referenced"] += 1
                continue
            # neutral copy key: re-derive from the proxy URL form
            neutral_rel = ("catalog2025/" +
                           bl.name[len(GCS_BRAND_PREFIX):].replace("/", "_").replace(WISDOM_IMG_TOKEN, "_2025_"))
            neutral_key = GCS_BRAND_PREFIX + neutral_rel
            if not bucket.blob(neutral_key).exists():
                c["orphan_no_copy"] += 1
                continue
            if write:
                try:
                    bl.delete()
                    c["deleted"] += 1
                except Exception as e:
                    c["errors"] += 1
                    log.error("  delete %s: %s", bl.name, str(e)[:160])
            else:
                c["deleted"] += 1
            if c["scanned"] % 1000 == 0:
                log.info("  ...%d scanned (%d eligible, %d orphan-no-copy)",
                         c["scanned"], c["deleted"], c["orphan_no_copy"])
    log.info("sweep %s done: %s", "WRITE" if write else "DRY-RUN", c)
    if c["orphan_no_copy"]:
        log.warning("  %d copy-less orphans LEFT in place (no neutral copy to fall back on).",
                    c["orphan_no_copy"])
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drop-broken", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--all", action="store_true", help="--drop-broken then --sweep.")
    ap.add_argument("--write", action="store_true", help="Apply (default: dry-run).")
    ap.add_argument("--sa-key", default=None)
    args = ap.parse_args()

    if not (args.drop_broken or args.sweep or args.all):
        ap.error("pick one of --drop-broken / --sweep / --all")
    if args.sa_key and Path(args.sa_key).exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.sa_key
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

    from google.cloud import storage
    bucket = storage.Client(project="ai-agents-go").bucket(GCS_BUCKET)
    tok = _admin_token()
    log.info("Authenticated against %s (%s)", BACKEND, "WRITE" if args.write else "DRY-RUN")

    if args.drop_broken or args.all:
        drop_broken(tok, bucket, args.write)
    if args.sweep or args.all:
        sweep(tok, bucket, args.write)
    if not args.write:
        print("\n[dry-run] no changes. Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
