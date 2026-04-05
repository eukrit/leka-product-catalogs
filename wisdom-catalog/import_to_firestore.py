"""
Import Wisdom product catalog data from Excel files into Firestore.
Uses GCP service account: claude@ai-agents-go.iam.gserviceaccount.com

Collection: products_wisdom (multi-brand architecture)
"""
import re
import sys
import json
import os
import glob
import pandas as pd
from datetime import datetime
from google.cloud import firestore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.base_importer import safe_float, parse_dimensions, batch_write, build_category_index
from shared.category_mapper import classify_category, classify_subcategory

SERVICE_ACCOUNT_PATH = r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-4c81b70995db.json"
DOWNLOADS_DIR = r"C:\Users\eukri\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\Wisdom Slack Downloads"

BRAND = "wisdom"
COLLECTION_NAME = "products_wisdom"

# Wisdom-specific category mapping based on item code prefixes
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


def import_full_catalog(db):
    """Import the main 2025 catalog (4903 products)."""
    path = f"{DOWNLOADS_DIR}/2025-11-07 2025 price list for whole Catalog.xlsx"
    df = pd.read_excel(path, sheet_name="2025 Price for China Catalog", header=0)
    print(f"Full catalog: {len(df)} rows")

    documents = []
    skipped = 0

    for _, row in df.iterrows():
        item_code = row.get("Item Code")
        if not item_code or pd.isna(item_code):
            skipped += 1
            continue

        item_code = str(item_code).strip()
        dims = parse_dimensions(row.get("Size"))
        material = dims.pop("material", None)

        doc_data = {
            "item_code": item_code,
            "brand": BRAND,
            "description": str(row.get("Description", "")).strip() if pd.notna(row.get("Description")) else "",
            "description_cn": str(row.get("2025\u5e74\u54c1\u540d", "")).strip() if pd.notna(row.get("2025\u5e74\u54c1\u540d")) else "",
            "category": classify_category(item_code, CATEGORY_MAP),
            "subcategory": classify_subcategory(row.get("Description")),
            "material": material,
            "dimensions": dims,
            "volume_cbm": safe_float(row.get("Volumn\uff08M3\uff09")),
            "weight_kg": None,
            "pricing": {
                "fob_usd": safe_float(row.get("2025 FOB price (USD)")),
                "currency": "USD",
                "price_date": "2025-11-07",
            },
            "catalog_page": int(row["Page"]) if pd.notna(row.get("Page")) else None,
            "catalog_source": "china_2025",
            "images": [],
            "status": "active",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        documents.append((item_code, doc_data))

    count = batch_write(db, COLLECTION_NAME, documents)
    print(f"  Done: {count} imported, {skipped} skipped")
    return count


def import_us_catalog(db):
    """Import US catalog, merging weight data into existing products or creating new ones."""
    path = f"{DOWNLOADS_DIR}/Wisdom US catalog price list 20250528.xlsx"
    df = pd.read_excel(path, sheet_name="Table 1", header=2)
    print(f"US catalog: {len(df)} rows")

    count = 0
    for _, row in df.iterrows():
        item_code = row.get("Item Code")
        if not item_code or pd.isna(item_code):
            continue

        item_code = str(item_code).strip()
        doc_ref = db.collection(COLLECTION_NAME).document(item_code)
        doc = doc_ref.get()

        price_val = safe_float(row.get("FOB Shanghai price (USD)"))
        weight_val = safe_float(row.get("Weight\uff08KG)"))
        volume_val = safe_float(row.get("Volume (CBM)"))

        if doc.exists:
            update = {"weight_kg": weight_val, "updated_at": firestore.SERVER_TIMESTAMP}
            if price_val:
                update["pricing.fob_usd_us"] = price_val
            doc_ref.update(update)
        else:
            doc_data = {
                "item_code": item_code,
                "brand": BRAND,
                "description": str(row.get("Description", "")).strip() if pd.notna(row.get("Description")) else "",
                "description_cn": "",
                "category": classify_category(item_code, CATEGORY_MAP),
                "subcategory": classify_subcategory(row.get("Description")),
                "material": None,
                "dimensions": {"raw": None},
                "volume_cbm": volume_val,
                "weight_kg": weight_val,
                "pricing": {
                    "fob_usd": price_val,
                    "currency": "USD",
                    "price_date": "2025-05-28",
                },
                "catalog_page": int(row["Page"]) if pd.notna(row.get("Page")) else None,
                "catalog_source": "us_2025",
                "images": [],
                "status": "active",
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
            doc_ref.set(doc_data)
        count += 1

    print(f"  Done: {count} merged/created")
    return count


def import_quotations(db):
    """Import quotation files as separate quotation documents."""
    quotation_files = glob.glob(f"{DOWNLOADS_DIR}/Quotation*.xlsx") + glob.glob(f"{DOWNLOADS_DIR}/*Quotation*.xlsx")
    quotation_files = list(set(quotation_files))
    print(f"Found {len(quotation_files)} quotation files")

    count = 0
    for fpath in sorted(quotation_files):
        fname = fpath.split("\\")[-1].split("/")[-1]
        date_match = re.search(r"(\d{8}|\d{6})", fname)
        date_str = date_match.group(1) if date_match else ""

        try:
            df = pd.read_excel(fpath, header=0)
        except Exception as e:
            print(f"  Skip {fname}: {e}")
            continue

        cols = df.columns.tolist()
        code_col = next((c for c in cols if "code" in str(c).lower() or "item" in str(c).lower()), cols[0] if cols else None)
        price_col = next((c for c in cols if "fob" in str(c).lower() or "price" in str(c).lower() or "usd" in str(c).lower()), None)
        vol_col = next((c for c in cols if "vol" in str(c).lower() or "cbm" in str(c).lower()), None)
        remarks_col = next((c for c in cols if "remark" in str(c).lower()), None)

        items = []
        for _, row in df.iterrows():
            code_val = row.get(code_col) if code_col else None
            if not code_val or pd.isna(code_val):
                continue
            items.append({
                "item_code": str(code_val).strip(),
                "fob_usd": safe_float(row.get(price_col)) if price_col else None,
                "volume_cbm": safe_float(row.get(vol_col)) if vol_col else None,
                "remarks": str(row.get(remarks_col)).strip() if remarks_col and pd.notna(row.get(remarks_col)) else None,
            })

        if items:
            doc_data = {
                "quotation_id": fname.replace(".xlsx", ""),
                "brand": BRAND,
                "date": date_str,
                "source": "slack_vendor_wisdom_playground",
                "items": items,
                "created_at": firestore.SERVER_TIMESTAMP,
            }
            doc_data["vendor_name"] = "Wisdom Playground Equipment Co., Ltd."
            db.collection("leka_vendor_quotations").add(doc_data)
            count += 1
            print(f"  {fname}: {len(items)} items")

    print(f"  Done: {count} quotations imported")
    return count


def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

    db = firestore.Client(project="ai-agents-go", database="leka-product-catalogs")
    print(f"Connected to Firestore (ai-agents-go) — Brand: {BRAND}\n")

    print("=== Step 1: Import Full Catalog ===")
    full_count = import_full_catalog(db)

    print("\n=== Step 2: Import US Catalog ===")
    us_count = import_us_catalog(db)

    print("\n=== Step 3: Import Quotations ===")
    import_quotations(db)

    print("\n=== Step 4: Build Category Index ===")
    build_category_index(db, COLLECTION_NAME, BRAND)

    print("\nImport complete!")


if __name__ == "__main__":
    main()
