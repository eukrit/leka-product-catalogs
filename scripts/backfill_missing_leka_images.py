"""Backfill the ~190 missing paths under gs://ai-agents-go-vendors/leka-project/.

These are products whose Pass-2 edit landed in `manual_review/` (partial logo
removal, QA rejected) or `error` (Gemini refused / 429 / 499). The customer-
facing prefix `leka-project/` has no blob for them, so Medusa product images
404 on the storefront.

Policy (per the rebrand follow-up):
  - edit_status = 'error' (6):
      Retry once via Gemini Nano Banana Pro at concurrency=1 with the brand-
      neutral EDIT_PROMPT and a long retry budget. If the retry produces a
      QA-clean edit, write it to leka-project/<path> and mark backfill_source
      = "gemini-retry". Otherwise fall back to copying the unedited original
      from wisdom/<path> and mark backfill_source = "wisdom-original".
  - edit_status = 'manual_review' (184):
      Server-side copy manual_review/<path> -> leka-project/<path>. Mark
      backfill_source = "manual_review". The Wisdom mark may still be partly
      visible — a human reviewer can come back and finish these. Better than
      a 404.

Idempotent. Updates `image_logo_edit/{sha}` with backfill_* fields so re-runs
are cheap and stay consistent with the existing Pass-2 checkpoint scheme.

Auth: ADC via google.auth.default() (workspace Rule 12b).

Usage:
    python scripts/backfill_missing_leka_images.py --dry-run    # plan
    python scripts/backfill_missing_leka_images.py              # execute
    python scripts/backfill_missing_leka_images.py --skip-retry # straight to fallback
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

from google.cloud import firestore, storage  # noqa: E402

# Reuse the existing Pass-2 building blocks.
from strip_wisdom_logos import (  # noqa: E402
    BUCKET,
    DST_PREFIX_ROOT,
    EDIT_COLLECTION,
    EDIT_MODEL,
    FIRESTORE_DB,
    PROJECT,
    SRC_PREFIX_ROOT,
    Blob,
    adc_check,
    edit_one,
    gemini_client,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("backfill_missing_leka_images")

REVIEW_PREFIX = "manual_review/"


def relative_path(source_path: str) -> str:
    """wisdom/catalog/foo.jpeg -> catalog/foo.jpeg."""
    if source_path.startswith(SRC_PREFIX_ROOT):
        return source_path[len(SRC_PREFIX_ROOT):]
    return source_path


def load_missing_docs(fs_client: firestore.Client) -> tuple[list[dict], list[dict]]:
    review: list[dict] = []
    errors: list[dict] = []
    for snap in fs_client.collection(EDIT_COLLECTION).where("edit_status", "==", "manual_review").stream():
        d = snap.to_dict()
        d["_id"] = snap.id
        review.append(d)
    for snap in fs_client.collection(EDIT_COLLECTION).where("edit_status", "==", "error").stream():
        d = snap.to_dict()
        d["_id"] = snap.id
        errors.append(d)
    return review, errors


def dst_blob_exists(bucket: storage.Bucket, dst_name: str) -> bool:
    try:
        return bucket.blob(dst_name).exists()
    except Exception:
        return False


def copy_blob(bucket: storage.Bucket, src_name: str, dst_name: str) -> None:
    src = bucket.blob(src_name)
    bucket.copy_blob(src, bucket, new_name=dst_name)


def backfill_manual_review(
    docs: list[dict],
    bucket: storage.Bucket,
    fs_client: firestore.Client,
    *,
    dry_run: bool,
) -> dict:
    counts = {"copied": 0, "skipped_existing": 0, "missing_review_blob": 0, "error": 0}
    for d in docs:
        src_path = d.get("source_path")
        if not src_path:
            counts["error"] += 1
            continue
        rel = relative_path(src_path)
        dst_name = DST_PREFIX_ROOT + rel
        review_name = REVIEW_PREFIX + rel
        if dst_blob_exists(bucket, dst_name):
            counts["skipped_existing"] += 1
            # Still tag the checkpoint so it's clear we visited.
            if not dry_run and not d.get("backfill_source"):
                fs_client.collection(EDIT_COLLECTION).document(d["_id"]).set({
                    "backfill_source": "manual_review",
                    "backfill_dst_path": dst_name,
                    "backfill_skipped_existing": True,
                    "backfill_at": firestore.SERVER_TIMESTAMP,
                }, merge=True)
            continue
        if not bucket.blob(review_name).exists():
            log.warning("manual_review blob missing for %s — falling back to wisdom original", src_path)
            try:
                copy_blob(bucket, src_path, dst_name) if not dry_run else None
                if not dry_run:
                    fs_client.collection(EDIT_COLLECTION).document(d["_id"]).set({
                        "backfill_source": "wisdom-original",
                        "backfill_dst_path": dst_name,
                        "backfill_note": "manual_review blob missing",
                        "backfill_at": firestore.SERVER_TIMESTAMP,
                    }, merge=True)
                counts["copied"] += 1
                counts["missing_review_blob"] += 1
            except Exception as e:
                log.warning("fallback copy failed %s: %s", src_path, e)
                counts["error"] += 1
            continue
        try:
            if not dry_run:
                copy_blob(bucket, review_name, dst_name)
                fs_client.collection(EDIT_COLLECTION).document(d["_id"]).set({
                    "backfill_source": "manual_review",
                    "backfill_dst_path": dst_name,
                    "backfill_at": firestore.SERVER_TIMESTAMP,
                }, merge=True)
            counts["copied"] += 1
        except Exception as e:
            log.warning("review->dst copy failed %s: %s", review_name, e)
            counts["error"] += 1
    return counts


def retry_or_fallback_errors(
    docs: list[dict],
    bucket: storage.Bucket,
    fs_client: firestore.Client,
    *,
    dry_run: bool,
    skip_retry: bool,
) -> dict:
    counts = {"gemini_retry_ok": 0, "gemini_retry_manual_review": 0,
              "wisdom_fallback": 0, "skipped_existing": 0, "error": 0}

    storage_client = bucket.client
    gem = None if skip_retry else gemini_client()

    for d in docs:
        src_path = d.get("source_path")
        if not src_path:
            counts["error"] += 1
            continue
        rel = relative_path(src_path)
        dst_name = DST_PREFIX_ROOT + rel
        if dst_blob_exists(bucket, dst_name):
            counts["skipped_existing"] += 1
            continue

        # Try Gemini one more time (concurrency=1 here, long retry budget inside edit_one)
        retry_succeeded = False
        if not skip_retry and gem is not None:
            try:
                src_blob = bucket.blob(src_path)
                src_blob.reload()
                b = Blob(
                    name=src_path,
                    size=src_blob.size or 0,
                    md5=src_blob.md5_hash or "",
                    content_type=src_blob.content_type or "",
                )
                if not dry_run:
                    rec = edit_one(b, storage_client, fs_client, gem, force=True, dry_run=False)
                    status = rec.get("edit_status")
                    if status == "ok":
                        counts["gemini_retry_ok"] += 1
                        fs_client.collection(EDIT_COLLECTION).document(b.sha).set({
                            "backfill_source": "gemini-retry",
                            "backfill_dst_path": dst_name,
                            "backfill_at": firestore.SERVER_TIMESTAMP,
                        }, merge=True)
                        retry_succeeded = True
                    elif status == "manual_review":
                        # Partial result. Promote to leka-project/ anyway — better than nothing.
                        review_name = REVIEW_PREFIX + rel
                        if bucket.blob(review_name).exists():
                            copy_blob(bucket, review_name, dst_name)
                            counts["gemini_retry_manual_review"] += 1
                            fs_client.collection(EDIT_COLLECTION).document(b.sha).set({
                                "backfill_source": "gemini-retry-manual-review",
                                "backfill_dst_path": dst_name,
                                "backfill_at": firestore.SERVER_TIMESTAMP,
                            }, merge=True)
                            retry_succeeded = True
                else:
                    log.info("[dry-run] would retry Gemini for %s", src_path)
                    retry_succeeded = True  # treat as success for dry-run plan accounting
                    counts["gemini_retry_ok"] += 1
            except Exception as e:
                log.warning("Gemini retry failed for %s: %s", src_path, e)

        if retry_succeeded:
            continue

        # Fall back to copying the unedited Wisdom original.
        try:
            if not dry_run:
                copy_blob(bucket, src_path, dst_name)
                doc_id = hashlib.sha1(src_path.encode()).hexdigest()
                fs_client.collection(EDIT_COLLECTION).document(doc_id).set({
                    "backfill_source": "wisdom-original",
                    "backfill_dst_path": dst_name,
                    "backfill_note": "Gemini retry exhausted or refused — original copied; will still show Wisdom branding",
                    "backfill_at": firestore.SERVER_TIMESTAMP,
                }, merge=True)
            counts["wisdom_fallback"] += 1
            log.warning("[fallback] copied original (with Wisdom logo) for %s", src_path)
        except Exception as e:
            log.error("fallback copy failed for %s: %s", src_path, e)
            counts["error"] += 1
    return counts


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="Plan only — no GCS writes, no Gemini calls, no Firestore writes.")
    p.add_argument("--skip-retry", action="store_true",
                   help="Skip the Gemini retry for `error` docs — go straight to wisdom-original fallback.")
    p.add_argument("--report-dir", default="migration",
                   help="Where to drop the JSON report.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    adc_check()

    storage_client = storage.Client(project=PROJECT)
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    bucket = storage_client.bucket(BUCKET)

    log.info("Loading missing-path docs from %s ...", EDIT_COLLECTION)
    review_docs, error_docs = load_missing_docs(fs_client)
    log.info("manual_review=%d  error=%d  total=%d (dry_run=%s, skip_retry=%s)",
             len(review_docs), len(error_docs), len(review_docs) + len(error_docs),
             args.dry_run, args.skip_retry)

    t0 = time.time()
    review_counts = backfill_manual_review(review_docs, bucket, fs_client, dry_run=args.dry_run)
    log.info("manual_review backfill: %s", review_counts)

    error_counts = retry_or_fallback_errors(
        error_docs, bucket, fs_client,
        dry_run=args.dry_run, skip_retry=args.skip_retry,
    )
    log.info("error backfill: %s", error_counts)

    elapsed = time.time() - t0
    report = {
        "phase": "backfill",
        "dry_run": args.dry_run,
        "skip_retry": args.skip_retry,
        "manual_review_input": len(review_docs),
        "error_input": len(error_docs),
        "manual_review_counts": review_counts,
        "error_counts": error_counts,
        "elapsed_seconds": round(elapsed, 1),
        "edit_model": EDIT_MODEL,
    }
    out = Path(args.report_dir) / "wisdom-image-backfill-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    log.info("Report -> %s", out)
    log.info("Done in %.1fs.", elapsed)


if __name__ == "__main__":
    main()
