"""Cross-check the image-less Vortex Medusa products against vortex-intl.com.

Background
----------
The Vortex sales channel holds 521 products: 272 scraped from vortex-intl.com
(each with images + a `metadata.source_url` product page) and ~249 "bare"
pricelist/component SKUs (handle `vortex-vor-XXXX`) that have NO thumbnail, NO
images, NO collection and a poor/garbled title. These bare products render as
placeholder cards on the storefront — the bulk of the "missing images on Vortex"
report.

The Vortex website exposes its products through the WP REST `products` CPT, which
is exhaustively 272 items (the scrape captured all of them). So a bare SKU is
"found on the website" only if it maps to one of those 272 products (i.e. it is a
variant/duplicate of a real product) — otherwise it is a component/spare part
with no product page and no recoverable image.

What this does
--------------
For every bare (no-thumbnail) Vortex product on the sales channel:
  1. Build the best search name from Firestore `vendors/vortex/products`
     (item_code -> name + collection) when present, else the cleaned Medusa title.
  2. Cross-check against the website:
       a. OFFLINE precise match to one of the 272 scraped products by slug/name
          (slug == slugify(collection name) / slugify(name), or exact name).
       b. LIVE WP REST `/products?search=` fallback for offline misses; a hit is
          only accepted when the returned product slug equals slugify(name)
          (high precision) — and we record whether that slug is among the 272.
  3. Classify each SKU:
       - duplicate_of_existing : maps to one of the 272 (real product already in
         the catalog, with images) -> safe to unpublish (the imaged product stays)
       - new_on_site           : a website product NOT in our 272 (unexpected) ->
         KEEP published, flag for manual image recovery (never auto-unpublished)
       - not_found             : no website product page (component/spare) ->
         unpublish
  4. ACTION (unless --dry-run): set status=draft on `duplicate_of_existing` and
     `not_found`. `new_on_site` is left published and only flagged.
  5. Write a flag report (JSON + Markdown) under vortex-catalog/.

Auth: LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD (email defaults to
admin@leka.studio; password from Secret Manager `medusa-admin-password`).
Firestore + ADC for vendors DB read.

Usage:
    python vortex-catalog/crosscheck_bare_products.py --dry-run
    python vortex-catalog/crosscheck_bare_products.py            # live (unpublish)
    python vortex-catalog/crosscheck_bare_products.py --no-live-search --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import requests

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SALES_CHANNEL = "sc_01KPRY1T8HZJ57020JPZVGAKZK"
PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
REST_BASE = "https://www.vortex-intl.com/wp-json/wp/v2"
HERE = os.path.dirname(__file__)
SCRAPE_JSON = os.path.join(HERE, "web-app", "public", "data", "products_all.json")
TIMEOUT = 45
UA = {"User-Agent": "Mozilla/5.0 (leka vortex cross-check)"}


def slugify(s: str | None) -> str:
    s = (s or "").lower()
    # strip mojibake / accents that pollute pricelist names (N°, ®, replacement char)
    s = s.replace("°", "").replace("®", "").replace("�", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)


def admin_token() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "admin@leka.studio")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not pw:
        raise SystemExit("Set LEKA_MEDUSA_ADMIN_PASSWORD (Secret Manager medusa-admin-password v5).")
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["token"]


def hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_bare_products(token: str) -> list[dict]:
    """All Vortex products with no thumbnail (the image-less set)."""
    out = []
    off = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/products", headers=hdrs(token), timeout=TIMEOUT,
                         params={"sales_channel_id[]": SALES_CHANNEL, "limit": 100, "offset": off,
                                 "fields": "id,handle,title,status,thumbnail,variants.sku"})
        r.raise_for_status()
        ps = r.json().get("products", [])
        if not ps:
            break
        for p in ps:
            if not p.get("thumbnail"):
                skus = [v.get("sku") for v in (p.get("variants") or []) if v.get("sku")]
                out.append({"id": p["id"], "handle": p["handle"], "title": p.get("title"),
                            "status": p.get("status"), "sku": (skus[0].upper() if skus else None)})
        off += 100
    return out


def load_firestore_meta() -> dict:
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    meta = {}
    for d in db.collection("vendors").document("vortex").collection("products").stream():
        x = d.to_dict() or {}
        ic = (x.get("item_code") or "").upper()
        if ic:
            meta[ic] = {"name": x.get("name"), "collection": x.get("collection")}
    return meta


def load_known272() -> tuple[dict, dict]:
    data = json.load(open(SCRAPE_JSON, encoding="utf-8"))
    by_slug = {p["slug"]: p for p in data if p.get("slug")}
    by_name = {}
    for p in data:
        by_name.setdefault(slugify(p.get("name")), p)
    return by_slug, by_name


def clean_title(t: str | None) -> str:
    """Strip the trailing ' VOR' tag and parentheticals from Medusa titles."""
    t = (t or "").replace("�", "")
    t = re.sub(r"\bVOR\b", "", t)
    t = re.sub(r"\([^)]*\)", "", t)
    return t.strip()


def search_name_for(b: dict, fs: dict) -> tuple[str, str | None]:
    """Return (name, collection) preferring Firestore pricelist data."""
    m = fs.get(b["sku"]) if b.get("sku") else None
    if m and m.get("name"):
        return m["name"], m.get("collection")
    return clean_title(b.get("title")), None


def offline_match(name: str, collection: str | None, by_slug: dict, by_name: dict):
    cands = [slugify(f"{collection} {name}") if collection else "", slugify(name)]
    for c in cands:
        if c and c in by_slug:
            return by_slug[c]
    sn = slugify(name)
    if sn and sn in by_name:
        return by_name[sn]
    return None


def live_search(name: str):
    """WP REST product search; accept only a product whose slug == slugify(name)."""
    q = urllib.parse.quote(name)
    url = f"{REST_BASE}/products?search={q}&per_page=5"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            arr = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    want = slugify(name)
    for a in arr:
        if a.get("slug") == want:
            return {"slug": a.get("slug"), "link": a.get("link")}
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-live-search", action="store_true",
                    help="skip the live WP REST fallback (offline match only)")
    ap.add_argument("--live-delay", type=float, default=1.2)
    args = ap.parse_args()

    token = admin_token()
    bare = fetch_bare_products(token)
    fs = load_firestore_meta()
    by_slug, by_name = load_known272()
    known_slugs = set(by_slug)
    print(f"bare products: {len(bare)} | firestore metas: {len(fs)} | known272: {len(by_slug)}")

    rows = []
    counts = {"duplicate_of_existing": 0, "new_on_site": 0, "not_found": 0}
    for i, b in enumerate(bare):
        name, col = search_name_for(b, fs)
        matched = offline_match(name, col, by_slug, by_name) if name else None
        source = "offline"
        if not matched and name and not args.no_live_search:
            hit = live_search(name)
            time.sleep(args.live_delay)
            if hit:
                source = "live"
                matched = by_slug.get(hit["slug"]) or {"slug": hit["slug"], "url": hit["link"], "_external": True}
        if matched:
            slug = matched.get("slug")
            url = matched.get("url")
            if slug in known_slugs:
                cls = "duplicate_of_existing"
            else:
                cls = "new_on_site"
        else:
            cls = "not_found"
            slug = url = None
        counts[cls] += 1
        rows.append({"sku": b["sku"], "handle": b["handle"], "title": b["title"],
                     "search_name": name, "collection": col, "class": cls,
                     "match_slug": slug, "match_url": url, "match_source": source,
                     "product_id": b["id"]})
        if (i + 1) % 25 == 0:
            print(f"  ...{i+1}/{len(bare)}  {counts}")

    print(f"\nClassification: {counts}")

    # Write report
    report_json = os.path.join(HERE, "bare_products_crosscheck.json")
    report_md = os.path.join(HERE, "bare_products_crosscheck.md")
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump({"counts": counts, "rows": rows}, f, indent=2, ensure_ascii=False)
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("# Vortex bare-product website cross-check\n\n")
        f.write(f"- duplicate_of_existing (variant of a real, imaged product): **{counts['duplicate_of_existing']}**\n")
        f.write(f"- new_on_site (website product NOT in our 272 — KEPT, manual image recovery): **{counts['new_on_site']}**\n")
        f.write(f"- not_found (component/spare part, no product page): **{counts['not_found']}**\n\n")
        for cls in ("new_on_site", "duplicate_of_existing", "not_found"):
            sub = [r for r in rows if r["class"] == cls]
            f.write(f"\n## {cls} ({len(sub)})\n\n")
            f.write("| SKU | name | collection | match |\n|---|---|---|---|\n")
            for r in sub:
                f.write(f"| {r['sku']} | {r['search_name']} | {r['collection'] or ''} | {r['match_slug'] or ''} |\n")
    print(f"Report: {report_json}\n        {report_md}")

    # Action: unpublish duplicate_of_existing + not_found. Keep new_on_site.
    to_unpub = [r for r in rows if r["class"] in ("duplicate_of_existing", "not_found")]
    print(f"\nTo unpublish (status=draft): {len(to_unpub)}  | kept (new_on_site): {counts['new_on_site']}")
    if args.dry_run:
        print("DRY-RUN — no writes.")
        return 0

    errs = 0
    for i, r in enumerate(to_unpub):
        resp = requests.post(f"{BACKEND}/admin/products/{r['product_id']}",
                             headers=hdrs(token), timeout=TIMEOUT, json={"status": "draft"})
        if resp.status_code >= 400:
            errs += 1
            print(f"  !! {r['handle']} unpublish failed: {resp.status_code} {resp.text[:150]}")
        if (i + 1) % 50 == 0:
            print(f"  unpublished {i+1}/{len(to_unpub)}")
            token = admin_token()  # refresh
    print(f"\nDONE: unpublished {len(to_unpub) - errs}/{len(to_unpub)} (errors={errs})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
