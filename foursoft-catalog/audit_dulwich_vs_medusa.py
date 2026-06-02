"""Compare Dulwich R2 proposal (Medusa draft order) QUOTED SGD unit prices
against the live Medusa CATALOG SGD variant prices. Read-only.

Draft order #10 (order_01KSTN74NRPQ3DGETVHERQ1Z2G) is the curated Dulwich R2
proposal (Proposal sales channel, SGD region). Each line carries its own
unit_price which OVERRIDES the variant's catalog price, so we must compare
them explicitly. Output: foursoft-catalog/data/dulwich_r2_vs_medusa.csv
"""
from __future__ import annotations
import csv, os, re
from pathlib import Path
import requests

B = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
DO_ID = "order_01KSTN74NRPQ3DGETVHERQ1Z2G"
OUT = Path(__file__).resolve().parent.parent / "foursoft-catalog" / "data" / "dulwich_r2_vs_medusa.csv"
TIMEOUT = 60


def is_epdm(code):
    return bool(re.match(r"^[A-Z]\d-\d{2}[A-Z]-\d{2,3}", (code or "").upper()))


def auth():
    return requests.post(B + "/auth/user/emailpass", json={
        "email": os.environ["LEKA_MEDUSA_ADMIN_EMAIL"],
        "password": os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]}, timeout=TIMEOUT).json()["token"]


def main():
    tok = auth()
    H = {"Authorization": "Bearer " + tok}

    # 1. Pull the draft order with line items (variant + unit_price + metadata).
    r = requests.get(f"{B}/admin/draft-orders/{DO_ID}", params={
        "fields": "id,display_id,currency_code,region_id,"
                  "items.id,items.title,items.quantity,items.unit_price,"
                  "items.variant_id,items.product_id,items.metadata,items.variant_sku"},
        headers=H, timeout=TIMEOUT)
    r.raise_for_status()
    o = r.json()["draft_order"]
    items = o.get("items") or []
    ccy = o.get("currency_code")
    print(f"Draft #{o.get('display_id')} ccy={ccy} items={len(items)}")

    # 2. Build variant_id -> catalog SGD price (from the variant's own prices).
    #    Query each variant's prices via /admin/products variant lookup in bulk.
    variant_ids = sorted({it["variant_id"] for it in items if it.get("variant_id")})
    cat_sgd = {}
    cat_ccys = {}  # variant_id -> set of currency codes priced
    # Pull all products with variant prices once, index by variant id.
    off = 0
    while True:
        pr = requests.get(f"{B}/admin/products", params={"limit": 200, "offset": off,
            "fields": "id,variants.id,variants.sku,variants.prices.amount,variants.prices.currency_code"},
            headers=H, timeout=TIMEOUT).json()
        b = pr.get("products", [])
        if not b:
            break
        for p in b:
            for v in p.get("variants") or []:
                ccys = {x.get("currency_code") for x in (v.get("prices") or [])}
                cat_ccys[v["id"]] = ccys
                sgd = next((x["amount"] for x in (v.get("prices") or [])
                            if x.get("currency_code") == "sgd"), None)
                if sgd is not None:
                    cat_sgd[v["id"]] = round(sgd / 100.0, 2)
        if len(b) < 200:
            break
        off += 200
    print(f"Indexed catalog SGD for {len(cat_sgd)} variants")

    rows = []
    for it in items:
        md = it.get("metadata") or {}
        code = md.get("product_code") or it.get("variant_sku")
        # Medusa draft-order line unit_price is in MINOR units (cents).
        quoted = round((it.get("unit_price") or 0) / 100.0, 2)
        vid = it.get("variant_id")
        catalog = cat_sgd.get(vid)
        match = ""
        if catalog is None:
            match = "no_catalog_price"
        elif abs(quoted - catalog) <= max(0.5, 0.01 * catalog):
            match = "MATCH"
        else:
            match = "MISMATCH"
        rows.append({
            "code": code,
            "name": (it.get("title") or "")[:50],
            "type": "4soft-EPDM" if is_epdm(code) else "other",
            "qty": it.get("quantity"),
            "quoted_sgd": quoted,
            "catalog_sgd": catalog,
            "delta": (round(quoted - catalog, 2) if catalog is not None else None),
            "match": match,
            "retail_status": md.get("retail_status"),
            "variant_id": vid,
        })

    rows.sort(key=lambda r: (r["type"], r["match"], r["code"] or ""))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    by_match = Counter(r["match"] for r in rows)
    epdm = [r for r in rows if r["type"] == "4soft-EPDM"]
    other = [r for r in rows if r["type"] == "other"]
    print("\n=== overall match ===", dict(by_match))
    print(f"4soft-EPDM lines: {len(epdm)}  | other: {len(other)}")
    print("4soft-EPDM match:", dict(Counter(r["match"] for r in epdm)))
    print("other match:", dict(Counter(r["match"] for r in other)))
    print("\n=== MISMATCHES ===")
    for r in [x for x in rows if x["match"] == "MISMATCH"]:
        print(f"  {r['code']:18} {r['type']:11} quoted={r['quoted_sgd']:>10} catalog={r['catalog_sgd']:>10} d={r['delta']:>10}  {r['name']}")
    print("\n=== 'no_catalog_price' lines (variant has these catalog currencies?) ===")
    for r in [x for x in rows if x["match"] == "no_catalog_price"]:
        ccys = sorted(cat_ccys.get(r["variant_id"]) or [])
        print(f"  {r['code']:18} quoted_sgd={r['quoted_sgd']:>9}  catalog_ccys={ccys}  {r['name']}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
