"""
Flag old collections in the (default) Firestore database as backup.
Adds a _backup_meta document to each collection marking it for deletion on 2026-04-11.
"""
import os
from datetime import datetime
from google.cloud import firestore

SERVICE_ACCOUNT_PATH = r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-0d28f3991b7b.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

COLLECTIONS = [
    "brands",
    "products",
    "products_vinci",
    "product_categories_vinci",
    "quotations",
]

db = firestore.Client(project="ai-agents-go")  # default database

for coll in COLLECTIONS:
    # Check collection exists and has docs
    docs = list(db.collection(coll).limit(1).stream())
    if not docs:
        print(f"  {coll}: empty, skipping")
        continue

    db.collection(coll).document("_backup_meta").set({
        "status": "BACKUP - DO NOT USE",
        "migrated_to_database": "leka-product-catalogs",
        "migrated_at": datetime.utcnow().isoformat() + "Z",
        "delete_after": "2026-04-11",
        "note": "Data migrated to leka-product-catalogs database. Safe to delete this collection after 2026-04-11.",
    })
    print(f"  {coll}: flagged as backup")

print("\nDone. Old collections flagged for deletion after 2026-04-11.")
