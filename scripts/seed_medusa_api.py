"""
Seed Medusa v2 from Firestore JSON exports via Admin API.

Usage:
    python scripts/seed_medusa_api.py
    python scripts/seed_medusa_api.py --limit 10  # test with 10 products
"""
import os
import sys
import json
import time
import argparse
import requests

BACKEND_URL = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
ADMIN_EMAIL = "admin@leka.studio"
ADMIN_PASSWORD = "LekaAdmin2026"
MIGRATION_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migration")

WISDOM_SC = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
VINCI_SC = "sc_01KNKTHC77716EPCE3E2BKAMQP"


def get_token():
    resp = requests.post(f"{BACKEND_URL}/auth/user/emailpass",
                         json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    resp.raise_for_status()
    return resp.json()["token"]


def admin_post(token, path, data):
    resp = requests.post(f"{BACKEND_URL}/admin{path}",
                         json=data,
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"})
    return resp


def seed_categories(token, products):
    """Create categories from unique category values."""
    cats = set()
    for p in products:
        cat = p.get("category")
        if cat:
            cats.add(cat)

    cat_map = {}
    for cat in sorted(cats):
        display = cat.replace("_", " ").title()
        resp = admin_post(token, "/product-categories", {
            "name": display, "handle": cat, "is_active": True, "is_internal": False
        })
        if resp.status_code == 200:
            cat_map[cat] = resp.json()["product_category"]["id"]
            print(f"  Category: {display} ({cat_map[cat]})")
        elif resp.status_code == 400 and "already exists" in resp.text.lower():
            # Fetch existing
            get_resp = requests.get(f"{BACKEND_URL}/admin/product-categories?handle={cat}&limit=1",
                                    headers={"Authorization": f"Bearer {token}"})
            if get_resp.status_code == 200:
                existing = get_resp.json().get("product_categories", [])
                if existing:
                    cat_map[cat] = existing[0]["id"]
                    print(f"  Category: {display} (existing: {cat_map[cat]})")
        else:
            print(f"  Category {display} failed: {resp.status_code} {resp.text[:100]}")

    return cat_map


def seed_collections(token, products):
    """Create collections from Vinci series."""
    series = {}
    for p in products:
        slug = p.get("series_slug")
        name = p.get("series_name")
        if slug and slug not in series:
            series[slug] = name or slug.upper()

    col_map = {}
    for slug, name in sorted(series.items()):
        resp = admin_post(token, "/collections", {"title": name, "handle": slug})
        if resp.status_code == 200:
            col_map[slug] = resp.json()["collection"]["id"]
            print(f"  Collection: {name} ({col_map[slug]})")
        else:
            print(f"  Collection {name} failed: {resp.status_code} {resp.text[:100]}")

    return col_map


def seed_product(token, p, brand, sc_id, cat_map, col_map):
    """Create a single product via Admin API."""
    item_code = p.get("item_code", "")
    handle = f"{brand}-{item_code}".lower().replace(" ", "-").replace("/", "-")

    # Build metadata
    metadata = {}
    for key in ["description_cn", "description_th", "specifications", "downloads",
                "certifications", "source_url", "catalog_page", "catalog_source",
                "material", "volume_cbm", "series_slug", "series_name"]:
        val = p.get(key)
        if val:
            metadata[key] = val

    # Images
    images = []
    for img in p.get("images", []):
        url = img.get("url", "")
        if url:
            images.append({"url": url})

    # Build product data
    data = {
        "title": p.get("name") or p.get("description") or item_code,
        "handle": handle,
        "description": p.get("description", ""),
        "status": "published" if p.get("status") == "active" else "draft",
        "metadata": metadata,
        "images": images,
        "sales_channels": [{"id": sc_id}],
        "options": [{"title": "Default", "values": ["Standard"]}],
        "variants": [{
            "title": "Standard",
            "sku": item_code,
            "manage_inventory": False,
            "options": {"Default": "Standard"},
            "prices": [],
        }],
    }

    # Add pricing
    pricing = p.get("pricing", {})
    fob = pricing.get("fob_usd")
    if fob and isinstance(fob, (int, float)):
        data["variants"][0]["prices"].append({
            "amount": int(round(fob * 100)),
            "currency_code": "usd",
        })

    # Dimensions (ensure numeric)
    dims = p.get("dimensions", {})
    for dim_key, med_key in [("length_cm", "length"), ("width_cm", "width"), ("height_cm", "height")]:
        val = dims.get(dim_key)
        if val is not None:
            try:
                data["variants"][0][med_key] = float(val)
            except (ValueError, TypeError):
                pass
    if p.get("weight_kg"):
        try:
            data["variants"][0]["weight"] = float(p["weight_kg"])
        except (ValueError, TypeError):
            pass

    # Category
    cat = p.get("category")
    if cat and cat in cat_map:
        data["categories"] = [{"id": cat_map[cat]}]

    resp = admin_post(token, "/products", data)
    if resp.status_code == 200:
        return True
    else:
        if "duplicate" not in resp.text.lower() and "already exists" not in resp.text.lower():
            print(f"    FAIL {handle}: {resp.status_code} {resp.text[:150]}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit products per brand (0=all)")
    args = parser.parse_args()

    print("=== Medusa Product Seed via Admin API ===\n")

    # Auth
    print("Authenticating...")
    token = get_token()
    print(f"  Token: {token[:20]}...\n")

    # Load data
    wisdom_file = os.path.join(MIGRATION_DIR, "wisdom_products.json")
    vinci_file = os.path.join(MIGRATION_DIR, "vinci_products.json")

    with open(wisdom_file, "r", encoding="utf-8") as f:
        wisdom = json.load(f)
    with open(vinci_file, "r", encoding="utf-8") as f:
        vinci = json.load(f)

    print(f"Loaded: {len(wisdom)} Wisdom, {len(vinci)} Vinci\n")

    if args.limit:
        wisdom = wisdom[:args.limit]
        vinci = vinci[:args.limit]
        print(f"  Limited to {args.limit} per brand\n")

    # Categories
    print("Creating categories...")
    all_products = wisdom + vinci
    cat_map = seed_categories(token, all_products)
    print(f"  {len(cat_map)} categories\n")

    # Collections (Vinci series)
    print("Creating collections (Vinci series)...")
    col_map = seed_collections(token, vinci)
    print(f"  {len(col_map)} collections\n")

    # Seed Wisdom products
    print(f"Seeding {len(wisdom)} Wisdom products...")
    ok, fail = 0, 0
    for i, p in enumerate(wisdom):
        if not p.get("item_code"):
            continue
        success = seed_product(token, p, "wisdom", WISDOM_SC, cat_map, col_map)
        if success:
            ok += 1
        else:
            fail += 1
        if (ok + fail) % 100 == 0:
            print(f"  {ok + fail} / {len(wisdom)} ({ok} ok, {fail} fail)")
            # Re-auth periodically (token expires)
            if (ok + fail) % 500 == 0:
                token = get_token()
        time.sleep(0.05)  # Rate limit
    print(f"  Done: {ok} ok, {fail} fail\n")

    # Seed Vinci products
    print(f"Seeding {len(vinci)} Vinci products...")
    ok, fail = 0, 0
    for i, p in enumerate(vinci):
        if not p.get("item_code"):
            continue
        success = seed_product(token, p, "vinci", VINCI_SC, cat_map, col_map)
        if success:
            ok += 1
        else:
            fail += 1
        if (ok + fail) % 100 == 0:
            print(f"  {ok + fail} / {len(vinci)} ({ok} ok, {fail} fail)")
            if (ok + fail) % 500 == 0:
                token = get_token()
        time.sleep(0.05)
    print(f"  Done: {ok} ok, {fail} fail\n")

    print("=== Seed Complete ===")


if __name__ == "__main__":
    main()
