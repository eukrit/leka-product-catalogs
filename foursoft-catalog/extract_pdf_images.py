"""Extract per-product images from the 4soft picture-pricelist PDF.

Source: `2025-06-25 4soft_EPDM_graphics_-_picture_-_price_list_2025_optimized.pdf`
(the picture variant of the .xls priced in v2.40.0). 89 pages, grid layout:
each product row has a 100x100px image in the left column (x≈44-99) and its
code at x≈135, e.g.:

    [img]   K1-02B-09   3D Sea star MINI   520,00   60 x 60

Most image cells carry a jpx (JPEG2000, Indexed palette) AND a jpeg (DeviceRGB)
at the same bbox — the DeviceRGB jpeg is the clean, browser-ready full-colour
image, so we prefer it; if a cell only has jpx we render the cell region
(composite → RGB) instead.

This is the only image source for the ~2,000 colour/UV/size SKU variants that
4soft.cz does NOT publish on the web (so v2.41.0 fell back to borrowed
base-design images for the 3D drafts). 100x100 native is the resolution ceiling.

Each image is matched to its code by y-row, validated against the committed
pricelist (only codes that exist in the pricelist are kept), and saved as
`foursoft-catalog/data/pdf_images/<handle>.jpg` plus a mapping JSON.

Usage:
    python foursoft-catalog/extract_pdf_images.py            # extract all
    python foursoft-catalog/extract_pdf_images.py --pages 1-3 # smoke test
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "foursoft-catalog" / "data"
PRICELIST_CSV = DATA_DIR / "pricelist_2025-03-01.csv"
OUT_DIR = DATA_DIR / "pdf_images"
MAP_JSON = DATA_DIR / "pdf_images_map.json"
DEFAULT_PDF = Path(
    r"C:\Users\Eukrit\My Drive\Partners Playground\4soft"
    r"\2025-06-25 4soft_EPDM_graphics_-_picture_-_price_list_2025_optimized.pdf"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("foursoft_pdf_images")

CODE_RE = re.compile(r"^[A-Z]\d{1,2}-\d{1,2}[A-Z]?-[0-9A-Z]+$")
ROW_TOL = 30.0          # px: code-to-image vertical alignment tolerance
LEFT_MAX_X = 110.0      # px: image left column is x0 < this
RENDER_ZOOM = 3.0       # for jpx-only fallback cells


def norm(code: str) -> str:
    return (code or "").strip().upper()


def handle_for(code: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")
    return f"4soft-{slug}"


def parse_pages_arg(s: str | None, n: int) -> range:
    if not s:
        return range(1, n)  # skip cover page 0
    a, _, b = s.partition("-")
    lo = int(a); hi = int(b) if b else lo
    return range(lo, hi + 1)


def left_images(page) -> list[dict]:
    """Left-column image cells on a page → [{bbox, ymid, xref, is_rgb_jpeg}].
    When jpx+jpeg share a bbox, prefer the DeviceRGB jpeg xref."""
    doc = page.parent
    by_box: dict[tuple, dict] = {}
    for img in page.get_images(full=True):
        xref, _smask, _w, _h, _bpc, cs = img[0], img[1], img[2], img[3], img[4], img[5]
        for r in page.get_image_rects(xref):
            if r.x0 >= LEFT_MAX_X:
                continue
            key = (round(r.x0), round(r.y0), round(r.x1), round(r.y1))
            is_rgb = (cs == "DeviceRGB")
            cur = by_box.get(key)
            if cur is None or (is_rgb and not cur["is_rgb_jpeg"]):
                by_box[key] = {
                    "bbox": (r.x0, r.y0, r.x1, r.y1),
                    "ymid": (r.y0 + r.y1) / 2.0,
                    "xref": xref,
                    "is_rgb_jpeg": is_rgb,
                }
    return sorted(by_box.values(), key=lambda d: d["ymid"])


def code_spans(page, valid: set[str]) -> list[dict]:
    out = []
    d = page.get_text("dict")
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                t = sp["text"].strip()
                if CODE_RE.match(t) and norm(t) in valid:
                    x0, y0, x1, y1 = sp["bbox"]
                    out.append({"code": norm(t), "ymid": (y0 + y1) / 2.0})
    return sorted(out, key=lambda d: d["ymid"])


def extract_cell(page, cell: dict) -> bytes:
    """Raw DeviceRGB jpeg bytes when available, else render the cell to jpeg."""
    if cell["is_rgb_jpeg"]:
        info = page.parent.extract_image(cell["xref"])
        if info.get("ext") in ("jpeg", "jpg", "png"):
            return info["image"]
    pix = page.get_pixmap(clip=fitz.Rect(*cell["bbox"]),
                          matrix=fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM))
    return pix.tobytes("jpeg")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--pages", help="e.g. '1-3' (1-based, inclusive). Default: all.")
    args = ap.parse_args()

    if not args.pdf.exists():
        log.error("PDF not found: %s", args.pdf); return 2
    valid = {norm(r["code"]) for r in csv.DictReader(PRICELIST_CSV.open(encoding="utf-8"))}
    log.info("pricelist codes: %d", len(valid))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(args.pdf))
    pages = parse_pages_arg(args.pages, doc.page_count)

    mapping: dict[str, dict] = {}
    rendered = 0
    multi_warn = 0
    for pno in pages:
        page = doc[pno]
        codes = code_spans(page, valid)
        imgs = left_images(page)
        used = [False] * len(imgs)
        for c in codes:
            if c["code"] in mapping:
                continue
            best, best_dy = None, ROW_TOL
            for i, im in enumerate(imgs):
                if used[i]:
                    continue
                dy = abs(im["ymid"] - c["ymid"])
                if dy < best_dy:
                    best, best_dy = i, dy
            if best is None:
                continue
            used[best] = True
            cell = imgs[best]
            data = extract_cell(page, cell)
            if not cell["is_rgb_jpeg"]:
                rendered += 1
            handle = handle_for(c["code"])
            (OUT_DIR / f"{handle}.jpg").write_bytes(data)
            mapping[c["code"]] = {
                "handle": handle, "page": pno + 1,
                "bytes": len(data),
                "method": "jpeg" if cell["is_rgb_jpeg"] else "render",
            }

    MAP_JSON.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    matched = len(mapping)
    log.info("pages scanned: %d", len(pages))
    log.info("images extracted: %d (native jpeg %d / rendered %d)",
             matched, matched - rendered, rendered)
    log.info("coverage: %d / %d pricelist codes (%.1f%%)",
             matched, len(valid), 100.0 * matched / len(valid))
    missing = sorted(valid - set(mapping))
    log.info("pricelist codes with NO PDF image: %d (sample: %s)",
             len(missing), missing[:8])
    log.info("output: %s  (map: %s)", OUT_DIR, MAP_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
