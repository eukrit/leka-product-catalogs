"""
update_pricing.py — Backfill and keep-current retail pricing on Wisdom products.

Reads every document in `products_wisdom` (Firestore, leka-product-catalogs DB),
computes landed cost + retail price using shared/wisdom_pricing.py, writes the
result back to Firestore, and pushes the THB retail price to Medusa.

Formula (defined in shared/wisdom_pricing.py):
  landed_thb  = fob_usd × usd_thb × (1 + 0.07)   # 7% import duty
  retail_thb  = landed_thb / (1 - 0.50)            # 50% gross margin

Usage:
    python wisdom-catalog/update_pricing.py
    python wisdom-catalog/update_pricing.py --dry-run
    python wisdom-catalog/update_pricing.py --skip-medusa
    python wisdom-catalog/update_pricing.py --usd-thb 34.5
"""
import os
import sys
import argparse
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.wisdom_pricing import (
    compute_wisdom_retail,
    compute_wisdom_retail_sg,
    pricing_metadata,
    pricing_metadata_sg,
    get_usd_thb,
    get_sgd_thb,
    get_usd_sgd,
    IMPORT_DUTY_RATE,
    THAI_VAT_RATE,
    GROSS_MARGIN,
)
from shared.medusa_importer import MedusaImporter

from google.cloud import firestore

GCP_PROJECT = "ai-agents-go"
CATALOG_DB = "leka-product-catalogs"
COLLECTION = "products_wisdom"
BATCH_SIZE = 400

# Post-rebrand sales channel — Wisdom products live under "Leka Project" in
# Medusa. Variant SKUs are now LP-XXXXXXXX; the original Wisdom item_code is
# preserved in `variants[].metadata.legacy_sku`.
LEKA_PROJECT_SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"


def _firestore_client() -> firestore.Client:
    sa_candidates = [
        r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code"
        r"\GCP Credentials\ai-agents-go-claude.json",
        r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code"
        r"\GCP Credentials\ai-agents-go-claude.json",
    ]
    for p in sa_candidates:
        if os.path.exists(p) and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = p
            break
    return firestore.Client(project=GCP_PROJECT, database=CATALOG_DB)


def update_firestore(db, rows: list[dict], price_date: str, dry_run: bool) -> int:
    """Batch-update pricing sub-fields on Wisdom Firestore documents.

    When a row carries a "sg_update" key (populated by --sg-channel), its
    pricing.sg.* sub-map is merged into the same batch update so TH + SG
    fields land in a single Firestore write per SKU.
    """
    batch = db.batch()
    count = 0
    for item in rows:
        doc_ref = db.collection(COLLECTION).document(item["item_code"])
        pricing = item["pricing_update"]
        sg_update = item.get("sg_update") or {}
        if dry_run:
            print(f"  [dry] {item['item_code']:12s}  "
                  f"FOB ${item['fob_usd']:>7.2f}  "
                  f"landed ฿{pricing['landed_thb']:>9,.0f}  "
                  f"retail ฿{pricing['retail_thb']:>9,.0f}")
            continue
        update_doc = {
            "pricing.landed_thb":       pricing["landed_thb"],
            "pricing.retail_thb":       pricing["retail_thb"],
            "pricing.retail_usd":       pricing["retail_usd"],
            "pricing.duty_thb":         pricing["duty_thb"],
            "pricing.vat_thb":          pricing["vat_thb"],
            "pricing.usd_thb":          pricing["usd_thb"],
            "pricing.import_duty_rate": pricing["import_duty_rate"],
            "pricing.thai_vat_rate":    pricing["thai_vat_rate"],
            "pricing.gross_margin":     pricing["gross_margin"],
            "pricing.price_date":       price_date,
        }
        update_doc.update(sg_update)
        batch.update(doc_ref, update_doc)
        count += 1
        if count % BATCH_SIZE == 0:
            batch.commit()
            batch = db.batch()
            print(f"  Committed {count} Firestore updates…")

    if not dry_run and count % BATCH_SIZE != 0:
        batch.commit()
    return count


def update_medusa(client: MedusaImporter, rows: list[dict], dry_run: bool) -> tuple[int, int]:
    """Push THB retail price to each Wisdom variant in Medusa.

    Post-rebrand strategy: build a single index from the Leka Project sales
    channel keyed by `variants[].metadata.legacy_sku` (the original Wisdom
    item_code), then look each row up in O(1). Falls back to current SKU
    match if a product was added after the rebrand.
    """
    if dry_run:
        for item in rows:
            retail_thb_cents = int(round(item["pricing_update"]["retail_thb"] * 100))
            retail_usd_cents = int(round(item["pricing_update"]["retail_usd"] * 100))
            print(f"  [dry-medusa] {item['item_code']:12s}  "
                  f"THB {retail_thb_cents / 100:,.0f}  "
                  f"USD {retail_usd_cents / 100:,.2f}")
        return 0, 0

    print("  Indexing Leka Project sales channel by legacy_sku…")
    sku_index = client.build_legacy_sku_index(LEKA_PROJECT_SC_ID)
    print(f"  Indexed {len(sku_index)} variants")

    updated = 0
    skipped = 0
    not_found = []
    for item in rows:
        retail_thb_cents = int(round(item["pricing_update"]["retail_thb"] * 100))
        fob_usd_cents    = int(round(item["fob_usd"] * 100))
        code = item["item_code"]

        product_id, variant_id = sku_index.get(code, (None, None))
        if not product_id:
            # Last-resort: direct SKU lookup (handles late-arrival products)
            product_id, variant_id = client.get_variant_by_sku(code)
        if not product_id:
            not_found.append(code)
            skipped += 1
            continue

        try:
            client.update_variant_prices(product_id, variant_id, [
                {"amount": fob_usd_cents,    "currency_code": "usd"},
                {"amount": retail_thb_cents, "currency_code": "thb"},
            ])
            updated += 1
            if updated % 100 == 0:
                print(f"  …{updated} variants priced")
            time.sleep(0.05)
        except Exception as e:
            print(f"  Medusa error for {code}: {e}")
            skipped += 1

    if not_found:
        print(f"  Not found in Leka Project SC: {len(not_found)} codes "
              f"(first 5: {not_found[:5]})")

    return updated, skipped


def main():
    parser = argparse.ArgumentParser(description="Update Wisdom retail pricing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print computed prices without writing anything")
    parser.add_argument("--skip-medusa", action="store_true",
                        help="Update Firestore only, skip Medusa")
    parser.add_argument("--usd-thb", type=float, default=None,
                        help="Override USD→THB rate (default: live lookup or 35.0)")
    parser.add_argument("--medusa-url",
                        default=os.environ.get("MEDUSA_BACKEND_URL", "http://localhost:9000"))
    parser.add_argument("--api-key",
                        default=os.environ.get("MEDUSA_ADMIN_API_KEY", ""))
    parser.add_argument("--sg-channel", action="store_true",
                        help="Also compute Singapore-channel landed cost "
                             "(china_to_singapore route, 9%% SG GST, 0%% duty) "
                             "and write pricing.sg.* fields. Prints an "
                             "[sg-compare] line per SKU showing old vs new "
                             "retail_sgd. No Medusa SG push this round.")
    args = parser.parse_args()

    usd_thb = args.usd_thb or get_usd_thb()
    price_date = date.today().isoformat()

    print(f"Wisdom / Leka Project pricing update — {price_date}")
    print(f"  Rate:         USD/THB {usd_thb:.4f}")
    print(f"  Import duty:  {IMPORT_DUTY_RATE * 100:.0f}%  (on CIF)")
    print(f"  Thai VAT:     {THAI_VAT_RATE * 100:.0f}%  (on CIF + duty)")
    print(f"  Gross margin: {GROSS_MARGIN * 100:.0f}%  (retail = landed / 0.50)")
    print(f"  Formula:      cif = FOB × {usd_thb:.2f};  "
          f"landed = cif × {(1 + IMPORT_DUTY_RATE) * (1 + THAI_VAT_RATE):.4f};  "
          f"retail = landed × {1 / (1 - GROSS_MARGIN):.2f}")
    sgd_thb = usd_sgd = None
    if args.sg_channel:
        sgd_thb = get_sgd_thb()
        usd_sgd = get_usd_sgd()
        print(f"  SG channel:   ON — china_to_singapore route, 9% GST, "
              f"USD/SGD {usd_sgd:.4f}  SGD/THB {sgd_thb:.4f}")
    print()

    # --- Load Wisdom products from Firestore ---
    db = _firestore_client()
    print("Loading products_wisdom from Firestore…")
    docs = list(db.collection(COLLECTION).stream())
    print(f"  Loaded {len(docs)} documents\n")

    # --- Compute pricing ---
    rows = []
    no_fob = 0
    sg_compare_lines: list[str] = []
    for doc in docs:
        d = doc.to_dict() or {}
        item_code = d.get("item_code") or doc.id
        pr = d.get("pricing") or {}
        fob = pr.get("fob_usd") or pr.get("fob_usd_us")
        if not fob:
            no_fob += 1
            continue
        result = compute_wisdom_retail(fob, usd_thb)
        if not result:
            no_fob += 1
            continue
        result.item_code = item_code
        row = {
            "item_code": item_code,
            "fob_usd": fob,
            "pricing_update": pricing_metadata(result, price_date),
        }
        if args.sg_channel:
            # Reuse CBM extraction the TH path already computes implicitly
            # via dimensions on the doc.
            cbm = 0.0
            kg = float(d.get("weight_kg") or 0.0)
            dims = d.get("dimensions") or {}
            try:
                l_cm = float(dims.get("length_cm") or 0)
                w_cm = float(dims.get("width_cm") or 0)
                h_cm = float(dims.get("height_cm") or 0)
                if l_cm > 0 and w_cm > 0 and h_cm > 0:
                    cbm = round(l_cm * w_cm * h_cm / 1_000_000.0 * 0.15, 4)
            except (TypeError, ValueError):
                pass
            sg_row = compute_wisdom_retail_sg(
                fob, cbm=cbm, kg=kg,
                usd_sgd=usd_sgd, sgd_thb=sgd_thb,
            )
            if sg_row:
                sg_row.item_code = item_code
                row["sg_update"] = pricing_metadata_sg(sg_row, price_date)
                old_sgd = result.retail_sgd
                new_sgd = sg_row.retail_sgd
                delta = (new_sgd - old_sgd) / old_sgd * 100 if old_sgd else 0.0
                sg_compare_lines.append(
                    f"[sg-compare] {item_code:14s}  "
                    f"old_sgd ${old_sgd:>8.2f}  "
                    f"new_sgd ${new_sgd:>8.2f}  "
                    f"Δ {delta:+6.1f}%  "
                    f"({sg_row.cbm_method})"
                )
        rows.append(row)

    print(f"  Priced: {len(rows)}  |  No FOB: {no_fob}\n")

    if args.sg_channel and sg_compare_lines:
        print(f"--- SG channel comparison (first 20 of {len(sg_compare_lines)}) ---")
        for line in sg_compare_lines[:20]:
            print(f"  {line}")
        print()

    if not rows:
        print("Nothing to update.")
        return

    # --- Sample preview ---
    print("Sample (first 5):")
    for r in rows[:5]:
        p = r["pricing_update"]
        print(f"  {r['item_code']:12s}  FOB ${r['fob_usd']:>7.2f}  "
              f"landed ฿{p['landed_thb']:>9,.0f}  retail ฿{p['retail_thb']:>9,.0f}")
    print()

    if args.dry_run:
        print("=== DRY RUN — printing all rows ===\n")
        update_firestore(db, rows, price_date, dry_run=True)
        if not args.skip_medusa:
            print()
            update_medusa(None, rows, dry_run=True)
        return

    # --- Write Firestore ---
    print("Updating Firestore…")
    fs_count = update_firestore(db, rows, price_date, dry_run=False)
    print(f"  Firestore: {fs_count} documents updated\n")

    # --- Update Medusa ---
    if not args.skip_medusa:
        print("Updating Medusa…")
        client = MedusaImporter(base_url=args.medusa_url, api_key=args.api_key)
        m_updated, m_skipped = update_medusa(client, rows, dry_run=False)
        print(f"  Medusa: {m_updated} variants updated, {m_skipped} skipped/not-found\n")

    print(f"Done. {len(rows)} Wisdom products priced at ฿ retail.")


if __name__ == "__main__":
    main()
