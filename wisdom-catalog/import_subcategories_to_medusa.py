"""
Create child product-categories under each Wisdom parent category and link
existing Wisdom products to their (parent, subcategory) pair.

The original `import_to_medusa.py` only links products to a single parent
category. This script reads the same Excel catalog, derives the subcategory
via shared.category_mapper.classify_subcategory, ensures a child category
exists under the parent (handle: `wisdom-<category>-<subcategory>`), and
PATCHes each existing Wisdom product to add the child category id.

Idempotent: safe to re-run. Existing links are preserved.

Usage:
    python wisdom-catalog/import_subcategories_to_medusa.py --dry-run
    python wisdom-catalog/import_subcategories_to_medusa.py
"""
import os
import sys
import argparse
import time
import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.category_mapper import classify_category, classify_subcategory
from shared.medusa_importer import MedusaImporter

def _default_downloads_dir() -> str:
    """Resolve the Wisdom Slack Downloads folder under the current user's OneDrive.

    Works on machines where the Windows username is either 'Eukrit' or 'eukri'.
    Tries the canonical workspace folder first, then falls back to the older
    sibling folder name used in some checkouts.
    """
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    base = os.path.join(home, "OneDrive", "Documents", "Claude Code")
    candidates = [
        os.path.join(base, "2026 Wisdom Product Catalogs Claude", "Wisdom Slack Downloads"),
        os.path.join(base, "2026 Product Catalogs Claude", "Wisdom Slack Downloads"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


DOWNLOADS_DIR = os.environ.get("WISDOM_DOWNLOADS_DIR") or _default_downloads_dir()

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


def main():
    parser = argparse.ArgumentParser(description="Create Wisdom subcategories in Medusa")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--medusa-url", default=os.environ.get("MEDUSA_BACKEND_URL", "http://localhost:9000"))
    parser.add_argument("--api-key", default=os.environ.get("MEDUSA_ADMIN_API_KEY", ""))
    args = parser.parse_args()

    path = os.path.join(DOWNLOADS_DIR, "2025-11-07 2025 price list for whole Catalog.xlsx")
    if not os.path.exists(path):
        sys.exit(
            f"Excel catalog not found at:\n  {path}\n"
            f"Set WISDOM_DOWNLOADS_DIR=<folder> if it's stored elsewhere."
        )
    df = pd.read_excel(path, sheet_name="2025 Price for China Catalog", header=0)
    print(f"Loaded {len(df)} rows from catalog Excel\n")

    # Build (handle -> [(category, subcategory)]) so we can map products by SKU.
    # Wisdom product handles are `wisdom-<item_code>` (lowercased).
    rows = []
    pairs = set()
    for _, row in df.iterrows():
        item_code = str(row.get("Item Code", "")).strip()
        if not item_code or pd.isna(row.get("Item Code")):
            continue
        cat = classify_category(item_code, CATEGORY_MAP)
        sub = classify_subcategory(row.get("Description"))
        if not sub:
            continue
        handle = f"wisdom-{item_code}".lower().replace(" ", "-")
        rows.append((handle, cat, sub))
        pairs.add((cat, sub))

    print(f"Found {len(rows)} products with a derived subcategory across {len(pairs)} (category, subcategory) pairs.\n")

    if args.dry_run:
        print("=== DRY RUN ===")
        from collections import Counter
        c = Counter((cat, sub) for _, cat, sub in rows)
        for (cat, sub), n in sorted(c.items()):
            print(f"  {cat:12s} / {sub:14s} -> {n} products")
        print(f"\n(would create {len(pairs)} child categories and update {len(rows)} products)")
        return

    client = MedusaImporter(base_url=args.medusa_url, api_key=args.api_key)

    # 1) Look up parent ids (created by import_to_medusa.py).
    print("Resolving parent category ids...")
    parent_ids = {}
    for cat in set(CATEGORY_MAP.values()):
        parent_ids[cat] = client.get_or_create_category(cat.replace("_", " ").title(), cat)
        print(f"  {cat:12s} -> {parent_ids[cat]}")

    # 2) Ensure child categories exist.
    print(f"\nEnsuring {len(pairs)} child categories...")
    child_ids = {}
    for cat, sub in sorted(pairs):
        handle = f"wisdom-{cat}-{sub}".replace("_", "-")
        name = sub.replace("_", " ").title()
        child_ids[(cat, sub)] = client.get_or_create_category(
            name, handle, parent_category_id=parent_ids[cat]
        )

    # 3) PATCH each product to add the child category id.
    print(f"\nLinking {len(rows)} products to subcategories...")
    linked = 0
    missing = 0
    errors = 0
    for i, (handle, cat, sub) in enumerate(rows):
        product_id = client.find_product_by_handle(handle)
        if not product_id:
            missing += 1
            continue
        try:
            client.add_categories_to_product(
                product_id, [parent_ids[cat], child_ids[(cat, sub)]]
            )
            linked += 1
            if linked % 100 == 0:
                print(f"  Linked {linked}/{len(rows)} (skipped {missing}, errors {errors})")
                time.sleep(0.1)
        except requests.HTTPError as e:
            errors += 1
            print(f"  Error on {handle}: {e.response.status_code} {e.response.text[:160]}")

    print(f"\nDone: {linked} linked, {missing} not found, {errors} errors.")


if __name__ == "__main__":
    main()
