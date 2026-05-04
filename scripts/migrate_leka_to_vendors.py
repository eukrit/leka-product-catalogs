"""Migrate per-brand product data from `leka-product-catalogs` Firestore DB
into the `vendors` Firestore DB, conforming to the schema documented at
`migration/vendors_target_schema.md`.

Phase 1 of the migration plan (see `~/.claude/plans/inspect-our-project-database-wise-feigenbaum.md`).

Usage:
    python scripts/migrate_leka_to_vendors.py --brand=wisdom --dry-run
    python scripts/migrate_leka_to_vendors.py --brand=wisdom
    python scripts/migrate_leka_to_vendors.py --brand=all

Reads:  firestore.Client(project="ai-agents-go", database="leka-product-catalogs")
Writes: firestore.Client(project="ai-agents-go", database="vendors")

Auth: ADC. Set GOOGLE_APPLICATION_CREDENTIALS to the SA key for local runs;
in Cloud Run / GCE the metadata server provides ADC automatically.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

from google.cloud import firestore

# Local dev convenience — same pattern as vendors/vortex-catalog/scripts/seed_firestore.py
_LOCAL_SA = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.exists(_LOCAL_SA):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _LOCAL_SA
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.base_importer import batch_write  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("migrate_leka_to_vendors")

PROJECT = "ai-agents-go"
SRC_DB = "leka-product-catalogs"
DST_DB = "vendors"

# Source-of-truth: medusa-storefront/src/lib/medusa-client.ts BRANDS map.
# Sales channel ids cross-checked against docs/HANDOFF_VENDOR_STOREFRONTS.md.
BRAND_REGISTRY: dict[str, dict] = {
    "wisdom": {
        "name": "Wisdom",
        "supplier": "Wisdom Playground",
        "country": "China",
        "description": "Playground & Furniture Equipment",
        "color": "#8003FF",
        "sales_channel_id": "sc_01KNKTHC0B7KFEDSZ3NNM49JQW",
        "src_collection": "products_wisdom",
        "src_categories": "product_categories_wisdom",
        "id_strategy": "item_code",  # doc_id is item_code
    },
    "vinci": {
        "name": "Vinci Play",
        "supplier": "Vinci Play sp. z o.o.",
        "country": "Poland",
        "description": "Playground Equipment",
        "color": "#970260",
        "domains": ["vinci-play.com"],
        "sales_channel_id": "sc_01KNKTHC77716EPCE3E2BKAMQP",
        "src_collection": "products_vinci",
        "src_categories": "product_categories_vinci",
        "id_strategy": "item_code_from_field",  # doc_id is series-itemcode, item_code is the field
    },
    "vortex": {
        "name": "Vortex Aquatics",
        "supplier": "Vortex International",
        "country": "Canada",
        "description": "Splashpads, Waterslides & Aquatic Play Structures",
        "color": "#153cba",
        "domains": ["vortex-intl.com", "vortexaquatic.com"],
        "sales_channel_id": "sc_01KPRY1T8HZJ57020JPZVGAKZK",
        "src_collection": "products_vortex",
        "src_categories": "product_categories_vortex",
        "id_strategy": "item_code",
    },
}

CATALOG_URL_TEMPLATE = "https://catalogs.leka.studio/{slug}"


def _normalize_handle(slug: str, item_code: str) -> str:
    """Medusa-style handle: '{slug}-{item_code_lower}'.

    Strips whitespace and forces lowercase. Spaces in item_code become hyphens
    to keep the handle URL-safe.
    """
    code = (item_code or "").strip().lower().replace(" ", "-")
    return f"{slug}-{code}"


def _map_product(slug: str, src_doc_id: str, src: dict, id_strategy: str) -> tuple[str, dict]:
    """Map a leka product doc → (handle, vendors-schema product doc)."""
    if id_strategy == "item_code_from_field":
        item_code = src.get("item_code") or src_doc_id
    else:
        item_code = src.get("item_code") or src_doc_id

    handle = _normalize_handle(slug, item_code)

    # Copy known fields 1:1; drop `brand` (now encoded in path).
    out = {k: v for k, v in src.items() if k != "brand"}
    out["handle"] = handle
    out["slug"] = slug
    out["item_code"] = item_code

    # Preserve createdAt; refresh updatedAt.
    if "created_at" in out and "createdAt" not in out:
        out["createdAt"] = out.pop("created_at")
    out.setdefault("createdAt", firestore.SERVER_TIMESTAMP)
    out["updatedAt"] = firestore.SERVER_TIMESTAMP
    out.pop("updated_at", None)

    out.setdefault("status", "active")
    return handle, out


def _iter_collection(db: firestore.Client, name: str) -> Iterable[firestore.DocumentSnapshot]:
    return db.collection(name).stream()


def migrate_brand(slug: str, dry_run: bool) -> dict:
    """Migrate one brand. Returns counters."""
    cfg = BRAND_REGISTRY[slug]
    src = firestore.Client(project=PROJECT, database=SRC_DB)
    dst = firestore.Client(project=PROJECT, database=DST_DB)

    counters = {"products": 0, "categories": 0, "quotations": 0}

    # --- products ---
    log.info("[%s] reading %s from %s", slug, cfg["src_collection"], SRC_DB)
    product_writes: list[tuple[str, dict]] = []
    for doc in _iter_collection(src, cfg["src_collection"]):
        handle, mapped = _map_product(slug, doc.id, doc.to_dict() or {}, cfg["id_strategy"])
        product_writes.append((handle, mapped))
    counters["products"] = len(product_writes)
    log.info("[%s] %d products mapped", slug, counters["products"])

    if not dry_run and product_writes:
        # Write into vendors/{slug}/products
        target_path = f"vendors/{slug}/products"
        log.info("[%s] writing %d products → %s (db=%s)", slug, len(product_writes), target_path, DST_DB)
        batch_write(dst, target_path, product_writes)

    # --- categories ---
    log.info("[%s] reading %s", slug, cfg["src_categories"])
    cat_writes: list[tuple[str, dict]] = []
    for doc in _iter_collection(src, cfg["src_categories"]):
        data = doc.to_dict() or {}
        data.pop("brand", None)
        data["updatedAt"] = firestore.SERVER_TIMESTAMP
        cat_writes.append((doc.id, data))
    counters["categories"] = len(cat_writes)
    log.info("[%s] %d categories mapped", slug, counters["categories"])

    if not dry_run and cat_writes:
        batch_write(dst, f"vendors/{slug}/product_categories", cat_writes)

    # --- quotations (global collection filtered by brand field) ---
    log.info("[%s] reading quotations where brand=%s", slug, slug)
    quote_writes: list[tuple[str, dict]] = []
    # Vinci was historically referenced as 'vinci'; same slug. Wisdom is 'wisdom'. Vortex 'vortex'.
    for doc in src.collection("quotations").where("brand", "==", slug).stream():
        data = doc.to_dict() or {}
        data.pop("brand", None)
        data.setdefault("createdAt", firestore.SERVER_TIMESTAMP)
        data["updatedAt"] = firestore.SERVER_TIMESTAMP
        quote_writes.append((doc.id, data))
    counters["quotations"] = len(quote_writes)
    log.info("[%s] %d quotations mapped", slug, counters["quotations"])

    if not dry_run and quote_writes:
        batch_write(dst, f"vendors/{slug}/quotations", quote_writes)

    # --- vendor root doc ---
    root_payload = {
        "slug": slug,
        "name": cfg["name"],
        "supplier": cfg["supplier"],
        "country": cfg["country"],
        "description": cfg["description"],
        "color": cfg["color"],
        "domains": cfg.get("domains", []),
        "sales_channel_id": cfg["sales_channel_id"],
        "catalog_url": CATALOG_URL_TEMPLATE.format(slug=slug),
        "product_count": counters["products"],
        "status": "active",
        "last_import": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    log.info("[%s] vendor root payload: name=%s, products=%d", slug, root_payload["name"], counters["products"])
    if not dry_run:
        dst.collection("vendors").document(slug).set(root_payload, merge=True)

    return counters


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True, help="Brand slug or 'all' (one of: %s, all)" % ", ".join(BRAND_REGISTRY))
    ap.add_argument("--dry-run", action="store_true", help="Read + map only; no writes.")
    args = ap.parse_args()

    brands = list(BRAND_REGISTRY) if args.brand == "all" else [args.brand]
    for b in brands:
        if b not in BRAND_REGISTRY:
            log.error("unknown brand: %s", b)
            return 2

    mode = "DRY-RUN" if args.dry_run else "WRITE"
    log.info("=== migrate_leka_to_vendors mode=%s brands=%s ===", mode, brands)

    totals = {"products": 0, "categories": 0, "quotations": 0}
    for slug in brands:
        c = migrate_brand(slug, args.dry_run)
        for k, v in c.items():
            totals[k] += v

    log.info("=== totals: %s ===", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
