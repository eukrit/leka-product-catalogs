"""Create new `vendors/weplay/products/<doc_id>` Firestore docs for SKUs
the PDF OCR (`ocr_weplay_local_pdfs.py`) found in our local catalogs but
that have no existing Firestore product.

These are legitimate Weplay catalog products — same shape as products
created by the upstream scrape pipeline but originating from a different
source (Vision-OCR'd PDF instead of HTML scrape). They start as
`status=draft_no_images` and need image ingest before they'll appear on
the storefront.

Doc fields written (matching `shape_weplay_to_medusa_schema.py` shape):
  handle           = slugified SKU
  name             = EN name from OCR
  product_name     = EN name (also kept here for upstream compatibility)
  description      = EN description from OCR (may be empty for grid pages)
  description_orig = ""
  item_code        = original SKU string from OCR
  sku              = original SKU string
  status           = "draft_no_images"
  vendor_id        = "weplay"
  vendor_name      = "Weplay"
  category         = inferred from SKU prefix (KB=balls, KM=motor, etc.)
  subcategory      = ""
  pricing          = {visible: false, ...}
  specs            = {age: "..."} when available
  source_url_pdf_ocr = "<pdf>:p<n>, ..."
  images           = []  (separate ingest pass)
  updated_at       = SERVER_TIMESTAMP

Idempotent: if a doc with the same handle already exists, skip.

Usage:
    py scripts/create_weplay_pdf_only_docs.py --dry-run --load=/tmp/pdf_ocr_full.json
    py scripts/create_weplay_pdf_only_docs.py --apply --load=/tmp/pdf_ocr_full.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys

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
log = logging.getLogger("create_weplay_pdf_only_docs")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")

# SKU-prefix → category mapping inferred from the existing 149 active products
# and the catalog section structure.
PREFIX_CATEGORY = {
    "KB": "balance",         # Balls / Balance (KB1300 School Set, KB0306 Massage Ball)
    "KM": "motor-skill",     # Motor skills (KM1003 Pile Balance Up, KM2016 Cheese Hill)
    "KT": "sensory",         # Tactile (KT0017 Squishy Tactile Shell)
    "KP": "construction",    # Play (KP4007 Bouncing Flowers, KP1003 Seasound Seesaw)
    "KC": "construction",    # Cubes / Constructive (KC0002 Brick Me, KC2001 Pattern Cubes)
    "KE": "classroom-furniture",  # Ergonomic / Cot / Modern Ball Chair
    "KF": "ball-play",       # Fish (KF0005 Tricky Fish)
    "KS": "sand-water",
    "EM": "motor-skill",     # Edusante (Trike, Walking Bike, Magnetic Sets)
    "ED": "other",           # ED-prefix singletons
    "AT": "other",
    "KY": "other",
    "WJ": "other",
}


def slugify_doc_id(sku: str) -> str:
    """Same convention as shape_weplay_to_medusa_schema.py."""
    return sku.lower().replace(".", "_").replace("-", "_").replace(" ", "_")


def slugify_handle(sku: str) -> str:
    """Medusa handle: URL-safe lowercase + dashes. Strip parens, &, etc."""
    s = sku.lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = s.replace(".", "-").replace("_", "-")
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--load", type=str, required=True,
                    help="JSON dump from ocr_weplay_local_pdfs.py")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    write = bool(args.apply)
    log.info("=== create_weplay_pdf_only_docs mode=%s ===", "WRITE" if write else "DRY-RUN")

    with open(args.load, "r", encoding="utf-8") as f:
        dump = json.load(f)
    by_sku = dump.get("by_sku") or dump
    log.info("loaded %d SKUs from dump", len(by_sku))

    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")

    # Build set of existing tokens AND existing doc_ids
    existing_tokens: set[str] = set()
    existing_doc_ids: set[str] = set()
    for snap in coll.stream():
        existing_doc_ids.add(snap.id)
        d = snap.to_dict() or {}
        sku = (d.get("item_code") or "").upper()
        m = SKU_TOKEN_RE.search(sku)
        if m:
            existing_tokens.add(m.group(1))
    log.info("indexed %d existing docs (%d unique tokens)",
             len(existing_doc_ids), len(existing_tokens))

    # Filter to PDF-only SKUs (no Firestore doc with matching token)
    candidates: list[dict] = []
    for token, det in by_sku.items():
        if token in existing_tokens:
            continue
        candidates.append({**det, "_token": token})
    log.info("PDF-only candidates (need new docs): %d", len(candidates))
    if args.limit:
        candidates = candidates[: args.limit]

    counters = {"candidates": len(candidates), "creates": 0, "skipped_id_collision": 0}
    sample_creates = []
    batch = db.batch()
    batch_n = 0

    for det in candidates:
        sku_raw = det["sku"]
        # Some OCR rows return compound SKUs like "KM4001.1, KM4001.1-004"
        # — pick the first (base) SKU only.
        sku = re.split(r"[,/]", sku_raw, 1)[0].strip()
        # Sanity check: must still match SKU pattern
        if not SKU_TOKEN_RE.search(sku):
            continue
        token = det["_token"]
        doc_id = slugify_doc_id(sku)
        if doc_id in existing_doc_ids:
            counters["skipped_id_collision"] += 1
            continue

        prefix = token[:2]
        category = PREFIX_CATEGORY.get(prefix, "other")
        sources = det.get("sources") or [det.get("source_page", "")]

        payload = {
            "handle": slugify_handle(sku),
            "name": det.get("name_en", ""),
            "product_name": det.get("name_en", ""),
            "description": det.get("description_en", ""),
            "description_orig": "",
            "item_code": sku,
            "sku": sku,
            "status": "draft_no_images",
            "vendor_id": SLUG,
            "vendor_name": "Weplay",
            "category": category,
            "subcategory": "",
            "pricing": {"visible": False, "unit": "", "currency": "", "price": 0},
            "source_url_pdf_ocr": ", ".join(sources[:3]),
            "images": [],
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if det.get("age_range"):
            payload["specs"] = {"age": det["age_range"]}

        counters["creates"] += 1
        existing_doc_ids.add(doc_id)
        if len(sample_creates) < 10:
            sample_creates.append(f"{doc_id} sku={sku} cat={category} name={(payload['name'] or '')[:50]!r}")

        if write:
            batch.set(coll.document(doc_id), payload)
            batch_n += 1
            if batch_n >= 200:
                batch.commit()
                log.info("committed batch (%d)", batch_n)
                batch = db.batch()
                batch_n = 0

    if write and batch_n:
        batch.commit()
        log.info("committed final batch (%d)", batch_n)

    log.info("=== summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    if sample_creates:
        log.info("sample creates:")
        for s in sample_creates:
            log.info("  %s", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
