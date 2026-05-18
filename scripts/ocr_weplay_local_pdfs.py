"""Vision-OCR the four image-only Weplay catalog PDFs to recover EN
content for the ~40 catalog-only SKUs (and uncover any others).

PDFs (in `C:\\Users\\Eukrit\\My Drive\\Catalogs GO\\WePlay Catalogs\\`):
  - 2025-2026 Weplay Catalog (95p, 153 MB, ~7 chars/p text — image-only)
  - Weplay Catalogue 2020-2021 (83p, 75 MB)
  - Weplay Catalogue 2022-2023 (91p, 183 MB)
  - WePlay New Products 2021-2023 (61p)

Approach
--------
1. PyMuPDF renders each page to a JPG bytes blob at ~200 DPI (good
   balance of OCR readability vs Gemini token cost).
2. Send the blob to Gemini 2.5 Flash with structured-output prompt:
   {"products":[{sku, name_en, description_en, age_range}, ...]}.
3. Cache page-level results to a JSON dump so re-runs skip already-
   processed pages.
4. Aggregate by SKU token, dedupe across pages/PDFs (keep richest).
5. Writeback merges into Firestore using same source-priority guard
   as flipbook (only writes when source_url_en/cached/flipbook/local
   are all unset).

Sequential calls with --polite-ms (1500ms default for safe free-tier
margin; 250ms for paid). 330 pages × 12s = ~70 min worst case.

Idempotent. Cost: ~$5-10 with Gemini Flash.

Usage:
    py scripts/ocr_weplay_local_pdfs.py --crawl --dump=/tmp/pdf_ocr.json
    py scripts/ocr_weplay_local_pdfs.py --crawl --pdf="2025-2026 Weplay Catalog 2025-2026.pdf" --polite-ms=250
    py scripts/ocr_weplay_local_pdfs.py --apply --load=/tmp/pdf_ocr.json
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
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
log = logging.getLogger("ocr_weplay_local_pdfs")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
FOLDER = Path(r"C:\Users\Eukrit\My Drive\Catalogs GO\WePlay Catalogs")
MODEL = "gemini-2.5-flash"
RENDER_DPI = 180  # pages are ~A4 @ 180 DPI = ~1450x2050 px ~ 600KB JPG

PDFS_TO_OCR = [
    "2025-05-21 Weplay Catalog 2025-2026.pdf",
    "Weplay Catalogue 2020-2021.pdf",
    "Weplay Catalogue 2022-2023.pdf",
    "WePlay New Products 2021-2023.pdf",
]

SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")

OCR_PROMPT = """\
This is a single page from an English-language Weplay product catalog
(Taiwan; children's playground equipment).

For EVERY distinct product card visible on this page, extract:
  - sku: the item code. Usually 2 letters + 4 digits ("KM1003", "KP4007"),
         sometimes with a dot/dash suffix (".1", "-00B"), or with a "6800"
         prefix ("6800KM1003"). Look near the photo or in a price/spec table.
  - name_en: the product's English display name. Strip "Weplay" prefix.
  - description_en: marketing/feature paragraph if visible (single line, "" if absent).
  - age_range: e.g. "3y+" or "2.5-3.5 y" or "" if absent.

Return STRICT JSON only — no commentary or markdown:
  {"products":[{"sku":"...","name_en":"...","description_en":"...","age_range":"..."},...]}

If page is a cover, TOC, section divider, or has no product cards, return:
  {"products":[]}
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


def render_page_jpg(pdf_path: Path, page_num: int, dpi: int = RENDER_DPI) -> bytes:
    """Render a single PDF page to JPG bytes."""
    with fitz.open(pdf_path) as doc:
        page = doc[page_num]
        # PyMuPDF DPI-to-zoom: zoom = dpi / 72
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes(output="jpeg", jpg_quality=85)


def ocr_one_page(client: genai.Client, jpg_bytes: bytes, label: str, retries: int = 2) -> list[dict]:
    parts = [
        genai_types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg"),
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
                wait = 30 * (attempt + 1)
                log.warning("[%s] 429, retry in %ds", label, wait)
                time.sleep(wait)
                continue
            log.warning("[%s] gemini error: %s", label, e)
            return []
        raw = (resp.text or "").strip()
        try:
            parsed = json.loads(raw)
        except Exception as e:
            log.warning("[%s] JSON parse failed: %s; raw=%.200s", label, e, raw)
            return []
        prods = parsed.get("products", [])
        return prods if isinstance(prods, list) else []
    return []


def crawl(pdf_filter: str | None, polite_ms: int, dump_path: str | None,
          start_page: int | None = None, end_page: int | None = None) -> dict:
    """Process all configured PDFs (or one matching pdf_filter) and return
    the aggregated SKU -> {name, desc, age, source_pages} dict.

    If dump_path exists, resumes by skipping already-processed pages."""
    client = _genai_client()

    by_sku: dict[str, dict] = {}
    page_done: set[str] = set()  # set of "{pdf_name}:p{n}" labels

    # Resume from existing dump
    if dump_path and Path(dump_path).exists():
        try:
            with open(dump_path, "r", encoding="utf-8") as f:
                prev = json.load(f)
            by_sku = prev.get("by_sku", {})
            page_done = set(prev.get("page_done", []))
            log.info("resuming from dump: %d SKUs, %d pages already done",
                     len(by_sku), len(page_done))
        except Exception as e:
            log.warning("could not load dump: %s", e)

    pdfs = [p for p in PDFS_TO_OCR if not pdf_filter or pdf_filter in p]
    for pdf_name in pdfs:
        path = FOLDER / pdf_name
        if not path.exists():
            log.warning("missing: %s", path)
            continue
        with fitz.open(path) as doc:
            n_pages = len(doc)
        s_page = start_page if start_page is not None else 0
        e_page = end_page if end_page is not None else n_pages
        log.info("\n=== %s (%d pages, processing %d-%d) ===", pdf_name, n_pages, s_page, e_page - 1)

        for page_idx in range(s_page, e_page):
            label = f"{pdf_name}:p{page_idx + 1}"
            if label in page_done:
                continue
            try:
                jpg = render_page_jpg(path, page_idx)
            except Exception as e:
                log.warning("[%s] render failed: %s", label, e)
                continue
            prods = ocr_one_page(client, jpg, label)
            new = 0
            for p in prods:
                sku = (p.get("sku") or "").upper().strip()
                if not sku:
                    continue
                tok_m = SKU_TOKEN_RE.search(sku)
                token = tok_m.group(1) if tok_m else sku
                p["sku_token"] = token
                p["sku"] = sku
                p["source_page"] = label
                p["name_en"] = re.sub(r"^\s*Weplay\s+", "", (p.get("name_en") or "")).strip()
                if token not in by_sku:
                    by_sku[token] = p
                    by_sku[token]["sources"] = [label]
                    new += 1
                else:
                    by_sku[token]["sources"].append(label)
                    if len(p.get("description_en") or "") > len(by_sku[token].get("description_en") or ""):
                        by_sku[token]["description_en"] = p["description_en"]
                    if not by_sku[token].get("age_range") and p.get("age_range"):
                        by_sku[token]["age_range"] = p["age_range"]
            page_done.add(label)
            log.info("[%s] %d products (+%d unique; total %d)", label, len(prods), new, len(by_sku))

            # Periodic checkpoint dump
            if dump_path and (page_idx + 1) % 5 == 0:
                with open(dump_path, "w", encoding="utf-8") as f:
                    json.dump({"by_sku": by_sku, "page_done": sorted(page_done)},
                              f, indent=2, ensure_ascii=False)

            time.sleep(polite_ms / 1000.0)

    # Final checkpoint
    if dump_path:
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump({"by_sku": by_sku, "page_done": sorted(page_done)},
                      f, indent=2, ensure_ascii=False)
        log.info("dumped to %s", dump_path)
    return {"by_sku": by_sku, "page_done": sorted(page_done)}


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

    for token, det in by_sku.items():
        targets = token_to_docs.get(token, [])
        if not targets:
            counters["no_doc_match"] += 1
            if len(sample_no_match) < 8:
                sample_no_match.append(f"{det['sku']}: {det.get('name_en')!r}")
            continue
        for snap in targets:
            counters["matched_to_doc"] += 1
            d = snap.to_dict() or {}
            if any(d.get(k) for k in ("source_url_en", "source_url_cached",
                                       "source_url_flipbook", "source_url_local")):
                counters["skipped_already_has_better_source"] += 1
                continue

            orig_name = d.get("product_name") or ""
            is_chinese_orig = bool(re.search(r"[一-鿿]", orig_name))
            payload = {
                "name": (det.get("name_en") or "").strip() or d.get("name"),
                "description": (det.get("description_en") or "").strip() or d.get("description"),
                "source_url_pdf_ocr": ", ".join((det.get("sources") or [det.get("source_page", "")])[:3]),
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
                    f"{snap.id} sku={det['sku']} name={(payload.get('name') or '')[:50]!r}"
                )
            if not dry_run:
                batch.set(snap.reference, payload, merge=True)
                batch_n += 1
                if batch_n >= 200:
                    batch.commit()
                    log.info("committed batch (%d)", batch_n)
                    batch = db.batch()
                    batch_n = 0

    if not dry_run and batch_n:
        batch.commit()
        log.info("committed final batch (%d)", batch_n)

    log.info("=== writeback summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    if sample_writes:
        log.info("sample writes: %s", sample_writes[:5])
    if sample_no_match:
        log.info("sample no-doc-match: %s", sample_no_match[:5])
    return counters


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--crawl", action="store_true")
    mode.add_argument("--apply", action="store_true",
                      help="--apply == crawl + writeback. Use --load to skip crawl.")
    mode.add_argument("--load", type=str,
                      help="Skip crawl; load JSON dump and writeback only.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pdf", type=str, default=None,
                    help="Filter to a single PDF (substring match in filename).")
    ap.add_argument("--start-page", type=int, default=None)
    ap.add_argument("--end-page", type=int, default=None)
    ap.add_argument("--polite-ms", type=int, default=250,
                    help="Sleep between Gemini calls in ms (default 250).")
    ap.add_argument("--dump", type=str, default=None,
                    help="JSON dump path. Resumes from this file if it exists.")
    args = ap.parse_args()

    if args.load:
        with open(args.load, "r", encoding="utf-8") as f:
            dump = json.load(f)
        by_sku = dump.get("by_sku") or dump  # tolerate both formats
        log.info("loaded %d SKUs from %s", len(by_sku), args.load)
        writeback(by_sku, dry_run=args.dry_run)
        return 0

    log.info("=== ocr_weplay_local_pdfs mode=%s polite=%dms pdf=%s ===",
             "APPLY" if args.apply else "CRAWL", args.polite_ms, args.pdf or "all")
    result = crawl(args.pdf, args.polite_ms, args.dump,
                   args.start_page, args.end_page)
    if args.apply:
        writeback(result["by_sku"], dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
