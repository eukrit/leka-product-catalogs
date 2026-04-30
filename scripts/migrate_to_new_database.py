"""
Migrate all leka-product-catalogs collections from Firestore 'default' database
to the new 'leka-product-catalogs' database.

Collections to migrate:
  - brands
  - products_wisdom
  - products_vinci
  - products (legacy Wisdom)
  - product_categories_wisdom
  - product_categories_vinci
  - quotations

Usage:
    python scripts/migrate_to_new_database.py --dry-run   # preview counts
    python scripts/migrate_to_new_database.py              # run migration
"""
import os
import sys
import argparse
from google.cloud import firestore

SERVICE_ACCOUNT_PATH = r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-0d28f3991b7b.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

PROJECT = "ai-agents-go"
NEW_DATABASE = "leka-product-catalogs"

COLLECTIONS = [
    "brands",
    "products",
    "products_wisdom",
    "products_vinci",
    "product_categories_wisdom",
    "product_categories_vinci",
    "quotations",
]


def migrate_collection(src_db, dst_db, collection_name, dry_run=False):
    """Copy all documents from src collection to dst collection."""
    docs = list(src_db.collection(collection_name).stream())
    count = len(docs)

    if count == 0:
        print(f"  {collection_name}: 0 documents (skipping)")
        return 0

    if dry_run:
        print(f"  {collection_name}: {count} documents (dry run)")
        return count

    batch = dst_db.batch()
    written = 0
    for doc in docs:
        dst_ref = dst_db.collection(collection_name).document(doc.id)
        batch.set(dst_ref, doc.to_dict())
        written += 1
        if written % 400 == 0:
            batch.commit()
            batch = dst_db.batch()
            print(f"    committed {written}/{count}...")

    if written % 400 != 0:
        batch.commit()

    print(f"  {collection_name}: {written} documents migrated")
    return written


def main():
    parser = argparse.ArgumentParser(description="Migrate Firestore collections to new database")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    src_db = firestore.Client(project=PROJECT)  # default database
    dst_db = firestore.Client(project=PROJECT, database=NEW_DATABASE)

    print(f"Source: (default) -> Destination: {NEW_DATABASE}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE MIGRATION'}\n")

    total = 0
    for coll in COLLECTIONS:
        count = migrate_collection(src_db, dst_db, coll, dry_run=args.dry_run)
        total += count

    print(f"\nTotal: {total} documents {'counted' if args.dry_run else 'migrated'}")

    if not args.dry_run:
        # Verify by counting docs in new database
        print("\n=== Verification ===")
        for coll in COLLECTIONS:
            new_count = len(list(dst_db.collection(coll).stream()))
            src_count = len(list(src_db.collection(coll).stream()))
            status = "OK" if new_count == src_count else "MISMATCH"
            print(f"  {coll}: {new_count}/{src_count} [{status}]")


if __name__ == "__main__":
    main()
