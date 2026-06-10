"""Verify the 28 Eurotramp collision SKUs are priced to their 2026 values.

Reads live Medusa variant prices (by SKU) and the 2026 Firestore pricing
(item_code == SKU), and asserts all 4 currencies match within 1 minor unit.
Also confirms each Firestore doc carries medusa_product_id / medusa_variant_id.
Read-only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.sync_vendors_to_medusa import BACKEND, TIMEOUT, _build_prices, _headers  # noqa: E402

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")
PROJECT, VENDORS_DB = "ai-agents-go", "vendors"
SKUS = [
    "93001", "93002", "93020", "93021", "93022", "93030", "93031", "93032",
    "97044", "97046", "97048", "97049", "97054", "97056", "97058", "97059",
    "E21004", "E21006", "E21008", "E21009", "E97441", "E97448", "E97641",
    "E97648", "E97841", "E97848", "E97941", "E97948",
]


def auth() -> str:
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": os.environ["LEKA_MEDUSA_ADMIN_EMAIL"],
                            "password": os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]},
                      timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["token"]


def medusa_prices(token: str) -> dict[str, dict]:
    want = set(SKUS)
    out: dict[str, dict] = {}
    offset = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/products",
                         params={"limit": 200, "offset": offset,
                                 "fields": "id,variants.sku,variants.prices.currency_code,variants.prices.amount"},
                         headers=_headers(token), timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            break
        for p in batch:
            for v in (p.get("variants") or []):
                sku = (v.get("sku") or "").strip()
                if sku in want:
                    out[sku] = {pr["currency_code"]: pr["amount"]
                                for pr in (v.get("prices") or [])}
        if len(batch) < 200:
            break
        offset += 200
    return out


def main() -> int:
    token = auth()
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    med = medusa_prices(token)

    fs: dict[str, dict] = {}
    for d in db.collection("vendors").document("eurotramp").collection("products").stream():
        dd = d.to_dict() or {}
        code = str(dd.get("item_code") or "").strip()
        if code in set(SKUS):
            fs[code] = dd

    ok = bad = 0
    for sku in SKUS:
        f = fs.get(sku); m = med.get(sku)
        if not f or m is None:
            print(f"  MISSING {sku}: fs={bool(f)} medusa={m is not None}")
            bad += 1
            continue
        expected = {p["currency_code"]: p["amount"] for p in _build_prices(f.get("pricing") or {})}
        diffs = {c: (expected[c], m.get(c)) for c in expected if abs(expected[c] - (m.get(c) or -1)) > 1}
        mp = f.get("medusa_product_id"); mv = f.get("medusa_variant_id")
        stamp = "stamped" if (mp and mv) else "NO-STAMP"
        if diffs:
            print(f"  MISMATCH {sku} [{stamp}]: {diffs}")
            bad += 1
        else:
            if stamp == "NO-STAMP":
                print(f"  PRICE-OK but {stamp} {sku}")
                bad += 1
            else:
                ok += 1
    print(f"\n=== verify: ok={ok} bad={bad} / {len(SKUS)} ===")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
