"""
create_r2_missing_products.py — Phase 2 of the Dulwich Rev2 pipeline.

Reads the R2 → catalog mapping report (produced in leka-projects by
src/map_r2_to_catalog.py) and creates the products that don't yet exist in the
Leka catalog / Medusa, as DRAFT with price TBC, preserving the Notion vendor URL.

Missing R2 codes fall into two vendor families:
  - epdm-graphics article codes (E1-02A-20, G2-26A-57UV ...) -> brand "4soft",
    Firestore products_4soft, Medusa sales channel "4soft".
  - UBX climbing codes (TPF-95xx)                            -> brand "ubx",
    Firestore products_ubx, Medusa sales channel "UBX" (get-or-create).

For each missing code we:
  1. Upsert a Firestore doc (id = code) into the brand collection (idempotent).
  2. Create a Medusa draft product with one variant (sku = code, no price),
     metadata.source_url + supplier_url = vendor URL (so the proposal render
     picks it up), attached to the brand sales channel. Idempotent via handle.

Dry-run by default; pass --write to apply.

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD (Medusa) and ADC
(Firestore). Mapping report path defaults to the leka-projects worktree but is
overridable with --mapping.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROJECT = "ai-agents-go"
CATALOG_DB = "leka-product-catalogs"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"

SC_4SOFT = "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y"   # existing "4soft" sales channel

# brand_guess -> (firestore collection, medusa sales channel resolver)
BRAND_COLLECTION = {"epdm-graphics": "products_4soft", "ubx": "products_ubx",
                    "unknown": "products_misc"}


def handle_for(brand: str, code: str) -> str:
    slug = code.lower().replace(" ", "-").replace("/", "-")
    return f"{brand}-{slug}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    default_mapping = (
        r"C:\Users\Eukrit\OneDrive\Claude Code\NUC11\leka-projects\.claude"
        r"\worktrees\goofy-snyder-ab838e\docs\reports\_data"
        r"\dulwich-singapore-r2-mapping.json")
    ap.add_argument("--mapping", default=default_mapping)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    report = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    missing = report["missing_codes"]
    print(f"== Phase 2: {len(missing)} missing R2 codes to create "
          f"({'WRITE' if args.write else 'DRY-RUN'}) ==")

    # group by brand
    from collections import Counter
    by_brand = Counter(m["brand_guess"] for m in missing.values())
    print("   by brand:", dict(by_brand))

    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    client = MedusaImporter(base_url=BACKEND)

    db = None
    if args.write:
        from google.cloud import firestore
        db = firestore.Client(project=PROJECT, database=CATALOG_DB)

    # resolve sales channels (create UBX if needed)
    sc_cache: dict[str, str] = {"epdm-graphics": SC_4SOFT}
    def sales_channel(brand_guess: str) -> str:
        if brand_guess in sc_cache:
            return sc_cache[brand_guess]
        name = {"ubx": "UBX"}.get(brand_guess, brand_guess or "Misc")
        scid = client.get_or_create_sales_channel(name, f"{name} (auto, Dulwich R2)") \
            if args.write else f"<{name}-SC>"
        sc_cache[brand_guess] = scid
        return scid

    created_fs = created_med = skipped_med = errors = 0
    for code, meta in sorted(missing.items()):
        bg = meta["brand_guess"]
        brand = {"epdm-graphics": "4soft", "ubx": "ubx"}.get(bg, bg or "misc")
        coll = BRAND_COLLECTION.get(bg, "products_misc")
        name = meta.get("name") or code
        url = meta.get("vendor_url")
        handle = handle_for(brand, code)
        scid = sales_channel(bg)

        # --- Firestore upsert ---
        fs_doc = {
            "item_code": code,
            "brand": brand,
            "description": name,
            "name": name,
            "website_url": url,
            "source_url": url,
            "status": "draft",
            "catalog_source": "notion-r2-dulwich",
            "source": "notion:R2:36f82cea8bb08003b63af7179e9378bc",
            "pricing": {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.write:
            ref = db.collection(coll).document(code)
            if not ref.get().exists:
                fs_doc["created_at"] = datetime.now(timezone.utc).isoformat()
            ref.set(fs_doc, merge=True)
            created_fs += 1

        # --- Medusa draft product ---
        metadata = {
            "source_url": url, "supplier_url": url,
            "supplier": meta.get("supplier") or brand,
            "legacy_sku": code, "vendor": brand,
            "dulwich_r2": True,
        }
        if args.write:
            try:
                if client.find_product_by_handle(handle):
                    skipped_med += 1
                else:
                    client.create_product(
                        title=name, handle=handle, description=name,
                        status="draft", metadata=metadata,
                        variant={"title": "Default", "sku": code,
                                 "manage_inventory": False, "prices": []},
                        sales_channel_ids=[scid])
                    created_med += 1
            except Exception as e:
                errors += 1
                body = getattr(getattr(e, "response", None), "text", "") or str(e)
                print(f"   ! medusa create {code}: {body[:300]}")
        else:
            print(f"   [dry] {code:14} brand={brand:6} sc={bg:13} "
                  f"handle={handle}  url={'Y' if url else '-'}")

    print(f"\n== done: firestore_upserts={created_fs} medusa_created={created_med} "
          f"medusa_skipped_existing={skipped_med} errors={errors} ==")
    if not args.write:
        print("   (dry-run — re-run with --write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
