"""Playwright-based image enrichment — fallback for products whose static
crawl yielded no usable photos.

The initial pass `enrich_images.py` linked images from the rampline.com
crawl HTML, but most product PDPs lazy-load their gallery photos via JS.
The static crawl only saw the "you might also like" carousel, which the
token filter (correctly) rejected.

This script targets just the products that ended up IMAGES_UPTODATE in the
static pass *with zero images*. For each, it:

  1. Opens the product's source_url in headless Chromium.
  2. Scrolls the page to trigger lazy-load.
  3. Reads `document.querySelectorAll('img')` and extracts every `src` /
     `srcset` URL (after JS has hydrated).
  4. Filters by the same name-token rule as `enrich_images.py` (so
     sibling-product carousel photos remain excluded).
  5. PATCHes the Medusa product with the new image URLs.

External CDN URLs (`rampline.imgix.net`) are linked directly. URLs on the
rampline.com host are skipped — they're rare and would require an
additional fetch+upload step.

Usage:
    pip install playwright && playwright install chromium

    # Dry-run — show what would be attached
    python rampline-catalog/enrich_images_playwright.py --dry-run

    # Apply
    python rampline-catalog/enrich_images_playwright.py --apply

    # Limit (useful for testing)
    python rampline-catalog/enrich_images_playwright.py --dry-run --limit 3
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
TIMEOUT = 60

# Image hosts we link directly. The imgix CDN is publicly cached; the
# rampline.com `wp-content/uploads/` path serves product photos straight
# from rampline's WordPress install (also publicly served).
_DIRECT_LINK_HOSTS = ("rampline.imgix.net",)
_DIRECT_LINK_PATH_PREFIXES = (
    "https://rampline.com/wp-content/uploads/",
    "http://rampline.com/wp-content/uploads/",
)

# URL/filename patterns to always skip.
_SKIP_URL_PATTERNS = (
    "/themes/rampline/images/icon-",
    "/themes/rampline/images/logo",
    "/wp-content/uploads/2020/02/rampline_logo",
    "/wp-content/uploads/2022/10/pil-left",
    "/wp-content/uploads/2022/10/pil-right",
    "favicon",
)
_SKIP_NAME_PATTERNS = ("pil-left", "pil-right", "loading", "spinner")

DEFAULT_MAX_IMAGES = 8

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_images_playwright")


# ---------------------------------------------------------------------------
# Medusa REST
# ---------------------------------------------------------------------------
class Medusa:
    def __init__(self):
        email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
        pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
        if not (email and pw):
            raise RuntimeError("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD")
        r = requests.post(f"{BACKEND}/auth/user/emailpass",
                          json={"email": email, "password": pw}, timeout=TIMEOUT)
        r.raise_for_status()
        self.token = r.json()["token"]
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.token}",
                                "Content-Type": "application/json"})

    def get(self, path, **params):
        r = self.s.get(f"{BACKEND}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status(); return r.json()

    def post(self, path, body):
        r = self.s.post(f"{BACKEND}{path}", json=body, timeout=TIMEOUT)
        if not r.ok:
            log.error("POST %s failed (%d): %s", path, r.status_code, r.text[:600])
            r.raise_for_status()
        return r.json()


def index_targets(med: Medusa) -> list[dict]:
    """Rampline products that have a source_url and 0 images today."""
    out = []
    off = 0
    while True:
        page = med.get(
            "/admin/products",
            **{"sales_channel_id[]": RAMPLINE_SALES_CHANNEL_ID, "limit": 100, "offset": off,
               "status[]": ["published", "draft"]},
            fields="id,handle,thumbnail,images.url,metadata",
        )
        batch = page.get("products") or []
        for p in batch:
            md = p.get("metadata") or {}
            existing = {(im.get("url") or "") for im in (p.get("images") or [])}
            src = md.get("source_url") or ""
            if not src or existing:
                continue
            out.append({
                "id": p["id"],
                "handle": p["handle"],
                "thumbnail": p.get("thumbnail"),
                "source_url": src,
                "existing_image_urls": existing,
            })
        if len(batch) < 100:
            break
        off += 100
    return out


# ---------------------------------------------------------------------------
# Playwright fetch
# ---------------------------------------------------------------------------
def fetch_rendered_imgs(url: str, scroll_iters: int = 4, scroll_pause_ms: int = 600) -> list[str]:
    """Open URL in Chromium, scroll to bottom, return list of <img> URLs."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/121.0.0.0 Safari/537.36"),
                viewport={"width": 1440, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Best-effort wait for network to quiet down (don't hard-fail if it
            # never reaches idle on a noisy WordPress site).
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            # Scroll to trigger lazy-load
            for _ in range(scroll_iters):
                page.evaluate("window.scrollBy(0, document.body.scrollHeight / 3)")
                time.sleep(scroll_pause_ms / 1000)
            # Read all <img> URLs (src + srcset + currentSrc) from the DOM
            urls: list[str] = page.evaluate("""
                () => {
                  const out = new Set();
                  for (const img of document.querySelectorAll('img')) {
                    if (img.src) out.add(img.src);
                    if (img.currentSrc) out.add(img.currentSrc);
                    const ss = img.getAttribute('srcset');
                    if (ss) for (const c of ss.split(',')) {
                      const u = c.trim().split(' ')[0];
                      if (u) out.add(u);
                    }
                  }
                  return Array.from(out);
                }
            """)
            return urls
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------
def _product_tokens(handle: str) -> set[str]:
    handle_slug = handle.replace("rampline-", "", 1).lower()
    out = set()
    for t in re.split(r"[-_/]+", handle_slug):
        t = t.strip()
        if len(t) >= 3 and t not in {"the", "and", "for", "with", "into", "play",
                                      "park", "english", "ramp", "rampline"}:
            out.add(t)
    if "-" in handle_slug:
        out.add(re.sub(r"[^a-z0-9]+", "", handle_slug))
    return out


def _filter_urls(urls: list[str], product_tokens: set[str]) -> list[str]:
    keep: list[str] = []
    for u in urls:
        if not u or u.startswith("data:"):
            continue
        if any(s in u for s in _SKIP_URL_PATTERNS):
            continue
        low = u.lower()
        if any(s in low for s in _SKIP_NAME_PATTERNS):
            continue
        # Must be on a whitelisted CDN or path
        if not (
            any(h in u for h in _DIRECT_LINK_HOSTS)
            or any(u.startswith(p) for p in _DIRECT_LINK_PATH_PREFIXES)
        ):
            continue
        # Token match against the product name
        name = u.rsplit("/", 1)[-1].split("?", 1)[0].lower()
        name_no_ext = re.sub(r"\.(png|jpg|jpeg|webp|gif|svg)$", "", name)
        name_alnum = re.sub(r"[^a-z0-9]+", "", name_no_ext)
        matched = False
        if not product_tokens:
            matched = True
        else:
            for tok in product_tokens:
                if tok in name_alnum or tok in name_no_ext:
                    matched = True
                    break
        if not matched:
            continue
        if u not in keep:
            keep.append(u)
    return keep


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------
def write_run_log(actions, skipped, result, dry_run, args) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = f"images_pw_{'dryrun' if dry_run else 'applied'}_{stamp}"
    out = RUN_LOG_DIR / f"{name}.json"
    serial = []
    for a in actions:
        serial.append({k: v for k, v in a.items() if not k.startswith("_")})
    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": dry_run,
        "max_images": args.max_images,
        "limit": args.limit,
        "totals": result.get("counts", {}),
        "actions_count": len(actions),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "errors": result.get("errors", []),
        "actions": serial,
    }, indent=2, default=str), encoding="utf-8")
    log.info("Run log: %s", out)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES)
    ap.add_argument("--limit", type=int, default=0,
                    help="Process at most N products (0 = all)")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("Specify --dry-run or --apply")

    med = Medusa()
    log.info("Indexing Rampline products with source_url + 0 images …")
    targets = index_targets(med)
    if args.limit:
        targets = targets[: args.limit]
    log.info("Targets: %d", len(targets))

    actions: list[dict] = []
    skipped: list[dict] = []

    for i, t in enumerate(targets, 1):
        log.info("[%d/%d] %s ← %s", i, len(targets), t["handle"], t["source_url"])
        try:
            urls = fetch_rendered_imgs(t["source_url"])
        except Exception as e:
            log.warning("  playwright failed: %s", e)
            skipped.append({"handle": t["handle"], "reason": f"playwright_error:{e}"})
            continue
        product_tokens = _product_tokens(t["handle"])
        keep = _filter_urls(urls, product_tokens)
        new_urls = keep[: args.max_images]
        log.info("  rendered=%d  kept=%d  new=%d", len(urls), len(keep), len(new_urls))
        if not new_urls:
            actions.append({
                "op": "NO_IMAGES_FOUND",
                "handle": t["handle"],
                "rendered_count": len(urls),
            })
            continue
        actions.append({
            "op": "ADD_IMAGES",
            "handle": t["handle"],
            "product_id": t["id"],
            "new_count": len(new_urls),
            "thumbnail_set": not t["thumbnail"],
            "_target_images": new_urls,
            "_target_thumbnail": new_urls[0] if not t["thumbnail"] else None,
            "_sample": new_urls[:3],
        })

    summary = defaultdict(int)
    for a in actions:
        summary[a["op"]] += 1
    log.info("Planned: %s   (skipped=%d)", dict(summary), len(skipped))

    if args.dry_run:
        result = {"counts": dict(summary), "errors": []}
        write_run_log(actions, skipped, result, dry_run=True, args=args)
        log.info("DRY RUN — no Medusa writes")
        return

    log.info("APPLYING %d ADD_IMAGES …",
             sum(1 for a in actions if a["op"] == "ADD_IMAGES"))
    errors = []
    for a in actions:
        if a["op"] != "ADD_IMAGES":
            continue
        try:
            body = {"images": [{"url": u} for u in a["_target_images"]]}
            if a["_target_thumbnail"]:
                body["thumbnail"] = a["_target_thumbnail"]
            med.post(f"/admin/products/{a['product_id']}", body)
            log.info("  ✓ %s +%d new%s", a["handle"], a["new_count"],
                     "  [thumb]" if a["thumbnail_set"] else "")
        except Exception as e:
            errors.append({"handle": a["handle"], "error": str(e)})
            log.error("apply failed for %s: %s", a["handle"], e)
    result = {"counts": dict(summary), "errors": errors}
    write_run_log(actions, skipped, result, dry_run=False, args=args)


if __name__ == "__main__":
    main()
