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
# When a slug is missing here, fall back to env LEKA_<SLUG>_SALES_CHANNEL_ID
# so a freshly-created brand can be imported without an extra commit.
BRAND_SALES_CHANNELS: dict[str, str] = {
    "wisdom":    "sc_01KNKTHC0B7KFEDSZ3NNM49JQW",
    "vinci":     "sc_01KNKTHC77716EPCE3E2BKAMQP",
    "vortex":    "sc_01KPRY1T8HZJ57020JPZVGAKZK",
    "berliner":  "sc_01KNQAA3QDYHP15Y9K4PPRMDF0",
    "eurotramp": "sc_01KNQAA3Y72W17B7CP2VQ93T3M",
    "rampline":  "sc_01KNQAA448RY0YPR51FNPM2TVA",
    "4soft":     "sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y",
    "weplay":    "sc_01KR6Z0VBSXWYZDVGF30EAP0EQ",
    "designpark": "sc_01KRRK0N4ET8QZHX6QB3KZ84YD",
    "lappset":   "sc_01KTGNBRJZ71VWWH3W7FAW0E4R",
}


def _resolve_sales_channel(slug: str) -> str:
    if slug in BRAND_SALES_CHANNELS:
        return BRAND_SALES_CHANNELS[slug]
    env_key = f"LEKA_{slug.upper()}_SALES_CHANNEL_ID"
    sc_id = os.environ.get(env_key)
    if not sc_id:
        raise RuntimeError(
            f"No Medusa sales-channel id known for brand '{slug}'. "
            f"Add it to BRAND_SALES_CHANNELS or export {env_key}=sc_..."
        )
    return sc_id


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
        params={"handle": handle, "limit": 1,
                "fields": "id,handle,thumbnail,images.url,"
                          "options.id,options.title,options.values.value,"
                          "variants.id,variants.title,variants.sku,"
                          "variants.options.value,variants.options.option_id,"
                          "variants.prices.id,variants.prices.currency_code,variants.prices.amount"},
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    products = r.json().get("products", [])
    return products[0] if products else None


def _fetch_product_by_id(token: str, product_id: str) -> dict | None:
    """Fetch one product by id (same field shape as _find_product_by_handle).

    Used for the variant-member fallback: docs stamped with medusa_product_id
    whose handle has no Medusa match (sub-variants of a multi-variant umbrella).
    """
    r = requests.get(
        f"{BACKEND}/admin/products/{product_id}",
        params={"fields": "id,handle,thumbnail,images.url,"
                          "options.id,options.title,options.values.value,"
                          "variants.id,variants.title,variants.sku,"
                          "variants.options.value,variants.options.option_id,"
                          "variants.prices.id,variants.prices.currency_code,variants.prices.amount"},
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("product")


# Pricing keys on `pricing.*` → Medusa currency code.
_RETAIL_KEYS: tuple[tuple[str, str], ...] = (
    ("retail_usd", "usd"),
    ("retail_thb", "thb"),
    ("retail_eur", "eur"),
    ("retail_sgd", "sgd"),
)


def _build_prices(pricing: dict) -> list[dict]:
    """Build a Medusa `prices` array from a `pricing.*` map.

    Preference order: retail_<ccy> (multi-currency, post-landed-calc pricing)
    → fob_usd (legacy USD-only).
    Amounts are minor units (cents/satang).
    """
    if not pricing:
        return []
    out: list[dict] = []
    for key, ccy in _RETAIL_KEYS:
        val = pricing.get(key)
        if val:
            out.append({"amount": int(round(val * 100)), "currency_code": ccy})
    if not out:
        fob = pricing.get("fob_usd")
        if fob:
            out.append({"amount": int(round(fob * 100)), "currency_code": "usd"})
    return out


def _build_create_payload(slug: str, sc_id: str, p: dict) -> dict:
    """Map a vendors product doc → Medusa create-product payload.

    If the doc carries a `variants[]` array (e.g. coating Standard / Additional
    on Eurotramp Kids Tramp), emit one Medusa option + one variant per entry.
    Otherwise emit a single Default variant.
    """
    handle = p["handle"]
    images = [img["url"] for img in (p.get("images") or []) if img.get("url")]
    pricing = p.get("pricing") or {}
    metadata = {
        "brand_slug": slug,
        "item_code": p.get("item_code"),
        "gtin": p.get("gtin"),
        "category": p.get("category"),
        "subcategory": p.get("subcategory"),
        "source_url": p.get("source_url"),
        # Canonical clean-white hero (produced at the vendors source by
        # lappset-catalog step8). Downstream renderers read this instead of
        # re-die-cutting. Dropped by the None-filter for brands that don't set it.
        "hero_white_gcs": p.get("hero_white_gcs"),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    variants_array = p.get("variants") or []
    if variants_array:
        option_title = p.get("variant_option") or "Variant"
        option_values = [v["title"] for v in variants_array]
        med_variants = []
        for v in variants_array:
            med_variants.append({
                "title": v["title"],
                "sku": v.get("sku") or f"{p.get('item_code', handle)}-{v['title'][:10]}",
                "manage_inventory": False,
                "prices": _build_prices(v.get("pricing") or pricing),
                "options": {option_title: v["title"]},
            })
        options = [{"title": option_title, "values": option_values}]
    else:
        med_variants = [{
            "title": p.get("name") or handle,
            "sku": p.get("item_code") or handle,
            "manage_inventory": False,
            "prices": _build_prices(pricing),
            "options": {"Default": "Default"},
        }]
        options = [{"title": "Default", "values": ["Default"]}]

    payload = {
        "title": p.get("name") or handle,
        "handle": handle,
        "description": p.get("description") or "",
        "status": "published" if (p.get("status") or "active") == "active" else "draft",
        "sales_channels": [{"id": sc_id}],
        "metadata": metadata,
        "options": options,
        "variants": med_variants,
    }
    if images:
        payload["images"] = [{"url": u} for u in images]
        payload["thumbnail"] = images[0]
    return payload


def _build_update_payload(p: dict, *, existing_image_urls: set[str] | None = None) -> dict:
    """Update payload — fields safe to refresh on every sync.

    Includes `images` and `thumbnail` when the Firestore doc carries images
    the Medusa product doesn't already have. We don't replace images blindly
    because Medusa preserves image ids; instead, we APPEND any new URLs by
    submitting the full union (Medusa de-dupes by URL on its end). When
    `existing_image_urls` is None we skip the image patch (caller didn't
    want to touch images).

    Includes `dimensions` and `source_url` in `metadata` so the storefront
    can render spec tables + outbound mfr links without re-querying Firestore.
    """
    metadata = {
        "brand_slug": p.get("slug"),
        "item_code": p.get("item_code"),
        "gtin": p.get("gtin"),
        "category": p.get("category"),
        "source_url": p.get("source_url"),
        "dimensions": p.get("dimensions"),
        "hero_white_gcs": p.get("hero_white_gcs"),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    out: dict = {
        "title": p.get("name") or p["handle"],
        "description": p.get("description") or "",
        "metadata": metadata,
    }

    # Image sync — only if caller passed the existing-URL set (i.e. we
    # fetched it from Medusa) so we can compute the union without overwriting.
    if existing_image_urls is not None:
        fs_urls = [img["url"] for img in (p.get("images") or []) if img.get("url")]
        new_urls = [u for u in fs_urls if u not in existing_image_urls]
        if new_urls:
            union = list(existing_image_urls) + new_urls
            out["images"] = [{"url": u} for u in union]
            # First image becomes thumbnail when there isn't one yet
            if fs_urls:
                out["thumbnail"] = fs_urls[0]
    return out


def _update_variant_prices(token: str, product_id: str, variant_id: str,
                            pricing: dict, existing_prices: list[dict] | None) -> None:
    """Upsert all currency prices on a variant.

    `pricing` is the `pricing.*` map from the Firestore product / variant doc.
    Existing price rows are matched by `currency_code` so we PATCH the same row
    rather than orphaning the previous one.
    """
    new_prices = _build_prices(pricing)
    if not new_prices:
        return
    existing_by_ccy = {(pr.get("currency_code") or "").lower(): pr.get("id")
                      for pr in (existing_prices or [])}
    for entry in new_prices:
        eid = existing_by_ccy.get(entry["currency_code"])
        if eid:
            entry["id"] = eid
    body = {"prices": new_prices}
    r = requests.post(
        f"{BACKEND}/admin/products/{product_id}/variants/{variant_id}",
        json=body,
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        log.warning("price update failed for variant %s: %s %s", variant_id, r.status_code, r.text[:200])


def _price_variant_member(token: str, existing: dict, p: dict) -> bool:
    """Price ONLY the variant whose SKU == this doc's item_code.

    For variant-member docs (a per-SKU vendors doc that maps to one variant of
    an existing multi-variant umbrella product). We deliberately do NOT touch
    product-level fields — many such docs share one umbrella, so overwriting
    title/description/images from a single member would clobber the others.
    Returns True if a matching variant was priced.
    """
    sku = (p.get("item_code") or "").strip()
    pricing = p.get("pricing") or {}
    if not sku or not _build_prices(pricing):
        return False
    for v in (existing.get("variants") or []):
        if (v.get("sku") or "").strip() == sku:
            _update_variant_prices(token, existing["id"], v["id"], pricing, v.get("prices"))
            return True
    log.warning("[variant-member] %s: sku %s not present on product %s",
                p.get("handle"), sku, existing.get("id"))
    return False


def _ensure_variants(token: str, product_id: str, p: dict,
                     existing_variants: list[dict]) -> list[dict]:
    """If the Firestore doc has multi-variant data and Medusa only has the
    default variant, create the additional variants. Returns the updated
    variants list (refetched lightly).
    """
    fs_variants = p.get("variants") or []
    if not fs_variants:
        return existing_variants
    option_title = p.get("variant_option") or "Variant"
    have_titles = {(v.get("title") or "").lower() for v in existing_variants}
    # Need at least one variant per FS entry; skip if all titles already present.
    missing = [v for v in fs_variants if (v["title"]).lower() not in have_titles]
    if not missing:
        return existing_variants
    # Medusa v2: cannot append a new option to an existing product via the
    # variants endpoint alone — the product needs the option defined. If the
    # product was created without it (legacy default-option), we skip variant
    # creation and log so the user knows.
    has_option = False
    for v in existing_variants:
        if option_title in (v.get("options") or {}):
            has_option = True
            break
    if not has_option:
        log.info("[variants] %s lacks option '%s' — skipping variant fold "
                 "(needs product re-create or admin migration)", p["handle"], option_title)
        return existing_variants
    for v in missing:
        body = {
            "title": v["title"],
            "sku": v.get("sku"),
            "manage_inventory": False,
            "prices": _build_prices(v.get("pricing") or {}),
            "options": {option_title: v["title"]},
        }
        r = requests.post(
            f"{BACKEND}/admin/products/{product_id}/variants",
            json=body,
            headers=_headers(token),
            timeout=TIMEOUT,
        )
        if r.status_code >= 400:
            log.warning("variant create failed for %s/%s: %s %s",
                        p["handle"], v["title"], r.status_code, r.text[:200])
    return existing_variants  # caller will refetch on next pass


def _lappset_hero_ok(p: dict) -> bool:
    """Guard: a Lappset product must lead with a normalized, proxy-served hero.

    Accepts either the canonical `hero_white` variant, OR — for the handful of
    products with no white/transparent source render (in-situ installation
    photos) — the proxy-served ORIGINAL explicitly flagged `needs_fallback`.
    Refuses anything else: a raw `webapi.lappset.com` studio URL, an empty
    images list, or an un-flagged non-hero_white lead. The whole point of the
    source-side fix is that no raw studio/transparent hero ever reaches the
    storefront. Run the producer
    (`vendors/lappset-catalog/scripts/step8_normalize_heroes.py --apply`) first.
    """
    imgs = p.get("images") or []
    if not imgs:
        return False
    first = imgs[0]
    url = first.get("url") or ""
    if first.get("source") == "hero_white" and "/api/i/lappset/hero_white/" in url:
        return True
    # Documented fallback: environment photo, proxy-served, explicitly flagged.
    if (first.get("source") == "original"
            and "/api/i/lappset/" in url
            and (p.get("hero_white") or {}).get("needs_fallback")):
        return True
    return False


def sync_brand(slug: str, dry_run: bool, limit: int | None, skip_no_images: bool = False) -> dict:
    sc_id = _resolve_sales_channel(slug)
    db = firestore.Client(project=PROJECT, database=SRC_DB)
    log.info("[%s] reading vendors/%s/products (db=%s)", slug, slug, SRC_DB)
    docs = list(db.collection("vendors").document(slug).collection("products").stream())
    if skip_no_images:
        before = len(docs)
        docs = [d for d in docs if (d.to_dict() or {}).get("images")]
        log.info("[%s] --skip-no-images: kept %d / %d products with images", slug, len(docs), before)
    if limit:
        docs = docs[:limit]
    log.info("[%s] %d products to sync", slug, len(docs))

    token = auth()
    created = updated = priced = errors = 0

    for i, doc in enumerate(docs, start=1):
        p = doc.to_dict() or {}
        # Medusa handles must be URL-safe (lowercase alphanumeric + hyphens).
        # Raw vendor docs (e.g. Lappset) have no explicit handle and fall back to
        # the underscore slug doc-id, so hyphenate that fallback.
        handle = p.get("handle") or doc.id.replace("_", "-")
        # Normalize raw vendor-template docs (e.g. Lappset, which stores
        # product_name/sku and no handle) into the field shape the payload
        # builders expect. setdefault never overrides brands that already carry
        # these (wisdom/vinci/etc.).
        p["handle"] = handle
        p.setdefault("name", p.get("product_name") or "")
        p.setdefault("item_code", p.get("sku") or "")
        p.setdefault("slug", slug)
        p.setdefault("status", "active")

        # Guardrail: never publish a Lappset product whose hero isn't the
        # normalized white variant (see _lappset_hero_ok).
        if slug == "lappset" and not _lappset_hero_ok(p):
            log.error("[lappset] %s: hero is not the normalized white variant "
                      "— skipping (run step8_normalize_heroes first)", handle)
            errors += 1
            continue

        if i % TOKEN_REFRESH_EVERY == 0:
            token = auth()

        variant_member = False
        try:
            existing = _find_product_by_handle(token, handle)
        except requests.HTTPError as e:
            log.warning("[%s] %s lookup failed: %s", slug, handle, e)
            errors += 1
            continue

        # Variant-member fallback. Some vendors docs are sub-variants of an
        # existing multi-variant umbrella product (the vendors model is
        # 1-doc-per-SKU; Medusa folds related SKUs into one product). Their
        # per-SKU handle never matches a Medusa handle, so a handle-only sync
        # would attempt a CREATE and 400 with "variant sku already exists".
        # When such a doc has been stamped with medusa_product_id, resolve to
        # that umbrella and UPDATE only its own variant price — never CREATE.
        if existing is None and p.get("medusa_product_id"):
            try:
                existing = _fetch_product_by_id(token, p["medusa_product_id"])
            except requests.HTTPError as e:
                log.warning("[%s] %s medusa_product_id lookup failed: %s", slug, handle, e)
            variant_member = existing is not None

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
        elif variant_member:
            if dry_run:
                log.info("[%s] UPDATE %s (variant-member of %s, dry)",
                         slug, handle, existing.get("handle"))
            else:
                if _price_variant_member(token, existing, p):
                    priced += 1
            updated += 1
        else:
            if dry_run:
                log.info("[%s] UPDATE %s (dry)", slug, handle)
            else:
                # Pass existing image URLs so the update payload can compute
                # the union and append-only new images (preserves Medusa's
                # image ids; avoids dropping reverse-imported ones).
                existing_img_urls = {
                    im.get("url") for im in (existing.get("images") or [])
                    if im.get("url")
                }
                r = requests.post(
                    f"{BACKEND}/admin/products/{existing['id']}",
                    json=_build_update_payload(p, existing_image_urls=existing_img_urls),
                    headers=_headers(token),
                    timeout=TIMEOUT,
                )
                if r.status_code >= 400:
                    log.warning("[%s] UPDATE %s failed: %s %s", slug, handle, r.status_code, r.text[:200])
                    errors += 1
                    continue
                pricing = p.get("pricing") or {}
                if _build_prices(pricing):
                    variants = existing.get("variants") or []
                    # Try to create any missing Firestore-declared variants first
                    variants = _ensure_variants(token, existing["id"], p, variants)
                    fs_variants_by_title = {
                        (v.get("title") or "").lower(): v.get("pricing") or pricing
                        for v in (p.get("variants") or [])
                    }
                    if variants:
                        for med_v in variants:
                            t = (med_v.get("title") or "").lower()
                            v_pricing = fs_variants_by_title.get(t, pricing)
                            _update_variant_prices(
                                token, existing["id"], med_v["id"], v_pricing,
                                med_v.get("prices"),
                            )
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
    ap.add_argument("--skip-no-images", action="store_true",
                    help="Skip products whose images[] is empty. Used for Weplay path 1B "
                         "(only sync the ~100 products that have URL-pattern-matched photos).")
    args = ap.parse_args()

    brands = list(BRAND_SALES_CHANNELS) if args.brand == "all" else [args.brand]
    for b in brands:
        try:
            _resolve_sales_channel(b)
        except RuntimeError as e:
            log.error("%s", e)
            return 2

    mode = "DRY-RUN" if args.dry_run else "WRITE"
    log.info("=== sync_vendors_to_medusa mode=%s brands=%s limit=%s ===", mode, brands, args.limit)

    grand: dict[str, int] = {"total": 0, "created": 0, "updated": 0, "priced": 0, "errors": 0}
    for slug in brands:
        s = sync_brand(slug, args.dry_run, args.limit, skip_no_images=args.skip_no_images)
        for k, v in s.items():
            grand[k] += v
        time.sleep(1)

    log.info("=== grand totals: %s ===", grand)
    return 0 if grand["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
