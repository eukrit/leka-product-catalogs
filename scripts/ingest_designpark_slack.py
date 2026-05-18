"""Phase C: ingest files from Slack `#vendor-design-park` (C0AESCDCZRQ).

Queries the Slack `files.list` API filtered by channel, downloads each file,
uploads to GCS, writes a `vendors/designpark/attachments/<sha>` doc, and
joins to a product when the file/message text mentions a known SKU.

This was deferred at v2.20.0 and re-prioritised in the v2.23.5 follow-ups.

Auth:
  SLACK_BOT_TOKEN env var, sourced from Secret Manager:
    gcloud secrets versions access latest --secret=slack-bot-token

Bot scopes required (the existing bot already has these on the workspace):
  channels:history, groups:history, files:read

For files that don't carry a SKU on filename/title/message but are clearly
multi-product (e.g. a waterplay brochure), they're stored as
vendor-level brochures on `vendors/designpark.brochures[]`.

Usage:
    py scripts/ingest_designpark_slack.py --dry-run
    py scripts/ingest_designpark_slack.py --apply
    py scripts/ingest_designpark_slack.py --apply --include-pdfs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_LOCAL_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for cand in _LOCAL_SA_CANDIDATES:
        if os.path.exists(cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests  # noqa: E402
from google.cloud import firestore, storage  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import ingest_designpark_assets as assets_mod  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("ingest_designpark_slack")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "designpark"
BUCKET = "ai-agents-go-vendors"
GCS_PREFIX = "designpark/media"
PROXY_BASE = "https://catalogs.leka.studio/api/i/designpark/media"
SLACK_CHANNEL_ID = "C0AESCDCZRQ"
SLACK_API = "https://slack.com/api"

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
CAD_EXTS = {"dwg", "dxf"}


def slack_get(method: str, token: str, params: dict) -> dict:
    r = requests.get(
        f"{SLACK_API}/{method}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"slack {method} failed: {j.get('error')} {j}")
    return j


def list_channel_files(token: str) -> list[dict]:
    """Page through files.list filtered by channel."""
    out: list[dict] = []
    page = 1
    while True:
        j = slack_get("files.list", token, {
            "channel": SLACK_CHANNEL_ID,
            "count": 100,
            "page": page,
        })
        out.extend(j.get("files") or [])
        paging = j.get("paging") or {}
        if page >= paging.get("pages", 1):
            break
        page += 1
        time.sleep(0.3)
    return out


def fetch_message_context(token: str, ts: str) -> str:
    """Fetch the originating message text for a file's `ts`. Best-effort."""
    if not ts:
        return ""
    try:
        j = slack_get("conversations.history", token, {
            "channel": SLACK_CHANNEL_ID,
            "latest": ts,
            "inclusive": "true",
            "limit": 1,
        })
        msgs = j.get("messages") or []
        return (msgs[0].get("text") if msgs else "") or ""
    except Exception as e:
        log.debug("message context fetch failed for ts=%s: %s", ts, e)
        return ""


def download(url: str, token: str) -> bytes:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    r.raise_for_status()
    return r.content


def kind_for(mime: str, ext: str) -> str:
    if mime in IMAGE_MIMES or ext in {"jpg", "jpeg", "png", "webp"}:
        return "image"
    if ext in CAD_EXTS or mime == "application/acad":
        return "drawing"
    if mime == "application/pdf" or ext == "pdf":
        return "brochure"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--include-pdfs", action="store_true",
                    help="store unmatched PDFs as vendor-level brochures (default: skip)")
    args = ap.parse_args()
    dry = args.dry_run

    token = os.environ.get("SLACK_BOT_TOKEN") or ""
    if not token:
        log.error("SLACK_BOT_TOKEN not set. Fetch via: "
                  "gcloud secrets versions access latest --secret=slack-bot-token")
        return 2

    log.info("listing files in #vendor-design-park (%s)", SLACK_CHANNEL_ID)
    files = list_channel_files(token)
    log.info("found %d files", len(files))

    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    storage_client = storage.Client(project=PROJECT)
    bucket = storage_client.bucket(BUCKET)
    idx = assets_mod.load_product_index(db)
    attach_coll = db.collection("vendors").document(SLUG).collection("attachments")
    prod_coll = db.collection("vendors").document(SLUG).collection("products")
    vendor_ref = db.collection("vendors").document(SLUG)

    brochures: list[dict] = []
    n_total, n_uploaded, n_skip, n_matched, n_unmatched_brochure, n_skipped_other = 0, 0, 0, 0, 0, 0

    for f in files:
        n_total += 1
        name = f.get("name") or f.get("title") or ""
        mime = (f.get("mimetype") or "").lower()
        ext = Path(name).suffix.lower().lstrip(".") or {
            "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
            "application/pdf": "pdf",
        }.get(mime, "bin")
        kind = kind_for(mime, ext)
        ts = f.get("timestamp") or f.get("created") or ""
        ts_str = str(ts)
        # Build a context blob for SKU sniffing.
        msg_ctx = fetch_message_context(token, f.get("timestamp", "")) if not dry else ""
        sources = " ".join([name, f.get("title") or "", msg_ctx])
        sku = assets_mod.find_sku_in_text(sources, idx["sku_set"])

        if dry:
            log.info("[DRY] %-50s kind=%-9s sku=%s mime=%s size=%s",
                     name[:50], kind, sku, mime, f.get("size"))
            if sku:
                n_matched += 1
            elif kind == "brochure":
                n_unmatched_brochure += 1
            else:
                n_skipped_other += 1
            continue

        url = f.get("url_private_download") or f.get("url_private")
        if not url:
            log.warning("no download url for %s", name)
            continue
        try:
            data = download(url, token)
        except Exception as e:
            log.warning("download failed for %s: %s", name, e)
            continue
        sha = hashlib.sha256(data).hexdigest()

        blob_path = f"{GCS_PREFIX}/{sha}.{ext}"
        blob = bucket.blob(blob_path)
        ctype = mime or assets_mod.content_type_for(ext)
        if not blob.exists():
            blob.upload_from_string(data, content_type=ctype)
            n_uploaded += 1
        else:
            n_skip += 1
        proxy_url = f"{PROXY_BASE}/{sha}.{ext}"

        attach_doc = {
            "sha": sha,
            "ext": ext,
            "kind": kind,
            "source": "slack",
            "source_slack_channel": SLACK_CHANNEL_ID,
            "source_slack_file_id": f.get("id"),
            "source_slack_permalink": f.get("permalink"),
            "source_slack_user": f.get("user"),
            "source_slack_ts": ts_str,
            "source_url_proxy": proxy_url,
            "sku_match": sku or "",
            "byte_size": len(data),
            "content_type": ctype,
            "filename": name,
            "title": f.get("title", ""),
            "message_text": msg_ctx[:1000],
        }
        attach_coll.document(sha).set(attach_doc, merge=True)

        if sku and sku in idx["sku"]:
            n_matched += 1
            handle = idx["sku"][sku]
            if kind == "image":
                prod_ref = prod_coll.document(handle)
                snap = prod_ref.get()
                existing = (snap.to_dict() or {}).get("images") or []
                if not any((img.get("sha") if isinstance(img, dict) else None) == sha for img in existing):
                    existing.append({"url": proxy_url, "sha": sha, "ext": ext, "source": "slack"})
                    prod_ref.set({"images": existing}, merge=True)
        else:
            if kind == "brochure" and args.include_pdfs:
                brochures.append({
                    "title": f.get("title") or name,
                    "url": proxy_url,
                    "sha": sha,
                    "ext": ext,
                    "source_slack_permalink": f.get("permalink", ""),
                })
                n_unmatched_brochure += 1
            else:
                n_skipped_other += 1

    # Vendor-level brochure roll-up.
    if brochures and not dry:
        snap = vendor_ref.get()
        existing = (snap.to_dict() or {}).get("brochures") or []
        seen_shas = {b.get("sha") for b in existing if isinstance(b, dict)}
        merged = list(existing) + [b for b in brochures if b["sha"] not in seen_shas]
        vendor_ref.set({"brochures": merged}, merge=True)
        log.info("attached %d brochures to vendors/%s.brochures[]",
                 len(brochures), SLUG)

    log.info("%s: total=%d uploaded=%d skip=%d matched=%d brochures=%d skipped_other=%d",
             "[DRY]" if dry else "done",
             n_total, n_uploaded, n_skip, n_matched,
             n_unmatched_brochure, n_skipped_other)
    return 0


if __name__ == "__main__":
    sys.exit(main())
