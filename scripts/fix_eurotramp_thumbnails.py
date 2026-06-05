"""Fix Eurotramp PDP thumbnails: re-point any product whose thumbnail is a
non-photo (cert / feature-badge / symbol / vector / placeholder / unknown) to
the best real product photo already present in its gallery, and reorder
images[] so real photos come first. Never drops any image.

Works directly off the live Medusa catalog — no scrape / TS audit needed.
Reuses `reclassify_eurotramp_images.classify` and the handle-token-overlap
guard from `backfill_eurotramp_photos_to_medusa` so a product never grabs an
unrelated accessory's photo.

Rollback: stashes metadata.previous_thumbnail / previous_images /
thumbnail_fixed_at once (idempotent). `--rollback` restores them.

Usage:
    python scripts/fix_eurotramp_thumbnails.py --dry-run
    python scripts/fix_eurotramp_thumbnails.py --apply [--limit N] [--force]
    python scripts/fix_eurotramp_thumbnails.py --rollback
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
REPORTS_DIR = REPO_ROOT / "docs" / "reports"

from shared.medusa_importer import MedusaImporter  # noqa: E402
from reclassify_eurotramp_images import classify  # noqa: E402

MEDUSA_URL = os.environ.get(
    "MEDUSA_BACKEND_URL",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)

PHOTO_PREFIX_RANK = [("productdetails-", 40), ("productdetail-", 35)]


def _env_alias() -> None:
    for a, b in (("LEKA_MEDUSA_ADMIN_EMAIL", "MEDUSA_ADMIN_EMAIL"),
                 ("LEKA_MEDUSA_ADMIN_PASSWORD", "MEDUSA_ADMIN_PASSWORD")):
        if not os.environ.get(b) and os.environ.get(a):
            os.environ[b] = os.environ[a]


def fn_of(url: str) -> str:
    return (url or "").rsplit("/", 1)[-1].split("?")[0]


def photo_rank(url: str) -> tuple[int, int]:
    fn = fn_of(url).lower()
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


def fetch_eurotramp(client: MedusaImporter) -> list[dict]:
    fields = "id,handle,thumbnail,images.url,metadata"
    out, offset, limit = [], 0, 200
    while True:
        r = client._get("/admin/products", {"limit": limit, "offset": offset, "fields": fields})
        batch = r.get("products", [])
        if not batch:
            break
        out += [p for p in batch if (p.get("handle") or "").startswith("eurotramp-")]
        offset += limit
    out.sort(key=lambda p: p["handle"])
    return out


def handle_tokens(handle: str) -> set[str]:
    return {t for t in re.split(r"[-_]+", handle.lower())
            if t and t not in {"eurotramp", "the", "and", "for"}}


def handle_overlap(fn: str, htoks: set[str]) -> int:
    toks = {p for p in re.split(r"[-_.]+", fn.lower()) if p}
    score = sum(1 for t in htoks if t in toks)
    if score == 0:
        for word in toks:
            for ht in htoks:
                if ht in word and len(ht) >= 4:
                    score += 1
    return score


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--rollback", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    _env_alias()
    client = MedusaImporter(base_url=MEDUSA_URL)
    if not client.api_key:
        print("ERROR: no Medusa admin auth.", file=sys.stderr)
        return 2

    products = fetch_eurotramp(client)
    if args.limit:
        products = products[: args.limit]
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    log, n_changed, n_fail = [], 0, 0

    # ── Rollback mode ──────────────────────────────────────────────────
    if args.rollback:
        for p in products:
            meta = dict(p.get("metadata") or {})
            if "previous_thumbnail" not in meta and "previous_images" not in meta:
                continue
            payload = {
                "thumbnail": meta.get("previous_thumbnail"),
                "images": [{"url": u} for u in (meta.get("previous_images") or [])],
            }
            for k in ("previous_thumbnail", "previous_images", "thumbnail_fixed_at"):
                meta.pop(k, None)
            payload["metadata"] = meta
            try:
                client._post(f"/admin/products/{p['id']}", payload)
                n_changed += 1
                print(f"  rolled back {p['handle']}")
            except Exception as e:
                n_fail += 1
                print(f"  ! rollback failed {p['handle']}: {e}")
        print(f"\nROLLBACK done: {n_changed} restored, {n_fail} failed")
        return 0

    # ── Re-pick mode ───────────────────────────────────────────────────
    for i, p in enumerate(products, 1):
        h = p["handle"]
        meta = dict(p.get("metadata") or {})
        if meta.get("thumbnail_fixed_at") and not args.force:
            continue

        urls = [im["url"] for im in (p.get("images") or [])]
        thumb = p.get("thumbnail")
        thumb_kind = classify(fn_of(thumb)) if thumb else "none"

        # Only touch products whose thumbnail is wrong (non-photo). Products
        # that already show a real photo are left untouched (no gallery churn).
        if thumb_kind == "photo" and not args.force:
            continue

        photos = [u for u in urls if classify(fn_of(u)) == "photo"]
        if not photos:
            continue  # zero-photo target — handled by the backfill pipeline

        htoks = handle_tokens(h)
        best = max(photos, key=lambda u: (handle_overlap(fn_of(u), htoks), *photo_rank(u)))
        best_overlap = handle_overlap(fn_of(best), htoks)

        # Reorder images: real photos first (ranked), then the rest, dedup.
        ranked_photos = sorted(photos, key=lambda u: (handle_overlap(fn_of(u), htoks), *photo_rank(u)), reverse=True)
        rest = [u for u in urls if u not in set(ranked_photos)]
        new_urls, seen = [], set()
        for u in ranked_photos + rest:
            if u not in seen:
                seen.add(u)
                new_urls.append(u)

        # New thumbnail: only change if current isn't already a photo and the
        # best candidate is relevant to this product (overlap > 0).
        new_thumb = thumb
        if thumb_kind != "photo" and best_overlap > 0:
            new_thumb = best
        elif thumb_kind != "photo" and best_overlap == 0:
            # leave thumbnail; flag for manual review (wrong-product risk)
            log.append({"handle": h, "status": "skipped_no_overlap",
                        "best_candidate": fn_of(best)})
            continue

        thumb_changed = new_thumb != thumb
        images_changed = new_urls != urls
        if not (thumb_changed or images_changed):
            continue

        print(f"[{i}/{len(products)}] {h}")
        if thumb_changed:
            print(f"   thumb: {thumb_kind} {fn_of(thumb)} -> photo {fn_of(new_thumb)}")
        if images_changed:
            print(f"   images reordered (photos-first), {len(urls)} -> {len(new_urls)}")

        if args.dry_run:
            log.append({"handle": h, "status": "dry_run", "thumb_changed": thumb_changed,
                        "images_reordered": images_changed})
            n_changed += 1
            continue

        meta.setdefault("previous_thumbnail", thumb)
        meta.setdefault("previous_images", urls)
        meta["thumbnail_fixed_at"] = now
        payload = {"thumbnail": new_thumb, "images": [{"url": u} for u in new_urls], "metadata": meta}
        try:
            client._post(f"/admin/products/{p['id']}", payload)
            n_changed += 1
            log.append({"handle": h, "status": "updated", "thumb_changed": thumb_changed})
            time.sleep(0.15)
        except Exception as e:
            n_fail += 1
            log.append({"handle": h, "status": "error", "error": str(e)})
            print(f"   ! failed: {e}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"eurotramp-thumbnail-fix-{today}.json"
    out_path.write_text(json.dumps({
        "generated_at": now, "mode": "dry-run" if args.dry_run else "apply",
        "totals": {"changed": n_changed, "failed": n_fail}, "log": log,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    skipped = [r for r in log if r.get("status") == "skipped_no_overlap"]
    print(f"\n=== {'DRY-RUN' if args.dry_run else 'APPLY'} ===")
    print(f"changed: {n_changed}, failed: {n_fail}, skipped(no-overlap): {len(skipped)}")
    if skipped:
        print("  skipped (manual review):", [r['handle'] for r in skipped])
    print(f"report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
