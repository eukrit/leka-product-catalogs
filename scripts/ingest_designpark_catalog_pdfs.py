"""Phase B3: backfill DesignPark product descriptions from catalog PDFs.

Sources (in priority order):
  1. C:\\Users\\Eukrit\\My Drive\\Catalogs GO\\DesignPark\\
       2024-05-30 ...DesignPark Catalogue_ENG_2024....pdf  (canonical)
  2. ...DesignPark Catalogue_ENG_2022.pdf
  3. D.PARK_Catalog_EN.pdf
  4. DesignPark-Catalogue.pdf

For each text-extractable page, find SKU tokens and theme names, and for any
matching `vendors/designpark/products/<handle>` doc that has an empty or
short `description`, append the page paragraph as the description with a
`source_catalog_pdf = "<filename>:p<N>"` provenance.

Image-only PDFs (no text layer) are reported but NOT processed here —
follow-up via Gemini Vision OCR if needed (mirror ocr_weplay_local_pdfs.py).

Idempotent — only writes when description is empty or shorter than the
candidate.

Usage:
    py scripts/ingest_designpark_catalog_pdfs.py --dry-run
    py scripts/ingest_designpark_catalog_pdfs.py --apply
    py scripts/ingest_designpark_catalog_pdfs.py --apply --only-file=Catalogue_ENG_2024
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_LOCAL_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for cand in _LOCAL_SA_CANDIDATES:
        if os.path.exists(cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import pdfplumber  # noqa: E402
from google.cloud import firestore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("ingest_designpark_catalog_pdfs")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "designpark"

DRIVE_CATALOGS = Path(r"C:\Users\Eukrit\My Drive\Catalogs GO\DesignPark")
CATALOG_PDFS = [
    DRIVE_CATALOGS / "2024-05-30 TalkFile_★DesignPark Catalogue_ENG_2024_240423_160728_24042_240425_131442.pdf",
    DRIVE_CATALOGS / "2023-09-14 ★DesignPark Catalogue_ENG_2022.pdf",
    DRIVE_CATALOGS / "D.PARK_Catalog_EN.pdf",
    DRIVE_CATALOGS / "DesignPark-Catalogue.pdf",
]

SKU_RE = re.compile(r"((?:SDM\d+|PTC\d+|PTM\d+|DPM\d+|DPF\d+|DPS\d+)[-_]?\d{2,4}(?:[-_]\d{1,4})?)", re.IGNORECASE)
SLUG_BAD_CHARS = re.compile(r"[^a-z0-9]+")
MIN_TEXT_PER_PAGE = 80  # below this, treat as image-only


def slugify(text: str) -> str:
    return SLUG_BAD_CHARS.sub("-", text.lower()).strip("-") or "unknown"


def load_product_index(db) -> dict:
    coll = db.collection("vendors").document(SLUG).collection("products")
    by_sku, by_name = {}, {}
    for snap in coll.stream():
        d = snap.to_dict() or {}
        handle = d.get("handle") or snap.id
        sku = (d.get("item_code") or "").upper()
        if sku:
            by_sku[sku] = (handle, d)
        if d.get("name"):
            by_name[slugify(d["name"])] = (handle, d)
    log.info("indexed %d products (%d skus, %d names)", len(by_name), len(by_sku), len(by_name))
    return {"sku": by_sku, "name": by_name}


def page_paragraphs(text: str) -> list[str]:
    """Split into paragraphs of >40 chars, trim."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "")]
    return [p for p in paras if len(p) > 40]


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--only-file", type=str, help="substring filter on PDF filename")
    args = ap.parse_args()
    dry = args.dry_run

    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    idx = load_product_index(db)
    prod_coll = db.collection("vendors").document(SLUG).collection("products")

    n_pages, n_image_only, n_writes = 0, 0, 0
    for pdf_path in CATALOG_PDFS:
        if not pdf_path.exists():
            log.warning("missing: %s", pdf_path)
            continue
        if args.only_file and args.only_file.lower() not in pdf_path.name.lower():
            continue
        log.info("opening: %s", pdf_path.name)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for p_idx, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    if len(text) < MIN_TEXT_PER_PAGE:
                        n_image_only += 1
                        continue
                    n_pages += 1
                    skus = {m.group(1).upper().replace("_", "-") for m in SKU_RE.finditer(text)}
                    paras = page_paragraphs(text)
                    if not skus and not paras:
                        continue

                    # Match by SKU first.
                    candidates: list[tuple[str, dict, str]] = []
                    for sku in skus:
                        if sku in idx["sku"]:
                            handle, d = idx["sku"][sku]
                            best = max(paras, key=len) if paras else ""
                            candidates.append((handle, d, best))

                    # Also try matching by product/theme name appearing in page text.
                    if not candidates:
                        for name_slug, (handle, d) in idx["name"].items():
                            if name_slug.replace("-", " ") in text.lower():
                                best = max(paras, key=len) if paras else ""
                                candidates.append((handle, d, best))
                                break  # one per page is enough

                    for handle, doc, new_desc in candidates:
                        old = (doc.get("description") or "").strip()
                        if len(new_desc) <= max(len(old), 40):
                            continue
                        prov = f"{pdf_path.name}:p{p_idx}"
                        if dry:
                            log.info("[DRY] would set description on %s (len %d → %d) from %s",
                                     handle, len(old), len(new_desc), prov)
                        else:
                            prod_coll.document(handle).set({
                                "description": new_desc,
                                "source_catalog_pdf": prov,
                            }, merge=True)
                        n_writes += 1
        except Exception as e:
            log.warning("pdf failed: %s — %s", pdf_path.name, e)

    log.info("text-pages=%d image-only-pages=%d writes=%d (dry=%s)",
             n_pages, n_image_only, n_writes, dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
