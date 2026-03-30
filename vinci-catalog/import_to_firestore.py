"""
Import Vinci Play product catalog data from scraped JSON into Firestore.
Uses GCP service account: claude@ai-agents-go.iam.gserviceaccount.com

Source: vinci-catalog/web-app/public/data/products_all.json (from scrape_catalog.py)
Collection: products_vinci (multi-brand architecture)

Usage:
    python vinci-catalog/import_to_firestore.py
    python vinci-catalog/import_to_firestore.py --dry-run   # preview without writing
"""
import os
import sys
import json
import argparse
from google.cloud import firestore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.base_importer import batch_write, build_category_index, register_brand

SERVICE_ACCOUNT_PATH = r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-4c81b70995db.json"

BRAND = "vinci"
COLLECTION_NAME = "products_vinci"
DATA_DIR = os.path.join(os.path.dirname(__file__), "web-app", "public", "data")

# Map Vinci series slugs to standardized categories
SERIES_TO_CATEGORY = {
    "robinia": "playground",
    "wooden": "playground",
    "naturo": "playground",
    "recycled": "playground",
    "castillo": "playground",
    "jungle": "playground",
    "space": "playground",
    "maxx": "playground",
    "roxx": "climbing",
    "steel": "playground",
    "steelplus": "playground",
    "crooc": "playground",
    "topicco": "playground",
    "solo": "playground",
    "minisweet": "early_years",
    "climboo": "climbing",
    "nettix": "climbing",
    "spring": "playground",
    "swing": "playground",
    "hoop": "playground",
    "arena": "sports",
    "jumpoo": "playground",
    "fitness": "fitness",
    "workout": "fitness",
    "workout-pro": "fitness",
    "active": "fitness",
    "woof": "outdoor",
    "park": "outdoor",
    "stock": "other",
}


def transform_product(scraped):
    """Transform a scraped product dict into the Firestore document format."""
    series_slug = scraped.get("series_slug", "")
    specs = scraped.get("specifications", {})
    dims = scraped.get("dimensions", {})

    # Build images array in shared schema format
    images = []
    for img in scraped.get("images", []):
        images.append({
            "url": img.get("url", ""),
            "alt_text": img.get("alt_text", ""),
            "is_primary": img.get("is_primary", False),
            "source": "website_scrape",
            "view_type": img.get("view_type", "render"),
        })

    return {
        "item_code": scraped.get("item_code", ""),
        "brand": BRAND,
        "description": scraped.get("description", ""),
        "name": scraped.get("name", ""),
        "category": SERIES_TO_CATEGORY.get(series_slug, "other"),
        "subcategory": series_slug,
        "series_slug": series_slug,
        "series_name": scraped.get("series_name", ""),
        "material": None,
        "dimensions": {
            "raw": f"{dims.get('length_cm', '')} x {dims.get('width_cm', '')} x {dims.get('height_cm', '')} cm" if dims.get("length_cm") else None,
            "length_cm": dims.get("length_cm"),
            "width_cm": dims.get("width_cm"),
            "height_cm": dims.get("height_cm"),
        },
        "specifications": {
            "age_group": specs.get("age_group"),
            "num_users": specs.get("num_users"),
            "safety_zone_m2": specs.get("safety_zone_m2"),
            "free_fall_height_cm": specs.get("free_fall_height_cm"),
            "platform_heights": specs.get("platform_heights"),
            "slide_platform_height": specs.get("slide_platform_height"),
            "tube_slide_platform_height": specs.get("tube_slide_platform_height"),
            "en_standard": specs.get("en_standard"),
            "spare_parts_available": specs.get("spare_parts_available"),
        },
        "images": images,
        "downloads": scraped.get("downloads", []),
        "certifications": scraped.get("certifications", []),
        "tags": scraped.get("tags", []),
        "source_url": scraped.get("url", ""),
        "status": "active",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }


def main():
    parser = argparse.ArgumentParser(description="Import Vinci Play products to Firestore")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Firestore")
    parser.add_argument("--data-file", type=str, default=os.path.join(DATA_DIR, "products_all.json"))
    args = parser.parse_args()

    # Load scraped data
    if not os.path.exists(args.data_file):
        print(f"Error: Data file not found: {args.data_file}")
        print("Run scrape_catalog.py first to generate product data.")
        sys.exit(1)

    with open(args.data_file, "r", encoding="utf-8") as f:
        scraped_products = json.load(f)

    print(f"Loaded {len(scraped_products)} products from {args.data_file}")

    # Transform products
    documents = []
    skipped = 0
    for sp in scraped_products:
        item_code = sp.get("item_code")
        if not item_code:
            skipped += 1
            continue
        doc = transform_product(sp)
        # Use series-code as doc ID for uniqueness
        doc_id = f"{sp.get('series_slug', 'unknown')}-{item_code}".lower()
        documents.append((doc_id, doc))

    print(f"Transformed {len(documents)} products ({skipped} skipped)")

    if args.dry_run:
        print("\n=== DRY RUN — Sample documents ===")
        for doc_id, doc in documents[:3]:
            print(f"\nDoc ID: {doc_id}")
            print(f"  Name: {doc['name']}")
            print(f"  Series: {doc['series_name']}")
            print(f"  Category: {doc['category']}")
            print(f"  Dimensions: {doc['dimensions']}")
            print(f"  Images: {len(doc['images'])}")
            print(f"  Downloads: {len(doc['downloads'])}")
        print(f"\n... and {len(documents) - 3} more")
        return

    # Write to Firestore
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH
    db = firestore.Client(project="ai-agents-go")
    print(f"Connected to Firestore (ai-agents-go) — Brand: {BRAND}\n")

    print("=== Step 1: Import Products ===")
    count = batch_write(db, COLLECTION_NAME, documents)
    print(f"  Done: {count} products imported to {COLLECTION_NAME}")

    print("\n=== Step 2: Build Category Index ===")
    cat_counts = build_category_index(db, COLLECTION_NAME, BRAND)

    print("\n=== Step 3: Register Brand ===")
    register_brand(
        db,
        brand=BRAND,
        name="Vinci Play",
        supplier="Vinci Play Sp. z o.o.",
        country="Poland",
        product_count=count,
        categories=list(cat_counts.keys()),
    )

    print(f"\nImport complete! {count} products in {COLLECTION_NAME}")


if __name__ == "__main__":
    main()
