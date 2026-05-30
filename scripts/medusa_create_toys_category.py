"""Create top-level Medusa product categories matching the AI taxonomy, then
assign every Wisdom/Leka Project product whose `metadata.category_inferred`
matches.

Why
---
Wisdom products were imported with `category_ids=[]` so the Medusa Admin
shows them as uncategorised. After `enrich_wisdom_with_ai.py` writes
`metadata.category_inferred = "toys" | "playground_equipment" | ...`, this
script:

  1. Ensures each top-level category exists in Medusa (creates if missing).
  2. For every Wisdom product, looks up its `category_inferred`, and adds the
     category to `product.categories` if not already present.

Categories created (mirrors CATEGORY_VOCAB in enrich_wisdom_with_ai.py):
  - Toys
  - Playground Equipment
  - Kids Furniture
  - Arts & Crafts
  - Educational Manipulatives
  - Music Instruments
  - Role Play
  - Sports & Outdoor
  - Infant & Toddler
  - Water Play
  - Sand Play
  - Climbing
  - Ride-Ons
  - Books & Media
  - Safety & Accessories
  - Other

Usage
-----
    python scripts/medusa_create_toys_category.py --ensure-categories
    python scripts/medusa_create_toys_category.py --link --dry-run
    python scripts/medusa_create_toys_category.py --link
    python scripts/medusa_create_toys_category.py --report
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests  # noqa: E402
from google.cloud import secretmanager  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("medusa_categories")

PROJECT = "ai-agents-go"
MEDUSA_BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
STORE_PK = "pk_b7d7b7412262b05054450cd08213cd3d7d3432616ffff885e4c8a57e1b596e53"
TIMEOUT = 60

# Map enrichment vocab -> display name + handle
CATEGORIES = [
    ("toys",                      "Toys",                       "toys"),
    ("playground_equipment",      "Playground Equipment",       "playground-equipment"),
    ("kids_furniture",            "Kids Furniture",             "kids-furniture"),
    ("arts_crafts",               "Arts & Crafts",              "arts-crafts"),
    ("educational_manipulatives", "Educational Manipulatives",  "educational-manipulatives"),
    ("music_instruments",         "Music Instruments",          "music-instruments"),
    ("role_play",                 "Role Play",                  "role-play"),
    ("sports_outdoor",            "Sports & Outdoor",           "sports-outdoor"),
    ("infant_toddler",            "Infant & Toddler",           "infant-toddler"),
    ("water_play",                "Water Play",                 "water-play"),
    ("sand_play",                 "Sand Play",                  "sand-play"),
    ("climbing",                  "Climbing",                   "climbing"),
    ("ride_on",                   "Ride-Ons",                   "ride-ons"),
    ("books_media",               "Books & Media",              "books-media"),
    ("safety_accessories",        "Safety & Accessories",       "safety-accessories"),
    ("other",                     "Other",                      "other"),
]


def _sm_secret(name: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{PROJECT}/secrets/{name}/versions/latest"
    return client.access_secret_version(name=path).payload.data.decode().strip()


def _medusa_admin_token() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL") or _sm_secret("medusa-admin-email")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD") or _sm_secret("medusa-admin-password")
    r = requests.post(
        f"{MEDUSA_BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        log.error("admin auth returned no token: %s", r.text[:200])
        sys.exit(2)
    log.info("Medusa admin auth OK (%s)", email)
    return tok


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _retry(method: str, url: str, tok: str | None, *, json_body=None, params=None,
           max_attempts: int = 5):
    delays = [2, 5, 15, 45]
    last: Exception | None = None
    for attempt in range(max_attempts):
        try:
            headers = _hdr(tok) if tok else None
            r = requests.request(method, url, headers=headers, json=json_body,
                                  params=params, timeout=TIMEOUT)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
            return r
        except (requests.RequestException, requests.HTTPError) as e:
            last = e
            if attempt == len(delays):
                break
            time.sleep(delays[attempt] + random.random() * 2)
    raise last if last else RuntimeError("retry exhausted")


def list_categories(tok: str) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        r = _retry("GET", f"{MEDUSA_BACKEND}/admin/product-categories", tok,
                   params={"limit": 100, "offset": offset, "fields": "id,name,handle"})
        r.raise_for_status()
        batch = r.json().get("product_categories", [])
        if not batch:
            break
        out.extend(batch)
        offset += 100
    return out


def ensure_category(tok: str, name: str, handle: str) -> str:
    """Find or create a top-level product category. Match on EXACT handle only —
    matching by name picks up legacy subcategories (e.g. `leka-project-outdoor-climbing`
    named 'Climbing') and blocks creation of the clean top-level handle.
    Returns its id."""
    cats = list_categories(tok)
    for c in cats:
        if c.get("handle") == handle:
            log.info("  exists: %s (%s)", name, c["id"])
            return c["id"]
    r = _retry("POST", f"{MEDUSA_BACKEND}/admin/product-categories", tok, json_body={
        "name": name,
        "handle": handle,
        "is_active": True,
        "is_internal": False,
    })
    r.raise_for_status()
    cid = r.json()["product_category"]["id"]
    log.info("  created: %s (%s)", name, cid)
    return cid


def cmd_ensure(args) -> None:
    tok = _medusa_admin_token()
    log.info("Ensuring %d categories exist...", len(CATEGORIES))
    ids: dict[str, str] = {}
    for vocab, name, handle in CATEGORIES:
        ids[vocab] = ensure_category(tok, name, handle)
    log.info("Done. vocab -> id map:")
    for v, i in ids.items():
        log.info("  %-28s %s", v, i)


def iter_wisdom_products(pk: str):
    """Yield {id, handle, title, category_inferred, category_ids[]} for every
    Wisdom-origin product on the Leka Project sales channel."""
    offset = 0
    while True:
        r = requests.get(
            f"{MEDUSA_BACKEND}/store/products",
            headers={"x-publishable-api-key": pk},
            params={
                "limit": 100,
                "offset": offset,
                "fields": "id,handle,title,metadata,categories.id,categories.handle",
            },
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            meta = p.get("metadata") or {}
            if meta.get("source_brand_internal") != "wisdom":
                continue
            yield {
                "id": p["id"],
                "handle": p.get("handle"),
                "title": p.get("title"),
                "category_inferred": meta.get("category_inferred"),
                "current_category_ids": [c["id"] for c in (p.get("categories") or [])],
                "current_category_handles": [c.get("handle") for c in (p.get("categories") or [])],
            }
        offset += 100


def cmd_link(args) -> None:
    tok = _medusa_admin_token()

    # Build vocab->id map from existing categories (assumes --ensure-categories ran).
    cats = list_categories(tok)
    handle_to_id = {c["handle"]: c["id"] for c in cats if c.get("handle")}
    vocab_to_id: dict[str, str] = {}
    for vocab, _name, handle in CATEGORIES:
        if handle in handle_to_id:
            vocab_to_id[vocab] = handle_to_id[handle]
    missing = [v for v, _, _ in CATEGORIES if v not in vocab_to_id]
    if missing:
        log.error("Missing categories in Medusa: %s -- run --ensure-categories first",
                  missing)
        sys.exit(2)

    log.info("Enumerating Wisdom products...")
    products = list(iter_wisdom_products(STORE_PK))
    log.info("  %d products", len(products))

    counts: dict[str, int] = {"linked": 0, "already": 0, "no_vocab": 0,
                              "unknown_vocab": 0, "errors": 0, "dry": 0}
    cat_counts: dict[str, int] = {}
    started = time.time()
    todo = products if not args.limit else products[: args.limit]

    for i, p in enumerate(todo, 1):
        vocab = p.get("category_inferred")
        if not vocab:
            counts["no_vocab"] += 1
            continue
        cid = vocab_to_id.get(vocab)
        if not cid:
            counts["unknown_vocab"] += 1
            continue
        if cid in p["current_category_ids"]:
            counts["already"] += 1
            continue
        new_ids = list(p["current_category_ids"]) + [cid]
        cat_counts[vocab] = cat_counts.get(vocab, 0) + 1
        if args.dry_run:
            counts["dry"] += 1
            if i <= 3:
                log.info("  [dry] %s -> +%s", p.get("handle"), vocab)
            continue
        try:
            # Medusa v2 admin: pass `categories: [{id}]`, NOT `category_ids`.
            r = _retry("POST", f"{MEDUSA_BACKEND}/admin/products/{p['id']}", tok,
                       json_body={"categories": [{"id": x} for x in new_ids]})
            r.raise_for_status()
            counts["linked"] += 1
        except Exception as e:
            log.error("  link %s failed: %s", p["id"], str(e)[:200])
            counts["errors"] += 1
        if i % 100 == 0 or i == len(todo):
            rate = i / max(time.time() - started, 0.001)
            log.info("  %d/%d (%.1f/s) %s", i, len(todo), rate, counts)

    log.info("Link done in %.1fs: %s", time.time() - started, counts)
    if cat_counts:
        log.info("Newly linked by category:")
        for c, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
            log.info("  %-28s %d", c, n)


def cmd_report(args) -> None:
    """Show per-category product counts for the Wisdom set."""
    counts: dict[str, int] = {}
    none = 0
    total = 0
    for p in iter_wisdom_products(STORE_PK):
        total += 1
        v = p.get("category_inferred") or ""
        if v:
            counts[v] = counts.get(v, 0) + 1
        else:
            none += 1
    log.info("Wisdom catalog category distribution (from metadata.category_inferred):")
    log.info("  total: %d", total)
    log.info("  unenriched (no category_inferred): %d", none)
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        log.info("  %-28s %d", c, n)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ensure-categories", action="store_true")
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    chosen = sum([args.ensure_categories, args.link, args.report])
    if chosen == 0:
        ap.print_help()
        sys.exit(2)
    if chosen > 1:
        log.error("Pick one mode at a time.")
        sys.exit(2)

    if args.ensure_categories:
        cmd_ensure(args)
    elif args.link:
        cmd_link(args)
    elif args.report:
        cmd_report(args)


if __name__ == "__main__":
    main()
