"""Import Urbanix vendor docs → Leka Project Medusa products.

Sources (Firestore DB `vendors`, read-only):
    vendors/urbanix_fitness/products/*    — 339 docs (fitness stations, outdoor gym)
    vendors/urbanix_playground/products/* — 959 docs (playground equipment)

Target:
    Medusa Sales Channel `sc_01KNKTHC0B7KFEDSZ3NNM49JQW` ("Leka Project")
    — same SC that holds the 5,061 Wisdom-origin products. Distinct internal
    SKU namespace keeps the two product lines separable.

Internal SKU scheme (assigned sequentially, persisted in `urbanix_mapping/`):
    LP-F-0001 .. LP-F-####   for urbanix_fitness
    LP-P-0001 .. LP-P-####   for urbanix_playground

The existing Wisdom-origin products use random 8-char nanoid SKUs
(LP-XXXXXXXX) so the three namespaces are structurally disjoint.

The mapping table (Firestore DB `leka-product-catalogs`, collection
`urbanix_mapping/`) is the audit source-of-truth — admin-only, never
exposed via the public Medusa storefront API.

Sanitization:
    Strips "Urbanix" / "UBX" / "UBX International Limited" + Urbanix-shaped
    item codes (UBX-###, CC-##, TPF-####-#) from product title + description
    so no source-brand identifier reaches a Leka customer.

Pricing:
    All 1,298 products are imported with NO Medusa price rows and
    `metadata.pricing_pending=true`. The 304 Urbanix-pricelist-linked docs
    still get this treatment — Leka pricing strategy is set per-SKU by the
    merchandiser, not inherited from the source.

Idempotency:
    Re-run is safe. Maps are keyed on `urbanix_doc_path`; existing mappings
    are refreshed (title/description/metadata) only when `source_sha`
    changed. New source docs get new sequential codes via a transactional
    counter at `urbanix_mapping/_counters`.

Auth:
    LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD (Medusa admin).
    GOOGLE_APPLICATION_CREDENTIALS or ADC (Firestore on ai-agents-go).

Usage:
    python scripts/import_from_urbanix.py --dry-run
    python scripts/import_from_urbanix.py --dry-run --limit 5
    python scripts/import_from_urbanix.py --vendor fitness --limit 10
    python scripts/import_from_urbanix.py                      # full live run
    python scripts/import_from_urbanix.py --report             # counts only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import string
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from google.cloud import firestore

_LOCAL_SA = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.exists(_LOCAL_SA):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _LOCAL_SA
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("import_from_urbanix")

GCP_PROJECT = "ai-agents-go"
SRC_DB = "vendors"
DEST_DB = "leka-product-catalogs"
BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
LEKA_PROJECT_SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
HANDLE_PREFIX = "leka-project"
TIMEOUT = 60
TOKEN_REFRESH_EVERY = 200  # products
ID_ALPHABET = string.ascii_lowercase + string.digits

MAPPING_COLLECTION = "urbanix_mapping"
COUNTER_DOC = "_counters"

VENDOR_SLUGS = {
    "fitness": "urbanix_fitness",
    "playground": "urbanix_playground",
}
LINE_SKU_PREFIX = {
    "urbanix_fitness": "LP-F",
    "urbanix_playground": "LP-P",
}
LINE_COUNTER_KEY = {
    "urbanix_fitness": "fitness_next",
    "urbanix_playground": "playground_next",
}

# Strip identifiers that would reveal the source brand. Matches:
#   "UBX International Limited" (case/space tolerant)
#   "Urbanix" / "URBANIX" / standalone "UBX"
#   "UBX-104" / "UBX-302A" item codes
#   "CC-01" / "CC-23A" CrossFit item codes
#   "TPF-2509-800" / "TPF-9548-1" playset item codes
SANITIZE_RE = re.compile(
    r"\b("
    r"UBX[\s\-]*International[\s\-]*Limited"
    r"|Urbanix"
    r"|UBX(?:[-\s]\d+[A-Z]?)?"
    r"|CC[-\s]\d+[A-Z]?"
    r"|TPF[-\s][\d\-]+[A-Z]?"
    r")\b",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s{2,}")
# Empty-parens / brackets left behind after stripping inline identifiers,
# e.g. "(CC-01)" -> "()" -> drop with surrounding space.
EMPTY_PARENS_RE = re.compile(r"\s*[\(\[]\s*[\)\]]\s*")
# "The is" / "The features" left when an identifier opened the sentence with
# a determiner. Promote "The" -> "This" so the sentence remains grammatical.
ORPHAN_DET_RE = re.compile(
    r"\bThe\s+(is|are|was|were|has|have|had|features|features|"
    r"includes?|comes?|offers?|provides?)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _auth() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        log.error("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.")
        sys.exit(2)
    r = requests.post(
        f"{BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        log.error("Auth response missing token: %s", r.json())
        sys.exit(2)
    return tok


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _request_with_retry(method: str, url: str, token: str, **kw) -> requests.Response:
    delays = [2, 5, 10, 30, 60]
    for attempt in range(len(delays) + 1):
        try:
            r = requests.request(method, url, headers=_headers(token), timeout=TIMEOUT, **kw)
            if r.status_code == 401:
                raise PermissionError("401 from Medusa; re-auth")
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
            return r
        except (requests.RequestException, requests.HTTPError) as e:
            if attempt == len(delays):
                raise
            sleep_for = delays[attempt] + random.random() * 2
            log.warning("retry %d for %s %s after %.1fs: %s",
                        attempt + 1, method, url, sleep_for, str(e)[:120])
            time.sleep(sleep_for)


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------
def sanitize(text: str | None) -> str:
    """Strip Urbanix/UBX/CC/TPF identifiers from a free-text field.

    Leaves the rest of the prose intact. Collapses double spaces and strips
    leading/trailing whitespace + dangling punctuation left behind by removal.
    """
    if not text:
        return ""
    out = SANITIZE_RE.sub("", text)
    out = EMPTY_PARENS_RE.sub(" ", out)
    out = ORPHAN_DET_RE.sub(lambda m: "This " + m.group(1), out)
    out = WHITESPACE_RE.sub(" ", out)
    out = out.strip(" -:,;.")
    return out


# ---------------------------------------------------------------------------
# SKU + handle generation
# ---------------------------------------------------------------------------
def _new_nanoid(length: int = 8) -> str:
    return "".join(random.choices(ID_ALPHABET, k=length))


def new_handle(seen: set[str]) -> str:
    for _ in range(20):
        h = f"{HANDLE_PREFIX}-{_new_nanoid(8)}"
        if h not in seen:
            seen.add(h)
            return h
    raise RuntimeError("Could not allocate a fresh handle in 20 tries.")


def format_sku(vendor_id: str, n: int) -> str:
    return f"{LINE_SKU_PREFIX[vendor_id]}-{n:04d}"


# ---------------------------------------------------------------------------
# Counter (Firestore transaction on urbanix_mapping/_counters)
# ---------------------------------------------------------------------------
def reserve_codes(db_leka: firestore.Client, n_by_line: dict[str, int]) -> dict[str, int]:
    """Atomically bump the counter and return the first allocated index per line.

    Returns a dict {vendor_id: first_n}. Caller assigns first_n, first_n+1, ...
    """
    counter_ref = db_leka.collection(MAPPING_COLLECTION).document(COUNTER_DOC)

    @firestore.transactional
    def _txn(transaction: firestore.Transaction) -> dict[str, int]:
        snap = counter_ref.get(transaction=transaction)
        cur = snap.to_dict() if snap.exists else {}
        starts: dict[str, int] = {}
        update: dict[str, object] = {"updated_at": firestore.SERVER_TIMESTAMP}
        for vendor_id, n_new in n_by_line.items():
            if n_new <= 0:
                continue
            key = LINE_COUNTER_KEY[vendor_id]
            start = int(cur.get(key, 0)) + 1
            starts[vendor_id] = start
            update[key] = start + n_new - 1
        if update.keys() - {"updated_at"}:
            transaction.set(counter_ref, update, merge=True)
        return starts

    return _txn(db_leka.transaction())


def read_counter(db_leka: firestore.Client) -> dict[str, int]:
    snap = db_leka.collection(MAPPING_COLLECTION).document(COUNTER_DOC).get()
    if not snap.exists:
        return {"fitness_next": 0, "playground_next": 0}
    d = snap.to_dict() or {}
    return {
        "fitness_next": int(d.get("fitness_next", 0)),
        "playground_next": int(d.get("playground_next", 0)),
    }


# ---------------------------------------------------------------------------
# Existing-mapping load
# ---------------------------------------------------------------------------
def load_mappings(db_leka: firestore.Client) -> dict[str, dict]:
    """Return {urbanix_doc_path: mapping_doc}."""
    out: dict[str, dict] = {}
    for doc in db_leka.collection(MAPPING_COLLECTION).stream():
        if doc.id == COUNTER_DOC:
            continue
        d = doc.to_dict() or {}
        path = d.get("urbanix_doc_path")
        if path:
            out[path] = {"_id": doc.id, **d}
    return out


# ---------------------------------------------------------------------------
# Medusa payload construction
# ---------------------------------------------------------------------------
def _strip_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _gather_image_urls(src: dict) -> list[str]:
    """Pull image URLs from the source doc.

    Source schema may carry images under `images[]` (storefront-ready) or
    `downloads[]` filtered by `type=image` / mime-type. Returns a de-duped
    list preserving insertion order.
    """
    urls: list[str] = []
    for img in (src.get("images") or []):
        u = img.get("url") if isinstance(img, dict) else img
        if u and u not in urls:
            urls.append(u)
    for dl in (src.get("downloads") or []):
        if not isinstance(dl, dict):
            continue
        t = (dl.get("type") or "").lower()
        fn = (dl.get("filename") or "").lower()
        if t in ("image", "photo") or any(fn.endswith(ext) for ext in
                                          (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            u = dl.get("url")
            if u and u not in urls:
                urls.append(u)
    return urls


def build_create_payload(src: dict, leka_sku: str, handle: str,
                          source_brand_internal: str, *, now_iso: str) -> dict:
    """Map an Urbanix product doc → Medusa create-product payload.

    Excludes pricing entirely (metadata.pricing_pending=true).
    Excludes Urbanix item code from variant SKU — uses leka_sku instead.
    Sanitizes title + description.
    """
    raw_name = src.get("product_name") or ""
    raw_desc = src.get("description") or ""
    title = sanitize(raw_name) or "Product"
    description = sanitize(raw_desc)

    images = _gather_image_urls(src)
    specs = src.get("specifications") or {}

    metadata = _strip_none({
        "brand_slug": "leka_project",
        "source_brand_internal": source_brand_internal,  # "urbanix_fitness" | "urbanix_playground"
        "source_system": "vendors/urbanix",
        "source_sha": src.get("source_sha") or None,
        "internal_sku": leka_sku,
        "category_inferred": src.get("category"),
        "subcategory": src.get("subcategory") or None,
        "specifications": specs or None,
        "pricing_pending": True,
        "imported_at": now_iso,
        "last_synced_at": now_iso,
    })

    variants = [{
        "title": "Default",
        "sku": leka_sku,
        "manage_inventory": False,
        "prices": [],  # explicit: no price rows, pricing is pending
        "options": {"Default": "Default"},
    }]

    payload = {
        "title": title,
        "handle": handle,
        "description": description,
        "status": "published",
        "sales_channels": [{"id": LEKA_PROJECT_SC_ID}],
        "metadata": metadata,
        "options": [{"title": "Default", "values": ["Default"]}],
        "variants": variants,
    }
    if images:
        payload["images"] = [{"url": u} for u in images]
        payload["thumbnail"] = images[0]
    return payload


def build_update_payload(src: dict, leka_sku: str, source_brand_internal: str,
                          *, existing_image_urls: set[str], now_iso: str) -> dict:
    """Refresh-only payload — title, description, metadata, image union.

    Handle + SKU are immutable post-import (mapping doc is authoritative).
    """
    raw_name = src.get("product_name") or ""
    raw_desc = src.get("description") or ""
    title = sanitize(raw_name) or "Product"
    description = sanitize(raw_desc)
    specs = src.get("specifications") or {}

    metadata = _strip_none({
        "brand_slug": "leka_project",
        "source_brand_internal": source_brand_internal,
        "source_system": "vendors/urbanix",
        "source_sha": src.get("source_sha") or None,
        "internal_sku": leka_sku,
        "category_inferred": src.get("category"),
        "subcategory": src.get("subcategory") or None,
        "specifications": specs or None,
        "pricing_pending": True,
        "last_synced_at": now_iso,
    })

    out: dict = {
        "title": title,
        "description": description,
        "metadata": metadata,
    }

    fs_urls = _gather_image_urls(src)
    new_urls = [u for u in fs_urls if u not in existing_image_urls]
    if new_urls:
        union = list(existing_image_urls) + new_urls
        out["images"] = [{"url": u} for u in union]
        if not existing_image_urls and fs_urls:
            out["thumbnail"] = fs_urls[0]
    return out


# ---------------------------------------------------------------------------
# Medusa lookup
# ---------------------------------------------------------------------------
def find_product(token: str, *, handle: str | None = None,
                  product_id: str | None = None) -> dict | None:
    if product_id:
        r = _request_with_retry(
            "GET", f"{BACKEND}/admin/products/{product_id}", token,
            params={"fields": "id,handle,thumbnail,images.url,metadata,variants.id,variants.sku"},
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("product")
    if handle:
        r = _request_with_retry(
            "GET", f"{BACKEND}/admin/products", token,
            params={"handle": handle, "limit": 1,
                    "fields": "id,handle,thumbnail,images.url,metadata,variants.id,variants.sku"},
        )
        r.raise_for_status()
        products = r.json().get("products", [])
        return products[0] if products else None
    return None


# ---------------------------------------------------------------------------
# Pre-scan: existing handles
# ---------------------------------------------------------------------------
def _load_existing_handles(token: str) -> set[str]:
    """Pull every leka-project-* handle so new nanoid handles don't collide."""
    seen: set[str] = set()
    offset = 0
    limit = 200
    while True:
        r = _request_with_retry(
            "GET", f"{BACKEND}/admin/products", token,
            params={"sales_channel_id[]": LEKA_PROJECT_SC_ID,
                    "limit": limit, "offset": offset, "fields": "id,handle"},
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return seen
        for p in batch:
            h = p.get("handle")
            if h:
                seen.add(h)
        if len(batch) < limit:
            return seen
        offset += limit


# ---------------------------------------------------------------------------
# Main import loop
# ---------------------------------------------------------------------------
def run_import(*, vendor_filter: str | None, dry_run: bool, limit: int | None) -> dict:
    db_src = firestore.Client(project=GCP_PROJECT, database=SRC_DB)
    db_leka = firestore.Client(project=GCP_PROJECT, database=DEST_DB)

    selected_slugs = (
        [VENDOR_SLUGS[vendor_filter]]
        if vendor_filter else list(VENDOR_SLUGS.values())
    )

    log.info("=== import_from_urbanix mode=%s vendors=%s limit=%s ===",
             "DRY-RUN" if dry_run else "WRITE", selected_slugs, limit)

    # Load source docs
    source_docs: dict[str, list[tuple[str, dict]]] = {}  # vendor_id -> [(doc_path, data)]
    for slug in selected_slugs:
        items = []
        for doc in db_src.collection("vendors").document(slug).collection("products").stream():
            items.append((doc.reference.path, doc.to_dict() or {}))
        items.sort(key=lambda kv: kv[0])  # deterministic
        if limit:
            items = items[:limit]
        source_docs[slug] = items
        log.info("[%s] %d source products loaded", slug, len(items))

    # Load existing mappings (idempotency keyset)
    mappings = load_mappings(db_leka)
    log.info("loaded %d existing mappings", len(mappings))

    # Bucket source docs into "new" and "existing"
    new_per_line: dict[str, list[tuple[str, dict]]] = {s: [] for s in selected_slugs}
    existing_to_refresh: list[tuple[str, dict, dict]] = []  # (path, source, mapping)
    for slug, items in source_docs.items():
        for path, data in items:
            if path in mappings:
                existing_to_refresh.append((path, data, mappings[path]))
            else:
                new_per_line[slug].append((path, data))

    log.info("new=%s | refresh=%d",
             {s: len(v) for s, v in new_per_line.items()}, len(existing_to_refresh))

    # Reserve sequential codes for new docs (one transaction)
    n_new_by_slug = {s: len(v) for s, v in new_per_line.items() if v}
    starts: dict[str, int] = {}
    if n_new_by_slug:
        if dry_run:
            cur = read_counter(db_leka)
            starts = {s: int(cur[LINE_COUNTER_KEY[s]]) + 1 for s in n_new_by_slug}
            log.info("[dry-run] would reserve codes: %s starting at %s", n_new_by_slug, starts)
        else:
            starts = reserve_codes(db_leka, n_new_by_slug)
            log.info("reserved codes: %s starting at %s", n_new_by_slug, starts)

    token = _auth()
    existing_handles = _load_existing_handles(token)
    log.info("preloaded %d existing leka-project-* handles", len(existing_handles))
    seen_handles = set(existing_handles)

    counts = {"created": 0, "refreshed": 0, "skipped_unchanged": 0, "errors": 0}
    sample_diffs: list[dict] = []
    request_n = 0

    def maybe_refresh_token():
        nonlocal token, request_n
        request_n += 1
        if request_n % TOKEN_REFRESH_EVERY == 0:
            token = _auth()

    # --- Phase 1: create new ---
    for slug, items in new_per_line.items():
        if not items:
            continue
        start_n = starts.get(slug, 0)
        for offset, (path, data) in enumerate(items):
            n = start_n + offset
            leka_sku = format_sku(slug, n)
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            handle = new_handle(seen_handles)
            payload = build_create_payload(
                data, leka_sku=leka_sku, handle=handle,
                source_brand_internal=slug, now_iso=now_iso,
            )

            if dry_run:
                if len(sample_diffs) < 5:
                    sample_diffs.append({
                        "leka_sku": leka_sku,
                        "urbanix_sku": data.get("sku"),
                        "urbanix_doc_path": path,
                        "title_after_sanitize": payload["title"],
                        "desc_after_sanitize_preview": (payload["description"] or "")[:160],
                    })
                counts["created"] += 1
                continue

            try:
                r = _request_with_retry(
                    "POST", f"{BACKEND}/admin/products", token,
                    json=payload,
                )
                if r.status_code >= 400:
                    log.warning("CREATE %s/%s failed: %s %s",
                                slug, leka_sku, r.status_code, r.text[:200])
                    counts["errors"] += 1
                    continue
                med_id = (r.json().get("product") or {}).get("id")
            except Exception as e:
                log.warning("CREATE %s/%s exception: %s", slug, leka_sku, e)
                counts["errors"] += 1
                continue

            # Write mapping doc atomically with create
            db_leka.collection(MAPPING_COLLECTION).document(leka_sku).set({
                "leka_sku": leka_sku,
                "urbanix_sku": data.get("sku"),
                "urbanix_doc_path": path,
                "urbanix_vendor_id": slug,
                "urbanix_source_sha": data.get("source_sha"),
                "medusa_product_id": med_id,
                "medusa_handle": handle,
                "imported_at": firestore.SERVER_TIMESTAMP,
                "last_synced_at": firestore.SERVER_TIMESTAMP,
                "pricelist_linked": bool((data.get("pricing") or {}).get("landed_thb")),
            })
            counts["created"] += 1
            maybe_refresh_token()

            if counts["created"] % 100 == 0:
                log.info("[%s] created %d / %d", slug, counts["created"],
                         sum(len(v) for v in new_per_line.values()))

    # --- Phase 2: refresh existing ---
    for path, data, mapping in existing_to_refresh:
        leka_sku = mapping["leka_sku"]
        slug = mapping["urbanix_vendor_id"]
        prior_sha = mapping.get("urbanix_source_sha")
        cur_sha = data.get("source_sha")

        if prior_sha and cur_sha and prior_sha == cur_sha:
            counts["skipped_unchanged"] += 1
            continue

        if dry_run:
            counts["refreshed"] += 1
            continue

        med_id = mapping.get("medusa_product_id")
        existing = find_product(token, product_id=med_id) if med_id else None
        if existing is None and mapping.get("medusa_handle"):
            existing = find_product(token, handle=mapping["medusa_handle"])
        if existing is None:
            log.warning("REFRESH %s: source doc remapped, but Medusa product missing "
                        "(handle=%s id=%s) — skipping",
                        leka_sku, mapping.get("medusa_handle"), med_id)
            counts["errors"] += 1
            continue

        existing_img_urls = {im.get("url") for im in (existing.get("images") or [])
                             if im.get("url")}
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        update = build_update_payload(
            data, leka_sku=leka_sku, source_brand_internal=slug,
            existing_image_urls=existing_img_urls, now_iso=now_iso,
        )

        try:
            r = _request_with_retry(
                "POST", f"{BACKEND}/admin/products/{existing['id']}", token,
                json=update,
            )
            if r.status_code >= 400:
                log.warning("REFRESH %s failed: %s %s",
                            leka_sku, r.status_code, r.text[:200])
                counts["errors"] += 1
                continue
        except Exception as e:
            log.warning("REFRESH %s exception: %s", leka_sku, e)
            counts["errors"] += 1
            continue

        db_leka.collection(MAPPING_COLLECTION).document(leka_sku).set({
            "urbanix_source_sha": cur_sha,
            "last_synced_at": firestore.SERVER_TIMESTAMP,
            "pricelist_linked": bool((data.get("pricing") or {}).get("landed_thb")),
        }, merge=True)
        counts["refreshed"] += 1
        maybe_refresh_token()

    log.info("=== summary: %s ===", counts)
    if dry_run and sample_diffs:
        log.info("--- sample diffs (first 5 new docs) ---")
        for s in sample_diffs:
            log.info("  %s ← %s (%s): %s",
                     s["leka_sku"], s["urbanix_sku"], Path(s["urbanix_doc_path"]).name,
                     s["title_after_sanitize"])
            if s["desc_after_sanitize_preview"]:
                log.info("    desc[:160]: %s", s["desc_after_sanitize_preview"])
    return counts


# ---------------------------------------------------------------------------
# Brand record refresh (Medusa SC description + pricing-config block)
# ---------------------------------------------------------------------------
NEW_SC_DESCRIPTION = (
    "Leka Project — house collection spanning early-years toys, "
    "commercial playground equipment, and outdoor fitness stations."
)


def refresh_brand_record(*, dry_run: bool) -> None:
    """One-shot, idempotent: refresh Medusa SC description + pricing-config brand block."""
    token = _auth()
    r = _request_with_retry(
        "GET", f"{BACKEND}/admin/sales-channels/{LEKA_PROJECT_SC_ID}", token,
    )
    sc = r.json().get("sales_channel", {})
    cur_desc = sc.get("description") or ""
    if cur_desc.strip() == NEW_SC_DESCRIPTION.strip():
        log.info("[brand] SC description already matches; skipping.")
    elif dry_run:
        log.info("[brand][dry-run] would update SC description: %r -> %r",
                 cur_desc[:80], NEW_SC_DESCRIPTION)
    else:
        r = _request_with_retry(
            "POST", f"{BACKEND}/admin/sales-channels/{LEKA_PROJECT_SC_ID}", token,
            json={"description": NEW_SC_DESCRIPTION},
        )
        r.raise_for_status()
        log.info("[brand] SC description refreshed.")

    # pricing-config brand block (Firestore DB leka-product-catalogs)
    db_leka = firestore.Client(project=GCP_PROJECT, database=DEST_DB)
    pc_ref = db_leka.collection("pricing_config").document("canonical")
    snap = pc_ref.get()
    if not snap.exists:
        log.warning("[brand] pricing_config/canonical missing — skipping block update.")
        return
    pc = snap.to_dict() or {}
    brands = pc.get("brands") or {}
    desired = {
        "display_name": "Leka Project",
        "internal_code_prefix": "LP",
        "internal_code_scheme": {
            "wisdom": "LP-XXXXXXXX (8-char nanoid)",
            "urbanix_fitness": "LP-F-####",
            "urbanix_playground": "LP-P-####",
        },
        "notes": ("House brand. Spans early-years toys (ex-Wisdom), commercial "
                  "playground equipment, and outdoor fitness stations."),
    }
    existing = brands.get("leka_project") or {}
    if all(existing.get(k) == v for k, v in desired.items()):
        log.info("[brand] pricing_config brands.leka_project already current; skipping.")
        return
    if dry_run:
        log.info("[brand][dry-run] would set pricing_config brands.leka_project = %s",
                 json.dumps(desired, indent=2))
        return
    pc_ref.set({"brands": {"leka_project": desired}}, merge=True)
    log.info("[brand] pricing_config brands.leka_project written.")


# ---------------------------------------------------------------------------
# Report mode — counts only, no writes
# ---------------------------------------------------------------------------
def report() -> None:
    db_src = firestore.Client(project=GCP_PROJECT, database=SRC_DB)
    db_leka = firestore.Client(project=GCP_PROJECT, database=DEST_DB)
    for slug in VENDOR_SLUGS.values():
        n = sum(1 for _ in db_src.collection("vendors").document(slug)
                .collection("products").stream())
        print(f"{slug}: {n} source products")
    cnt = read_counter(db_leka)
    print(f"counter: {cnt}")
    n_map = sum(1 for d in db_leka.collection(MAPPING_COLLECTION).stream() if d.id != COUNTER_DOC)
    print(f"urbanix_mapping/: {n_map} docs")


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------
def revert(*, dry_run: bool) -> None:
    """Remove imported Medusa products + clear mapping docs.

    Safety: only deletes Medusa products whose id is in urbanix_mapping/ AND
    whose metadata.source_system == 'vendors/urbanix'.
    """
    db_leka = firestore.Client(project=GCP_PROJECT, database=DEST_DB)
    token = _auth()
    deleted = 0
    skipped = 0
    for doc in db_leka.collection(MAPPING_COLLECTION).stream():
        if doc.id == COUNTER_DOC:
            continue
        d = doc.to_dict() or {}
        med_id = d.get("medusa_product_id")
        if not med_id:
            continue
        # Safety check via metadata.source_system
        try:
            existing = find_product(token, product_id=med_id)
        except Exception:
            existing = None
        if not existing:
            log.info("[revert] %s: product %s not found, dropping mapping only",
                     doc.id, med_id)
        else:
            ss = (existing.get("metadata") or {}).get("source_system")
            if ss != "vendors/urbanix":
                log.warning("[revert] %s: product %s metadata.source_system=%r != 'vendors/urbanix' — SKIP",
                            doc.id, med_id, ss)
                skipped += 1
                continue
            if dry_run:
                log.info("[revert][dry-run] would DELETE %s (%s)", doc.id, med_id)
            else:
                r = _request_with_retry("DELETE", f"{BACKEND}/admin/products/{med_id}", token)
                if r.status_code >= 400:
                    log.warning("[revert] DELETE %s failed: %s %s",
                                med_id, r.status_code, r.text[:200])
                    skipped += 1
                    continue
        if not dry_run:
            doc.reference.delete()
        deleted += 1
    log.info("=== revert: deleted=%d skipped=%d ===", deleted, skipped)
    # Counter is left in place so subsequent re-imports continue from the next code,
    # preserving the audit trail of historical numbers.


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--vendor", choices=list(VENDOR_SLUGS) + ["all"], default="all")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap N per vendor (smoke testing).")
    ap.add_argument("--report", action="store_true",
                    help="Print source counts + mapping/counter state, then exit.")
    ap.add_argument("--refresh-brand-only", action="store_true",
                    help="Skip product import; only refresh the SC description + pricing-config block.")
    ap.add_argument("--revert", action="store_true",
                    help="Delete imported Medusa products + clear mappings (safety-checked).")
    args = ap.parse_args()

    if args.report:
        report()
        return 0
    if args.revert:
        revert(dry_run=args.dry_run)
        return 0
    if args.refresh_brand_only:
        refresh_brand_record(dry_run=args.dry_run)
        return 0

    counts = run_import(
        vendor_filter=None if args.vendor == "all" else args.vendor,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    refresh_brand_record(dry_run=args.dry_run)
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
