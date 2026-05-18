"""Ingest the 2025-11-05 Weplay quotation (AQ1251030077) and sync USD
quote prices + audit-only fields into Firestore `vendors/weplay/products/*`.

Source PDF:
  C:\\Users\\Eukrit\\My Drive\\Partners Playground\\Weplay\\
    2025-11-05 Quotation - AQ1251030077 - Go Corporation (Standard Item).pdf

What it writes (per matched doc, merge=True):
  - pricing.quote_2025_usd          : float (always written — audit-only key)
  - pricing.quote_aq1251030077_at   : "2025-10-30"
  - pricing.quote_aq1251030077_unit : "PC" | "SET" | "PAC" | "DZN" ...
  - quotation_refs                  : ArrayUnion(["AQ1251030077"])
  - source_url_local                : "AQ1251030077:p<N>"  (only if doc has
                                      no source_url_* yet)
  - name                            : ONLY if doc is missing name AND has no
                                      source_url_* (i.e. draft_no_images
                                      with no provenance)
  - description                     : same gate as name

Source-priority hierarchy (unchanged from earlier ingest passes):
  source_url_en > source_url_cached > source_url_flipbook >
  source_url_pdf_ocr > source_url_local > source_ai_inferred

Usage:
  py scripts/ingest_weplay_quotation_aq1251030077.py --dry-run
  py scripts/ingest_weplay_quotation_aq1251030077.py --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import pdfplumber
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
log = logging.getLogger("ingest_weplay_quotation_aq1251030077")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
QUOTATION_REF = "AQ1251030077"
QUOTATION_DATE = "2025-10-30"
PDF_PATH = Path(
    r"C:\Users\Eukrit\My Drive\Partners Playground\Weplay"
    r"\2025-11-05 Quotation - AQ1251030077 - Go Corporation (Standard Item).pdf"
)

# Same boundary-less SKU regex as scripts/ingest_weplay_local_catalogs.py —
# must match KM1003 inside 6800KM1003 for cross-doc lookup.
SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")

# Line format per inspection:
#   SKU  DESCRIPTION  PRICE / UNIT  PACK_QTY  CBM  G.W. [REMARK]
# SKU = 2 letters + digits + optional [.-]suffix (e.g. KC0004-032, KP2002.1-00B)
LINE_RE = re.compile(
    r"^(?P<sku>[A-Z]{2}\d{3,}(?:[.\-][A-Z0-9]+)*)"
    r"\s+(?P<desc>.+?)"
    r"\s+(?P<price>[\d,]+\.\d{2})"
    r"\s*/\s*(?P<unit>[A-Z]+)"
    r"\s+(?P<pack>[\d.]+)"
    r"\s+(?P<cbm>[\d.]+)"
    r"\s+(?P<gw>[\d.]+)"
    r"(?:\s+.*)?$"
)


def parse_pdf(path: Path) -> list[dict]:
    rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for pn, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.split("\n"):
                line = raw.strip()
                if not line:
                    continue
                m = LINE_RE.match(line)
                if not m:
                    continue
                sku = m.group("sku").upper()
                token_m = SKU_TOKEN_RE.search(sku)
                if not token_m:
                    continue
                desc = m.group("desc").strip()
                if len(desc) < 3:
                    continue
                try:
                    price = float(m.group("price").replace(",", ""))
                except ValueError:
                    continue
                rows.append({
                    "sku": sku,
                    "sku_token": token_m.group(1),
                    "name": desc,
                    "price_usd": price,
                    "unit": m.group("unit"),
                    "page": pn,
                })
    log.info("parsed %d quotation rows from %s", len(rows), path.name)
    return rows


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """One entry per SKU token. If multiple rows share a token (e.g. KC0004
    + KC0004-032 + KC0004-065), prefer the row whose SKU matches the token
    most exactly (shortest SKU)."""
    by_token: dict[str, dict] = {}
    for r in rows:
        token = r["sku_token"]
        existing = by_token.get(token)
        if existing is None or len(r["sku"]) < len(existing["sku"]):
            # Keep variants list for audit
            variants = existing.get("variants", []) if existing else []
            variants.append({"sku": r["sku"], "price_usd": r["price_usd"], "unit": r["unit"]})
            r = dict(r, variants=variants)
            by_token[token] = r
        else:
            existing.setdefault("variants", []).append(
                {"sku": r["sku"], "price_usd": r["price_usd"], "unit": r["unit"]}
            )
    return by_token


PROVENANCE_KEYS = (
    "source_url_en",
    "source_url_cached",
    "source_url_flipbook",
    "source_url_pdf_ocr",
    "source_url_local",
)


def writeback(by_token: dict[str, dict], dry_run: bool) -> dict:
    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    token_to_docs: dict[str, list] = {}
    total_docs = 0
    for snap in coll.stream():
        total_docs += 1
        d = snap.to_dict() or {}
        sku = (d.get("item_code") or "").upper()
        m = SKU_TOKEN_RE.search(sku)
        if not m:
            continue
        token_to_docs.setdefault(m.group(1), []).append(snap)
    log.info("scanned %d Firestore docs; %d unique SKU tokens indexed",
             total_docs, len(token_to_docs))

    counters = {
        "rows_parsed": sum(1 for _ in by_token),
        "matched_to_doc": 0,
        "no_doc_match": 0,
        "writes": 0,
        "skipped_provenance_for_name": 0,
        "price_only_writes": 0,
    }
    sample_writes, sample_no_match = [], []
    batch = db.batch()
    batch_n = 0
    BATCH = 200

    for token, det in by_token.items():
        targets = token_to_docs.get(token, [])
        if not targets:
            counters["no_doc_match"] += 1
            if len(sample_no_match) < 12:
                sample_no_match.append(f"{det['sku']}: {det['name']!r} ${det['price_usd']}")
            continue
        for snap in targets:
            counters["matched_to_doc"] += 1
            d = snap.to_dict() or {}

            pricing = dict(d.get("pricing") or {})
            pricing["quote_2025_usd"] = det["price_usd"]
            pricing[f"quote_{QUOTATION_REF.lower()}_at"] = QUOTATION_DATE
            pricing[f"quote_{QUOTATION_REF.lower()}_unit"] = det["unit"]

            payload: dict = {
                "pricing": pricing,
                "quotation_refs": firestore.ArrayUnion([QUOTATION_REF]),
            }

            has_any_provenance = any(d.get(k) for k in PROVENANCE_KEYS)
            doc_missing_name = not (d.get("name") or d.get("product_name"))
            doc_missing_desc = not d.get("description")
            is_draft = d.get("status") in {"draft_no_images", "draft"} or doc_missing_name

            # Only write name/description when doc has no provenance source
            # (otherwise richer source wins) AND the doc is in a draft state /
            # missing the field.
            wrote_name = False
            if not has_any_provenance and doc_missing_name and is_draft:
                payload["name"] = det["name"]
                wrote_name = True
            if not has_any_provenance and doc_missing_desc and is_draft:
                payload["description"] = det["name"]
            if wrote_name or (not has_any_provenance and is_draft):
                payload["source_url_local"] = f"{QUOTATION_REF}:p{det['page']}"
            else:
                counters["skipped_provenance_for_name"] += 1
                counters["price_only_writes"] += 1

            counters["writes"] += 1
            if len(sample_writes) < 12:
                sample_writes.append(
                    f"{snap.id} sku_token={token} ${det['price_usd']:.2f}/{det['unit']}"
                    f" {'+name' if wrote_name else ''} (existing_name={(d.get('name') or '')[:40]!r})"
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
    log.info("sample writes:")
    for s in sample_writes:
        log.info("  %s", s)
    if sample_no_match:
        log.info("sample no-doc-match:")
        for s in sample_no_match:
            log.info("  %s", s)
    return counters


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    write = bool(args.apply)
    log.info("=== ingest_weplay_quotation_%s mode=%s ===",
             QUOTATION_REF, "WRITE" if write else "DRY-RUN")

    if not PDF_PATH.exists():
        log.error("PDF not found: %s", PDF_PATH)
        return 2

    rows = parse_pdf(PDF_PATH)
    by_token = aggregate(rows)
    log.info("aggregated %d unique SKU tokens from %d rows", len(by_token), len(rows))

    writeback(by_token, dry_run=not write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
