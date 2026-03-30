"""
Scrape the full Vinci Play product catalog from vinci-play.com.

Extracts all products across all series with:
- Product info (name, code, description, series, category)
- Specifications (dimensions, age, users, safety zone, free fall height, etc.)
- Image URLs (renders, top view, front view)
- Download links (PDF tech sheet, DWG 2D, DWG 3D)
- Certifications and standards

Output: vinci-catalog/web-app/public/data/products.json
        vinci-catalog/web-app/public/data/series.json

Usage:
    python vinci-catalog/scrape_catalog.py
    python vinci-catalog/scrape_catalog.py --series robinia   # single series
    python vinci-catalog/scrape_catalog.py --resume            # resume from last checkpoint
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

BASE_URL = "https://vinci-play.com"
LANG = "en"

# All known product series with their URL slugs
# listing_slug = slug used on /en/playground-equipment/{slug} (may have suffix)
# offer_slug = slug used in /en/offer/{slug}/{product} (the canonical series ID)
# When listing_slug differs from slug, the listing page uses a suffixed URL
SERIES = [
    {"slug": "robinia", "name": "ROBINIA", "description": "Acacia wood playground equipment"},
    {"slug": "wooden", "name": "WOODEN", "description": "Wooden playground equipment"},
    {"slug": "naturo", "name": "NATURO", "description": "Natural wood playground"},
    {"slug": "recycled", "name": "RECYCLED", "description": "Recycled material playground equipment"},
    {"slug": "castillo", "name": "CASTILLO", "description": "Castle-themed towers and sets"},
    {"slug": "jungle", "name": "JUNGLE", "description": "Tropical forest motif towers"},
    {"slug": "space", "name": "SPACE", "description": "Space stations and rocket towers"},
    {"slug": "maxx", "name": "MAXX", "description": "Large multi-functional structures"},
    {"slug": "roxx", "name": "ROXX", "description": "Geometric climbing modules"},
    {"slug": "steel", "name": "STEEL", "description": "Steel playground equipment"},
    {"slug": "steelplus", "listing_slug": "steel-048", "name": "STEEL+", "description": "Enhanced steel playground equipment"},
    {"slug": "crooc", "name": "CROOC", "description": "Stainless steel playground equipment"},
    {"slug": "topicco", "name": "TOPICCO", "description": "Creative vehicles"},
    {"slug": "solo", "name": "SOLO", "description": "Single play devices"},
    {"slug": "minisweet", "name": "MINISWEET", "description": "Play sets for young children"},
    {"slug": "climboo", "name": "CLIMBOO", "description": "Climbing and fitness equipment"},
    {"slug": "nettix", "name": "NETTIX", "description": "Activity equipment and ropeways"},
    {"slug": "spring", "name": "SPRING", "description": "Spring riders"},
    {"slug": "swing", "name": "SWING", "description": "Swings"},
    {"slug": "hoop", "name": "HOOP", "description": "Playground carousels"},
    {"slug": "arena", "listing_slug": "arena-fe8", "name": "ARENA", "description": "Multifunctional playing fields"},
    {"slug": "jumpoo", "listing_slug": "jumpoo-f94", "name": "JUMPOO", "description": "Trampolines"},
    {"slug": "fitness", "name": "FITNESS", "description": "Fitness activity equipment"},
    {"slug": "workout", "name": "WORKOUT", "description": "Bodyweight training equipment"},
    {"slug": "workout-pro", "name": "WORKOUT PRO", "description": "Professional training equipment"},
    {"slug": "active", "name": "ACTIVE", "description": "Equipment for seniors"},
    {"slug": "woof", "name": "WOOF", "description": "Dog agility equipment"},
    {"slug": "park", "name": "PARK", "description": "Small architecture"},
    {"slug": "stock", "name": "STOCK", "description": "Ready-to-ship products"},
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "web-app", "public", "data")
CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), ".scrape_checkpoint.json")

# Rate limiting
REQUEST_DELAY = 1.0  # seconds between requests
MAX_RETRIES = 3
RETRY_DELAY = 5.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vinci-scraper")

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; LekaCatalogBot/1.0; +https://github.com/eukrit/leka-product-catalogs)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
})


def fetch_page(url, retries=MAX_RETRIES):
    """Fetch a page with retry logic and rate limiting."""
    for attempt in range(retries):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            log.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    log.error(f"Failed to fetch {url} after {retries} attempts")
    return None


def get_product_urls_for_series(series_info):
    """Scrape all product URLs from a series listing page.

    Uses listing_slug (if different from slug) for the category page,
    and detects the actual offer slug from product hrefs.
    """
    listing_slug = series_info.get("listing_slug", series_info["slug"])
    offer_slug = series_info["slug"]

    url = f"{BASE_URL}/{LANG}/playground-equipment/{listing_slug}"
    log.info(f"Fetching series page: {url}")
    soup = fetch_page(url)
    if not soup:
        return []

    product_urls = []
    # Product links follow pattern: /en/offer/{offer_slug}/{product-slug}
    # Match broadly on /en/offer/ and filter for this series
    offer_pattern = re.compile(rf"^/{LANG}/offer/")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if offer_pattern.match(href):
            # Extract the offer series from the URL
            parts = href.strip("/").split("/")
            if len(parts) >= 4:  # en/offer/{series}/{product}
                url_series = parts[2]
                # Accept if it matches the offer_slug or listing_slug
                if url_series == offer_slug or url_series == listing_slug:
                    full_url = urljoin(BASE_URL, href)
                    if full_url not in product_urls:
                        product_urls.append(full_url)

    log.info(f"  Found {len(product_urls)} products in {series_info['name']} (listing: {listing_slug}, offer: {offer_slug})")
    return product_urls


def parse_spec_value(text):
    """Parse a specification value, extracting numbers where possible."""
    text = text.strip()
    # Try to extract numeric value with unit
    num_match = re.match(r"^([\d.,]+)\s*(cm|m²|m|kg|mm)?$", text)
    if num_match:
        val = num_match.group(1).replace(",", "")
        try:
            return float(val) if "." in val else int(val)
        except ValueError:
            pass
    return text


def scrape_product(url, series_slug, series_name):
    """Scrape all data from a single product page."""
    soup = fetch_page(url)
    if not soup:
        return None

    product = {
        "url": url,
        "series_slug": series_slug,
        "series_name": series_name,
        "category": "playground_equipment",
        "brand": "vinci",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    # --- Product name and code ---
    h1 = soup.find("h1")
    if h1:
        product["name"] = h1.get_text(strip=True)
    # Extract item code from URL: /en/offer/series/series-CODE -> CODE
    url_match = re.search(r"/offer/[^/]+/[^/]+-(.+)$", url.rstrip("/"))
    if url_match:
        raw_code = url_match.group(1).upper()
        product["item_code"] = raw_code
    else:
        # Fallback: use product name
        product["item_code"] = product.get("name", "").replace(" ", "-").upper()

    # --- Description ---
    # Look for description paragraphs near the product
    desc_candidates = []
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 40 and not text.startswith("©"):
            desc_candidates.append(text)
    if desc_candidates:
        product["description"] = desc_candidates[0]

    # --- Specifications ---
    specs = {}
    spec_mapping = {
        "length": "length_cm",
        "width": "width_cm",
        "total height": "total_height_cm",
        "height": "total_height_cm",
        "age": "age_group",
        "age group": "age_group",
        "number of users": "num_users",
        "users": "num_users",
        "safety zone": "safety_zone_m2",
        "free fall height": "free_fall_height_cm",
        "free-fall height": "free_fall_height_cm",
        "platform height": "platform_heights",
        "platform heights": "platform_heights",
        "slide platform height": "slide_platform_height",
        "tube slide platform height": "tube_slide_platform_height",
        "en norm": "en_standard",
        "standard": "en_standard",
        "spare parts": "spare_parts_available",
    }

    # Specs are typically in table rows, definition lists, or labeled divs
    # Try tables first
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower().rstrip(":")
                value = cells[1].get_text(strip=True)
                matched_key = None
                for pattern, key in spec_mapping.items():
                    if pattern in label:
                        matched_key = key
                        break
                if matched_key:
                    specs[matched_key] = parse_spec_value(value)
                elif label and value:
                    specs[label] = value

    # Try definition lists
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True).lower().rstrip(":")
            value = dd.get_text(strip=True)
            matched_key = None
            for pattern, key in spec_mapping.items():
                if pattern in label:
                    matched_key = key
                    break
            if matched_key:
                specs[matched_key] = parse_spec_value(value)
            elif label and value:
                specs[label] = value

    # Try labeled spans/divs (common in modern sites)
    for el in soup.find_all(["div", "span", "li"], class_=re.compile(r"spec|param|feature|detail|attr", re.I)):
        text = el.get_text(" ", strip=True)
        for pattern, key in spec_mapping.items():
            if pattern in text.lower():
                # Try to extract the value after the label
                val_match = re.search(r"[\d.,]+\s*(?:cm|m²|m|kg|mm|years)?", text)
                if val_match:
                    specs[key] = parse_spec_value(val_match.group())
                    break

    # Also scan all text for spec patterns as fallback
    page_text = soup.get_text(" ", strip=True)
    if "length_cm" not in specs:
        m = re.search(r"[Ll]ength[:\s]+([\d.,]+)\s*cm", page_text)
        if m:
            specs["length_cm"] = parse_spec_value(m.group(1))
    if "width_cm" not in specs:
        m = re.search(r"[Ww]idth[:\s]+([\d.,]+)\s*cm", page_text)
        if m:
            specs["width_cm"] = parse_spec_value(m.group(1))
    if "total_height_cm" not in specs:
        m = re.search(r"[Hh]eight[:\s]+([\d.,]+)\s*cm", page_text)
        if m:
            specs["total_height_cm"] = parse_spec_value(m.group(1))
    if "age_group" not in specs:
        m = re.search(r"(\d+[\+\-]\s*(?:\d+\s*)?years?)", page_text, re.I)
        if m:
            specs["age_group"] = m.group(1).strip()
    if "num_users" not in specs:
        m = re.search(r"(\d+)\s*(?:kids|users|children)", page_text, re.I)
        if m:
            specs["num_users"] = int(m.group(1))
    if "safety_zone_m2" not in specs:
        m = re.search(r"[Ss]afety\s*[Zz]one[:\s]+([\d.,]+)\s*m²", page_text)
        if m:
            specs["safety_zone_m2"] = parse_spec_value(m.group(1))
    if "free_fall_height_cm" not in specs:
        m = re.search(r"[Ff]ree\s*[Ff]all\s*[Hh]eight[:\s]+[<>]?([\d.,]+)\s*cm", page_text)
        if m:
            specs["free_fall_height_cm"] = parse_spec_value(m.group(1))
    if "en_standard" not in specs:
        # EN 1176 (playground), EN 16630 (fitness), EN 15312 (sport)
        m = re.search(r"(EN\s*(?:1176|16630|15312)[\w:+\-. ]*)", page_text)
        if m:
            specs["en_standard"] = m.group(1).strip()

    product["specifications"] = specs

    # Build dimensions map for compatibility with shared schema
    product["dimensions"] = {
        "length_cm": specs.get("length_cm"),
        "width_cm": specs.get("width_cm"),
        "height_cm": specs.get("total_height_cm"),
    }

    # --- Images ---
    images = []
    seen_urls = set()
    # Look for render images from zamowienia.vinci-play.pl
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if "renders_webp" in src or "renders/" in src or "vinci-play" in src:
            full_src = urljoin(BASE_URL, src)
            if full_src not in seen_urls:
                seen_urls.add(full_src)
                alt = img.get("alt", "")
                is_top = "top" in src.lower()
                is_front = "front" in src.lower()
                view_type = "top" if is_top else ("front" if is_front else "render")
                images.append({
                    "url": full_src,
                    "alt_text": alt,
                    "view_type": view_type,
                    "is_primary": len(images) == 0 and not is_top and not is_front,
                })
    # Also check srcset and data-src (lazy loading)
    for img in soup.find_all("img", attrs={"data-src": True}):
        src = img["data-src"]
        if "renders" in src or "vinci-play" in src:
            full_src = urljoin(BASE_URL, src)
            if full_src not in seen_urls:
                seen_urls.add(full_src)
                images.append({
                    "url": full_src,
                    "alt_text": img.get("alt", ""),
                    "view_type": "render",
                    "is_primary": False,
                })
    # Check source elements in picture tags
    for source in soup.find_all("source", srcset=True):
        srcset = source["srcset"]
        for src_part in srcset.split(","):
            src = src_part.strip().split(" ")[0]
            if "renders" in src or "vinci-play" in src:
                full_src = urljoin(BASE_URL, src)
                if full_src not in seen_urls:
                    seen_urls.add(full_src)
                    images.append({
                        "url": full_src,
                        "alt_text": "",
                        "view_type": "render",
                        "is_primary": False,
                    })

    product["images"] = images

    # --- Downloads ---
    downloads = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True).lower()
        full_href = urljoin(BASE_URL, href)

        if "technicalsheet" in href:
            downloads.append({
                "type": "technical_sheet",
                "format": "pdf",
                "url": full_href,
                "label": "Technical Data Sheet",
            })
        elif "download.php" in href and "dwg" in href:
            if "3d" in href.lower():
                downloads.append({
                    "type": "dwg_3d",
                    "format": "dwg",
                    "url": full_href,
                    "label": "3D DWG Drawing",
                })
            else:
                downloads.append({
                    "type": "dwg_2d",
                    "format": "dwg",
                    "url": full_href,
                    "label": "2D DWG Drawing",
                })
        elif href.endswith(".pdf") or "pdf" in text:
            downloads.append({
                "type": "document",
                "format": "pdf",
                "url": full_href,
                "label": text or "PDF Document",
            })
        elif href.endswith(".dwg"):
            downloads.append({
                "type": "drawing",
                "format": "dwg",
                "url": full_href,
                "label": text or "DWG Drawing",
            })

    product["downloads"] = downloads

    # --- Certifications ---
    certs = []
    cert_keywords = {
        "TÜV": "TÜV Rheinland",
        "TUV": "TÜV Rheinland",
        "ISO 9001": "ISO 9001:2015",
        "ISO 14001": "ISO 14001:2015",
        "EN 1176": specs.get("en_standard", "EN 1176"),
    }
    for keyword, cert_name in cert_keywords.items():
        if keyword.lower() in page_text.lower():
            if cert_name not in certs:
                certs.append(cert_name)
    product["certifications"] = certs

    # --- Badges / Tags ---
    tags = []
    if soup.find(string=re.compile(r"new", re.I)):
        # Check if "new" is a product badge, not just page text
        for badge in soup.find_all(class_=re.compile(r"badge|label|tag|new|flag", re.I)):
            if "new" in badge.get_text(strip=True).lower():
                tags.append("new")
                break
    for badge in soup.find_all(class_=re.compile(r"inclusive|accessible|wheelchair", re.I)):
        tags.append("inclusive")
        break
    # Check for inclusive icon in images
    for img in soup.find_all("img", alt=re.compile(r"inclusive|wheelchair|accessible", re.I)):
        if "inclusive" not in tags:
            tags.append("inclusive")
    product["tags"] = tags

    return product


def save_checkpoint(data):
    """Save scraping progress to resume later."""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f)


def load_checkpoint():
    """Load previous scraping progress."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return None


def main():
    parser = argparse.ArgumentParser(description="Scrape Vinci Play product catalog")
    parser.add_argument("--series", type=str, help="Scrape only this series (slug)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Delay between requests (seconds)")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()

    global REQUEST_DELAY
    REQUEST_DELAY = args.delay
    os.makedirs(args.output, exist_ok=True)

    # Determine which series to scrape
    if args.series:
        target_series = [s for s in SERIES if s["slug"] == args.series or s.get("listing_slug") == args.series]
        if not target_series:
            log.error(f"Unknown series: {args.series}")
            log.info(f"Available: {', '.join(s['slug'] for s in SERIES)}")
            sys.exit(1)
    else:
        target_series = SERIES

    # Load checkpoint if resuming
    all_products = []
    scraped_urls = set()
    completed_series = set()
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            all_products = checkpoint.get("products", [])
            scraped_urls = set(checkpoint.get("scraped_urls", []))
            completed_series = set(checkpoint.get("completed_series", []))
            log.info(f"Resuming: {len(all_products)} products, {len(completed_series)} series done")

    series_data = []
    total_start = time.time()

    for series_info in target_series:
        slug = series_info["slug"]
        name = series_info["name"]

        if slug in completed_series:
            log.info(f"Skipping {name} (already scraped)")
            continue

        log.info(f"\n{'='*60}")
        log.info(f"SERIES: {name} ({slug})")
        log.info(f"{'='*60}")

        # Get all product URLs for this series
        product_urls = get_product_urls_for_series(series_info)

        series_products = []
        for i, url in enumerate(product_urls):
            if url in scraped_urls:
                log.info(f"  [{i+1}/{len(product_urls)}] Skipping (cached): {url}")
                continue

            log.info(f"  [{i+1}/{len(product_urls)}] Scraping: {url}")
            product = scrape_product(url, slug, name)

            if product:
                all_products.append(product)
                series_products.append(product)
                scraped_urls.add(url)
                log.info(f"    -> {product.get('name', 'N/A')} | {len(product.get('images', []))} images | {len(product.get('downloads', []))} downloads")
            else:
                log.warning(f"    -> Failed to scrape")

            # Checkpoint every 50 products
            if len(all_products) % 50 == 0:
                save_checkpoint({
                    "products": all_products,
                    "scraped_urls": list(scraped_urls),
                    "completed_series": list(completed_series),
                })
                log.info(f"  [Checkpoint saved: {len(all_products)} products]")

        series_data.append({
            **series_info,
            "product_count": len(series_products) + sum(
                1 for p in all_products if p.get("series_slug") == slug and p not in series_products
            ),
        })
        completed_series.add(slug)

        # Save checkpoint after each series
        save_checkpoint({
            "products": all_products,
            "scraped_urls": list(scraped_urls),
            "completed_series": list(completed_series),
        })

    elapsed = time.time() - total_start

    # --- Save outputs ---
    # Products JSON (paginated for large datasets)
    products_per_file = 500
    for i in range(0, len(all_products), products_per_file):
        chunk = all_products[i:i + products_per_file]
        page_num = i // products_per_file + 1
        out_path = os.path.join(args.output, f"products_{page_num}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(chunk, f, indent=2, ensure_ascii=False)
        log.info(f"Saved {out_path} ({len(chunk)} products)")

    # Full products file
    full_path = os.path.join(args.output, "products_all.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)
    log.info(f"Saved {full_path} ({len(all_products)} total products)")

    # Series metadata
    # Rebuild series_data with final counts for all series
    final_series = []
    for s in SERIES:
        count = sum(1 for p in all_products if p.get("series_slug") == s["slug"])
        if count > 0 or s in target_series:
            final_series.append({**s, "product_count": count})
    series_path = os.path.join(args.output, "series.json")
    with open(series_path, "w", encoding="utf-8") as f:
        json.dump(final_series, f, indent=2, ensure_ascii=False)
    log.info(f"Saved {series_path}")

    # Summary
    log.info(f"\n{'='*60}")
    log.info(f"SCRAPING COMPLETE")
    log.info(f"{'='*60}")
    log.info(f"Total products: {len(all_products)}")
    log.info(f"Total series: {len(final_series)}")
    log.info(f"Time elapsed: {elapsed:.1f}s")
    log.info(f"Output: {args.output}")

    # Clean up checkpoint on success
    if os.path.exists(CHECKPOINT_FILE) and not args.series:
        os.remove(CHECKPOINT_FILE)
        log.info("Checkpoint cleaned up")


if __name__ == "__main__":
    main()
