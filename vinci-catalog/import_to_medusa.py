"""
Import Vinci Play product catalog from scraped JSON into Medusa Commerce v2.

Replaces import_to_firestore.py — same JSON parsing, targets Medusa Admin API.

Usage:
    python vinci-catalog/import_to_medusa.py
    python vinci-catalog/import_to_medusa.py --dry-run
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.medusa_importer import MedusaImporter

DATA_DIR = os.path.join(os.path.dirname(__file__), "web-app", "public", "data")

SERIES_TO_CATEGORY = {
    "robinia": "playground", "wooden": "playground", "naturo": "playground",
    "recycled": "playground", "castillo": "playground", "jungle": "playground",
    "space": "playground", "maxx": "playground", "roxx": "climbing",
    "steel": "playground", "steelplus": "playground", "crooc": "playground",
    "topicco": "playground", "solo": "playground", "minisweet": "early_years",
    "climboo": "climbing", "nettix": "climbing", "spring": "playground",
    "swing": "playground", "hoop": "playground", "arena": "sports",
    "jumpoo": "playground", "fitness": "fitness", "workout": "fitness",
    "workout-pro": "fitness", "active": "fitness", "woof": "outdoor",
    "park": "outdoor", "stock": "other",
}


def transform_product(scraped, category_ids, collection_ids, tag_ids):
    """Transform a scraped product dict into Medusa product create kwargs."""
    item_code = scraped.get("item_code", "")
    series_slug = scraped.get("series_slug", "")
    specs = scraped.get("specifications", {})
    dims = scraped.get("dimensions", {})

    handle = f"vinci-{series_slug}-{item_code}".lower().replace(" ", "-").replace("/", "-")
    category_name = SERIES_TO_CATEGORY.get(series_slug, "other")

    # Build metadata
    metadata = {
        "series_slug": series_slug,
        "series_name": scraped.get("series_name", ""),
    }
    if specs:
        metadata["specifications"] = specs
    if scraped.get("downloads"):
        metadata["downloads"] = scraped["downloads"]
    if scraped.get("certifications"):
        metadata["certifications"] = scraped["certifications"]
    if scraped.get("url"):
        metadata["source_url"] = scraped["url"]

    # Images
    images = [img["url"] for img in scraped.get("images", []) if img.get("url")]

    # Tags
    product_tag_ids = [tag_ids[t] for t in scraped.get("tags", []) if t in tag_ids]

    # Variant
    variant = {
        "title": "Default",
        "sku": item_code,
        "manage_inventory": False,
        "prices": [],
    }
    if dims.get("length_cm"):
        variant["length"] = dims["length_cm"]
    if dims.get("width_cm"):
        variant["width"] = dims["width_cm"]
    if dims.get("height_cm"):
        variant["height"] = dims["height_cm"]

    return {
        "title": scraped.get("name", item_code),
        "handle": handle,
        "description": scraped.get("description", ""),
        "status": "published",
        "metadata": metadata,
        "images": images,
        "category_ids": [category_ids[category_name]] if category_name in category_ids else [],
        "collection_id": collection_ids.get(series_slug),
        "tag_ids": product_tag_ids,
        "variant": variant,
    }


def main():
    parser = argparse.ArgumentParser(description="Import Vinci Play products to Medusa")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-file", default=os.path.join(DATA_DIR, "products_all.json"))
    parser.add_argument("--medusa-url", default=os.environ.get("MEDUSA_BACKEND_URL", "http://localhost:9000"))
    parser.add_argument("--api-key", default=os.environ.get("MEDUSA_ADMIN_API_KEY", ""))
    args = parser.parse_args()

    if not os.path.exists(args.data_file):
        print(f"Error: Data file not found: {args.data_file}")
        print("Run scrape_catalog.py first.")
        sys.exit(1)

    with open(args.data_file, "r", encoding="utf-8") as f:
        scraped_products = json.load(f)

    print(f"Loaded {len(scraped_products)} products from {args.data_file}\n")

    if args.dry_run:
        print("=== DRY RUN ===")
        for sp in scraped_products[:3]:
            product = transform_product(sp, {}, {}, {})
            print(f"  {product['handle']}: {product['title']}")
            print(f"    SKU: {product['variant']['sku']}")
            print(f"    Images: {len(product.get('images', []))}")
            print(f"    Downloads: {len(product['metadata'].get('downloads', []))}")
        print(f"... and {len(scraped_products) - 3} more")
        return

    client = MedusaImporter(base_url=args.medusa_url, api_key=args.api_key)

    # Ensure categories exist
    print("Creating categories...")
    all_cats = set(SERIES_TO_CATEGORY.values())
    category_ids = {}
    for cat in all_cats:
        display_name = cat.replace("_", " ").title()
        category_ids[cat] = client.get_or_create_category(display_name, cat)
        print(f"  {display_name}: {category_ids[cat]}")

    # Ensure collections (series) exist
    print("\nCreating collections (series)...")
    collection_ids = {}
    series_names = {}
    for sp in scraped_products:
        slug = sp.get("series_slug", "")
        if slug and slug not in series_names:
            series_names[slug] = sp.get("series_name", slug.upper())

    for slug, name in series_names.items():
        collection_ids[slug] = client.get_or_create_collection(name, slug)
        print(f"  {name}: {collection_ids[slug]}")

    # Ensure tags exist
    print("\nCreating tags...")
    all_tags = set()
    for sp in scraped_products:
        for tag in sp.get("tags", []):
            all_tags.add(tag)

    tag_ids = {}
    for tag_name in all_tags:
        tag_ids[tag_name] = client.get_or_create_tag(tag_name)

    print(f"  {len(tag_ids)} tags")

    # Transform and import
    print(f"\nImporting {len(scraped_products)} Vinci Play products...")
    products = []
    for sp in scraped_products:
        if not sp.get("item_code"):
            continue
        product = transform_product(sp, category_ids, collection_ids, tag_ids)
        products.append(product)

    count = client.batch_import(products)
    print(f"\nImport complete: {count} Vinci Play products")


if __name__ == "__main__":
    main()
