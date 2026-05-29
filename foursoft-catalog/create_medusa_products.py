"""Create missing 4soft products in the Leka Medusa 4soft sales channel.

Context (v2.39.0): PR #63 priced all 2,410 pricelist SKUs in
vendors/4soft/products, but only 377 existed as Medusa products. 4soft.cz only
publishes ~400 products on the web (the other ~2,000 pricelist SKUs are
colour/size variants with no individual page), so a full create would add ~2,000
image-less products. User decision (2026-05-29): create the **3D scope only**
(dimension == "3D" = 592 SKUs: 3D animals/nature/shapes/sport, tunnels+slides,
water fountains, EPDM houses, furniture) — the hero physical play elements — and
defer the ~1,800 flat 2D ground markings. New products are created as **draft**
for review before publishing.

Reuses the handle-based create pattern + helpers from
scripts/sync_vendors_to_medusa.py, but adds: scope filter, draft status,
EN-name titles from the pricelist, and base-design image borrowing (already
written into the Firestore docs by backfill_scraped_details.py).

New products are created with an initial price set from `pricing` (a variant
needs at least one price); the authoritative multi-currency prices are pushed
afterwards by scripts/sync_brand_prices_to_medusa.py. For products that already
exist (the 130 in-scope of the 377), only the title (Czech → English pricelist
name) and metadata are refreshed here — existing prices are left untouched.

Usage:
    export LEKA_MEDUSA_ADMIN_EMAIL=$(gcloud secrets versions access latest --secret=medusa-admin-email --project ai-agents-go)
    export LEKA_MEDUSA_ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=medusa-admin-password --project ai-agents-go)
    python foursoft-catalog/create_medusa_products.py --dry-run
    python foursoft-catalog/create_medusa_products.py --scope 3D --status draft
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse helpers (module sets GAC only if unset; ours is already set).
from scripts.sync_vendors_to_medusa import (  # noqa: E402
    BACKEND, TIMEOUT, auth, _headers, _build_prices,
)
from google.cloud import firestore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("foursoft_create_medusa")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "4soft"
SALES_CHANNEL = "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y"
TOKEN_REFRESH_EVERY = 300


def _index_handles(token: str) -> dict[str, str]:
    """One paginated pass over the 4soft sales channel → {handle: product_id}.
    Avoids a per-row lookup (592 GETs)."""
    idx: dict[str, str] = {}
    offset = 0
    while True:
        r = requests.get(f"{BACKEND}/admin/products", params={
            "sales_channel_id[]": SALES_CHANNEL, "limit": 200, "offset": offset,
            "fields": "id,handle"},
            headers=_headers(token), timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json().get("products", [])
        for p in batch:
            if p.get("handle"):
                idx[p["handle"]] = p["id"]
        if len(batch) < 200:
            break
        offset += 200
    return idx


def _metadata(p: dict) -> dict:
    md = {
        "brand_slug": SLUG,
        "item_code": p.get("item_code"),
        "category": p.get("category"),
        "source_url": p.get("source_url"),
        "dimensions": p.get("dimensions"),
    }
    pm = p.get("metadata") or {}
    for k in ("dimension", "product_group", "unit", "pricelist_date"):
        if pm.get(k) is not None:
            md[k] = pm[k]
    pr = p.get("pricing") or {}
    if pr.get("cbm_method"):
        md["cbm_method"] = pr["cbm_method"]
    return {k: v for k, v in md.items() if v is not None}


def _create_payload(p: dict, status: str) -> dict:
    handle = p["handle"]
    name = p.get("name") or handle
    images = [img["url"] for img in (p.get("images") or []) if img.get("url")]
    payload = {
        "title": name,
        "handle": handle,
        "description": p.get("description") or "",
        "status": status,
        "sales_channels": [{"id": SALES_CHANNEL}],
        "metadata": _metadata(p),
        "options": [{"title": "Default", "values": ["Default"]}],
        "variants": [{
            "title": name,
            "sku": p.get("item_code") or handle,
            "manage_inventory": False,
            "prices": _build_prices(p.get("pricing") or {}),
            "options": {"Default": "Default"},
        }],
    }
    if images:
        payload["images"] = [{"url": u} for u in images]
        payload["thumbnail"] = images[0]
    return payload


def _update_existing(token: str, product_id: str, p: dict) -> requests.Response:
    """Rename Czech → EN pricelist title + refresh metadata (no price/image churn)."""
    body = {"title": p.get("name") or p["handle"], "metadata": _metadata(p)}
    return requests.post(f"{BACKEND}/admin/products/{product_id}", json=body,
                         headers=_headers(token), timeout=TIMEOUT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", default="3D",
                    help="metadata.dimension to include (default 3D). 'all' = every dimension.")
    ap.add_argument("--status", default="draft", choices=["draft", "published"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-update-existing", action="store_true",
                    help="Skip renaming the already-present in-scope products to EN.")
    args = ap.parse_args()

    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    docs = list(db.collection("vendors").document(SLUG).collection("products").stream())
    rows = []
    for d in docs:
        dd = d.to_dict() or {}
        dim = (dd.get("metadata") or {}).get("dimension")
        if args.scope != "all" and dim != args.scope:
            continue
        dd.setdefault("handle", d.id)
        rows.append(dd)
    rows.sort(key=lambda r: r.get("item_code") or r["handle"])
    if args.limit:
        rows = rows[: args.limit]
    log.info("scope=%s status=%s → %d in-scope vendor docs", args.scope, args.status, len(rows))

    token = auth()
    log.info("indexing existing 4soft channel products by handle …")
    idx = _index_handles(token)
    log.info("indexed %d existing products", len(idx))

    created = updated = skipped = errors = with_img = 0
    for i, p in enumerate(rows, 1):
        if i % TOKEN_REFRESH_EVERY == 0:
            token = auth()
        handle = p["handle"]
        existing_id = idx.get(handle)

        if existing_id is None:
            payload = _create_payload(p, args.status)
            if payload.get("images"):
                with_img += 1
            if args.dry_run:
                if created < 10:
                    log.info("[dry] CREATE %-22s %-46s img=%s prices=%d", handle,
                             (p.get("name") or "")[:46], bool(payload.get("images")),
                             len(payload["variants"][0]["prices"]))
                created += 1
                continue
            r = requests.post(f"{BACKEND}/admin/products", json=payload,
                              headers=_headers(token), timeout=TIMEOUT)
            if r.status_code >= 400:
                log.warning("CREATE %s failed: %s %s", handle, r.status_code, r.text[:180])
                errors += 1; continue
            created += 1
        else:
            if args.no_update_existing:
                skipped += 1; continue
            if args.dry_run:
                if updated < 4:
                    log.info("[dry] UPDATE(title→EN) %-22s %s", handle, (p.get("name") or "")[:46])
                updated += 1; continue
            r = _update_existing(token, existing_id, p)
            if r.status_code >= 400:
                log.warning("UPDATE %s failed: %s %s", handle, r.status_code, r.text[:180])
                errors += 1; continue
            updated += 1

        if i % 100 == 0:
            log.info("…%d/%d (created=%d updated=%d errors=%d)", i, len(rows), created, updated, errors)
            time.sleep(0.2)

    log.info("DONE scope=%s: created=%d (with_image=%d) updated=%d skipped=%d errors=%d%s",
             args.scope, created, with_img, updated, skipped, errors,
             "  [DRY RUN]" if args.dry_run else "")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
