"""
Import Vortex Aquatics products from scraped JSON into Medusa Commerce v2.

Creates:
- Sales Channel "Vortex Aquatics" (+ publishable API key)
- Category: water_play
- Collections: one per product-type (splashpad, waterslide, ...) + one fallback
- 272 Products linked to the Vortex sales channel, with GCS-mirrored images.

Usage:
    python vortex-catalog/import_to_medusa.py --dry-run
    python vortex-catalog/import_to_medusa.py
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.medusa_importer import MedusaImporter

DATA_DIR = os.path.join(os.path.dirname(__file__), "web-app", "public", "data")
SALES_CHANNEL_NAME = "Vortex Aquatics"
SALES_CHANNEL_DESCRIPTION = "Vortex Aquatic Structures — splashpads, waterslides, aquatic play"

# All Vortex products are water_play regardless of sub-family
VORTEX_CATEGORY = "water_play"

KNOWN_PRODUCT_TYPES = {
    "splashpad": "Splashpad",
    "waterslide": "Waterslide",
    "elevations-playnuk": "Elevations & PlayNuk",
    "playable-fountains": "Playable Fountains",
    "coolhub": "CoolHub",
    "dream-tunnel": "Dream Tunnel",
    "water-management-solutions": "Water Management Solutions",
    "uncategorized": "Uncategorized",
}


def transform_product(scraped, category_ids, collection_ids, sales_channel_id):
    """Transform a scraped Vortex product dict into Medusa product create kwargs."""
    slug = scraped.get("slug") or f"vortex-{scraped.get('id')}"
    model_code = scraped.get("model_code") or f"VOR-{slug.upper()}"
    product_types = scraped.get("product_types") or ["uncategorized"]
    primary_type = product_types[0]

    handle = f"vortex-{primary_type}-{slug}".lower().replace(" ", "-").replace("/", "-")[:120]

    # Prefer GCS URLs (post-mirror). Fall back to source URL if mirror failed.
    images = []
    for img in scraped.get("images", []):
        url = img.get("gcs_url") or img.get("url")
        if url and url not in images:
            images.append(url)

    metadata = {
        "model_code": model_code,
        "product_types": product_types,
        "source_url": scraped.get("url"),
        "source_id": scraped.get("id"),
        "source_modified": scraped.get("source_date_modified"),
    }
    if scraped.get("specifications"):
        metadata["specifications"] = scraped["specifications"]

    variant = {
        "title": "Default",
        "sku": model_code,
        "manage_inventory": False,
        "prices": [],
    }

    collection_id = collection_ids.get(primary_type) or collection_ids.get("uncategorized")

    return {
        "title": scraped.get("name") or slug.replace("-", " ").title(),
        "handle": handle,
        "description": scraped.get("description", ""),
        "status": "published",
        "metadata": metadata,
        "images": images,
        "category_ids": [category_ids[VORTEX_CATEGORY]] if VORTEX_CATEGORY in category_ids else [],
        "collection_id": collection_id,
        "variant": variant,
        "sales_channel_ids": [sales_channel_id] if sales_channel_id else [],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-file", default=os.path.join(DATA_DIR, "products_all.json"))
    parser.add_argument("--medusa-url", default=os.environ.get("MEDUSA_BACKEND_URL", "http://localhost:9000"))
    parser.add_argument("--api-key", default=os.environ.get("MEDUSA_ADMIN_API_KEY", ""))
    args = parser.parse_args()

    if not os.path.exists(args.data_file):
        print(f"Data file not found: {args.data_file}")
        sys.exit(1)

    with open(args.data_file, encoding="utf-8") as f:
        scraped = json.load(f)

    print(f"Loaded {len(scraped)} Vortex products from {args.data_file}")

    if args.dry_run:
        print("=== DRY RUN ===")
        for sp in scraped[:3]:
            product = transform_product(sp, {VORTEX_CATEGORY: "cat_dummy"}, {pt: f"col_{pt}" for pt in KNOWN_PRODUCT_TYPES}, "sc_dummy")
            print(f"\n  handle:  {product['handle']}")
            print(f"  title:   {product['title']}")
            print(f"  SKU:     {product['variant']['sku']}")
            print(f"  images:  {len(product['images'])}")
            print(f"  types:   {product['metadata']['product_types']}")
            print(f"  desc:    {product['description'][:80]!r}")
        print(f"\n... and {len(scraped) - 3} more products")
        return

    client = MedusaImporter(base_url=args.medusa_url, api_key=args.api_key)

    print(f"\nSales Channel: {SALES_CHANNEL_NAME}")
    sc_id = client.get_or_create_sales_channel(SALES_CHANNEL_NAME, SALES_CHANNEL_DESCRIPTION)
    print(f"  id: {sc_id}")

    try:
        pk = client.create_publishable_api_key("Vortex Aquatics Storefront", sc_id)
        print(f"  publishable key id: {pk['id']}")
        if pk.get("token"):
            print(f"  publishable token: {pk['token']}")
    except Exception as e:
        print(f"  (publishable key: {e} — may already exist, continuing)")

    print("\nCategory:")
    category_ids = {VORTEX_CATEGORY: client.get_or_create_category("Water Play", VORTEX_CATEGORY)}
    print(f"  {VORTEX_CATEGORY}: {category_ids[VORTEX_CATEGORY]}")

    print("\nCollections (product_types):")
    collection_ids = {}
    for slug, title in KNOWN_PRODUCT_TYPES.items():
        collection_ids[slug] = client.get_or_create_collection(f"Vortex — {title}", f"vortex-{slug}")
        print(f"  {slug}: {collection_ids[slug]}")

    # Transform
    print(f"\nTransforming {len(scraped)} products...")
    products = []
    for sp in scraped:
        if not sp.get("slug"):
            continue
        products.append(transform_product(sp, category_ids, collection_ids, sc_id))

    print(f"\nImporting {len(products)} Vortex products to Medusa...")
    count = client.batch_import(products)
    print(f"\nImport complete: {count} Vortex products")


if __name__ == "__main__":
    main()
