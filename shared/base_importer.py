"""
Base importer with shared utilities for all brand catalog imports.

Each brand importer should:
1. Subclass BaseImporter
2. Override BRAND, COLLECTION_NAME, and import methods
3. Call shared helpers for parsing, batching, and category building
"""
import re
import pandas as pd
from google.cloud import firestore


def safe_float(val):
    """Parse a value to float, handling ranges, currencies, and edge cases."""
    if val is None or pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        s = str(val)
        range_match = re.match(r"([\d.]+)\s*[-–]\s*[\d.]+", s)
        if range_match:
            return float(range_match.group(1))
        cleaned = re.sub(r"[^\d.]", "", s)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None


def parse_dimensions(size_str):
    """Extract L×W×H dimensions and optional material from a size string."""
    if not size_str or pd.isna(size_str):
        return {"raw": None}
    raw = str(size_str)
    result = {"raw": raw}
    mat_match = re.search(r"Material:\s*(.+?)(?:\n|$)", raw)
    if mat_match:
        result["material"] = mat_match.group(1).strip()
    dim_match = re.search(r"([\d.]+)\s*[×xX]\s*([\d.]+)\s*[×xX]\s*([\d.]+)", raw)
    if dim_match:
        result["length_cm"] = float(dim_match.group(1))
        result["width_cm"] = float(dim_match.group(2))
        result["height_cm"] = float(dim_match.group(3))
    return result


def batch_write(db, collection_name, documents, batch_size=400):
    """Write documents to Firestore in batches.

    Args:
        db: Firestore client
        collection_name: Target collection (e.g. "products_wisdom")
        documents: List of (doc_id, doc_data) tuples
        batch_size: Documents per batch commit
    Returns:
        Number of documents written
    """
    batch = db.batch()
    count = 0
    for doc_id, doc_data in documents:
        doc_ref = db.collection(collection_name).document(doc_id)
        batch.set(doc_ref, doc_data)
        count += 1
        if count % batch_size == 0:
            batch.commit()
            batch = db.batch()
            print(f"  Committed {count} documents...")
    if count % batch_size != 0:
        batch.commit()
    return count


def build_category_index(db, collection_name, brand):
    """Build product_categories from product data in a brand collection.

    Writes to product_categories_{brand} collection.
    """
    products = db.collection(collection_name).stream()
    cat_counts = {}
    for doc in products:
        data = doc.to_dict()
        cat = data.get("category", "uncategorized")
        if cat not in cat_counts:
            cat_counts[cat] = {"count": 0, "prefixes": set()}
        cat_counts[cat]["count"] += 1
        code = data.get("item_code", "")
        prefix = re.match(r"^([A-Z]+\d*)", code)
        if prefix:
            cat_counts[cat]["prefixes"].add(prefix.group(1))

    cat_collection = f"product_categories_{brand}"
    for cat, info in cat_counts.items():
        db.collection(cat_collection).document(cat).set({
            "name": cat.replace("_", " ").title(),
            "brand": brand,
            "prefix_patterns": sorted(info["prefixes"]),
            "product_count": info["count"],
        })
        print(f"  {cat}: {info['count']} products")

    return cat_counts


