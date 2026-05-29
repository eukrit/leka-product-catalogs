"""Download the new Eurotramp photo URLs identified by
diff_eurotramp_scrape_vs_medusa.py and upload them to
``gs://ai-agents-go-vendors/eurotramp/<handle>/<filename>``.

The image proxy at ``catalogs.leka.studio/api/i/eurotramp/<handle>/...``
reads from this bucket layout.

Usage:
    python scripts/rehost_missing_eurotramp_photos.py [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
GCS_BUCKET = "ai-agents-go-vendors"
GCS_PREFIX = "eurotramp"
PROXY_BASE = "https://catalogs.leka.studio/api/i"

UA = "AredaCatalogBot/1.0 (Eurotramp photo backfill; +https://catalogs.leka.studio)"

# Try google-cloud-storage; fall back to gsutil/gcloud for environments
# that don't have the SDK installed.
try:
    from google.cloud import storage  # type: ignore
    _GCS_SDK = True
except Exception:
    _GCS_SDK = False


def latest_diff_json() -> Path:
    files = sorted(REPORTS_DIR.glob("eurotramp-backfill-diff-*.json"))
    if not files:
        raise SystemExit("Run scripts/diff_eurotramp_scrape_vs_medusa.py first.")
    return files[-1]


def filename_from_url(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?")[0]


def upload_via_sdk(client, bucket_name: str, local_path: Path, gcs_path: str, dry_run: bool) -> bool:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    if blob.exists():
        return False
    if dry_run:
        return True
    blob.upload_from_filename(str(local_path), content_type="image/jpeg")
    return True


def upload_via_gcloud(bucket_name: str, local_path: Path, gcs_path: str, dry_run: bool) -> bool:
    import subprocess

    gcs_uri = f"gs://{bucket_name}/{gcs_path}"
    # Check existence
    check = subprocess.run(
        ["gcloud", "storage", "ls", gcs_uri],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0 and gcs_uri in check.stdout:
        return False
    if dry_run:
        return True
    up = subprocess.run(
        [
            "gcloud",
            "storage",
            "cp",
            "--no-clobber",
            "--content-type=image/jpeg",
            str(local_path),
            gcs_uri,
        ],
        capture_output=True,
        text=True,
    )
    if up.returncode != 0:
        raise RuntimeError(f"gcloud upload failed: {up.stderr}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of products processed (0 = no limit)")
    args = parser.parse_args()

    diff_path = latest_diff_json()
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    diffs = diff["diffs"]

    if args.limit > 0:
        diffs = diffs[: args.limit]

    # Only process products that actually have new photos
    targets = [d for d in diffs if d["new_photo_urls"]]
    print(f"Diff: {diff_path.name}")
    print(f"Products to rehost: {len(targets)}")
    print(f"Total new photo URLs: {sum(len(d['new_photo_urls']) for d in targets)}")
    if args.dry_run:
        print("DRY RUN — no downloads, no uploads")

    client = None
    if _GCS_SDK:
        try:
            client = storage.Client(project="ai-agents-go")
        except Exception as e:
            print(f"  (google-cloud-storage init failed: {e}; falling back to gcloud CLI)")
            client = None

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    tmp_dir = REPO_ROOT / "data" / "scraped" / "eurotramp" / "_rehost_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    uploads_per_handle: dict[str, list[dict]] = {}
    today = datetime.date.today().isoformat()

    total_downloaded = 0
    total_uploaded = 0
    total_skipped = 0
    total_failed = 0
    failures: list[dict] = []

    for i, d in enumerate(targets, 1):
        handle = d["handle"]
        new_urls = d["new_photo_urls"]
        print(f"\n[{i}/{len(targets)}] {handle}  ({len(new_urls)} photos)")
        uploads_per_handle[handle] = []

        for url in new_urls:
            fn = filename_from_url(url)
            gcs_path = f"{GCS_PREFIX}/{handle}/{fn}"
            local_path = tmp_dir / fn

            # Download (skip if already cached)
            if not local_path.exists():
                if args.dry_run:
                    print(f"  [dry] would download {url}")
                else:
                    try:
                        time.sleep(0.25)
                        r = session.get(url, timeout=30)
                        if r.status_code != 200 or len(r.content) < 200:
                            print(f"  ✗ download failed ({r.status_code}, {len(r.content)}B): {url}")
                            total_failed += 1
                            failures.append({"handle": handle, "url": url, "stage": "download", "status": r.status_code})
                            continue
                        local_path.write_bytes(r.content)
                        total_downloaded += 1
                    except Exception as e:
                        print(f"  ✗ download error: {e}: {url}")
                        total_failed += 1
                        failures.append({"handle": handle, "url": url, "stage": "download", "error": str(e)})
                        continue

            # Upload to GCS
            try:
                if client is not None:
                    uploaded = upload_via_sdk(client, GCS_BUCKET, local_path, gcs_path, args.dry_run)
                else:
                    uploaded = upload_via_gcloud(GCS_BUCKET, local_path, gcs_path, args.dry_run)
            except Exception as e:
                print(f"  ✗ upload error: {e}: {gcs_path}")
                total_failed += 1
                failures.append({"handle": handle, "url": url, "stage": "upload", "error": str(e)})
                continue

            if uploaded:
                total_uploaded += 1
                print(f"  {'[dry] ' if args.dry_run else ''}uploaded gs://{GCS_BUCKET}/{gcs_path}")
            else:
                total_skipped += 1
                print(f"  skipped (already in GCS): {gcs_path}")

            uploads_per_handle[handle].append(
                {
                    "filename": fn,
                    "source_url": url,
                    "gcs_path": f"gs://{GCS_BUCKET}/{gcs_path}",
                    "proxy_url": f"{PROXY_BASE}/{GCS_PREFIX}/{handle}/{fn}",
                }
            )

    # Persist the manifest so the Medusa backfill step can read it.
    manifest_path = REPORTS_DIR / f"eurotramp-rehost-manifest-{today}.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": today,
                "dry_run": args.dry_run,
                "diff_source": diff_path.name,
                "totals": {
                    "downloaded": total_downloaded,
                    "uploaded": total_uploaded,
                    "skipped_existing": total_skipped,
                    "failed": total_failed,
                },
                "failures": failures,
                "by_handle": uploads_per_handle,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n=== DONE ===")
    print(f"Downloaded: {total_downloaded}")
    print(f"Uploaded:   {total_uploaded}")
    print(f"Skipped (already in GCS): {total_skipped}")
    print(f"Failed:     {total_failed}")
    print(f"Manifest:   {manifest_path}")


if __name__ == "__main__":
    main()
