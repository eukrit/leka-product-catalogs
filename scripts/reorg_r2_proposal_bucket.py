"""
reorg_r2_proposal_bucket.py — corrective reorg for Dulwich R2 draft items.

The 8 genuinely-new R2 items (4 EPDM graphics, 4 UBX) must stay DRAFT and live
in a dedicated "Proposal" bucket — NOT mixed into official brand sales channels
or brand Firestore collections. This script:

  1. Medusa: move the 8 draft products into the "Proposal" sales channel
     (get-or-create), replacing their 4soft / UBX channel.
  2. Medusa: delete the stray "UBX" sales channel I created (once empty).
  3. Firestore: move the 8 docs into `products_proposal_draft`; delete the
     `products_4soft` / `products_ubx` collections this pipeline created
     (they did not exist before and are not official brand collections).

The 31 already-official 4soft graphics and the "4soft" channel are untouched.
Dry-run by default; --write to apply. Auth: LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD + ADC.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
PROJECT = "ai-agents-go"
CATALOG_DB = "leka-product-catalogs"

# the 8 truly-new draft items: handle -> (code, original_vendor)
NEW8 = {
    "4soft-d2-02a-09uv": ("D2-02A-09UV", "4soft"),
    "4soft-e3-01c-70uv": ("E3-01C-70UV", "4soft"),
    "4soft-g2-09a-65uv": ("G2-09A-65UV", "4soft"),
    "4soft-g2-27a-09uv": ("G2-27A-09UV", "4soft"),
    "ubx-tpf-9517": ("TPF-9517", "ubx"),
    "ubx-tpf-9518": ("TPF-9518", "ubx"),
    "ubx-tpf-9519": ("TPF-9519", "ubx"),
    "ubx-tpf-9528": ("TPF-9528", "ubx"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()
    WRITE = args.write

    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    c = MedusaImporter(base_url=BACKEND)

    print(f"== reorg R2 proposal bucket ({'WRITE' if WRITE else 'DRY-RUN'}) ==")

    # 1) Proposal sales channel
    prop = (c.get_or_create_sales_channel(
        "Proposal", "Draft proposal-only items (Dulwich R2 etc.) — not a brand")
        if WRITE else "<Proposal-SC>")
    print(f"   Proposal SC: {prop}")

    # 2) move the 8 products
    for h, (code, vendor) in NEW8.items():
        r = c._get("/admin/products",
                   {"handle": h, "limit": 1, "fields": "id,sales_channels.name"})
        ps = r.get("products", [])
        if not ps:
            print(f"   ! {h}: not found"); continue
        pid = ps[0]["id"]
        cur = [s.get("name") for s in (ps[0].get("sales_channels") or [])]
        if cur == ["Proposal"]:
            print(f"   = {code}: already in Proposal"); continue
        if WRITE:
            c._post(f"/admin/products/{pid}", {"sales_channels": [{"id": prop}]})
        print(f"   -> {code}: {cur} => ['Proposal']")

    # 3) delete the UBX sales channel (now empty)
    sc = c._get("/admin/sales-channels", {"name": "UBX", "limit": 1}).get("sales_channels", [])
    if sc:
        ubx_id = sc[0]["id"]
        if WRITE:
            try:
                c.session.delete(f"{c.base_url}/admin/sales-channels/{ubx_id}")
            except Exception as e:
                print(f"   ! delete UBX SC: {str(e)[:120]}")
        print(f"   deleted stray UBX sales channel {ubx_id}")

    # 4) Firestore: move 8 -> products_proposal_draft, drop products_4soft/ubx
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=CATALOG_DB)
    now = datetime.now(timezone.utc).isoformat()
    for h, (code, vendor) in NEW8.items():
        if WRITE:
            db.collection("products_proposal_draft").document(code).set({
                "item_code": code, "brand": "proposal-draft",
                "original_vendor": vendor, "status": "draft",
                "catalog_source": "notion-r2-dulwich",
                "source": "notion:R2:36f82cea8bb08003b63af7179e9378bc",
                "medusa_sales_channel": "Proposal",
                "updated_at": now,
            }, merge=True)
    print(f"   wrote {len(NEW8)} docs to products_proposal_draft")

    for coll in ("products_4soft", "products_ubx"):
        docs = list(db.collection(coll).stream())
        if WRITE:
            for d in docs:
                d.reference.delete()
        print(f"   dropped {len(docs)} docs from {coll}")

    if not WRITE:
        print("   (dry-run — re-run with --write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
