"""Reverse-import vendor brands from Leka Medusa → vendors Firestore DB.

Phase 2 of the migration plan. Brands berliner / eurotramp / rampline / 4soft
were originally pushed straight to Medusa with no Firestore source-of-truth.
This script reads them back via Medusa Admin API and writes them into
`vendors/{slug}/products/{handle}` so the vendors DB becomes canonical.

Usage:
    python scripts/reverse_import_medusa_to_vendors.py --brand=berliner --dry-run
    python scripts/reverse_import_medusa_to_vendors.py --brand=all

Auth: env vars LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD,
or `Credentials Claude Code/Medusa Admin Credentials.txt` fallback
(same loader as vortex-catalog/scripts/push_to_medusa.py).
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Iterable

import requests
from google.cloud import firestore

_LOCAL_SA = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.exists(_LOCAL_SA):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _LOCAL_SA
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared.base_importer import batch_write  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("reverse_import_medusa")

PROJECT = "ai-agents-go"
DST_DB = "vendors"

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
TIMEOUT = 60

# slug → (sales_channel_id, display name, country, description, color, supplier, domains)
BRAND_REGISTRY: dict[str, dict] = {
    "berliner": {
        "name": "Berliner Seilfabrik",
        "supplier": "Berliner Seilfabrik GmbH & Co.",
        "country": "Germany",
        "description": "Rope Play Equipment",
        "color": "#182557",
        "domains": ["berliner-seilfabrik.com"],
        "sales_channel_id": "sc_01KNQAA3QDYHP15Y9K4PPRMDF0",
    },
    "eurotramp": {
        "name": "Eurotramp",
        "supplier": "Eurotramp Trampoline Kurt Hack GmbH",
        "country": "Germany",
        "description": "Premium Trampolines",
        "color": "#E54822",
        "domains": ["eurotramp.com"],
        "sales_channel_id": "sc_01KNQAA3Y72W17B7CP2VQ93T3M",
    },
    "rampline": {
        "name": "Rampline",
        "supplier": "Rampline AS",
        "country": "Norway",
        "description": "Motor Skill Playground Equipment",
        "color": "#970260",
        "domains": ["rampline.no"],
        "sales_channel_id": "sc_01KNQAA448RY0YPR51FNPM2TVA",
    },
    "4soft": {
        "name": "4soft",
        "supplier": "4soft s.r.o.",
        "country": "Czech Republic",
        "description": "EPDM Playground Surfaces & 3D Elements",
        "color": "#FFA900",
        "domains": ["4soft.cz"],
        "sales_channel_id": "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y",
    },
}

CATALOG_URL_TEMPLATE = "https://catalogs.leka.studio/{slug}"


def _load_admin_credentials() -> tuple[str, str]:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if email and pw:
        return email, pw
    creds_file = Path(
        r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\Medusa Admin Credentials.txt"
    )
    if creds_file.exists():
        text = creds_file.read_text(encoding="utf-8")
        if "leka-medusa" in text.lower():
            email_m = re.search(r"Email:\s*(\S+)", text)
            pw_m = re.search(r"Password:\s*(\S+)", text)
            if email_m and pw_m:
                return email_m.group(1), pw_m.group(1)
    raise RuntimeError(
        "Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD before running."
    )


def auth() -> str:
    email, pw = _load_admin_credentials()
    r = requests.post(
        f"{BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["token"]


def _list_products_for_sales_channel(token: str, sc_id: str) -> Iterable[dict]:
    """Page through Medusa admin products, filtered to one sales channel."""
    headers = {"Authorization": f"Bearer {token}"}
    offset = 0
    limit = 100
    while True:
        params = {
            "limit": limit,
            "offset": offset,
            "sales_channel_id[]": sc_id,
            "fields": "id,handle,title,subtitle,description,status,thumbnail,images.*,"
                      "tags.value,categories.handle,categories.name,collection.handle,"
                      "collection.title,metadata,variants.id,variants.sku,variants.title,"
                      "variants.metadata,variants.prices.amount,variants.prices.currency_code",
        }
        r = requests.get(f"{BACKEND}/admin/products", params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        body = r.json()
        products = body.get("products", [])
        if not products:
            break
        for p in products:
            yield p
        if len(products) < limit:
            break
        offset += limit


def _map_medusa_product(slug: str, p: dict) -> tuple[str, dict]:
    """Map a Medusa product → (handle, vendors-schema product doc)."""
    handle = p.get("handle") or f"{slug}-{p['id']}"
    meta = p.get("metadata") or {}
    variants = p.get("variants") or []
    primary_variant = variants[0] if variants else {}

    item_code = (
        meta.get("item_code")
        or primary_variant.get("sku")
        or handle.replace(f"{slug}-", "", 1)
    )

    # Pricing — pick USD from primary variant.
    fob_usd = None
    for price in (primary_variant.get("prices") or []):
        if price.get("currency_code", "").lower() == "usd":
            # Medusa stores price in minor units (cents).
            fob_usd = price["amount"] / 100.0
            break

    images = []
    for i, img in enumerate(p.get("images") or []):
        url = img.get("url") if isinstance(img, dict) else img
        if url:
            images.append({
                "url": url,
                "is_primary": i == 0,
                "source": "medusa_reverse_import",
            })
    if not images and p.get("thumbnail"):
        images.append({"url": p["thumbnail"], "is_primary": True, "source": "medusa_reverse_import"})

    categories = p.get("categories") or []
    category = categories[0]["handle"] if categories else meta.get("category", "other")

    out = {
        "handle": handle,
        "slug": slug,
        "item_code": item_code,
        "name": p.get("title") or "",
        "description": p.get("description") or "",
        "category": category,
        "subcategory": (categories[1]["handle"] if len(categories) > 1 else None),
        "series_slug": (p.get("collection") or {}).get("handle"),
        "series_name": (p.get("collection") or {}).get("title"),
        "images": images,
        "tags": [t["value"] for t in (p.get("tags") or []) if t.get("value")],
        "pricing": {"currency": "USD", "fob_usd": fob_usd, "price_date": None} if fob_usd else None,
        "source_url": meta.get("source_url"),
        "catalog_source": meta.get("catalog_source") or f"medusa_reverse_import_{slug}",
        "status": p.get("status") or "active",
        "medusa_product_id": p.get("id"),
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    # Drop empty optional fields to keep docs lean.
    return handle, {k: v for k, v in out.items() if v is not None}


def import_brand(slug: str, dry_run: bool) -> dict:
    cfg = BRAND_REGISTRY[slug]
    log.info("[%s] auth + fetch from Medusa SC=%s", slug, cfg["sales_channel_id"])
    token = auth()

    writes: list[tuple[str, dict]] = []
    for p in _list_products_for_sales_channel(token, cfg["sales_channel_id"]):
        handle, mapped = _map_medusa_product(slug, p)
        writes.append((handle, mapped))

    log.info("[%s] %d products fetched from Medusa", slug, len(writes))

    dst = firestore.Client(project=PROJECT, database=DST_DB)
    if not dry_run and writes:
        batch_write(dst, f"vendors/{slug}/products", writes)

    root_payload = {
        "slug": slug,
        "name": cfg["name"],
        "supplier": cfg["supplier"],
        "country": cfg["country"],
        "description": cfg["description"],
        "color": cfg["color"],
        "domains": cfg["domains"],
        "sales_channel_id": cfg["sales_channel_id"],
        "catalog_url": CATALOG_URL_TEMPLATE.format(slug=slug),
        "product_count": len(writes),
        "status": "active",
        "last_import": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if not dry_run:
        dst.collection("vendors").document(slug).set(root_payload, merge=True)

    return {"products": len(writes)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True, help="Brand slug or 'all' (one of: %s, all)" % ", ".join(BRAND_REGISTRY))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    brands = list(BRAND_REGISTRY) if args.brand == "all" else [args.brand]
    for b in brands:
        if b not in BRAND_REGISTRY:
            log.error("unknown brand: %s", b)
            return 2

    mode = "DRY-RUN" if args.dry_run else "WRITE"
    log.info("=== reverse_import_medusa_to_vendors mode=%s brands=%s ===", mode, brands)

    totals = {"products": 0}
    for slug in brands:
        c = import_brand(slug, args.dry_run)
        totals["products"] += c["products"]

    log.info("=== totals: %s ===", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
