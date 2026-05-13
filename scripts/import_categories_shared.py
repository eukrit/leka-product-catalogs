"""
Create the shared (brand-agnostic) product categories in Firestore.

Database: leka-product-catalogs
Collection: product_categories  (parallel to per-brand product_categories_{brand})
Docs: epdm, infill

Idempotent: uses set(..., merge=True). Also recounts products by scanning
products_epdm / products_infill so product_count stays current.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import firestore

FIRESTORE_DB = "leka-product-catalogs"
SA_KEY = Path(
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code"
    r"\GCP Credentials\ai-agents-go-claude.json"
)

CATEGORIES = {
    "epdm": {
        "name": "EPDM",
        "name_th": "EPDM ยางอัดพื้น",
        "brand": None,
        "description": (
            "Rubber wet-pour surfacing (EPDM / SBR / TPV). Two-layer system with a "
            "decorative top granule (EPDM/TPV) bonded over a shock-pad SBR backing. "
            "Used for playgrounds, athletic tracks and pool decks. The CFH (Critical "
            "Fall Height, metres) field on each product is the certified safety rating."
        ),
        "prefix_patterns": [
            "SBR ", "EPDM Blk ", "EPDM E ", "EPDM E UV ", "EPDM CG UV ", "TPV UV ",
        ],
        "icon": "shield-check",
        "queryable_fields": [
            "cfh_m", "thickness_mm", "sbr_mm", "system", "pricing.quote_thb_per_sqm",
        ],
    },
    "infill": {
        "name": "Infill",
        "name_th": "วัสดุอินฟิลล์สนามหญ้าเทียม",
        "brand": None,
        "description": (
            "Granular infill for artificial-turf soccer fields. Sand infill (16/30, 20/40) "
            "stabilises short/long grass; rubber/TPE infill (SBR, TPE) provides shock "
            "absorption. Sold by kg/sq.m. — not by thickness."
        ),
        "prefix_patterns": ["SAND ", "SBR ", "TPE "],
        "icon": "grid",
        "queryable_fields": ["sbr_kg_per_sqm", "system", "pricing.quote_thb_per_sqm"],
    },
}


def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(SA_KEY)
    db = firestore.Client(project="ai-agents-go", database=FIRESTORE_DB)
    now = datetime.now(timezone.utc)

    for slug, base in CATEGORIES.items():
        count = sum(1 for _ in db.collection(f"products_{slug}").stream())
        doc = {**base, "product_count": count, "updated_at": now}
        ref = db.collection("product_categories").document(slug)
        if not ref.get().exists:
            doc["created_at"] = now
        ref.set(doc, merge=True)
        print(f"  {slug:8s} -> {count} products")

    print("Done.")


if __name__ == "__main__":
    main()
