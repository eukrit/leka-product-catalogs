"""Relink Vinci Play products to their series collections.

Symptom: catalogs.leka.studio/vinci series badges render correctly but
clicking one returns 0 products. Root cause: 1,096 Vinci products in
Medusa have `collection_id = null` even though `metadata.series_slug`
is populated. The /vinci import was re-run at some point with a code
path that wrote products without the `collection_id` field
(`handle = vinci-{item_code}` — the series segment dropped — confirms
a different import shape). Berliner / 4soft / Vortex are not affected.

This script reads `metadata.series_slug` and `metadata.series_name` from
each Vinci product, gets-or-creates the matching Medusa collection
(`title=series_name, handle=series_slug`), and PATCHes the product to
set `collection_id`. Idempotent.

Auth: requires MEDUSA_ADMIN_EMAIL + MEDUSA_ADMIN_PASSWORD (or
MEDUSA_ADMIN_API_KEY) and MEDUSA_BACKEND_URL.
"""
import argparse
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.medusa_importer import MedusaImporter


VINCI_SALES_CHANNEL_ID = "sc_01KNKTHC77716EPCE3E2BKAMQP"


def iter_vinci_products(client: MedusaImporter, page_size: int = 200):
    offset = 0
    while True:
        resp = client._get(
            "/admin/products",
            {
                "sales_channel_id[]": VINCI_SALES_CHANNEL_ID,
                "limit": page_size,
                "offset": offset,
                "fields": "id,handle,collection_id,+metadata",
            },
        )
        batch = resp.get("products", [])
        for p in batch:
            yield p
        if len(batch) < page_size:
            return
        offset += page_size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--medusa-url",
        default=os.environ.get("MEDUSA_BACKEND_URL")
        or "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
    )
    args = parser.parse_args()

    client = MedusaImporter(base_url=args.medusa_url)

    products = list(iter_vinci_products(client))
    print(f"Fetched {len(products)} Vinci products")

    by_slug: dict[str, str] = {}
    missing_slug = 0
    already_linked = 0
    needs_relink: list[tuple[str, str, str]] = []  # (product_id, handle, slug)

    for p in products:
        meta = p.get("metadata") or {}
        slug = (meta.get("series_slug") or "").strip()
        name = (meta.get("series_name") or slug.upper()).strip()
        if not slug:
            missing_slug += 1
            continue
        if p.get("collection_id"):
            already_linked += 1
            continue
        if slug not in by_slug:
            by_slug[slug] = name
        needs_relink.append((p["id"], p["handle"], slug))

    slug_counts = Counter(s for _, _, s in needs_relink)
    print(
        f"\nNeeds relink: {len(needs_relink)} | already linked: {already_linked} | "
        f"missing series_slug: {missing_slug}"
    )
    print(f"Distinct series: {len(slug_counts)}")
    for slug, n in slug_counts.most_common():
        print(f"  {slug:30s} {n:4d} products  -> {by_slug[slug]}")

    if args.dry_run:
        print("\nDRY RUN — no writes.")
        return

    print("\nGet-or-create collections...")
    collection_ids: dict[str, str] = {}
    for slug, name in by_slug.items():
        cid = client.get_or_create_collection(name, slug)
        collection_ids[slug] = cid
        print(f"  {slug} -> {cid}")

    print(f"\nPatching {len(needs_relink)} products...")
    ok = 0
    err = 0
    for i, (pid, handle, slug) in enumerate(needs_relink, 1):
        try:
            client.set_product_collection(pid, collection_ids[slug])
            ok += 1
            if i % 50 == 0:
                print(f"  {i}/{len(needs_relink)} done")
                time.sleep(0.1)
        except Exception as e:
            err += 1
            print(f"  ERROR {handle}: {e}")

    print(f"\nDone. patched={ok} errors={err}")


if __name__ == "__main__":
    main()
