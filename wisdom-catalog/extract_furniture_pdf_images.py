"""Extract per-product images from the 2025-08-11 Wisdom Furniture Catalog PDF.

Source: `2025-08-11 Wisdom International Furniture Catalog.pdf` (355 pages,
~5,286 raw embedded images, 1,418 SKU codes detected). KB-dominated furniture
catalog never previously ingested into `vendors/wisdom/products`.

Strategy — spatial proximity (mirrors `wisdom-catalog/map_images_verified.py`):
  1. Build a text index over all pages: SKU-code token -> list of (page, cx, cy)
     from `page.get_text("dict")` span bboxes.
  2. For each page that mentions at least one code, enumerate image rects via
     `page.get_image_rects(xref)`, compute centers, and attribute each image
     to the nearest code on that page within distance <= MAX_DISTANCE.
  3. Cap at MAX_IMAGES per code (keep the closest distances).
  4. When multiple xrefs share a bbox (jpx + jpeg from the same render),
     prefer DeviceRGB JPEG (mirrors `foursoft-catalog/extract_pdf_images.py`).
  5. For JPX-only cells, render the page region via `page.get_pixmap` at
     RENDER_ZOOM=3.0 and save as JPEG q=85.
  6. Idempotency: page-level checkpoint in Firestore
     `wisdom_pdf_extract/{pdf_sha256}/pages/{N}`. Re-run picks up where we
     left off. Local md5 collision = same image, skipped.

Gap filter: by default we only attribute images to codes that EITHER currently
have `images=[]` in `vendors/wisdom/products` OR don't yet exist as a vendor
doc (likely new furniture SKUs). The set is loaded once from Firestore.

Flags:
    --dry-run            (default off) emit data/furniture_candidates.csv, no writes
    --extract            do the local JPEG writes + mapping JSON + checkpoint
    --pages 1-30         smoke-test slice
    --limit-codes N      cap distinct codes attributed (sorted by page)
    --include-filled     attribute to codes that already have images (debug only)
    --no-gap-filter      attribute to ANY detected code (for spot-check audits)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io as io_mod
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import fitz  # PyMuPDF
from google.cloud import firestore
from PIL import Image as PILImage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("extract_furniture")

# ---------------------------------------------------------------------------
# Constants

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
CHECKPOINT_DB = "leka-product-catalogs"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path(
    r"C:\Users\Eukrit\My Drive\Catalogs GO\Wisdom Playground"
    r"\2025-08-11 Wisdom International Furniture Catalog.pdf"
)
DATA_DIR = REPO_ROOT / "wisdom-catalog" / "data"
IMG_DIR = DATA_DIR / "pdf_images"
MAP_JSON = DATA_DIR / "pdf_images_map.json"
CANDIDATES_CSV = DATA_DIR / "furniture_candidates.csv"

CATALOG_TAG = "furniture_2025"

MAX_IMAGES = 2
MAX_DISTANCE = 600.0     # px in PDF coord space
MIN_IMG_AREA = 3000      # min w*h on the image-rect plane (skip tiny icons)
MIN_PIXEL_AREA = 100 * 100  # min w*h on raster (skip near-empty)
RENDER_ZOOM = 3.0

# Furniture-catalog regex set: same as wisdom-catalog/extract_images.py:30-44
# plus the prefixes observed in scripts/_peek_pdfs.py: KB, HW, GP, WP, EI, CD,
# CF, MGF, XPB, TBS, AS, LF.
CODE_PATTERNS = [
    re.compile(r"[A-Z]{2,5}\d?-[A-Z]*\d+[A-Z]*(?:-[A-Z]?\d+)*"),
    re.compile(r"QSWP-\d+[A-Z]\d+"),
    re.compile(r"WPPE-\d+[A-Z]?\d*"),
    re.compile(r"SW\d+[A-Z]*-[A-Z]\d+"),
    re.compile(r"SR-\d+"),
    re.compile(r"\d{2,3}-\d{5}(?:-\d+)?"),
]


def codes_in_span(text: str) -> set[str]:
    s: set[str] = set()
    if not text:
        return s
    for pat in CODE_PATTERNS:
        for m in pat.finditer(text):
            c = m.group(0)
            if len(c) >= 5:
                s.add(c)
    return s


def handle_for(code: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")
    return f"wisdom-{slug}"


# ---------------------------------------------------------------------------
# Gap filter — codes that vendors/wisdom/products say have empty images[]

def load_gap_codes(include_filled: bool, no_gap_filter: bool) -> tuple[set[str], set[str]]:
    """Returns (codes_with_empty_images, all_known_codes).

    If no_gap_filter is True, codes_with_empty_images is the union of all
    known wisdom codes — used for spot-check / audit only.
    """
    if no_gap_filter:
        log.info("Gap filter DISABLED — attributing to any detected code")
        return set(), set()
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    col = db.collection("vendors").document("wisdom").collection("products")
    empty: set[str] = set()
    all_codes: set[str] = set()
    for d in col.stream():
        data = d.to_dict() or {}
        code = data.get("item_code") or d.id.replace("wisdom-", "")
        if not isinstance(code, str):
            continue
        all_codes.add(code)
        imgs = data.get("images") or []
        # "Empty" = no images, OR only borrowed/base-design placeholders
        only_borrowed = bool(imgs) and all(
            isinstance(img, dict)
            and any(t in (img.get("source") or "") for t in ("borrowed", "base_design"))
            for img in imgs
        )
        if not imgs or (include_filled and only_borrowed):
            empty.add(code)
    log.info("Gap codes loaded: %d empty / %d total wisdom codes", len(empty), len(all_codes))
    return empty, all_codes


# ---------------------------------------------------------------------------
# PDF processing

def parse_pages(s: str | None, n_pages: int) -> range:
    if not s:
        return range(0, n_pages)  # 0-indexed
    a, _, b = s.partition("-")
    lo = max(0, int(a) - 1)
    hi = min(n_pages, int(b) if b else lo + 1)
    return range(lo, hi)


def build_text_index(doc: fitz.Document, page_range: range) -> dict[str, list[dict]]:
    """code -> list of {page, x, y} from span bbox centers."""
    index: dict[str, list[dict]] = defaultdict(list)
    for pg in page_range:
        page = doc[pg]
        try:
            d = page.get_text("dict")
        except Exception as e:
            log.warning("page %d get_text dict failed: %s", pg + 1, e)
            continue
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    cx = (bbox[0] + bbox[2]) / 2
                    cy = (bbox[1] + bbox[3]) / 2
                    for code in codes_in_span(text):
                        index[code].append({"page": pg, "x": cx, "y": cy})
    return index


def best_image_xref_for_rect(page: fitz.Page, rect: fitz.Rect,
                              rect_to_xrefs: dict) -> tuple[int, str] | None:
    """Pick the cleanest xref for a given rect.

    rect_to_xrefs: {rect_key: [(xref, ext, cs)]} pre-built per page.
    Prefer DeviceRGB JPEG over JPX, else the largest.
    """
    key = (round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1))
    candidates = rect_to_xrefs.get(key) or []
    if not candidates:
        return None
    # Prefer DeviceRGB jpeg
    for xref, ext, cs in candidates:
        if ext in ("jpeg", "jpg") and "DeviceRGB" in (cs or ""):
            return xref, ext
    # Then any jpeg
    for xref, ext, cs in candidates:
        if ext in ("jpeg", "jpg"):
            return xref, ext
    # Else first
    xref, ext, _cs = candidates[0]
    return xref, ext


def extract_image_bytes(doc: fitz.Document, page: fitz.Page, xref: int,
                        ext: str, rect: fitz.Rect) -> tuple[bytes, str] | None:
    """Return (jpeg_bytes, ext='jpg'). PIL-convert if not browser-safe."""
    try:
        base = doc.extract_image(xref)
    except Exception:
        base = None
    if base and base.get("image"):
        raw = base["image"]
        w = base.get("width", 0)
        h = base.get("height", 0)
        if w * h < MIN_PIXEL_AREA:
            return None
        # Browser-safe JPEG path
        if ext in ("jpeg", "jpg"):
            try:
                # Validate it actually decodes
                im = PILImage.open(io_mod.BytesIO(raw))
                im.verify()
                return raw, "jpg"
            except Exception:
                pass
        # Recompress via PIL
        try:
            im = PILImage.open(io_mod.BytesIO(raw))
            im = im.convert("RGB")
            out = io_mod.BytesIO()
            im.save(out, "JPEG", quality=85, optimize=True)
            return out.getvalue(), "jpg"
        except Exception:
            pass
    # Render fallback (jpx-only or extract failure): rasterize the rect region
    try:
        mat = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)
        pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
        png = pix.tobytes("png")
        im = PILImage.open(io_mod.BytesIO(png)).convert("RGB")
        if im.size[0] * im.size[1] < MIN_PIXEL_AREA:
            return None
        out = io_mod.BytesIO()
        im.save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue(), "jpg"
    except Exception as e:
        log.debug("render fallback failed: %s", e)
        return None


def page_image_rects(page: fitz.Page) -> tuple[list[dict], dict]:
    """Return (rects, rect_to_xrefs).

    rects: [{xref, ext, cs, cx, cy, area, rect}]
    rect_to_xrefs: maps (x0,y0,x1,y1)-rounded -> [(xref, ext, cs)]
    """
    rects: list[dict] = []
    by_rect: dict[tuple, list] = defaultdict(list)
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        ext_raw = img_info[8] if len(img_info) > 8 else ""
        cs = img_info[5] if len(img_info) > 5 else ""
        try:
            irs = page.get_image_rects(xref)
        except Exception:
            irs = []
        if not irs:
            continue
        for rect in irs:
            cx = (rect.x0 + rect.x1) / 2
            cy = (rect.y0 + rect.y1) / 2
            area = (rect.x1 - rect.x0) * (rect.y1 - rect.y0)
            if area < MIN_IMG_AREA:
                continue
            key = (round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1))
            by_rect[key].append((xref, ext_raw, cs))
            rects.append({"xref": xref, "ext": ext_raw, "cs": cs,
                          "cx": cx, "cy": cy, "area": area, "rect": rect})
    # Dedup rects (multiple xrefs at same bbox -> single rect)
    seen = set()
    unique = []
    for r in rects:
        k = (round(r["rect"].x0, 1), round(r["rect"].y0, 1),
             round(r["rect"].x1, 1), round(r["rect"].y1, 1))
        if k in seen:
            continue
        seen.add(k)
        unique.append(r)
    return unique, by_rect


def attribute_images(page_idx: int, page: fitz.Page,
                      codes_on_page: dict[str, list[dict]]) -> list[dict]:
    """For each (code, code-position) on this page, find nearest image rect.

    Returns list of attribution records: {code, page, xref, ext, distance,
    rect, image_w, image_h}.
    """
    rects, by_rect = page_image_rects(page)
    if not rects:
        return []
    out: list[dict] = []
    for code, positions in codes_on_page.items():
        for pos in positions:
            best = None
            best_d = float("inf")
            for r in rects:
                d = ((pos["x"] - r["cx"]) ** 2 + (pos["y"] - r["cy"]) ** 2) ** 0.5
                if d < best_d:
                    best_d = d
                    best = r
            if best is None or best_d > MAX_DISTANCE:
                continue
            picked = best_image_xref_for_rect(page, best["rect"], by_rect)
            if not picked:
                continue
            xref, ext = picked
            out.append({
                "code": code,
                "page": page_idx,
                "xref": xref,
                "ext": ext,
                "distance": best_d,
                "rect": best["rect"],
                "image_w": int(best["rect"].x1 - best["rect"].x0),
                "image_h": int(best["rect"].y1 - best["rect"].y0),
                "code_x": pos["x"],
                "code_y": pos["y"],
            })
    return out


# ---------------------------------------------------------------------------
# Checkpoint

def pdf_sha(pdf_path: Path) -> str:
    h = hashlib.sha256()
    with pdf_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", default=str(DEFAULT_PDF))
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Emit candidates CSV only — no writes.")
    ap.add_argument("--extract", action="store_true",
                    help="Write local JPEGs + mapping JSON + Firestore page checkpoints.")
    ap.add_argument("--pages", default=None, help="e.g. 1-30 (1-indexed)")
    ap.add_argument("--limit-codes", type=int, default=None)
    ap.add_argument("--include-filled", action="store_true",
                    help="Also attribute to codes whose images[] is only borrowed/base-design.")
    ap.add_argument("--no-gap-filter", action="store_true",
                    help="Attribute to any detected code (audit only).")
    args = ap.parse_args()

    if not args.dry_run and not args.extract:
        log.error("Pick a mode: --dry-run or --extract")
        sys.exit(2)
    if args.dry_run and args.extract:
        log.error("--dry-run and --extract are mutually exclusive")
        sys.exit(2)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        log.error("PDF not found: %s", pdf_path)
        sys.exit(2)
    log.info("PDF: %s (%.1f MB)", pdf_path, pdf_path.stat().st_size / 1e6)

    # Load gap codes
    gap_codes, all_codes = load_gap_codes(args.include_filled, args.no_gap_filter)

    # Open PDF + checkpoint
    doc = fitz.open(pdf_path)
    n = len(doc)
    page_range = parse_pages(args.pages, n)
    log.info("Pages: %d total, processing %s", n, list(page_range)[:3] + ["..."] + list(page_range)[-3:])
    pdf_hash = pdf_sha(pdf_path)
    log.info("PDF sha16: %s", pdf_hash)

    fs_ck = None
    if args.extract:
        fs_ck = firestore.Client(project=PROJECT, database=CHECKPOINT_DB)

    # Build text index
    log.info("Building text index across pages...")
    text_index = build_text_index(doc, page_range)
    log.info("Distinct codes detected in PDF (in range): %d", len(text_index))

    # Filter by gap
    if args.no_gap_filter:
        target_codes = set(text_index)
    else:
        target_codes = set(text_index) & gap_codes
        # New SKUs (in PDF but not yet in vendors) also welcome:
        new_skus = set(text_index) - all_codes
        target_codes |= new_skus
        log.info("Gap-intersect codes: %d (incl. %d new SKUs not in vendors)",
                 len(target_codes), len(new_skus))

    # Optionally limit
    if args.limit_codes:
        target_codes = set(sorted(target_codes)[: args.limit_codes])
        log.info("--limit-codes applied: %d", len(target_codes))

    # Index pages with any target code
    pages_with_targets: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for code, positions in text_index.items():
        if code not in target_codes:
            continue
        for pos in positions:
            pages_with_targets[pos["page"]][code].append(pos)

    log.info("Pages to process: %d", len(pages_with_targets))

    # Walk pages, attribute, write
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, list[dict]] = defaultdict(list)
    csv_rows: list[dict] = []
    counts = {
        "pages_processed": 0,
        "attributions": 0,
        "images_written": 0,
        "images_skipped_existing": 0,
        "images_skipped_decode": 0,
        "codes_with_at_least_one_image": 0,
    }
    written_filenames: set[str] = set()

    for pg in sorted(pages_with_targets):
        codes_on_page = pages_with_targets[pg]
        # Checkpoint: skip page if already done
        if args.extract and fs_ck is not None:
            ck_ref = (fs_ck.collection("wisdom_pdf_extract")
                          .document(pdf_hash)
                          .collection("pages")
                          .document(str(pg)))
            snap = ck_ref.get()
            if snap.exists and (snap.to_dict() or {}).get("status") == "done":
                counts["pages_processed"] += 1
                continue
        page = doc[pg]
        attribs = attribute_images(pg, page, codes_on_page)
        counts["pages_processed"] += 1
        for a in attribs:
            counts["attributions"] += 1
            # Per-code MAX_IMAGES gate
            existing = mapping[a["code"]]
            if len(existing) >= MAX_IMAGES:
                # Keep the better (smaller) distance
                worst_i = max(range(len(existing)), key=lambda i: existing[i]["distance"])
                if a["distance"] >= existing[worst_i]["distance"]:
                    continue
                existing.pop(worst_i)
            # Build filename + maybe write
            target_filename = None
            img_hash = None
            written = False
            decode_status = "pending"
            if args.extract:
                got = extract_image_bytes(doc, page, a["xref"], a["ext"], a["rect"])
                if not got:
                    counts["images_skipped_decode"] += 1
                    decode_status = "decode_fail"
                    continue
                jpeg_bytes, _ext = got
                img_hash = hashlib.md5(jpeg_bytes).hexdigest()[:8]
                target_filename = f"{a['code']}_{CATALOG_TAG}_p{pg+1:03d}_{img_hash}.jpg"
                local_path = IMG_DIR / target_filename
                if local_path.exists() or target_filename in written_filenames:
                    counts["images_skipped_existing"] += 1
                    decode_status = "exists"
                else:
                    local_path.write_bytes(jpeg_bytes)
                    written_filenames.add(target_filename)
                    counts["images_written"] += 1
                    written = True
                    decode_status = "written"
            else:
                # Dry-run: predict filename using xref + raw bytes (or skip the hash)
                target_filename = f"{a['code']}_{CATALOG_TAG}_p{pg+1:03d}_dry.jpg"
                decode_status = "dry"

            existing.append({
                "filename": target_filename,
                "page": pg + 1,
                "distance": a["distance"],
                "xref": a["xref"],
                "image_w": a["image_w"],
                "image_h": a["image_h"],
                "ext": a["ext"],
            })
            csv_rows.append({
                "code": a["code"],
                "page": pg + 1,
                "distance": round(a["distance"], 2),
                "xref": a["xref"],
                "image_w": a["image_w"],
                "image_h": a["image_h"],
                "target_filename": target_filename,
                "decode_status": decode_status,
                "written": written,
            })

        # Mark page done
        if args.extract and fs_ck is not None:
            ck_ref.set({
                "status": "done",
                "attributions": len(attribs),
                "processed_at": firestore.SERVER_TIMESTAMP,
            })

    counts["codes_with_at_least_one_image"] = sum(1 for v in mapping.values() if v)

    # Write CSV + mapping
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CANDIDATES_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "code", "page", "distance", "xref", "image_w", "image_h",
            "target_filename", "decode_status", "written",
        ])
        w.writeheader()
        for r in sorted(csv_rows, key=lambda x: (x["code"], x["page"])):
            w.writerow(r)

    if args.extract:
        # Persist mapping JSON (write atomically — small file)
        clean_map = {code: imgs for code, imgs in mapping.items() if imgs}
        MAP_JSON.write_text(
            json.dumps(clean_map, indent=2, default=str), encoding="utf-8"
        )
        log.info("Mapping JSON: %s", MAP_JSON)

    # Distance distribution
    if csv_rows:
        ds = sorted(r["distance"] for r in csv_rows)
        log.info("Distance distribution (px): min=%.1f p50=%.1f p80=%.1f p95=%.1f max=%.1f",
                 ds[0], ds[len(ds)//2], ds[int(len(ds)*0.8)], ds[int(len(ds)*0.95)], ds[-1])
        tight = sum(1 for d in ds if d < 200) / len(ds)
        log.info("Fraction with distance < 200 px: %.1f%%", tight * 100)

    log.info("Done. Counts: %s", counts)
    log.info("CSV: %s", CANDIDATES_CSV)


if __name__ == "__main__":
    main()
