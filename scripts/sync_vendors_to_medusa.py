"""Sync `vendors/{slug}/products` (Firestore DB `vendors`) → Leka Medusa.

Phase 3 of the migration plan. Generalizes the vortex push pattern from
`vendors/vortex-catalog/scripts/push_to_medusa.py` to all 7 brands.

For each brand:
  1. Read every product doc from `vendors/{slug}/products`.
  2. Lookup existing Medusa product by handle.
  3. If missing → create. If present → update title/description/metadata
     and the primary variant price (when `pricing.fob_usd` is set).
  4. Attach to the brand's sales channel.
  5. Refresh per-brand `product_count` on the vendor root doc.

Usage:
    python scripts/sync_vendors_to_medusa.py --brand=wisdom --dry-run
    python scripts/sync_vendors_to_medusa.py --brand=all
    python scripts/sync_vendors_to_medusa.py --brand=vinci --limit=10

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
from google.cloud import firestore

_LOCAL_SA = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.exists(_LOCAL_SA):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _LOCAL_SA
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("sync_vendors_to_medusa")

PROJECT = "ai-agents-go"
SRC_DB = "vendors"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
TIMEOUT = 60
TOKEN_REFRESH_EVERY = 400  # products

# slug → Medusa Sales Channel id (lifted from medusa-storefront/src/lib/medusa-client.ts).
BRAND_SALES_CHANNELS: dict[str, str] = {
    "wisdom":    "sc_01KNKTHC0B7KFEDSZ3NNM49JQW",
    "vinci":     "sc_01KNKTHC77716EPCE3E2BKAMQP",
    "vortex":    "sc_01KPRY1T8HZJ57020JPZVGAKZK",
    "berliner":  "sc_01KNQAA3QDYHP15Y9K4PPRMDF0",
    "eurotramp": "sc_01KNQAA3Y72W17B7CP2VQ93T3M",
    "rampline":  "sc_01KNQAA448RY0YPR51FNPM2TVA",
    "4soft":     "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y",
}


def _load_admin_credentials() -> tuple[str, str]:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        raise RuntimeError("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.")
    return email, pw


def auth() -> str:
    email, pw = _load_admin_credentials()
    r = requests.post(
        f"{BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _find_product_by_handle(token: str, handle: str) -> dict | None:
    r = requests.get(
        f"{BACKEND}/admin/products",
        params={"handle": handle, "limit": 1, "fields": "id,handle,variants.id,variants.prices.id,variants.prices.currency_code"},
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    products = r.json().get("products", [])
    return products[0] if products else None


def _build_create_payload(slug: str, sc_id: str, p: dict) -> dict:
    """Map a vendors product doc → Medusa create-product payload."""
    handle = p["handle"]
    images = [img["url"] for img in (p.get("images") or []) if img.get("url")]
    fob = (p.get("pricing") or {}).get("fob_usd")
    metadata = {
        "brand_slug": slug,
        "item_code": p.get("item_code"),
        "category": p.get("category"),
        "subcategory": p.get("subcategory"),
        "source_url": p.get("source_url"),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    variant = {
        "title": p.get("name") or handle,
        "sku": p.get("item_code") or handle,
        "manage_inventory": False,
    }
    if fob:
        variant["prices"] = [{"amount": int(round(fob * 100)), "currency_code": "usd"}]

    payload = {
        "title": p.get("name") or handle,
        "handle": handle,
        "description": p.get("description") or "",
        "status": "published" if (p.get("status") or "active") == "active" else "draft",
        "sales_channels": [{"id": sc_id}],
        "metadata": metadata,
        "options": [{"title": "Default", "values": ["Default"]}],
        "variants": [variant | {"options": {"Default": "Default"}}],
    }
    if images:
        payload["images"] = [{"url": u} for u in images]
        payload["thumbnail"] = images[0]
    return payload


def _build_update_payload(p: dict) -> dict:
    """Update payload — fields safe to refresh on every sync."""
    metadata = {
        "brand_slug": p.get("slug"),
        "item_code": p.get("item_code"),
        "category": p.get("category"),
        "source_url": p.get("source_url"),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}
    return {
        "title": p.get("name") or p["handle"],
        "description": p.get("description") or "",
        "metadata": metadata,
    }


def _update_variant_price(token: str, variant_id: str, fob_usd: float, existing_price_id: str | None) -> None:
    """Upsert USD price on a variant. Medusa stores amount in minor units."""
    amount = int(round(fob_usd * 100))
    body = {"prices": [{"amount": amount, "currency_code": "usd"}]}
    if existing_price_id:
        body["prices"][0]["id"] = existing_price_id
    r = requests.post(
        f"{BACKEND}/admin/products/variants/{variant_id}",
        json=body,
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        log.warning("price update failed for variant %s: %s %s", variant_id, r.status_code, r.text[:200])


def sync_brand(slug: str, dry_run: bool, limit: int | None) -> dict:
    sc_id = BRAND_SALES_CHANNELS[slug]
    db = firestore.Client(project=PROJECT, database=SRC_DB)
    log.info("[%s] reading vendors/%s/products (db=%s)", slug, slug, SRC_DB)
    docs = list(db.collection("vendors").document(slug).collection("products").stream())
    if limit:
        docs = docs[:limit]
    log.info("[%s] %d products to sync", slug, len(docs))

    token = auth()
    created = updated = priced = errors = 0

    for i, doc in enumerate(docs, start=1):
        p = doc.to_dict() or {}
        handle = p.get("handle") or doc.id

        if i % TOKEN_REFRESH_EVERY == 0:
            token = auth()

        try:
            existing = _find_product_by_handle(token, handle)
        except requests.HTTPError as e:
            log.warning("[%s] %s lookup failed: %s", slug, handle, e)
            errors += 1
            continue

        if existing is None:
            if dry_run:
                log.info("[%s] CREATE %s (dry)", slug, handle)
            else:
                payload = _build_create_payload(slug, sc_id, p)
                r = requests.post(
                    f"{BACKEND}/admin/products",
                    json=payload,
                    headers=_headers(token),
                    timeout=TIMEOUT,
                )
                if r.status_code >= 400:
                    log.warning("[%s] CREATE %s failed: %s %s", slug, handle, r.status_code, r.text[:200])
                    errors += 1
                    continue
            created += 1
        else:
            if dry_run:
                log.info("[%s] UPDATE %s (dry)", slug, handle)
            else:
                r = requests.post(
                    f"{BACKEND}/admin/products/{existing['id']}",
                    json=_build_update_payload(p),
                    headers=_headers(token),
                    timeout=TIMEOUT,
                )
                if r.status_code >= 400:
                    log.warning("[%s] UPDATE %s failed: %s %s", slug, handle, r.status_code, r.text[:200])
                    errors += 1
                    continue
                fob = (p.get("pricing") or {}).get("fob_usd")
                if fob:
                    variants = existing.get("variants") or []
                    if variants:
                        primary = variants[0]
                        existing_price_id = None
                        for pr in primary.get("prices") or []:
                            if (pr.get("currency_code") or "").lower() == "usd":
                                existing_price_id = pr.get("id")
                                break
                        _update_variant_price(token, primary["id"], fob, existing_price_id)
                        priced += 1
            updated += 1

        if i % 100 == 0:
            log.info("[%s] progress %d/%d (created=%d, updated=%d, errors=%d)",
                     slug, i, len(docs), created, updated, errors)

    # Refresh vendor root doc product_count
    if not dry_run:
        db.collection("vendors").document(slug).set(
            {"product_count": len(docs), "last_sync": firestore.SERVER_TIMESTAMP},
            merge=True,
        )

    summary = {"total": len(docs), "created": created, "updated": updated,
               "priced": priced, "errors": errors}
    log.info("[%s] done: %s", slug, summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True,
                    help="Brand slug or 'all' (one of: %s, all)" % ", ".join(BRAND_SALES_CHANNELS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="Process only first N products (smoke test).")
    args = ap.parse_args()

    brands = list(BRAND_SALES_CHANNELS) if args.brand == "all" else [args.brand]
    for b in brands:
        if b not in BRAND_SALES_CHANNELS:
            log.error("unknown brand: %s", b)
            return 2

    mode = "DRY-RUN" if args.dry_run else "WRITE"
    log.info("=== sync_vendors_to_medusa mode=%s brands=%s limit=%s ===", mode, brands, args.limit)

    grand: dict[str, int] = {"total": 0, "created": 0, "updated": 0, "priced": 0, "errors": 0}
    for slug in brands:
        s = sync_brand(slug, args.dry_run, args.limit)
        for k, v in s.items():
            grand[k] += v
        time.sleep(1)

    log.info("=== grand totals: %s ===", grand)
    return 0 if grand["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
