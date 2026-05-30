"""
rehost_4soft_images.py — give 4soft (EPDM-graphic) products a working image.

Two problems with the existing 4soft images:
  1. The `gs://ai-agents-go-vendors/4soft/...` objects are actually 10 KB HTML
     error pages (the original scrape saved error pages, content-type mislabeled
     image/*) — there is no real image there.
  2. Even if real, the `catalogs.leka.studio/api/i/` proxy only serves objects
     ONE level under `leka-project/` (e.g. `leka-project/<file>`).

Fix: use the REAL graphic previews captured from the Notion R2 page (mirrored to
`gs://go-leka-projects/dulwich-singapore/notion/images/...`), copy them to
`gs://ai-agents-go-vendors/leka-project/4soft-<code>_r2_<sha8>.<ext>` (flat,
space-free, uploaded with an explicit content-type), and point each 4soft Medusa
product's images/thumbnail at the working `/api/i/leka-project/...` proxy URL.

Dry-run by default; --write to apply. Auth: Medusa LEKA_MEDUSA_ADMIN_*; GCS ADC.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
DST_BUCKET = "ai-agents-go-vendors"
DST_PREFIX = "leka-project/"
PROXY = "https://catalogs.leka.studio/api/i/leka-project/"
SELECTION = (r"C:\Users\Eukrit\OneDrive\Claude Code\NUC11\leka-projects\.claude"
             r"\worktrees\goofy-snyder-ab838e\projects\dulwich-singapore\_data"
             r"\dulwich-singapore-r2-selection.json")
CT = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def is_epdm(code) -> bool:
    return bool(re.match(r"^[A-Z]\d-\d{2}[A-Z]-\d{2,3}", (code or "").upper()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    from shared.medusa_importer import MedusaImporter
    from google.cloud import storage
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    c = MedusaImporter(base_url=BACKEND)
    sc = storage.Client(project="ai-agents-go")
    dst = sc.bucket(DST_BUCKET)

    sel = json.loads(Path(SELECTION).read_text(encoding="utf-8"))
    # one item per 4soft code (dedupe)
    by_code = {}
    for it in sel["items"]:
        cd = it.get("product_code")
        if cd and is_epdm(cd) and norm(cd) not in by_code and (it.get("images")):
            by_code[norm(cd)] = it
    print(f"== rehost 4soft from Notion images: {len(by_code)} codes "
          f"({'WRITE' if args.write else 'DRY-RUN'}) ==")

    fixed = noimg = errors = 0
    for it in by_code.values():
        code = it["product_code"]
        handle = f"4soft-{code.lower()}"
        r = c._get("/admin/products", {"handle": handle, "limit": 1, "fields": "id,handle"})
        ps = r.get("products", [])
        if not ps:
            print(f"   ? {code}: no medusa product {handle}")
            continue
        pid = ps[0]["id"]
        urls = []
        for n, im in enumerate(it.get("images") or []):
            gcs = im.get("gcs")
            m = re.match(r"gs://([^/]+)/(.+)", gcs or "")
            if not m:
                continue
            ext = Path(m.group(2)).suffix.lower() or ".png"
            sha8 = (im.get("sha") or "")[:8] or str(n)
            flat = f"4soft-{code.lower()}_r2_{sha8}{ext}"
            urls.append(PROXY + flat)
            if args.write:
                try:
                    data = sc.bucket(m.group(1)).blob(m.group(2)).download_as_bytes()
                    b = dst.blob(DST_PREFIX + flat)
                    if not b.exists():
                        b.upload_from_string(data, content_type=CT.get(ext, "image/jpeg"))
                except Exception as e:
                    errors += 1
                    print(f"   ! {code} copy: {str(e)[:120]}")
        if not urls:
            noimg += 1
            continue
        fixed += 1
        print(f"   {code:14} -> {len(urls)} img  {urls[0].rsplit('/',1)[-1]}")
        if args.write:
            try:
                c._post(f"/admin/products/{pid}",
                        {"images": [{"url": u} for u in urls], "thumbnail": urls[0],
                         "metadata": {"image_status": "notion_r2_4soft"}})
            except Exception as e:
                errors += 1
                print(f"   ! {code} medusa update: {str(e)[:120]}")

    print(f"\n== done: fixed={fixed} no_notion_img={noimg} errors={errors} ==")
    if not args.write:
        print("   (dry-run — re-run with --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
