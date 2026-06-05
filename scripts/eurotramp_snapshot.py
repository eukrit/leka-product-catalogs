"""Snapshot every Eurotramp product in the live Medusa catalog.

Writes a full pre-change backup (id, handle, title, status, thumbnail, images,
variants, options, categories, collection, metadata, brand) to
`docs/reports/eurotramp-snapshot-<date>.json`. Re-run after each phase and diff
against the Phase-0 snapshot to confirm only intended fields changed.

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD (or
MEDUSA_ADMIN_EMAIL / MEDUSA_ADMIN_PASSWORD), or GCP Secret Manager secrets
`medusa-admin-email` / `medusa-admin-password` (pulled by the caller into env).

Usage:
    python scripts/eurotramp_snapshot.py                 # writes dated snapshot
    python scripts/eurotramp_snapshot.py --tag pre-phase1
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
REPORTS_DIR = REPO_ROOT / "docs" / "reports"

from shared.medusa_importer import MedusaImporter  # noqa: E402

MEDUSA_URL = os.environ.get(
    "MEDUSA_BACKEND_URL",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)

# Heavy field set — everything we might mutate, so the snapshot is a true backup.
FIELDS = ",".join([
    "id", "handle", "title", "status", "thumbnail", "subtitle",
    "images.id", "images.url",
    "variants.id", "variants.sku", "variants.title",
    "variants.options.option_id", "variants.options.value",
    "options.id", "options.title", "options.values.value",
    "categories.id", "categories.name", "categories.handle",
    "collection.id", "collection.title", "collection.handle",
    "metadata",
    "brand.id", "brand.handle", "brand.name",
])


def _env_alias() -> None:
    """MedusaImporter reads MEDUSA_ADMIN_EMAIL/PASSWORD; mirror the LEKA_* names."""
    if not os.environ.get("MEDUSA_ADMIN_EMAIL") and os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL"):
        os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ["LEKA_MEDUSA_ADMIN_EMAIL"]
    if not os.environ.get("MEDUSA_ADMIN_PASSWORD") and os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD"):
        os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]


def fetch_eurotramp_products(client: MedusaImporter) -> list[dict]:
    out: list[dict] = []
    offset, limit = 0, 200
    while True:
        r = client._get("/admin/products", {"limit": limit, "offset": offset, "fields": FIELDS})
        batch = r.get("products", [])
        if not batch:
            break
        for p in batch:
            handle = p.get("handle") or ""
            brand = p.get("brand") if isinstance(p.get("brand"), dict) else {}
            if handle.startswith("eurotramp-") or (brand or {}).get("handle") == "eurotramp":
                out.append(p)
        offset += limit
    out.sort(key=lambda p: p.get("handle") or "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="", help="Optional filename tag, e.g. pre-phase1")
    args = ap.parse_args()

    _env_alias()
    client = MedusaImporter(base_url=MEDUSA_URL)
    if not client.api_key:
        print("ERROR: no Medusa admin auth. Set LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD.", file=sys.stderr)
        return 2

    products = fetch_eurotramp_products(client)
    today = datetime.date.today().isoformat()
    now = datetime.datetime.utcnow().isoformat() + "Z"

    status_counts: dict[str, int] = {}
    cat_counts: dict[str, int] = {}
    for p in products:
        status_counts[p.get("status", "?")] = status_counts.get(p.get("status", "?"), 0) + 1
        cats = p.get("categories") or []
        if not cats:
            cat_counts["<none>"] = cat_counts.get("<none>", 0) + 1
        for c in cats:
            h = c.get("handle", "?")
            cat_counts[h] = cat_counts.get(h, 0) + 1

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"-{args.tag}" if args.tag else ""
    out_path = REPORTS_DIR / f"eurotramp-snapshot-{today}{tag}.json"
    out_path.write_text(
        json.dumps(
            {
                "generated_at": now,
                "backend": MEDUSA_URL,
                "count": len(products),
                "status_counts": status_counts,
                "category_counts": cat_counts,
                "products": products,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Snapshot written: {out_path}")
    print(f"  products: {len(products)}")
    print(f"  status:   {status_counts}")
    print(f"  categories (top): {dict(sorted(cat_counts.items(), key=lambda kv: -kv[1])[:15])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
