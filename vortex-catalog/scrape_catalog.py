"""
Scrape the Vortex Aquatics product catalog from vortex-intl.com.

Hybrid approach:
1. Bulk-list via WP REST: /wp-json/wp/v2/products?per_page=100&_embed=1 (3 calls, 272 products)
   -> id, slug, title, link, featured_media source URL
2. Per-product HTML fetch (rate-limited) for description, gallery, specs, model code, product-type

Output: vortex-catalog/web-app/public/data/products_all.json
        vortex-catalog/web-app/public/data/products_{N}.json (500/chunk)
        vortex-catalog/web-app/public/data/families.json

Usage:
    python vortex-catalog/scrape_catalog.py
    python vortex-catalog/scrape_catalog.py --limit 5          # smoke test
    python vortex-catalog/scrape_catalog.py --product-type splashpad
    python vortex-catalog/scrape_catalog.py --resume
    python vortex-catalog/scrape_catalog.py --delay 10         # respect Crawl-delay
"""
import os
import re
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.vortex-intl.com"
REST_BASE = f"{BASE_URL}/wp-json/wp/v2"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "web-app", "public", "data")
CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), ".scrape_checkpoint.json")

# Crawl-delay per robots.txt: 10s
DEFAULT_DELAY = 10.0
MAX_RETRIES = 3
RETRY_BACKOFF = 5.0

# Known Vortex product-type slugs (from sitemap / site navigation)
KNOWN_PRODUCT_TYPES = [
    "splashpad",
    "waterslide",
    "elevations-playnuk",
    "playable-fountains",
    "coolhub",
    "dream-tunnel",
    "water-management-solutions",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vortex-scraper")

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; LekaCatalogBot/1.0; +https://github.com/eukrit/leka-product-catalogs)",
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "en-US,en;q=0.9",
})


def fetch(url, as_json=False, retries=MAX_RETRIES):
    """Fetch a URL with retries. Returns parsed JSON, BeautifulSoup, or None."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=45)
            resp.raise_for_status()
            if as_json:
                return resp.json()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            log.warning(f"  fetch attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
    log.error(f"  giving up on {url}")
    return None


def list_all_products():
    """Pull all 272 products via WP REST in bulk pages of 100."""
    products = []
    page = 1
    per_page = 100
    while True:
        url = f"{REST_BASE}/products?per_page={per_page}&page={page}&_embed=1"
        log.info(f"WP REST page {page}: {url}")
        data = fetch(url, as_json=True)
        if not data:
            break
        products.extend(data)
        if len(data) < per_page:
            break
        page += 1
        if page > 10:  # safety
            break
    log.info(f"WP REST returned {len(products)} products total")
    return products


def discover_product_types(delay):
    """Map slug -> [product_type...] by paginating each product-type listing."""
    slug_to_types = {}
    for pt in KNOWN_PRODUCT_TYPES:
        for pg in range(1, 12):  # safety cap
            url = f"{BASE_URL}/products/?product_types={pt}&pg={pg}"
            log.info(f"listing {pt} pg={pg}")
            time.sleep(delay)
            soup = fetch(url, as_json=False)
            if not soup:
                break
            found_this_page = 0
            for a in soup.find_all("a", href=re.compile(r"/products/[^/]+/?$")):
                href = a["href"]
                m = re.search(r"/products/([^/]+)/?$", href)
                if not m:
                    continue
                slug = m.group(1)
                if slug == "" or slug == "products":
                    continue
                found_this_page += 1
                slug_to_types.setdefault(slug, set()).add(pt)
            if found_this_page == 0:
                break
    # convert sets to sorted lists
    result = {s: sorted(list(v)) for s, v in slug_to_types.items()}
    log.info(f"  mapped {len(result)} slugs to product_types")
    return result


def extract_featured_image(rest_item):
    """Pull the best-size featured image URL from an embedded REST product."""
    embedded = rest_item.get("_embedded", {})
    media_list = embedded.get("wp:featuredmedia") or []
    if not media_list:
        return None
    media = media_list[0]
    if not isinstance(media, dict):
        return None
    # Prefer "full" size; fall back to source_url
    sizes = media.get("media_details", {}).get("sizes", {})
    for preferred in ("full", "2048x2048", "1536x1536", "large"):
        if preferred in sizes and sizes[preferred].get("source_url"):
            return sizes[preferred]["source_url"]
    return media.get("source_url")


def parse_product_html(soup, url):
    """Extract description, gallery, specs, model code, and product-type from HTML."""
    result = {
        "description": "",
        "images": [],
        "specifications": {},
        "model_code": None,
        "product_types": [],
    }
    if not soup:
        return result

    page_text = soup.get_text(" ", strip=True)

    # --- Model code (VOR XXXX) ---
    m = re.search(r"\bVOR\s*(\d{3,5}[A-Z]?)\b", page_text)
    if m:
        result["model_code"] = f"VOR-{m.group(1)}"

    # --- Description: og:description, then first long paragraph in main content ---
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        result["description"] = og_desc["content"].strip()
    if not result["description"]:
        for p in soup.find_all("p"):
            txt = p.get_text(strip=True)
            if len(txt) > 80 and not txt.lower().startswith("copyright"):
                result["description"] = txt
                break

    # Product-type taxonomy is populated externally via discover_product_types()

    # --- Gallery images ---
    # Only collect product-image <img> tags (class like "attachment-*" from WP, or inside
    # an identified product gallery container). Skip logos/icons/related-products thumbs.
    seen = set()
    gallery = []

    def add_image(src, alt=""):
        if not src or src.startswith("data:"):
            return
        full = urljoin(BASE_URL, src)
        low = full.lower()
        if any(t in low for t in ("/themes/", "/plugins/", "logo", "icon", "placeholder", "sprite")):
            return
        if "/wp-content/uploads/" not in low:
            return
        # Drop tiny images (thumbs) by URL suffix — WP sizes like -150x150, -300x300
        if re.search(r"-(?:150|300|100|75|60)x\d+\.(?:jpe?g|png|webp)$", low):
            return
        if full in seen:
            return
        seen.add(full)
        gallery.append({"url": full, "alt_text": alt})

    # Restrict to images with WP attachment classes (hero, product, gallery sizes)
    attachment_re = re.compile(r"attachment-(lrg-hero|hero|full|large|post-thumb|gallery|featprod)", re.I)
    for img in soup.find_all("img", class_=attachment_re):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        add_image(src, img.get("alt", ""))
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            best_url, best_w = None, 0
            for part in srcset.split(","):
                bits = part.strip().split()
                if len(bits) >= 2:
                    try:
                        w = int(re.sub(r"\D", "", bits[1]) or 0)
                    except ValueError:
                        w = 0
                    if w > best_w:
                        best_w, best_url = w, bits[0]
            if best_url:
                add_image(best_url, img.get("alt", ""))

    # Cap to 15 images max per product (avoids related-product bleed-through)
    result["images"] = gallery[:15]

    # --- Specs: look for labelled rows like "Height: 1.8 m" or label/value pairs in tabs ---
    specs = {}
    spec_label_map = {
        "height": "height",
        "width": "width",
        "length": "length",
        "weight": "weight",
        "water flow rate": "water_flow_rate",
        "flow rate": "water_flow_rate",
        "installation depth": "installation_depth",
        "max. working pressure": "max_working_pressure",
        "working pressure": "max_working_pressure",
        "connection size": "connection_size",
        "inlet size": "inlet_size",
    }

    # Table rows
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(" ", strip=True).lower().rstrip(":").strip()
                value = cells[1].get_text(" ", strip=True)
                for pattern, key in spec_label_map.items():
                    if pattern in label:
                        specs[key] = value
                        break
                else:
                    if label and value and len(label) < 60:
                        specs[label.replace(" ", "_")] = value

    # Definition lists
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = dt.get_text(" ", strip=True).lower().rstrip(":").strip()
            value = dd.get_text(" ", strip=True)
            for pattern, key in spec_label_map.items():
                if pattern in label:
                    specs[key] = value
                    break

    # Fallback text-regex scans for common spec shapes
    for pattern, key in (
        (r"Height[:\s]+([\d.,]+\s*(?:m|cm|mm|ft|in))", "height"),
        (r"Width[:\s]+([\d.,]+\s*(?:m|cm|mm|ft|in))", "width"),
        (r"Length[:\s]+([\d.,]+\s*(?:m|cm|mm|ft|in))", "length"),
        (r"Water\s*[Ff]low\s*[Rr]ate[:\s]+([\d.,]+\s*(?:L/min|GPM|l/min|gpm|m3/h))", "water_flow_rate"),
        (r"Installation\s*[Dd]epth[:\s]+([\d.,]+\s*(?:m|cm|mm|ft|in))", "installation_depth"),
    ):
        if key not in specs:
            m = re.search(pattern, page_text)
            if m:
                specs[key] = m.group(1).strip()

    result["specifications"] = specs
    return result


def scrape_one(rest_item, delay, slug_to_types=None):
    """Scrape one product: merge REST metadata + HTML-parsed fields."""
    slug = rest_item.get("slug")
    link = rest_item.get("link")
    title = (rest_item.get("title") or {}).get("rendered", "")
    featured = extract_featured_image(rest_item)

    log.info(f"  [HTML] {link}")
    time.sleep(delay)
    soup = fetch(link, as_json=False)
    parsed = parse_product_html(soup, link)

    if slug_to_types and slug in slug_to_types:
        parsed["product_types"] = slug_to_types[slug]

    # Merge images: featured first, then gallery (deduped)
    all_images = []
    seen = set()
    if featured:
        all_images.append({"url": featured, "alt_text": title, "is_primary": True})
        seen.add(featured)
    for img in parsed["images"]:
        if img["url"] not in seen:
            seen.add(img["url"])
            all_images.append({**img, "is_primary": False})

    return {
        "id": rest_item.get("id"),
        "slug": slug,
        "url": link,
        "name": title,
        "model_code": parsed["model_code"],
        "description": parsed["description"],
        "product_types": parsed["product_types"],
        "specifications": parsed["specifications"],
        "images": all_images,
        "brand": "vortex",
        "source_date_modified": rest_item.get("modified"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def save_checkpoint(data):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    parser = argparse.ArgumentParser(description="Scrape Vortex Aquatics product catalog")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N products (smoke test)")
    parser.add_argument("--product-type", type=str, help="Scrape only products whose page has this product-type class")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between HTML requests")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR)
    parser.add_argument("--skip-types", action="store_true", help="Skip product-type discovery pass")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # 1) Bulk metadata via REST
    rest_items = list_all_products()
    if args.limit:
        rest_items = rest_items[: args.limit]

    # 1b) Discover product-types by paginating each type's archive listing
    slug_to_types = {}
    if not args.skip_types:
        slug_to_types = discover_product_types(delay=args.delay)

    # 2) Resume state
    scraped_by_id = {}
    if args.resume:
        cp = load_checkpoint()
        if cp:
            for p in cp.get("products", []):
                scraped_by_id[p["id"]] = p
            log.info(f"Resuming with {len(scraped_by_id)} already scraped")

    start = time.time()
    for i, item in enumerate(rest_items):
        pid = item.get("id")
        if pid in scraped_by_id:
            log.info(f"[{i+1}/{len(rest_items)}] skip (cached): {item.get('slug')}")
            continue
        log.info(f"[{i+1}/{len(rest_items)}] {item.get('slug')}")
        product = scrape_one(item, args.delay, slug_to_types=slug_to_types)
        # product_type filter (if supplied, only keep matching)
        if args.product_type and args.product_type not in product.get("product_types", []):
            log.info(f"  -> filtered out (product_types={product.get('product_types')})")
            continue
        scraped_by_id[pid] = product

        if (i + 1) % 10 == 0:
            save_checkpoint({"products": list(scraped_by_id.values())})
            log.info(f"  [checkpoint @ {len(scraped_by_id)}]")

    elapsed = time.time() - start
    all_products = list(scraped_by_id.values())

    # 3) Write outputs
    full_path = os.path.join(args.output, "products_all.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)
    log.info(f"Wrote {full_path} ({len(all_products)} products)")

    # Chunked
    chunk = 500
    for i in range(0, len(all_products), chunk):
        part = all_products[i : i + chunk]
        page = i // chunk + 1
        out = os.path.join(args.output, f"products_{page}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(part, f, indent=2, ensure_ascii=False)
        log.info(f"Wrote {out} ({len(part)})")

    # Families aggregate
    counts = {}
    for p in all_products:
        for pt in p.get("product_types", []) or ["uncategorized"]:
            counts[pt] = counts.get(pt, 0) + 1
    families = [{"slug": k, "product_count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    fam_path = os.path.join(args.output, "families.json")
    with open(fam_path, "w", encoding="utf-8") as f:
        json.dump(families, f, indent=2, ensure_ascii=False)
    log.info(f"Wrote {fam_path}")

    log.info(f"DONE: {len(all_products)} products in {elapsed:.0f}s")

    # Clean checkpoint on full-run success
    if not args.limit and not args.product_type and os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


if __name__ == "__main__":
    main()
