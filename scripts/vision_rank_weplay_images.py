"""Rank each Weplay product's images by how well they show a child or
person actively using the product, then reorder `images[]` so the best
"lifestyle with kids" photo is first (becomes the storefront card thumb).

Why
---
The 136 active Weplay products have 3-10 photos each in `vendors/weplay/products/<doc>.images[]`. Today the order is whatever the
upstream scrape happened to write — often a packshot or a technical
drawing first, with the actual marketing/lifestyle shot buried mid-list.
Cards on `catalogs.leka.studio/weplay` look catalog-y not storefront-y.

How
---
For each product:
  1. Send all `images[].url` to Gemini 2.5 Flash with a structured-output
     prompt asking for a 0-100 "kids/users in scene with the product"
     score per image.
  2. Cache scores back to `images[].score_kids` so re-runs are free.
  3. Sort `images[]` desc by score; idempotent.
  4. Sync runs separately — `sync_vendors_to_medusa.py` already uses
     `images[0]` as `thumbnail`, so reordering propagates automatically
     on the next sync.

Cost (one-shot for 136 products, avg 7 imgs each ≈ 950 inferences):
  Gemini 2.5 Flash @ ~$0.30 / 1M output tokens, ~$0.075 / 1M image input
  → roughly $1-3 for the full pass.

Usage
-----
    py scripts/vision_rank_weplay_images.py --dry-run --limit-products=5
    py scripts/vision_rank_weplay_images.py --apply
    py scripts/vision_rank_weplay_images.py --apply --rescore   # ignore cache
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Any

from google.cloud import firestore
from google import genai
from google.genai import types as genai_types

_DEFAULT_SA = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
_FALLBACK_ADC = (
    r"C:\Users\Eukrit\AppData\Roaming\gcloud\legacy_credentials"
    r"\codex-chatgpt@ai-agents-go.iam.gserviceaccount.com\adc.json"
)
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ or not os.path.exists(
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
):
    if os.path.exists(_DEFAULT_SA):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _DEFAULT_SA
    elif os.path.exists(_FALLBACK_ADC):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _FALLBACK_ADC
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("vision_rank_weplay")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
MODEL = "gemini-2.5-flash"

# Score schema asked of Gemini per image
SCORE_INSTRUCTION = """\
You are scoring product photos for a children's playground equipment storefront.

For each image, output a JSON object with two keys:
  "score": integer 0-100 — how well this image shows the product being USED in
           a real-world setting (kids playing on it, adults engaging with it,
           a classroom or playground scene). Higher = more "lifestyle".
  "tag":   short label, one of: "kids_using", "adults_using", "lifestyle_no_people",
           "packshot_white_bg", "technical_drawing", "certification", "logo",
           "other".

Scoring rubric:
  90-100: kids actively playing on the product, multiple kids, joyful scene
  70-89:  one child or adult using the product, clear interaction
  50-69:  product in a playground/classroom but no people visible
  30-49:  packshot — product alone on a clean/white background
  10-29:  isolated product on patterned/marketing background
  0-9:    technical drawing, dimensional schematic, certification badge, logo

Return STRICT JSON: {"images":[{"score":N,"tag":"..."}, ...]} — same length and
order as the input image list. No commentary outside the JSON.
"""


def _genai_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Pull from Secret Manager (fast, in-process)
        from google.cloud import secretmanager
        sm = secretmanager.SecretManagerServiceClient()
        api_key = sm.access_secret_version(
            name=f"projects/{PROJECT}/secrets/gemini-api-key/versions/latest"
        ).payload.data.decode().strip()
    return genai.Client(api_key=api_key)


def _images_unscored(images: list[Any], rescore: bool) -> list[tuple[int, str]]:
    """Return [(idx, url)] for entries that don't have a cached score."""
    out: list[tuple[int, str]] = []
    for i, img in enumerate(images or []):
        if not isinstance(img, dict) or not img.get("url"):
            continue
        if not rescore and isinstance(img.get("score_kids"), int):
            continue
        out.append((i, img["url"]))
    return out


BATCH_SIZE_IMAGES = 5  # cap images per Gemini call — large batches lead to truncated JSON


def _score_batch(
    client: genai.Client,
    urls: list[str],
    name: str,
    handle: str,
) -> list[dict] | None:
    """Score a single batch of image URLs. Returns list of {score,tag} or None on failure."""
    parts: list[genai_types.Part] = []
    for url in urls:
        parts.append(genai_types.Part.from_uri(file_uri=url, mime_type="image/jpeg"))
    parts.append(genai_types.Part.from_text(
        text=f"Product: {name} (SKU/handle: {handle}).\n{SCORE_INSTRUCTION}"
    ))
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=parts,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=800,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
    except Exception as e:
        log.warning("[%s] gemini call failed: %s", handle, e)
        return None
    raw = (resp.text or "").strip()
    try:
        parsed = json.loads(raw)
        scores = parsed.get("images", [])
    except Exception as e:
        log.warning("[%s] response not JSON (%s); raw=%.200s", handle, e, raw)
        return None
    if not isinstance(scores, list):
        return None
    return scores


def _rank_one_product(
    client: genai.Client,
    images: list[dict],
    name: str,
    handle: str,
    rescore: bool,
) -> tuple[list[dict], int, dict]:
    """Score un-scored images in small batches via Gemini Vision."""
    to_score = _images_unscored(images, rescore)
    diag = {"new_scores": 0, "tags": {}}
    if not to_score:
        return images, 0, diag

    # Batch in groups of BATCH_SIZE_IMAGES
    for batch_start in range(0, len(to_score), BATCH_SIZE_IMAGES):
        chunk = to_score[batch_start: batch_start + BATCH_SIZE_IMAGES]
        urls = [u for _i, u in chunk]
        scores = _score_batch(client, urls, name, handle)
        if scores is None:
            continue
        # Tolerate length mismatch — zip up to min len
        for (idx, _url), sc in zip(chunk, scores):
            if not isinstance(sc, dict):
                continue
            score = sc.get("score")
            tag = sc.get("tag") or "other"
            if not isinstance(score, int) or not (0 <= score <= 100):
                continue
            images[idx]["score_kids"] = score
            images[idx]["tag_kids"] = tag
            diag["new_scores"] += 1
            diag["tags"].setdefault(tag, 0)
            diag["tags"][tag] += 1
    return images, diag["new_scores"], diag


def _sort_by_score(images: list[dict]) -> list[dict]:
    def key(img: dict) -> tuple[int, int]:
        s = img.get("score_kids")
        return (0 if isinstance(s, int) else 1, -(s or 0))
    return sorted(images, key=key)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit-products", type=int, default=None)
    ap.add_argument("--rescore", action="store_true",
                    help="Re-score images even when score_kids is already cached.")
    ap.add_argument("--polite-ms", type=int, default=300,
                    help="Sleep between Gemini calls in ms (default 300).")
    args = ap.parse_args()

    write = bool(args.apply)
    log.info("=== vision_rank_weplay mode=%s limit=%s rescore=%s ===",
             "WRITE" if write else "DRY-RUN", args.limit_products, args.rescore)

    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    client = _genai_client()

    # Only score active products with images
    docs = []
    for snap in coll.stream():
        d = snap.to_dict() or {}
        if d.get("status") != "active":
            continue
        if not d.get("images"):
            continue
        docs.append(snap)
    if args.limit_products:
        docs = docs[: args.limit_products]
    log.info("processing %d active products with images", len(docs))

    counters = {
        "products_processed": 0,
        "products_reordered": 0,
        "images_scored": 0,
        "tag_totals": {},
        "primary_changed": 0,
    }

    batch = db.batch()
    batch_n = 0
    BATCH_SIZE = 50

    for snap in docs:
        d = snap.to_dict() or {}
        images = list(d.get("images") or [])
        # Coerce non-dict entries (legacy) into dicts
        coerced = []
        for img in images:
            if isinstance(img, dict):
                coerced.append(dict(img))
            elif isinstance(img, str):
                coerced.append({"url": img})
        images = coerced

        original_first_url = images[0].get("url") if images else None

        images, new_scores, diag = _rank_one_product(
            client, images, name=d.get("name") or snap.id, handle=snap.id, rescore=args.rescore,
        )
        counters["products_processed"] += 1
        counters["images_scored"] += new_scores
        for tag, cnt in diag["tags"].items():
            counters["tag_totals"][tag] = counters["tag_totals"].get(tag, 0) + cnt

        sorted_images = _sort_by_score(images)
        new_first_url = sorted_images[0].get("url") if sorted_images else None
        if [i.get("url") for i in sorted_images] != [i.get("url") for i in images]:
            counters["products_reordered"] += 1
        if new_first_url != original_first_url:
            counters["primary_changed"] += 1

        if write:
            payload = {"images": sorted_images}
            batch.set(snap.reference, payload, merge=True)
            batch_n += 1
            if batch_n >= BATCH_SIZE:
                batch.commit()
                log.info("  committed batch (%d docs)", batch_n)
                batch = db.batch()
                batch_n = 0

        if counters["products_processed"] % 10 == 0:
            log.info("progress: %d/%d processed, %d new scores, %d reordered, %d primary changed",
                     counters["products_processed"], len(docs),
                     counters["images_scored"], counters["products_reordered"],
                     counters["primary_changed"])

        time.sleep(args.polite_ms / 1000.0)

    if write and batch_n:
        batch.commit()
        log.info("committed final batch (%d docs)", batch_n)

    log.info("=== summary ===")
    for k, v in counters.items():
        log.info("  %s: %s", k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
