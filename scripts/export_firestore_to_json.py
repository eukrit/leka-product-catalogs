"""
Export Firestore collections to JSON files for Medusa migration.

Exports:
  - products_wisdom -> migration/wisdom_products.json
  - products_vinci -> migration/vinci_products.json
  - product_categories_wisdom -> migration/wisdom_categories.json
  - product_categories_vinci -> migration/vinci_categories.json
  - leka_vendor_quotations -> migration/quotations.json

Usage:
    python scripts/export_firestore_to_json.py
    python scripts/export_firestore_to_json.py --dry-run
"""
import os
import sys
import json
import argparse
from datetime import datetime

from google.cloud import firestore

SERVICE_ACCOUNT_PATH = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
MIGRATION_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migration")

COLLECTIONS = [
    ("products_wisdom", "wisdom_products.json"),
    ("products_vinci", "vinci_products.json"),
    ("product_categories_wisdom", "wisdom_categories.json"),
    ("product_categories_vinci", "vinci_categories.json"),
    ("leka_vendor_quotations", "quotations.json"),
]


def serialize_doc(doc_dict):
    """Convert Firestore document to JSON-serializable dict."""
    result = {}
    for key, value in doc_dict.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, "seconds"):  # Firestore Timestamp
            result[key] = datetime.fromtimestamp(value.seconds).isoformat()
        elif isinstance(value, dict):
            result[key] = serialize_doc(value)
        elif isinstance(value, list):
            result[key] = [
                serialize_doc(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def export_collection(db, collection_name, output_file, dry_run=False):
    """Export a single Firestore collection to JSON."""
    print(f"  Exporting {collection_name}...")
    docs = db.collection(collection_name).stream()
    data = []
    for doc in docs:
        doc_dict = serialize_doc(doc.to_dict())
        doc_dict["_doc_id"] = doc.id
        data.append(doc_dict)

    print(f"    {len(data)} documents")

    if not dry_run:
        output_path = os.path.join(MIGRATION_DIR, output_file)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"    Saved to {output_path}")

    return len(data)


def main():
    parser = argparse.ArgumentParser(description="Export Firestore to JSON for Medusa migration")
    parser.add_argument("--dry-run", action="store_true", help="Count documents without writing files")
    args = parser.parse_args()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

    if not args.dry_run:
        os.makedirs(MIGRATION_DIR, exist_ok=True)

    db = firestore.Client(project="ai-agents-go", database="leka-product-catalogs")
    print("Connected to Firestore (ai-agents-go / leka-product-catalogs)\n")

    total = 0
    for collection_name, output_file in COLLECTIONS:
        count = export_collection(db, collection_name, output_file, dry_run=args.dry_run)
        total += count

    print(f"\nExport complete: {total} total documents")
    if args.dry_run:
        print("(dry run — no files written)")


if __name__ == "__main__":
    main()
