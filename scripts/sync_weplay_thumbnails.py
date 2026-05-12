"""One-shot: push reordered images[] + thumbnail to Medusa for active Weplay
products. Use after `vision_rank_weplay_images.py` reorders the array so the
kids-with-product shot moves to images[0].

`sync_vendors_to_medusa.py`'s update path only refreshes title/description/
metadata on existing products (not images[]/thumbnail), so this script
fills the gap. Idempotent — safe to re-run.

Usage:
    py scripts/sync_weplay_thumbnails.py --dry-run
    py scripts/sync_weplay_thumbnails.py --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import requests
from google.cloud import firestore

_FALLBACK_ADC = (
    r"C:\Users\Eukrit\AppData\Roaming\gcloud\legacy_credentials"
    r"\codex-chatgpt@ai-agents-go.iam.gserviceaccount.com\adc.json"
)
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ or not os.path.exists(
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
):
    if os.path.exists(_FALLBACK_ADC):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _FALLBACK_ADC
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("sync_weplay_thumbnails")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
SC_ID = "sc_01KR6Z0VBSXWYZDVGF30EAP0EQ"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"


def auth() -> str:
    email = os.environ["LEKA_MEDUSA_ADMIN_EMAIL"]
    pw = os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _fetch_all_products(token: str) -> dict[str, dict]:
    """Map handle -> {id, thumbnail, image_urls} for the Weplay SC."""
    out: dict[str, dict] = {}
    headers = {"Authorization": f"Bearer {token}"}
    offset = 0
    page = 100
    while True:
        r = requests.get(
            f"{BACKEND}/admin/products",
            params={"sales_channel_id[]": SC_ID, "limit": page, "offset": offset,
                    "fields": "id,handle,thumbnail,images.url"},
            headers=headers, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        for p in data.get("products", []):
            out[p["handle"]] = {
                "id": p["id"],
                "thumbnail": p.get("thumbnail"),
                "image_urls": [i.get("url") for i in (p.get("images") or [])],
            }
        if len(data.get("products", [])) < page:
            break
        offset += page
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    write = bool(args.apply)
    log.info("=== sync_weplay_thumbnails mode=%s ===", "WRITE" if write else "DRY-RUN")

    token = auth()
    medusa = _fetch_all_products(token)
    log.info("loaded %d Medusa products under Weplay SC", len(medusa))

    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    counters = {"firestore_active": 0, "medusa_unknown": 0, "no_change": 0,
                "thumbnail_updated": 0, "image_order_updated": 0, "errors": 0}
    samples = []

    for snap in coll.stream():
        d = snap.to_dict() or {}
        if d.get("status") != "active":
            continue
        images = d.get("images") or []
        if not images:
            continue
        counters["firestore_active"] += 1
        handle = d.get("handle") or snap.id.lower().replace(".", "-").replace("_", "-")
        target = medusa.get(handle)
        if not target:
            counters["medusa_unknown"] += 1
            continue

        new_image_urls = [i.get("url") for i in images if isinstance(i, dict) and i.get("url")]
        new_thumb = new_image_urls[0] if new_image_urls else None
        if not new_thumb:
            continue
        thumb_changed = (new_thumb != target["thumbnail"])
        order_changed = (new_image_urls != target["image_urls"])
        if not thumb_changed and not order_changed:
            counters["no_change"] += 1
            continue

        body: dict = {}
        if thumb_changed:
            body["thumbnail"] = new_thumb
            counters["thumbnail_updated"] += 1
        if order_changed:
            body["images"] = [{"url": u} for u in new_image_urls]
            counters["image_order_updated"] += 1

        if len(samples) < 8:
            samples.append(f"{handle}: thumb={thumb_changed} order={order_changed} new_thumb=...{new_thumb[-40:]}")

        if not write:
            continue
        r = requests.post(
            f"{BACKEND}/admin/products/{target['id']}",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        if r.status_code >= 400:
            log.warning("[%s] update failed: %s %s", handle, r.status_code, r.text[:200])
            counters["errors"] += 1
            # Refresh token if 401
            if r.status_code == 401:
                token = auth()
        time.sleep(0.05)  # be a little gentle

    log.info("=== summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    log.info("samples:")
    for s in samples:
        log.info("  %s", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
