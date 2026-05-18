"""OCR the 188-page Weplay EN 2025 Flash flipbook (one high-res JPG per
page) via Gemini Vision to recover EN names/descriptions for the ~116
draft products that aren't reachable via the live nav.

Source pages:
    https://www.weplay.com.tw/download/EN/Catalog/2025/files/mobile/{1..188}.jpg

Strategy per page:
    Send the page JPG URL to Gemini 2.5 Flash with a structured-output
    instruction asking it to return every product card visible on the page
    as {sku, name_en, description_en, age_range, max_load, weight}.

Result is merged into Firestore the same way as `scrape_weplay_cached.py`:
only write fields for product docs whose item_code's SKU token matches
AND whose `source_url_en` / `source_url_cached` / `source_url_flipbook`
isn't already set.

We DON'T attach images here — the flipbook is page-level layout, not
per-product photos. Drafts that gain a name + description here stay
draft until a future image source is found.

Idempotent. ~$2-4 spend (188 vision calls).

Usage:
    py scripts/ocr_weplay_flipbook.py --crawl --dump=/tmp/flipbook.json
    py scripts/ocr_weplay_flipbook.py --apply --load=/tmp/flipbook.json
    py scripts/ocr_weplay_flipbook.py --apply --start-page=1 --end-page=20    # smoke
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time

from google.cloud import firestore
from google import genai
from google.genai import types as genai_types

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
log = logging.getLogger("ocr_weplay_flipbook")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
PAGE_URL_TMPL = "https://www.weplay.com.tw/download/EN/Catalog/2025/files/mobile/{n}.jpg"
TOTAL_PAGES = 188
MODEL = "gemini-2.5-flash"

SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")

OCR_PROMPT = """\
This is a single page from an English-language product catalog by Weplay
(Taiwanese children's playground equipment maker).

For EVERY product card visible on this page, extract:
  - sku: the item code (alphanumeric, usually 2 letters + 4 digits, sometimes
         with a dot-suffix like .1 or a color suffix like -00B). May appear as
         "Item No.", "KM1003", "6800KM1003", or printed alongside the photo.
  - name_en: the product's English display name (e.g. "Pile Balance Up",
             "Animal Parade (Dinosaur)"). Strip any leading "Weplay" prefix.
  - description_en: the marketing description paragraph on the card. Cleaned to
             a single line. Empty string "" if not visible.
  - age_range: e.g. "3y+" or "2.5-3.5 y". Empty string if not visible.

Return STRICT JSON only — no commentary:
{"products": [{"sku":"...","name_en":"...","description_en":"...","age_range":"..."}, ...]}

If the page is a TOC/cover/section divider with NO product cards, return:
{"products": []}
"""


def _genai_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        from google.cloud import secretmanager
        sm = secretmanager.SecretManagerServiceClient()
        api_key = sm.access_secret_version(
            name=f"projects/{PROJECT}/secrets/gemini-api-key/versions/latest"
        ).payload.data.decode().strip()
    return genai.Client(api_key=api_key)


def ocr_one_page(client: genai.Client, page_num: int, retries: int = 2) -> list[dict]:
    url = PAGE_URL_TMPL.format(n=page_num)
    parts = [
        genai_types.Part.from_uri(file_uri=url, mime_type="image/jpeg"),
        genai_types.Part.from_text(text=OCR_PROMPT),
    ]
    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=parts,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                    max_output_tokens=4096,
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as e:
            if "429" in str(e) and attempt < retries:
                wait = 20 * (attempt + 1)
                log.warning("page %d: 429, retry in %ds", page_num, wait)
                time.sleep(wait)
                continue
            log.warning("page %d: error %s", page_num, e)
            return []
        raw = (resp.text or "").strip()
        try:
            parsed = json.loads(raw)
        except Exception as e:
            log.warning("page %d: JSON parse failed: %s; raw=%.200s", page_num, e, raw)
            return []
        products = parsed.get("products", [])
        if not isinstance(products, list):
            return []
        for p in products:
            p["page_num"] = page_num
        return products
    return []


def crawl(start: int, end: int, polite_ms: int) -> dict[str, dict]:
    client = _genai_client()
    by_sku: dict[str, dict] = {}
    for n in range(start, end + 1):
        prods = ocr_one_page(client, n)
        new = 0
        for p in prods:
            sku = (p.get("sku") or "").upper().strip()
            if not sku:
                continue
            token_m = SKU_TOKEN_RE.search(sku)
            p["sku_token"] = token_m.group(1) if token_m else sku
            p["sku"] = sku
            # Drop "Weplay" prefix that sometimes leaks through
            p["name_en"] = re.sub(r"^\s*Weplay\s+", "", (p.get("name_en") or "")).strip()
            if sku not in by_sku:
                by_sku[sku] = p
                new += 1
            else:
                # Merge longer description
                if len(p.get("description_en") or "") > len(by_sku[sku].get("description_en") or ""):
                    by_sku[sku]["description_en"] = p["description_en"]
        log.info("page %d: %d products extracted (+%d unique; running total %d)",
                 n, len(prods), new, len(by_sku))
        time.sleep(polite_ms / 1000.0)
    return by_sku


def writeback(by_sku: dict[str, dict], dry_run: bool) -> dict:
    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    token_to_docs: dict[str, list[firestore.DocumentSnapshot]] = {}
    for snap in coll.stream():
        d = snap.to_dict() or {}
        sku = (d.get("item_code") or "").upper()
        m = SKU_TOKEN_RE.search(sku)
        if not m:
            continue
        token_to_docs.setdefault(m.group(1), []).append(snap)

    counters = {
        "ocr_skus": len(by_sku),
        "matched_to_doc": 0,
        "skipped_already_has_better_source": 0,
        "writes": 0,
        "no_doc_match": 0,
    }
    sample_writes, sample_no_match = [], []
    batch = db.batch()
    batch_n = 0
    BATCH = 200

    for sku, det in by_sku.items():
        token = det.get("sku_token") or sku
        targets = token_to_docs.get(token, [])
        if not targets:
            counters["no_doc_match"] += 1
            if len(sample_no_match) < 8:
                sample_no_match.append(f"{sku}: {det.get('name_en')!r}")
            continue
        for snap in targets:
            counters["matched_to_doc"] += 1
            d = snap.to_dict() or {}
            # Don't clobber live or cached-HTML data (both have richer
            # descriptions + image URLs than the flipbook OCR).
            if d.get("source_url_en") or d.get("source_url_cached"):
                counters["skipped_already_has_better_source"] += 1
                continue

            orig_name = d.get("product_name") or ""
            is_chinese_orig = bool(re.search(r"[一-鿿]", orig_name))
            payload = {
                "name": (det.get("name_en") or "").strip() or d.get("name"),
                "description": (det.get("description_en") or "").strip() or d.get("description"),
                "source_url_flipbook": f"page_{det.get('page_num')}",
                "description_orig": d.get("description"),
            }
            specs = {}
            if det.get("age_range"):
                specs["age"] = det["age_range"]
            if specs:
                payload["specs"] = specs
            if is_chinese_orig:
                payload["name_zh"] = orig_name

            counters["writes"] += 1
            if len(sample_writes) < 8:
                sample_writes.append(
                    f"{snap.id} sku={sku} name={(payload.get('name') or '')[:60]!r}"
                )
            if not dry_run:
                batch.set(snap.reference, payload, merge=True)
                batch_n += 1
                if batch_n >= BATCH:
                    batch.commit()
                    log.info("committed batch (%d docs)", batch_n)
                    batch = db.batch()
                    batch_n = 0

    if not dry_run and batch_n:
        batch.commit()
        log.info("committed final batch (%d docs)", batch_n)

    log.info("=== summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    if sample_writes:
        log.info("sample writes: %s", sample_writes)
    if sample_no_match:
        log.info("sample no-doc-match: %s", sample_no_match)
    return counters


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--crawl", action="store_true", help="OCR-only, no writeback.")
    mode.add_argument("--apply", action="store_true", help="OCR + writeback.")
    mode.add_argument("--load", type=str, help="Skip OCR; load JSON dump and writeback.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--end-page", type=int, default=TOTAL_PAGES)
    ap.add_argument("--polite-ms", type=int, default=1500,
                    help="Sleep between Gemini calls (free-tier ~5 RPM).")
    ap.add_argument("--dump", type=str, default=None)
    args = ap.parse_args()

    if args.load:
        log.info("loading from %s", args.load)
        with open(args.load, "r", encoding="utf-8") as f:
            by_sku = json.load(f)
        log.info("loaded %d SKUs", len(by_sku))
        writeback(by_sku, dry_run=args.dry_run)
        return 0

    log.info("=== ocr_weplay_flipbook pages=%d-%d polite=%dms ===",
             args.start_page, args.end_page, args.polite_ms)
    by_sku = crawl(args.start_page, args.end_page, args.polite_ms)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(by_sku, f, indent=2, ensure_ascii=False)
        log.info("dumped %d SKUs to %s", len(by_sku), args.dump)
    if args.apply:
        writeback(by_sku, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
