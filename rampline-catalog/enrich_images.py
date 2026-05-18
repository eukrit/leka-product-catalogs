"""Rampline image enrichment: vendors/rampline crawl media → Medusa.

For each Medusa product on the Rampline sales channel that has a matching
crawled product (by source_url in metadata, set by enrich_from_vendors.py),
this script:

  1. Loads `vendors/rampline-catalog/source-files/_manifest.json` and finds
     the crawled HTML page for that product's source_url.
  2. Parses the page HTML to extract `<img src=…>` URLs (and `srcset` first
     candidates).
  3. Looks each image URL up in `manifest.by_url` → media SHA + extension.
  4. Builds proxy URLs of the form
       https://catalogs.leka.studio/api/i/rampline/media/<sha>.<ext>
     which the Next.js storefront serves from the private GCS bucket via
     `leka-website/catalogs/src/app/api/i/[...path]/route.ts`.
  5. PATCHes the Medusa product with the union of existing + crawled image
     URLs (same idempotency contract as v2.22.3
     `sync_vendors_to_medusa.py::_build_update_payload`: never replaces,
     never removes — just adds new URLs).

The first crawled image becomes the `thumbnail` IFF Medusa has none.

Image filters (skip when):
  - URL contains `/themes/rampline/images/icon-`
  - URL contains `/wp-content/themes/rampline/images/logo`
  - manifest entry has `bucket != 'media'` (e.g. design-system logo,
    favicon, css-referenced sprite)

Run modes:
  --dry-run                Plan + per-product image-URL list, no Medusa writes
  --apply                  Plan + execute PATCH
  --limit-family <s>       Only act on products whose handle/sku/category
                           matches this substring
  --max-images N           Cap new images added per product (default 8)

Run logs land in rampline-catalog/data/build_runs/ with the same shape as
enrich_from_vendors.py:
    images_dryrun_<ts>.json
    images_applied_<ts>.json

Usage:
    python rampline-catalog/enrich_images.py --dry-run
    python rampline-catalog/enrich_images.py --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"

# Default crawl tree
DEFAULT_CRAWL_ROOT = (
    REPO_ROOT.parent / "vendors" / "rampline-catalog"
)

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
TIMEOUT = 60

# Image proxy in front of gs://ai-agents-go-vendors
PROXY_BASE = "https://catalogs.leka.studio/api/i/rampline/media"

# Per-product image cap. We do NOT remove existing images — this is the
# upper bound on net-new crawled URLs added per product.
DEFAULT_MAX_IMAGES = 8

# Allow images from these hosts (rampline serves product photos from its
# imgix CDN, which the crawler doesn't fetch because it's off-host). Each
# of these is publicly cached and stable, so we link to them directly
# rather than mirroring into GCS.
_DIRECT_LINK_HOSTS = (
    "rampline.imgix.net",
)

# Exclude rampline.com decorations / chrome
_SKIP_URL_PATTERNS = (
    "/themes/rampline/images/icon-",
    "/themes/rampline/images/logo",
    "/wp-content/uploads/2020/02/rampline_logo",
    "/wp-content/uploads/2022/10/pil-left",
    "/wp-content/uploads/2022/10/pil-right",
    "favicon",
)

# Image filename / extension filter: skip clearly non-product chrome
_SKIP_NAME_PATTERNS = ("pil-left", "pil-right", "loading", "spinner")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_images")


# ---------------------------------------------------------------------------
# HTML <img> parser
# ---------------------------------------------------------------------------
class ImgCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "img":
            return
        a = dict(attrs)
        # Prefer the explicit `src`; fall back to first srcset candidate.
        src = a.get("src") or ""
        if not src and a.get("srcset"):
            src = a["srcset"].split(",")[0].strip().split(" ")[0]
        if not src or src.startswith("data:"):
            return
        if src not in self._seen:
            self._seen.add(src)
            self.urls.append(src)


def extract_img_urls(html_text: str, base_url: str) -> list[str]:
    coll = ImgCollector()
    try:
        coll.feed(html_text)
    except Exception:
        pass
    out = []
    for u in coll.urls:
        absolute = urljoin(base_url, u)
        # HTML entity decoding for &#038; etc.
        import html
        absolute = html.unescape(absolute)
        if any(skip in absolute for skip in _SKIP_URL_PATTERNS):
            continue
        if any(skip in absolute.lower() for skip in _SKIP_NAME_PATTERNS):
            continue
        out.append(absolute)
    return out


# ---------------------------------------------------------------------------
# Medusa REST client
# ---------------------------------------------------------------------------
class Medusa:
    def __init__(self):
        email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
        pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
        if not (email and pw):
            raise RuntimeError("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD")
        r = requests.post(
            f"{BACKEND}/auth/user/emailpass",
            json={"email": email, "password": pw},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        self.token = r.json()["token"]
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })

    def get(self, path: str, **params) -> dict:
        r = self.session.get(f"{BACKEND}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> dict:
        r = self.session.post(f"{BACKEND}{path}", json=body, timeout=TIMEOUT)
        if not r.ok:
            log.error("POST %s failed (%d): %s", path, r.status_code, r.text[:600])
            r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Index Medusa products with images + source_url
# ---------------------------------------------------------------------------
def index_products(med: Medusa) -> list[dict]:
    out: list[dict] = []
    off = 0
    while True:
        page = med.get(
            "/admin/products",
            **{
                "sales_channel_id[]": RAMPLINE_SALES_CHANNEL_ID,
                "limit": 100,
                "offset": off,
                "status[]": ["published", "draft"],
            },
            fields="id,handle,thumbnail,images.url,metadata",
        )
        batch = page.get("products") or []
        for p in batch:
            md = p.get("metadata") or {}
            out.append({
                "id": p["id"],
                "handle": p["handle"],
                "thumbnail": p.get("thumbnail"),
                "existing_image_urls": {(img.get("url") or "") for img in (p.get("images") or [])},
                "source_url": md.get("source_url") or "",
                "crawl_category": md.get("crawl_category") or "",
            })
        if len(batch) < 100:
            break
        off += 100
    return out


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
def plan_actions(
    products: list[dict],
    manifest: dict,
    crawl_root: Path,
    max_images: int,
    limit_family: str | None,
) -> tuple[list[dict], list[dict]]:
    by_url = manifest.get("by_url", {})
    entries = manifest.get("entries", {})
    pages_dir = crawl_root / "source-files" / "pages"

    actions: list[dict] = []
    skipped: list[dict] = []

    for p in products:
        src = (p["source_url"] or "").rstrip("/")
        if not src:
            skipped.append({"handle": p["handle"], "reason": "no_source_url"})
            continue
        if limit_family:
            needle = limit_family.lower()
            hay = (p["handle"] + " " + p["crawl_category"]).lower()
            if needle not in hay:
                continue

        # Find the page SHA. by_url keys are the literal source_urls (may
        # include a trailing slash).
        page_sha = by_url.get(src) or by_url.get(src + "/") or by_url.get(src.rstrip("/") + "/")
        if not page_sha:
            skipped.append({"handle": p["handle"], "reason": "page_not_in_manifest",
                            "source_url": src})
            continue

        page_path = pages_dir / f"{page_sha}.html"
        if not page_path.exists():
            skipped.append({"handle": p["handle"], "reason": "page_html_missing",
                            "page_sha": page_sha})
            continue

        try:
            html = page_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            skipped.append({"handle": p["handle"], "reason": f"read_error:{e}"})
            continue

        img_urls = extract_img_urls(html, base_url=src)

        # Filename-similarity filter: rampline.com pages include a
        # "you might also like" carousel that pulls in sibling-product
        # photos. We attach an image only if its filename plausibly relates
        # to THIS product (token overlap with handle or product slug).
        # Tokens are derived from the Medusa handle (strip "rampline-").
        handle_slug = p["handle"].replace("rampline-", "", 1)
        product_tokens = set()
        for t in re.split(r"[-_/]+", handle_slug.lower()):
            t = t.strip()
            if len(t) >= 3 and t not in {"the", "and", "for", "with", "into", "play",
                                          "park", "english", "ramp", "rampline"}:
                product_tokens.add(t)
                # Also a no-hyphen variant to catch CamelCase imgix names:
                # "fast-and-curious" → token "fastandcurious"
        if "-" in handle_slug:
            product_tokens.add(re.sub(r"[^a-z0-9]+", "", handle_slug.lower()))

        def _image_matches_product(url: str) -> bool:
            if not product_tokens:
                return True  # nothing to filter against; keep all
            # filename = last path segment before ?
            name = url.rsplit("/", 1)[-1].split("?", 1)[0].lower()
            name_no_ext = re.sub(r"\.(png|jpg|jpeg|webp|gif|svg)$", "", name)
            name_alnum = re.sub(r"[^a-z0-9]+", "", name_no_ext)
            for tok in product_tokens:
                if tok in name_alnum or tok in name_no_ext:
                    return True
            return False

        resolved_urls: list[str] = []
        carousel_filtered = 0
        for img_url in img_urls:
            # Skip sibling-product carousel photos
            if not _image_matches_product(img_url):
                carousel_filtered += 1
                continue
            # Path A: image is in our crawl manifest → use GCS proxy URL.
            media_sha = by_url.get(img_url)
            if media_sha:
                entry = entries.get(media_sha) or {}
                if entry.get("bucket") == "media":
                    ext = entry.get("ext") or ""
                    if ext:
                        u = f"{PROXY_BASE}/{media_sha}.{ext}"
                        if u not in resolved_urls:
                            resolved_urls.append(u)
                        continue
            # Path B: image is on a whitelisted external CDN → link directly.
            if any(host in img_url for host in _DIRECT_LINK_HOSTS):
                if img_url not in resolved_urls:
                    resolved_urls.append(img_url)

        new_urls = [u for u in resolved_urls if u not in p["existing_image_urls"]][:max_images]
        if not new_urls:
            actions.append({
                "op": "IMAGES_UPTODATE",
                "handle": p["handle"],
                "existing_count": len(p["existing_image_urls"]),
                "crawl_candidates": len(resolved_urls),
            })
            continue

        target = list(p["existing_image_urls"]) + new_urls
        new_thumb = None
        if not p["thumbnail"]:
            new_thumb = new_urls[0]

        actions.append({
            "op": "ADD_IMAGES",
            "handle": p["handle"],
            "product_id": p["id"],
            "existing_count": len(p["existing_image_urls"]),
            "new_count": len(new_urls),
            "total_count": len(target),
            "crawl_candidates": len(resolved_urls),
            "thumbnail_set": bool(new_thumb),
            "_target_images": target,
            "_target_thumbnail": new_thumb,
            "_sample_new": new_urls[:3],
        })

    return actions, skipped


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------
def execute(med: Medusa, actions: list[dict], dry_run: bool) -> dict:
    counts: dict[str, int] = defaultdict(int)
    errors: list[dict] = []
    for action in actions:
        op = action["op"]
        counts[op] += 1
        if dry_run or op != "ADD_IMAGES":
            continue
        try:
            body: dict = {
                "images": [{"url": u} for u in action["_target_images"]],
            }
            if action["_target_thumbnail"]:
                body["thumbnail"] = action["_target_thumbnail"]
            med.post(f"/admin/products/{action['product_id']}", body)
            log.info(
                "  ✓ %s  +%d new (now %d total)%s",
                action["handle"], action["new_count"], action["total_count"],
                "  [thumb]" if action["thumbnail_set"] else "",
            )
        except Exception as e:
            errors.append({"handle": action["handle"], "error": str(e)})
            log.error("image enrich failed for %s: %s", action["handle"], e)
    return {"counts": dict(counts), "errors": errors}


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------
def write_run_log(actions, skipped, result, dry_run, args) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = f"images_{'dryrun' if dry_run else 'applied'}_{stamp}"
    out = RUN_LOG_DIR / f"{name}.json"
    serializable = []
    for a in actions:
        serializable.append({k: v for k, v in a.items() if not k.startswith("_")})
    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": dry_run,
        "max_images": args.max_images,
        "limit_family": args.limit_family,
        "crawl_root": str(args.crawl_root),
        "totals": result.get("counts", {}),
        "actions_count": len(actions),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "errors": result.get("errors", []),
        "actions": serializable,
    }, indent=2, default=str), encoding="utf-8")
    log.info("Run log: %s", out)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl-root", type=Path, default=DEFAULT_CRAWL_ROOT,
                    help="vendors/rampline-catalog directory")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES)
    ap.add_argument("--limit-family", default=None)
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("Specify --dry-run or --apply")

    manifest_path = args.crawl_root / "source-files" / "_manifest.json"
    log.info("Loading manifest: %s", manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    log.info("Manifest: %d entries · %d url→sha mappings",
             len(manifest.get("entries", {})), len(manifest.get("by_url", {})))

    med = Medusa()
    log.info("Indexing Rampline products on Medusa…")
    products = index_products(med)
    enriched = [p for p in products if p["source_url"]]
    log.info("Indexed %d products (%d with source_url metadata)",
             len(products), len(enriched))

    actions, skipped = plan_actions(
        enriched, manifest, args.crawl_root, args.max_images, args.limit_family
    )
    summary = defaultdict(int)
    for a in actions:
        summary[a["op"]] += 1
    log.info("Planned: %s   (skipped=%d)", dict(summary), len(skipped))

    if args.dry_run:
        for a in [x for x in actions if x["op"] == "ADD_IMAGES"][:5]:
            log.info(
                "  ADD_IMAGES %s  existing=%d  new=%d  cands=%d  sample=%s",
                a["handle"], a["existing_count"], a["new_count"],
                a["crawl_candidates"],
                ", ".join(u.rsplit("/", 1)[-1] for u in a["_sample_new"]),
            )
        result = {"counts": dict(summary), "errors": []}
        write_run_log(actions, skipped, result, dry_run=True, args=args)
        log.info("DRY RUN — no Medusa writes")
        return

    log.info("APPLYING %d ADD_IMAGES actions…",
             sum(1 for a in actions if a["op"] == "ADD_IMAGES"))
    result = execute(med, actions, dry_run=False)
    log.info("Result: %s", result["counts"])
    if result["errors"]:
        log.error("%d errors", len(result["errors"]))
    write_run_log(actions, skipped, result, dry_run=False, args=args)


if __name__ == "__main__":
    main()
