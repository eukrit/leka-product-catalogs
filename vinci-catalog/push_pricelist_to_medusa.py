"""Push the latest Vinci landed-cost CSV directly to Medusa.

Reads `vinci-catalog/data/pricelist_<date>_landed.csv` (produced by
import_pricelist.py --dry-run or full run) and updates each Medusa product
variant's THB / USD / EUR retail prices. Bypasses Firestore — useful when
ADC has expired or for a one-shot refresh without touching the vendors DB.

Usage:
    LEKA_MEDUSA_ADMIN_EMAIL=admin@leka.studio \\
    LEKA_MEDUSA_ADMIN_PASSWORD=... \\
    python vinci-catalog/push_pricelist_to_medusa.py
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import time
from pathlib import Path

import requests

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
TIMEOUT = 60
TOKEN_REFRESH_EVERY = 300

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "vinci-catalog" / "data" / "pricelist_2026-05-11_landed.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("vinci_push")


def auth() -> str:
    email = os.environ["LEKA_MEDUSA_ADMIN_EMAIL"]
    pw = os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["token"]


def find_product(token: str, handle: str) -> dict | None:
    r = requests.get(
        f"{BACKEND}/admin/products",
        params={"handle": handle, "limit": 1,
                "fields": "id,handle,variants.id,variants.prices.id,variants.prices.currency_code"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        return None
    items = r.json().get("products", [])
    return items[0] if items else None


def push_prices(token: str, product_id: str, variant_id: str,
                retail_thb: float, retail_usd: float, retail_eur: float,
                existing_prices: list[dict]) -> bool:
    by_ccy = {(p.get("currency_code") or "").lower(): p.get("id") for p in (existing_prices or [])}
    prices: list[dict] = []
    for amt, ccy in ((retail_thb, "thb"), (retail_usd, "usd"), (retail_eur, "eur")):
        if amt and amt > 0:
            item = {"amount": int(round(amt * 100)), "currency_code": ccy}
            if by_ccy.get(ccy):
                item["id"] = by_ccy[ccy]
            prices.append(item)
    r = requests.post(
        f"{BACKEND}/admin/products/{product_id}/variants/{variant_id}",
        json={"prices": prices},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        log.warning("variant %s price update failed: %s %s", variant_id, r.status_code, r.text[:300])
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    if args.limit:
        rows = rows[: args.limit]
    log.info("Loaded %d rows from %s", len(rows), args.csv.name)

    token = auth()
    pushed = miss = err = 0
    t0 = time.time()
    for i, r in enumerate(rows, start=1):
        if i % TOKEN_REFRESH_EVERY == 0:
            token = auth()
            log.info("token refreshed at %d/%d (rate %.1f/s)", i, len(rows), i / (time.time() - t0))

        handle = f"vinci-{r['item_code'].lower()}"
        retail_thb = float(r["retail_thb"] or 0)
        retail_usd = float(r["retail_usd"] or 0)
        retail_eur = float(r["retail_eur"] or 0)

        try:
            prod = find_product(token, handle)
        except Exception as e:
            log.warning("lookup %s failed: %s", handle, e)
            err += 1
            continue
        if not prod or not prod.get("variants"):
            miss += 1
            continue
        v = prod["variants"][0]
        if args.dry_run:
            log.info("DRY %s thb=%.0f usd=%.0f eur=%.0f", handle, retail_thb, retail_usd, retail_eur)
            pushed += 1
            continue
        ok = push_prices(token, prod["id"], v["id"], retail_thb, retail_usd, retail_eur, v.get("prices") or [])
        if ok:
            pushed += 1
        else:
            err += 1
        if i % 50 == 0:
            log.info("progress %d/%d (pushed=%d miss=%d err=%d, %.1f/s)",
                     i, len(rows), pushed, miss, err, i / (time.time() - t0))

    log.info("done: pushed=%d miss=%d err=%d total=%d", pushed, miss, err, len(rows))


if __name__ == "__main__":
    main()
