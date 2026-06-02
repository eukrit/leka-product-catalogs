"""4soft pricing AUDIT (read-only) — live Medusa vs script-computed (sea-LCL vs air).

Pulls every product/variant in the 4soft Medusa sales channel (id, status,
sku, all-currency prices), joins against the two committed landed CSVs:
  * pricelist_2025-03-01_landed.csv            -> sea-LCL basis (the LIVE basis)
  * pricelist_2025-03-01_landed_AIR-DRYRUN-mid.csv -> air-freight (dry-run, NOT live)
and against Firestore vendors/4soft/products (the price the sync reads from).

Writes foursoft-catalog/data/4soft_pricing_audit.csv with one row per pricelist
SKU + Medusa presence/status/live-SGD + sea & air computed SGD + flags.
Makes NO changes anywhere. Auth: GOOGLE_APPLICATION_CREDENTIALS + Medusa admin
creds in env (LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD).
"""
from __future__ import annotations
import csv, json, os, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "foursoft-catalog" / "data"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SALES_CHANNEL = "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y"
TIMEOUT = 60
OUT_CSV = DATA / "4soft_pricing_audit.csv"
OUT_JSON = DATA / "4soft_pricing_audit_summary.json"
TBC_KNOWN = {"D2-02A-09UV", "G2-27A-09UV"}


def norm(s):
    return (s or "").strip().upper()


def auth():
    email = os.environ["LEKA_MEDUSA_ADMIN_EMAIL"]
    pw = os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["token"]


def headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def load_csv(name, key="item_code"):
    out = {}
    with (DATA / name).open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[norm(row[key])] = row
    return out


def fetch_medusa(tok):
    """Index 4soft sales-channel variants -> dict keyed by norm(sku)."""
    by_code = {}
    offset = 0
    n_products = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/products", params={
            "sales_channel_id[]": SALES_CHANNEL, "limit": 200, "offset": offset,
            "fields": "id,handle,status,variants.id,variants.sku,"
                      "variants.metadata.legacy_sku,variants.prices.amount,"
                      "variants.prices.currency_code"},
            headers=headers(tok), timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            break
        for p in batch:
            n_products += 1
            for v in p.get("variants") or []:
                prices = {pp.get("currency_code"): pp.get("amount")
                          for pp in (v.get("prices") or [])}
                rec = {
                    "product_id": p["id"], "handle": p.get("handle"),
                    "status": p.get("status"), "variant_id": v["id"],
                    "sku": v.get("sku"),
                    "sgd": (prices.get("sgd") or 0) / 100.0 if prices.get("sgd") is not None else None,
                    "thb": (prices.get("thb") or 0) / 100.0 if prices.get("thb") is not None else None,
                    "usd": (prices.get("usd") or 0) / 100.0 if prices.get("usd") is not None else None,
                    "eur": (prices.get("eur") or 0) / 100.0 if prices.get("eur") is not None else None,
                    "n_prices": len(prices),
                }
                for k in (v.get("sku"), (v.get("metadata") or {}).get("legacy_sku")):
                    if k:
                        by_code.setdefault(norm(k), rec)
        if len(batch) < 200:
            break
        offset += 200
    return by_code, n_products


def fetch_firestore():
    from google.cloud import firestore
    db = firestore.Client(project="ai-agents-go", database="vendors")
    docs = db.collection("vendors").document("4soft").collection("products").stream()
    out = {}
    for d in docs:
        x = d.to_dict() or {}
        code = x.get("item_code") or d.id
        pr = x.get("pricing") or {}
        out[norm(code)] = {
            "retail_sgd": pr.get("retail_sgd"), "retail_thb": pr.get("retail_thb"),
            "calculated_at": pr.get("calculated_at"),
            "cbm_method": pr.get("cbm_method"),
            "fx": (pr.get("fx_snapshot") or {}),
        }
    return out


def main():
    tok = auth()
    print("Pulling live Medusa 4soft channel ...", file=sys.stderr)
    med, n_med_products = fetch_medusa(tok)
    print(f"  {n_med_products} products, {len(med)} variant-keys", file=sys.stderr)
    print("Pulling Firestore vendors/4soft/products ...", file=sys.stderr)
    fs = fetch_firestore()
    print(f"  {len(fs)} Firestore docs", file=sys.stderr)

    sea = load_csv("pricelist_2025-03-01_landed.csv")
    air = load_csv("pricelist_2025-03-01_landed_AIR-DRYRUN-mid.csv")
    base = load_csv("pricelist_2025-03-01.csv", key="code")  # raw parsed (type/list_eur)

    rows = []
    for code, b in base.items():
        s = sea.get(code, {})
        a = air.get(code, {})
        m = med.get(code)
        f = fs.get(code, {})

        def num(d, k):
            try:
                return round(float(d[k]), 2)
            except Exception:
                return None

        sea_sgd = num(s, "retail_sgd")
        air_sgd = num(a, "retail_sgd")
        live_sgd = round(m["sgd"], 2) if (m and m.get("sgd") is not None) else None
        fs_sgd = round(float(f["retail_sgd"]), 2) if f.get("retail_sgd") is not None else None

        # Classify live SGD against the two bases.
        def close(x, y):
            return x is not None and y is not None and abs(x - y) <= max(1.0, 0.01 * y)

        if m is None:
            price_state = "not_in_medusa"
        elif live_sgd is None or live_sgd == 0:
            price_state = "zero_or_missing"
        elif close(live_sgd, sea_sgd):
            price_state = "live=sea-LCL"
        elif close(live_sgd, air_sgd):
            price_state = "live=air"
        else:
            price_state = "live=other"

        rows.append({
            "item_code": code,
            "type": b.get("dimension"),
            "product_group": b.get("product_group"),
            "name": (b.get("name") or "")[:60],
            "list_eur": num(b, "list_eur"),
            "eur_fob": num(s, "eur_fob"),
            "cbm_method": s.get("cbm_method"),
            "landed_thb_sea": num(s, "landed_thb"),
            "landed_thb_air": num(a, "landed_thb"),
            "retail_sgd_sea_computed": sea_sgd,
            "retail_sgd_air_computed": air_sgd,
            "retail_sgd_firestore": fs_sgd,
            "retail_sgd_live_medusa": live_sgd,
            "medusa_status": m["status"] if m else None,
            "in_medusa": bool(m),
            "n_prices_live": m["n_prices"] if m else 0,
            "price_state": price_state,
            "known_tbc": code in {norm(x) for x in TBC_KNOWN},
        })

    rows.sort(key=lambda r: (r["type"] or "z", r["item_code"]))
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Summaries
    from collections import Counter
    by_type = Counter(r["type"] for r in rows)
    by_state = Counter(r["price_state"] for r in rows)
    by_status = Counter(r["medusa_status"] for r in rows)
    in_med = [r for r in rows if r["in_medusa"]]
    priced_live = [r for r in in_med if r["retail_sgd_live_medusa"]]
    tbc_or_zero = [r for r in in_med if not r["retail_sgd_live_medusa"]]

    summary = {
        "total_pricelist_skus": len(rows),
        "by_type": dict(by_type),
        "in_medusa": len(in_med),
        "not_in_medusa": len(rows) - len(in_med),
        "medusa_by_status": dict(by_status),
        "live_priced_sgd": len(priced_live),
        "live_zero_or_missing_sgd": len(tbc_or_zero),
        "price_state": dict(by_state),
        "known_tbc_codes": {},
    }
    for code in TBC_KNOWN:
        r = next((x for x in rows if x["item_code"] == norm(code)), None)
        summary["known_tbc_codes"][code] = {
            "in_pricelist": bool(r),
            "in_medusa": r["in_medusa"] if r else False,
            "live_sgd": r["retail_sgd_live_medusa"] if r else None,
            "sea_computed_sgd": r["retail_sgd_sea_computed"] if r else None,
            "status": r["medusa_status"] if r else None,
        }
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT_CSV}\nWrote {OUT_JSON}", file=sys.stderr)


if __name__ == "__main__":
    main()
