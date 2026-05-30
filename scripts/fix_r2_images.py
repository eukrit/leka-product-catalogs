"""
fix_r2_images.py — image quality pass for the Dulwich R2 product set on Medusa.

Two phases (bounded to the products referenced by the R2 selection):

  --reorder       Vision-classify each image of every R2 product that has 2+ real
                  images (Gemini 2.5 Flash via Vertex), then reorder product.images
                  so a real render/photo is the hero and technical/plan DRAWINGS go
                  last; set thumbnail = new hero. Idempotent (skips if already ordered).

  --attach-notion For every R2 product that currently has only the leka-coming-soon
                  placeholder but DOES have a photo on the Notion R2 page, copy the
                  Notion image(s) from gs://go-leka-projects/... into
                  gs://ai-agents-go-vendors/leka-project/<code>_notionr2_<sha8>.<ext>
                  and set them as the product's images (served via the catalogs proxy).

Bound: only products whose variant sku/legacy_sku matches an R2 code. Official catalog
products outside R2 are untouched. Dry-run by default; --write to apply.

Auth: Medusa via LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD (emailpass JWT); GCS + Vertex via ADC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

PROJECT = "ai-agents-go"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
VENDORS_BUCKET = "ai-agents-go-vendors"
LEKA_PREFIX = "leka-project/"
PROXY_PREFIX = "https://catalogs.leka.studio/api/i/leka-project/"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_LOCATION = "global"

SELECTION = (r"C:\Users\Eukrit\OneDrive\Claude Code\NUC11\leka-projects\.claude"
             r"\worktrees\goofy-snyder-ab838e\projects\dulwich-singapore\_data"
             r"\dulwich-singapore-r2-selection.json")

SCORE_INSTRUCTION = """\
You are ordering product images for a children's playground-equipment proposal.
For each image return a JSON object with:
  "score": integer 0-100 — how good this image is as the PRIMARY/hero product shot.
           90-100 photo/3D render of the product in a scene or on a clean background;
           50-79 plain product render/packshot; 10-29 cropped/partial/poor photo;
           0-9 technical line drawing, top-down plan, dimensional schematic, logo, blank.
  "tag":   one of "render","photo","packshot","partial","technical_drawing","plan","other".
Return STRICT JSON {"images":[{"score":N,"tag":"..."}, ...]} — same length & order as input.
"""


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def medusa_index(c):
    idx = {}
    off = 0
    while True:
        r = c._get("/admin/products", {
            "limit": 200, "offset": off,
            "fields": "id,handle,title,thumbnail,images.url,variants.sku,variants.metadata.legacy_sku"})
        b = r.get("products", [])
        if not b:
            break
        for p in b:
            for v in p.get("variants") or []:
                for k in (v.get("sku"), (v.get("metadata") or {}).get("legacy_sku")):
                    if k:
                        idx.setdefault(norm(k), p)
        if len(b) < 200:
            break
        off += 200
    return idx


def is_real(url: str) -> bool:
    return bool(url) and "coming-soon" not in url.lower() and "_placeholder/" not in url.lower()


# ─────────────────────────── vision reorder ───────────────────────────

_IMG_CACHE: dict[str, bytes] = {}


def _fetch(url: str) -> bytes | None:
    if url in _IMG_CACHE:
        return _IMG_CACHE[url]
    import requests
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        _IMG_CACHE[url] = r.content
        return r.content
    except Exception:
        return None


def _mime(url: str) -> str:
    ext = Path(url.split("?")[0]).suffix.lower()
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/jpeg")


def _ascii(s: str) -> str:
    return (s or "").encode("ascii", "replace").decode("ascii")


def classify(gem, urls, title):
    # Vertex can't crawl catalogs.leka.studio (robots) via from_uri — send bytes.
    from google.genai import types as gt
    parts = []
    for u in urls:
        data = _fetch(u)
        if data is None:
            return None
        parts.append(gt.Part.from_bytes(data=data, mime_type=_mime(u)))
    parts.append(gt.Part.from_text(text=f"Product: {_ascii(title)}.\n{SCORE_INSTRUCTION}"))
    try:
        resp = gem.models.generate_content(
            model=GEMINI_MODEL, contents=parts,
            config=gt.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.0,
                max_output_tokens=800,
                thinking_config=gt.ThinkingConfig(thinking_budget=0)))
        return json.loads((resp.text or "").strip()).get("images", [])
    except Exception as e:
        print(f"   ! gemini {_ascii(title)[:30]}: {_ascii(str(e))[:120]}")
        return None


def do_reorder(c, idx, sel, write):
    from google import genai
    gem = genai.Client(vertexai=True, project=PROJECT, location=GEMINI_LOCATION)
    seen = set()
    reordered = changed_hero = skipped = 0
    for it in sel["items"]:
        code = it.get("product_code")
        if not code or norm(code) in seen:
            continue
        seen.add(norm(code))
        p = idx.get(norm(code))
        if not p:
            continue
        urls = [im.get("url") for im in (p.get("images") or []) if is_real(im.get("url"))]
        if len(urls) < 2:
            continue
        scores = classify(gem, urls[:8], p.get("title") or code)
        if not scores or len(scores) < len(urls[:8]):
            skipped += 1
            continue
        scored = list(zip(urls[:8], scores)) + [(u, {"score": -1}) for u in urls[8:]]
        new_order = [u for u, s in sorted(
            scored, key=lambda x: -(x[1].get("score") if isinstance(x[1].get("score"), int) else -1))]
        if new_order == urls:
            continue
        reordered += 1
        if new_order[0] != urls[0]:
            changed_hero += 1
        tags = [s.get("tag") for _, s in scored]
        print(f"   {code:14} hero: {urls[0].rsplit('/',1)[-1][:24]} -> "
              f"{new_order[0].rsplit('/',1)[-1][:24]}  tags={tags}")
        if write:
            c._post(f"/admin/products/{p['id']}",
                    {"images": [{"url": u} for u in new_order], "thumbnail": new_order[0]})
        time.sleep(0.2)
    print(f"\n   reorder: products_reordered={reordered} hero_changed={changed_hero} skipped={skipped}")


# ─────────────────────────── notion attach ───────────────────────────

def do_attach_notion(c, idx, sel, write):
    from google.cloud import storage
    sc = storage.Client(project=PROJECT)
    dst = sc.bucket(VENDORS_BUCKET)
    seen = set()
    attached = noimg = 0
    for it in sel["items"]:
        code = it.get("product_code")
        if not code or norm(code) in seen:
            continue
        seen.add(norm(code))
        p = idx.get(norm(code))
        if not p:
            continue
        real = [im.get("url") for im in (p.get("images") or []) if is_real(im.get("url"))]
        if real:
            continue  # already has a real image
        notion = [im for im in (it.get("images") or []) if im.get("gcs")]
        if not notion:
            noimg += 1
            continue
        proxy_urls = []
        for im in notion[:4]:
            gcs = im["gcs"]  # gs://bucket/blob
            m = re.match(r"gs://([^/]+)/(.+)", gcs)
            if not m:
                continue
            src_bucket, src_blob = m.group(1), m.group(2)
            ext = Path(src_blob).suffix.lower() or ".jpg"
            sha8 = (im.get("sha") or "")[:8] or hashlib.sha1(gcs.encode()).hexdigest()[:8]
            rel = f"{code}_notionr2_{sha8}{ext}"
            if write:
                data = sc.bucket(src_bucket).blob(src_blob).download_as_bytes()
                b = dst.blob(LEKA_PREFIX + rel)
                if not b.exists():
                    ct = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
                    b.upload_from_string(data, content_type=ct)
            proxy_urls.append(PROXY_PREFIX + rel)
        if not proxy_urls:
            continue
        attached += 1
        print(f"   {code:14} {p.get('handle'):28} <- {len(proxy_urls)} notion img(s)")
        if write:
            c._post(f"/admin/products/{p['id']}", {
                "images": [{"url": u} for u in proxy_urls], "thumbnail": proxy_urls[0],
                "metadata": {"image_status": "notion_r2",
                             "image_status_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}})
        time.sleep(0.15)
    print(f"\n   attach-notion: attached={attached} placeholder_no_notion_img={noimg}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reorder", action="store_true")
    ap.add_argument("--attach-notion", action="store_true")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not (args.reorder or args.attach_notion):
        print("pick --reorder and/or --attach-notion"); return 2

    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    c = MedusaImporter(base_url=BACKEND)
    sel = json.loads(Path(SELECTION).read_text(encoding="utf-8"))
    print(f"== fix_r2_images ({'WRITE' if args.write else 'DRY-RUN'}) ==")
    print("   indexing Medusa…")
    idx = medusa_index(c)
    print(f"   indexed {len(idx)} keys")

    if args.reorder:
        print("\n-- Phase: vision reorder --")
        do_reorder(c, idx, sel, args.write)
    if args.attach_notion:
        print("\n-- Phase: attach Notion photos to placeholders --")
        # refresh index after reorder writes so we see updated images
        if args.write and args.reorder:
            idx = medusa_index(c)
        do_attach_notion(c, idx, sel, args.write)
    if not args.write:
        print("\n   (dry-run — re-run with --write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
