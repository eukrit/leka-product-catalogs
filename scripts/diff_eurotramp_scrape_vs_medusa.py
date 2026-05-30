"""Diff a fresh Eurotramp scrape against the current Medusa image set.

For each Medusa Eurotramp product (from the audit JSON), find the matching
scraped product (by handle) and compute:
  - scraped_real_photos: photo-class URLs in the fresh scrape
  - medusa_filenames: filenames currently in Medusa
  - new_photo_urls: photos in scrape that aren't already in Medusa

Output: docs/reports/eurotramp-backfill-diff-<date>.json
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPE_JSON = REPO_ROOT / "data" / "scraped" / "eurotramp" / "products.json"
REPORTS_DIR = REPO_ROOT / "docs" / "reports"

# Reuse the classifier from reclassify_eurotramp_images.py
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "rec", str(REPO_ROOT / "scripts" / "reclassify_eurotramp_images.py")
)
_rec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rec)
classify = _rec.classify


def filename_from_url(url: str) -> str:
    if not url:
        return ""
    return url.rsplit("/", 1)[-1].split("?")[0]


def main() -> None:
    # Locate the most recent classified Medusa audit JSON.
    audits = sorted(REPORTS_DIR.glob("eurotramp-image-audit-*-classified.json"))
    if not audits:
        raise SystemExit("No classified audit JSON found — run reclassify_eurotramp_images.py first.")
    audit_path = audits[-1]

    if not SCRAPE_JSON.exists():
        raise SystemExit(
            f"Fresh scrape not found at {SCRAPE_JSON} — run scripts/scrape-eurotramp.ts first."
        )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    scrape = json.loads(SCRAPE_JSON.read_text(encoding="utf-8"))

    by_handle: dict[str, dict] = {p["handle"]: p for p in scrape}

    today = datetime.date.today().isoformat()
    out_path = REPORTS_DIR / f"eurotramp-backfill-diff-{today}.json"

    targets = [r for r in audit["rows"] if r["is_backfill_target"]]
    cert_thumbs_with_photos = [
        r
        for r in audit["rows"]
        if r["thumb_kind"] == "cert" and not r["is_backfill_target"]
    ]

    print(f"Audit: {audit_path.name}")
    print(f"Backfill targets: {len(targets)}")
    print(f"Cert-thumb (photos available): {len(cert_thumbs_with_photos)}")
    print(f"Scrape: {len(scrape)} products")

    diffs: list[dict] = []
    upstream_gap: list[str] = []
    not_in_scrape: list[str] = []

    for r in audit["rows"]:
        handle = r["handle"]
        scraped = by_handle.get(handle)
        if scraped is None:
            # Not present in the fresh scrape — likely a sub-handle or
            # accessory whose vendor URL wasn't crawled.
            if r["is_backfill_target"] or r["thumb_kind"] == "cert":
                not_in_scrape.append(handle)
            continue

        scrape_urls = scraped.get("image_urls", []) or []
        # Classify each scraped URL by filename
        scraped_photos = [u for u in scrape_urls if classify(filename_from_url(u)) == "photo"]

        # Current Medusa filename set (lowercased for case-insensitive match)
        medusa_filenames = {fn.lower() for fn in r["image_filenames"]}
        if r["thumbnail"]:
            medusa_filenames.add(filename_from_url(r["thumbnail"]).lower())

        # New photos = scraped photos whose filename isn't already in Medusa
        new_photos = [
            u for u in scraped_photos
            if filename_from_url(u).lower() not in medusa_filenames
        ]

        # Dedup by filename (prefer the largest size — heuristic: longest URL)
        by_fn: dict[str, str] = {}
        for u in new_photos:
            fn = filename_from_url(u)
            if fn not in by_fn or len(u) > len(by_fn[fn]):
                by_fn[fn] = u
        new_photos_dedup = list(by_fn.values())

        # Pick best thumbnail candidate — prefer `productdetails-` or
        # highest-size `<articleNo>-` photo. Fall back to first photo.
        def thumb_rank(url: str) -> tuple[int, int]:
            fn = filename_from_url(url).lower()
            base_score = 0
            if "productdetails-" in fn:
                base_score = 30
            elif "productdetail-" in fn:
                base_score = 25
            elif re.match(r"^e?\d{3,6}[-_].*?\d+x\d+", fn):
                base_score = 20
            elif re.match(r"^e?\d{3,6}[-_]", fn):
                base_score = 15
            # Larger image dimension > smaller. Extract trailing _WxH.
            m = re.search(r"_(\d+)x(\d+)\.", fn)
            size = int(m.group(1)) * int(m.group(2)) if m else 0
            return (base_score, size)

        all_photo_urls = scraped_photos[:]  # includes ones Medusa already has
        # Combine: prefer new + existing
        ranked = sorted(all_photo_urls, key=thumb_rank, reverse=True)
        best_thumb = ranked[0] if ranked else None

        # Flag: target with no upstream photo either
        if r["is_backfill_target"] and not scraped_photos:
            upstream_gap.append(handle)

        diffs.append(
            {
                "handle": handle,
                "title": r["title"],
                "is_backfill_target": r["is_backfill_target"],
                "thumb_kind": r["thumb_kind"],
                "current_thumbnail": r["thumbnail"],
                "scraped_photo_count": len(scraped_photos),
                "scraped_photo_urls": scraped_photos,
                "new_photo_urls": new_photos_dedup,
                "best_thumb_candidate": best_thumb,
                "vendor_url": r.get("vendor_url", ""),
            }
        )

    out = {
        "generated_at": today,
        "audit_source": audit_path.name,
        "scrape_source": str(SCRAPE_JSON.relative_to(REPO_ROOT)),
        "summary": {
            "diffs": len(diffs),
            "backfill_targets_with_upstream_photos": sum(
                1 for d in diffs if d["is_backfill_target"] and d["scraped_photo_count"] > 0
            ),
            "backfill_targets_no_upstream_photos": len(upstream_gap),
            "targets_not_in_scrape": len(not_in_scrape),
            "cert_thumb_with_photos": len(cert_thumbs_with_photos),
        },
        "upstream_gap_handles": upstream_gap,
        "not_in_scrape_handles": not_in_scrape,
        "diffs": diffs,
    }

    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n=== DONE ===")
    for k, v in out["summary"].items():
        print(f"  {k}: {v}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
