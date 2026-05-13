"""Push the Berliner landed-cost CSV to Medusa, keyed by variant SKU.

The Berliner sales channel already has ~498 products in Medusa from a prior
scrape, with handles like `berliner-swingo-02` (slugified name) — NOT
`berliner-{item_code}`. So the generic `scripts/sync_vendors_to_medusa.py`
(which looks up by handle) fails with 400 "SKU already exists" when it tries
to CREATE.

This script:
  1. Pages through every product in the Berliner sales channel.
  2. Builds a SKU → (product_id, variant_id, handle, existing_prices) map.
  3. For each row in the landed-cost CSV:
       * If row has an item_code AND a matching SKU exists in Medusa → UPDATE
         the variant's THB/USD/EUR prices.
       * If row has an item_code but no match → CREATE product using
         berliner-{slug(name or item_code)} handle, attach to SC, set prices.
       * If row has no item_code (accessory/feature line) → CREATE product
         using berliner-{slug(name)} handle (with counter on collision).
       * On-request rows → CREATE/skip with draft status, no price.

Usage:
    LEKA_MEDUSA_ADMIN_EMAIL=admin@leka.studio \\
    LEKA_MEDUSA_ADMIN_PASSWORD=... \\
    python berliner-catalog/push_pricelist_to_medusa.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SALES_CHANNEL_ID = "sc_01KNQAA3QDYHP15Y9K4PPRMDF0"  # Berliner
TIMEOUT = 60
TOKEN_REFRESH_EVERY = 300

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "berliner-catalog" / "data" / "pricelist_2026-01-01_landed.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("berliner_push")


def slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "item"


def auth() -> str:
    email = os.environ["LEKA_MEDUSA_ADMIN_EMAIL"]
    pw = os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]
    r = requests.post(
        f"{BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def build_sku_map(token: str) -> dict[str, dict]:
    """Paginate all Berliner SC products → {sku: {product_id, variant_id, handle, prices, title}}."""
    out: dict[str, dict] = {}
    offset = 0
    limit = 100
    while True:
        r = requests.get(
            f"{BACKEND}/admin/products",
            params={
                "sales_channel_id[]": SALES_CHANNEL_ID,
                "limit": limit,
                "offset": offset,
                "fields": "id,handle,title,status,variants.id,variants.sku,variants.prices.id,variants.prices.currency_code,variants.prices.amount",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        prods = data.get("products", [])
        if not prods:
            break
        for p in prods:
            variants = p.get("variants") or []
            for v in variants:
                sku = (v.get("sku") or "").strip()
                if not sku:
                    continue
                out[sku] = {
                    "product_id": p["id"],
                    "variant_id": v["id"],
                    "handle": p.get("handle"),
                    "title": p.get("title"),
                    "status": p.get("status"),
                    "prices": v.get("prices") or [],
                }
        offset += limit
        if offset >= data.get("count", 0):
            break
    return out


def build_handle_set(sku_map: dict[str, dict]) -> set[str]:
    return {info["handle"] for info in sku_map.values() if info.get("handle")}


def update_variant_prices(
    token: str, product_id: str, variant_id: str,
    retail_thb: float, retail_usd: float, retail_eur: float,
    existing_prices: list[dict],
) -> bool:
    by_ccy = {(p.get("currency_code") or "").lower(): p.get("id") for p in existing_prices}
    prices: list[dict] = []
    for amt, ccy in ((retail_thb, "thb"), (retail_usd, "usd"), (retail_eur, "eur")):
        if amt and amt > 0:
            item = {"amount": int(round(amt * 100)), "currency_code": ccy}
            if by_ccy.get(ccy):
                item["id"] = by_ccy[ccy]
            prices.append(item)
    if not prices:
        return False
    r = requests.post(
        f"{BACKEND}/admin/products/{product_id}/variants/{variant_id}",
        json={"prices": prices},
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        log.warning("variant %s price update failed: %s %s", variant_id, r.status_code, r.text[:300])
        return False
    return True


def create_product(
    token: str, handle: str, title: str, sku: str | None,
    retail_thb: float, retail_usd: float, retail_eur: float,
    status: str, metadata: dict,
) -> tuple[bool, str]:
    """Create a Berliner product. Returns (ok, product_id_or_error)."""
    variant_prices: list[dict] = []
    for amt, ccy in ((retail_thb, "thb"), (retail_usd, "usd"), (retail_eur, "eur")):
        if amt and amt > 0:
            variant_prices.append({"amount": int(round(amt * 100)), "currency_code": ccy})

    variant = {
        "title": "Default",
        "sku": sku or handle,
        "manage_inventory": False,
        "prices": variant_prices,
        "options": {"Default": "Default"},
    }
    payload = {
        "title": title,
        "handle": handle,
        "description": "",
        "status": status,  # "published" or "draft"
        "sales_channels": [{"id": SALES_CHANNEL_ID}],
        "metadata": metadata,
        "options": [{"title": "Default", "values": ["Default"]}],
        "variants": [variant],
    }
    r = requests.post(
        f"{BACKEND}/admin/products",
        json=payload,
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        return False, f"{r.status_code}:{r.text[:200]}"
    return True, r.json().get("product", {}).get("id", "?")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    if args.limit:
        rows = rows[: args.limit]
    log.info("Loaded %d rows from %s", len(rows), args.csv.name)

    log.info("Authenticating to Medusa…")
    token = auth()

    log.info("Building Medusa SKU map for Berliner SC…")
    sku_map = build_sku_map(token)
    log.info("Indexed %d existing SKUs across Berliner products", len(sku_map))
    existing_handles = build_handle_set(sku_map)

    t0 = time.time()
    updated = created = skipped = errors = 0
    seen_handles: set[str] = set()

    for i, r in enumerate(rows, start=1):
        if i % TOKEN_REFRESH_EVERY == 0:
            token = auth()
            log.info("token refreshed at %d/%d (rate %.1f/s)", i, len(rows), i / (time.time() - t0))

        item_code = (r.get("item_code") or "").strip()
        name = (r.get("name") or "").strip()
        status_in = r.get("status") or "active"
        list_eur = (r.get("list_eur") or "").strip()
        retail_thb = float(r.get("retail_thb") or 0)
        retail_usd = float(r.get("retail_usd") or 0)
        retail_eur = float(r.get("retail_eur") or 0)
        is_on_request = (not list_eur)
        medusa_status = "draft" if is_on_request else "published"

        # 1) SKU match → UPDATE prices.
        # For rows with item_code we look up by the real SKU; name-only rows
        # use the CSV's `handle` field as the synthetic SKU — that's exactly
        # what create_product wrote earlier (sku = sku or handle), and it's
        # unique per CSV row (parse_pricelist.py disambiguates collisions
        # with -2/-3 suffixes), so it round-trips cleanly on every re-run.
        csv_handle = (r.get("handle") or "").strip()
        lookup_sku = item_code or csv_handle
        if lookup_sku and lookup_sku in sku_map:
            info = sku_map[lookup_sku]
            if is_on_request:
                skipped += 1
                continue
            if args.dry_run:
                log.info("UPDATE %s (sku=%s) thb=%.0f usd=%.0f eur=%.0f",
                         info["handle"], item_code, retail_thb, retail_usd, retail_eur)
                updated += 1
            else:
                ok = update_variant_prices(
                    token, info["product_id"], info["variant_id"],
                    retail_thb, retail_usd, retail_eur, info["prices"],
                )
                if ok:
                    updated += 1
                else:
                    errors += 1
            continue

        # 2) Need to CREATE
        title = name or item_code or "Untitled"
        base_handle = f"berliner-{slugify(name or item_code)}"
        handle = base_handle
        n = 1
        while handle in existing_handles or handle in seen_handles:
            n += 1
            handle = f"{base_handle}-{n}"
        seen_handles.add(handle)

        metadata = {
            "brand_slug": "berliner",
            "item_code": item_code,
            "category": "playground",
            "source_url": "https://www.berliner-seilfabrik.com/",
            "pricelist_date": "2026-01-01",
            "page": r.get("page", ""),
            "remarks": r.get("remarks", ""),
            "row_status": status_in,
        }
        if args.dry_run:
            log.info("CREATE %s | %s | sku=%s | status=%s | thb=%.0f",
                     handle, title[:40], item_code or "-", medusa_status, retail_thb)
            created += 1
            continue
        ok, info = create_product(
            token, handle, title, item_code or None,
            retail_thb, retail_usd, retail_eur, medusa_status, metadata,
        )
        if ok:
            created += 1
        else:
            log.warning("CREATE %s failed: %s", handle, info)
            errors += 1

        if i % 50 == 0:
            log.info("progress %d/%d (upd=%d cre=%d skip=%d err=%d, %.1f/s)",
                     i, len(rows), updated, created, skipped, errors, i / (time.time() - t0))

    log.info("done: updated=%d created=%d skipped=%d errors=%d total=%d",
             updated, created, skipped, errors, len(rows))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
