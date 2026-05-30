"""Backfill product photos to Medusa for Eurotramp products.

Reads:
  - docs/reports/eurotramp-backfill-diff-<date>.json   (which products need backfill)
  - docs/reports/eurotramp-rehost-manifest-<date>.json (GCS proxy URLs to add)

For each affected product:
  1. Append new proxy URLs to images[] (preserves existing badges/certs).
  2. If thumbnail is non-photo (cert/badge/symbol/vector/placeholder), re-point
     it to the highest-rank `productdetails-*` or `<articleNo>-*` URL.
  3. Stash `metadata.previous_thumbnail` + `metadata.previous_images` for
     rollback, and write `metadata.photo_backfilled_at` for idempotency.

Usage:
    python scripts/backfill_eurotramp_photos_to_medusa.py --dry-run [--limit N]
    python scripts/backfill_eurotramp_photos_to_medusa.py [--limit N] [--force]
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
MEDUSA_URL = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
ADMIN_EMAIL = "admin@leka.studio"
ADMIN_PASSWORD = "LekaAdmin2026"

PHOTO_PREFIX_RANK = [
    ("productdetails-", 40),
    ("productdetail-", 35),
]


def filename_from_url(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?")[0]


def photo_rank(url: str) -> tuple[int, int]:
    fn = filename_from_url(url).lower()
    base = 0
    for prefix, score in PHOTO_PREFIX_RANK:
        if prefix in fn:
            base = score
            break
    if base == 0 and re.match(r"^e?\d{3,6}[-_]", fn):
        base = 20
    m = re.search(r"_(\d+)x(\d+)\.", fn)
    size = int(m.group(1)) * int(m.group(2)) if m else 0
    return (base, size)


def latest_diff_json() -> Path:
    files = sorted(REPORTS_DIR.glob("eurotramp-backfill-diff-*.json"))
    if not files:
        raise SystemExit("Run diff_eurotramp_scrape_vs_medusa.py first.")
    return files[-1]


def latest_manifest_json() -> Path:
    files = sorted(REPORTS_DIR.glob("eurotramp-rehost-manifest-*.json"))
    if not files:
        raise SystemExit("Run rehost_missing_eurotramp_photos.py first.")
    return files[-1]


def authenticate(session: requests.Session) -> str:
    r = session.post(
        f"{MEDUSA_URL}/auth/user/emailpass",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def admin_get(session: requests.Session, token: str, endpoint: str) -> dict:
    r = session.get(
        f"{MEDUSA_URL}{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {endpoint}: {r.text[:300]}")
    return r.json()


def admin_post(session: requests.Session, token: str, endpoint: str, payload: dict) -> dict:
    r = session.post(
        f"{MEDUSA_URL}{endpoint}",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {endpoint}: {r.text[:500]}")
    return r.json()


def find_product_by_handle(session, token, handle: str) -> dict | None:
    data = admin_get(
        session,
        token,
        f"/admin/products?handle={handle}&fields=id,handle,thumbnail,+images.url,metadata",
    )
    products = data.get("products", [])
    return products[0] if products else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true",
                        help="Re-apply even if metadata.photo_backfilled_at exists")
    parser.add_argument("--cert-thumbs-only", action="store_true",
                        help="Only re-point cert thumbnails; skip true backfill targets")
    args = parser.parse_args()

    diff_path = latest_diff_json()
    manifest_path = latest_manifest_json()
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    print(f"Diff:     {diff_path.name}")
    print(f"Manifest: {manifest_path.name}")
    print(f"DRY RUN" if args.dry_run else "LIVE RUN")

    by_handle_manifest = manifest["by_handle"]
    diffs = diff["diffs"]

    # Filter to products that need work:
    #   - backfill target with at least one new uploaded photo, OR
    #   - cert-thumb-with-photos product where we re-point thumbnail
    todo = []
    for d in diffs:
        is_target = d["is_backfill_target"]
        has_cert_thumb = d["thumb_kind"] == "cert"
        manifest_entries = by_handle_manifest.get(d["handle"], [])

        if args.cert_thumbs_only:
            if has_cert_thumb:
                todo.append(d)
            continue

        if is_target and manifest_entries:
            todo.append(d)
        elif has_cert_thumb:
            # No new photos needed (cert-thumb-with-photos) — just thumb re-point
            todo.append(d)

    if args.limit > 0:
        todo = todo[: args.limit]

    print(f"Products to update: {len(todo)}")

    session = requests.Session()
    token = authenticate(session)

    today_iso = datetime.datetime.utcnow().isoformat() + "Z"
    log: list[dict] = []
    n_updated = 0
    n_skipped = 0
    n_failed = 0

    for i, d in enumerate(todo, 1):
        handle = d["handle"]
        print(f"\n[{i}/{len(todo)}] {handle}")

        try:
            product = find_product_by_handle(session, token, handle)
        except Exception as e:
            print(f"  ✗ lookup failed: {e}")
            n_failed += 1
            log.append({"handle": handle, "status": "error", "error": str(e)})
            continue

        if product is None:
            print("  ✗ not found in Medusa")
            n_failed += 1
            log.append({"handle": handle, "status": "not_found"})
            continue

        meta = product.get("metadata") or {}
        if meta.get("photo_backfilled_at") and not args.force:
            print(f"  skip (already backfilled at {meta['photo_backfilled_at']})")
            n_skipped += 1
            continue

        # Build the new images[] list — preserve order: real photos first
        # (newly added), then existing non-photo content, dedup by URL.
        existing_images = product.get("images") or []
        existing_urls = [img["url"] for img in existing_images]
        existing_filenames = {filename_from_url(u).lower() for u in existing_urls}

        manifest_entries = by_handle_manifest.get(handle, [])
        new_urls = [m["proxy_url"] for m in manifest_entries]

        # Filter to only URLs whose filename isn't already in images[]
        added_new_urls = [
            u for u in new_urls
            if filename_from_url(u).lower() not in existing_filenames
        ]

        # Compose final images list: new photos first, then existing
        final_image_urls = added_new_urls + existing_urls
        # Dedup preserving order
        seen = set()
        deduped_urls = []
        for u in final_image_urls:
            if u not in seen:
                seen.add(u)
                deduped_urls.append(u)

        # Pick new thumbnail. Candidates: any photo in final_image_urls.
        # Prefer photos whose filename overlaps the product handle (so a
        # `kids-tramp-kindergarten` product doesn't grab an unrelated
        # `impactprotectionsystem` accessory photo).
        handle_tokens = {
            t for t in re.split(r"[-_]+", handle.lower())
            if t and t not in {"eurotramp", "the", "and", "for"}
        }

        def fn_tokens(fn: str) -> set[str]:
            # productdetails-wehrfritzfunroundplayground_<hash>_<size>.jpg
            #   → ['productdetails','wehrfritzfunroundplayground','hash','size','jpg']
            parts = re.split(r"[-_.]+", fn.lower())
            return {p for p in parts if p}

        def handle_overlap(fn: str) -> int:
            toks = fn_tokens(fn)
            # Substring match too (joined-word filenames)
            score = sum(1 for t in handle_tokens if t in toks)
            if score == 0:
                # joined-word handling: e.g. handle token "kindergarten" inside
                # filename word "97509-sport-thiemeadventure-trampkindergarten…"
                for word in toks:
                    for ht in handle_tokens:
                        if ht in word and len(ht) >= 4:
                            score += 1
            return score

        photo_candidates = []
        for u in deduped_urls:
            fn = filename_from_url(u).lower()
            if re.match(r"^e?\d{3,6}[-_]", fn) or "productdetails-" in fn or "productdetail-" in fn:
                photo_candidates.append(u)

        new_thumb = product.get("thumbnail")
        if photo_candidates:
            # Rank: handle-overlap first, then photo_rank().
            def rank_key(u: str) -> tuple:
                fn = filename_from_url(u).lower()
                return (handle_overlap(fn), *photo_rank(u))

            best = max(photo_candidates, key=rank_key)
            best_overlap = handle_overlap(filename_from_url(best).lower())

            current = product.get("thumbnail") or ""
            current_fn = filename_from_url(current).lower()
            is_current_photo = bool(
                re.match(r"^e?\d{3,6}[-_]", current_fn)
                or "productdetails-" in current_fn
                or "productdetail-" in current_fn
            )
            # Re-point only if (a) current thumb isn't already a photo AND
            # (b) the best candidate has at least one handle-token overlap
            # (avoids swapping in a wrong-product photo).
            if not is_current_photo and best_overlap > 0:
                new_thumb = best
            elif not is_current_photo and best_overlap == 0:
                print(f"  ! best candidate {filename_from_url(best)} has no handle-token overlap — leaving thumbnail unchanged")

        # Compute the changes
        thumb_changed = new_thumb != product.get("thumbnail")
        images_changed = deduped_urls != existing_urls

        if not thumb_changed and not images_changed:
            print("  skip (no change needed)")
            n_skipped += 1
            continue

        print(f"  images: {len(existing_urls)} → {len(deduped_urls)} (+{len(added_new_urls)})")
        if thumb_changed:
            print(f"  thumb : {filename_from_url(product.get('thumbnail') or '')}")
            print(f"       → {filename_from_url(new_thumb or '')}")

        # Build payload — include rollback metadata
        new_metadata = dict(meta)
        new_metadata["previous_thumbnail"] = product.get("thumbnail")
        new_metadata["previous_images"] = existing_urls
        new_metadata["photo_backfilled_at"] = today_iso

        payload = {
            "images": [{"url": u} for u in deduped_urls],
            "thumbnail": new_thumb,
            "metadata": new_metadata,
        }

        if args.dry_run:
            print("  [dry] skipping POST")
            log.append({"handle": handle, "status": "dry_run", "thumb_changed": thumb_changed,
                        "images_added": len(added_new_urls)})
            continue

        try:
            admin_post(session, token, f"/admin/products/{product['id']}", payload)
            n_updated += 1
            log.append({"handle": handle, "status": "updated", "thumb_changed": thumb_changed,
                        "images_added": len(added_new_urls)})
            time.sleep(0.2)  # gentle rate-limit
        except Exception as e:
            print(f"  ✗ update failed: {e}")
            n_failed += 1
            log.append({"handle": handle, "status": "error", "error": str(e)})

    # Save run log
    today = datetime.date.today().isoformat()
    log_path = REPORTS_DIR / f"eurotramp-backfill-log-{today}.json"
    log_path.write_text(
        json.dumps(
            {
                "generated_at": today_iso,
                "dry_run": args.dry_run,
                "totals": {"updated": n_updated, "skipped": n_skipped, "failed": n_failed},
                "log": log,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n=== DONE ===")
    print(f"Updated: {n_updated}")
    print(f"Skipped: {n_skipped}")
    print(f"Failed:  {n_failed}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
