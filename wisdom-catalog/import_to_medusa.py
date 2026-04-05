"""
Import Wisdom product catalog from Excel into Medusa Commerce v2.

Replaces import_to_firestore.py — same Excel parsing, targets Medusa Admin API.

Usage:
    python wisdom-catalog/import_to_medusa.py
    python wisdom-catalog/import_to_medusa.py --dry-run
"""
import os
import sys
import argparse
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.base_importer import safe_float, parse_dimensions
from shared.category_mapper import classify_category, classify_subcategory
from shared.medusa_importer import MedusaImporter

DOWNLOADS_DIR = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\Wisdom Slack Downloads"

BRAND = "wisdom"

CATEGORY_MAP = {
    "KB": "furniture",
    "GP": "playground",
    "HW": "outdoor",
    "N": "nature_play",
    "B": "balance",
    "L": "loose_parts",
    "CX": "creative",
    "WG": "water_play",
    "CH": "climbing",
    "E": "early_years",
    "QSWP": "playground",
    "SW": "playground",
    "SR": "playground",
    "WPPE": "playground",
}


def transform_product(row, category_ids, tag_ids):
    """Transform an Excel row into Medusa product create kwargs."""
    item_code = str(row.get("Item Code", "")).strip()
    if not item_code or pd.isna(row.get("Item Code")):
        return None

    dims = parse_dimensions(row.get("Size"))
    material = dims.pop("material", None)
    category_name = classify_category(item_code, CATEGORY_MAP)
    fob_usd = safe_float(row.get("2025 FOB price (USD)"))

    handle = f"wisdom-{item_code}".lower().replace(" ", "-")
    description_en = str(row.get("Description", "")).strip() if pd.notna(row.get("Description")) else ""
    description_cn = str(row.get("2025年品名", "")).strip() if pd.notna(row.get("2025年品名")) else ""

    metadata = {}
    if description_cn:
        metadata["description_cn"] = description_cn
    if material:
        metadata["material"] = material
    vol = safe_float(row.get("Volumn（M3）"))
    if vol:
        metadata["volume_cbm"] = vol
    page = int(row["Page"]) if pd.notna(row.get("Page")) else None
    if page:
        metadata["catalog_page"] = page
    metadata["catalog_source"] = "china_2025"

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

    if fob_usd:
        variant["prices"].append({
            "amount": int(round(fob_usd * 100)),
            "currency_code": "usd",
        })

    return {
        "title": description_en or item_code,
        "handle": handle,
        "description": description_en,
        "status": "published",
        "metadata": metadata,
        "category_ids": [category_ids[category_name]] if category_name in category_ids else [],
        "variant": variant,
    }


def main():
    parser = argparse.ArgumentParser(description="Import Wisdom products to Medusa")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--medusa-url", default=os.environ.get("MEDUSA_BACKEND_URL", "http://localhost:9000"))
    parser.add_argument("--api-key", default=os.environ.get("MEDUSA_ADMIN_API_KEY", ""))
    args = parser.parse_args()

    path = f"{DOWNLOADS_DIR}/2025-11-07 2025 price list for whole Catalog.xlsx"
    df = pd.read_excel(path, sheet_name="2025 Price for China Catalog", header=0)
    print(f"Loaded {len(df)} rows from catalog Excel\n")

    if args.dry_run:
        print("=== DRY RUN ===")
        for _, row in list(df.iterrows())[:3]:
            product = transform_product(row, {}, {})
            if product:
                print(f"  {product['handle']}: {product['title']}")
                print(f"    SKU: {product['variant']['sku']}")
                print(f"    Prices: {product['variant']['prices']}")
        print(f"... and {len(df) - 3} more rows")
        return

    client = MedusaImporter(base_url=args.medusa_url, api_key=args.api_key)

    # Ensure categories exist
    print("Creating categories...")
    category_ids = {}
    for cat in set(CATEGORY_MAP.values()):
        display_name = cat.replace("_", " ").title()
        category_ids[cat] = client.get_or_create_category(display_name, cat)
        print(f"  {display_name}: {category_ids[cat]}")

    # Transform and import
    print(f"\nImporting {len(df)} Wisdom products...")
    products = []
    for _, row in df.iterrows():
        product = transform_product(row, category_ids, {})
        if product:
            products.append(product)

    count = client.batch_import(products)
    print(f"\nImport complete: {count} Wisdom products")


if __name__ == "__main__":
    main()
