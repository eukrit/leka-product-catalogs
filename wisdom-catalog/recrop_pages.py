"""Phase 2 — render catalog pages, ask Gemini 2.5 Pro for per-SKU bounding
boxes, crop, save, build review HTML.

Reads wisdom-catalog/recrop_worklist.json (Phase 1 output). Filters work
units by --pages <list> for the spot-check; runs all 37 by default.

Output:
    wisdom-catalog/preview/pages/p<N>.png         # full-page raster
    wisdom-catalog/preview/crops/<sku>_p<N>.jpeg  # proposed crop
    wisdom-catalog/preview/recrop-preview.html    # human-review file
    wisdom-catalog/recrop_results.json            # machine-readable per-SKU result

Usage:
    python wisdom-catalog/recrop_pages.py --pages 77,86,87   # spot-check 3 pages
    python wisdom-catalog/recrop_pages.py                    # all pages in worklist
    python wisdom-catalog/recrop_pages.py --pages all --upload-gcs
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import sys
import time
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("recrop_pages")

PDF_SEARCH_DIRS = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\2026 Wisdom Product Catalogs Claude\Wisdom Slack Downloads",
    r"C:\Users\Eukrit\My Drive\Catalogs GO\Wisdom Playground",
]


def find_pdf(name: str) -> Optional[str]:
    for d in PDF_SEARCH_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None
PREVIEW_DIR = os.path.join(THIS_DIR, "preview")
PAGE_DIR = os.path.join(PREVIEW_DIR, "pages")
CROP_DIR = os.path.join(PREVIEW_DIR, "crops")
PREVIEW_HTML = os.path.join(PREVIEW_DIR, "recrop-preview.html")
RESULTS_JSON = os.path.join(THIS_DIR, "recrop_results.json")
WORKLIST_JSON = os.path.join(THIS_DIR, "recrop_worklist.json")

GCP_PROJECT = "ai-agents-go"
GEMINI_LOCATION = "global"
GEMINI_MODEL = "gemini-2.5-pro"

# Schema — Gemini object-detection convention: ymin/xmin/ymax/xmax in [0, 1000]
BBOX_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "boxes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "sku": {"type": "STRING"},
                    "found": {"type": "BOOLEAN"},
                    "ymin": {"type": "NUMBER"},
                    "xmin": {"type": "NUMBER"},
                    "ymax": {"type": "NUMBER"},
                    "xmax": {"type": "NUMBER"},
                    "confidence": {"type": "NUMBER"},
                    "reasoning": {"type": "STRING"},
                },
                "required": ["sku", "found", "confidence"],
            },
        }
    },
    "required": ["boxes"],
}


def open_gemini():
    from google import genai
    return genai.Client(vertexai=True, project=GCP_PROJECT, location=GEMINI_LOCATION)


def render_page(pdf_path: str, page_num: int, dpi: int = 300) -> Image.Image:
    """1-based page index."""
    with fitz.open(pdf_path) as doc:
        page = doc[page_num - 1]
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def bbox_prompt(candidates: list[dict]) -> str:
    lines = []
    for c in candidates:
        lines.append(f"  - sku={c['sku']}: \"{c['title']}\"")
    return (
        "You are looking at a single page from a children's outdoor-play catalog.\n"
        "Several products are usually shown on the page. I need a tight bounding box "
        "around the primary product photo for each item code listed below.\n\n"
        "Item codes that the merged JSON says appear on this page:\n"
        + "\n".join(lines) + "\n\n"
        "For each item code:\n"
        "  - If you can identify which product on the page corresponds to that code "
        "(via a label, caption, code text near a photo, or by elimination), return "
        "found=true with a tight bounding box around the cleanest product photo for "
        "that SKU (exclude captions, prices, other products).\n"
        "  - If you cannot confidently locate it on this page, return found=false.\n\n"
        "Coordinates: ymin/xmin/ymax/xmax in the 0-1000 normalized range. "
        "0,0 = top-left, 1000,1000 = bottom-right. ymax > ymin, xmax > xmin.\n"
        "confidence: 0-1.0, your confidence in the box.\n"
        "reasoning: UNDER 10 WORDS (e.g. \"code under photo\", \"caption matches\", \"only sand-water station\").\n\n"
        "Be conservative: prefer found=false over a wild guess. If the same photo could "
        "match multiple SKUs (e.g. a collage that's the same for both standard packages), "
        "return the same box for each."
    )


def call_gemini_bbox(gem, page_image: Image.Image,
                     candidates: list[dict]) -> dict:
    from google.genai import types as genai_types

    buf = io.BytesIO()
    # Use JPEG to keep payload small; bbox precision unaffected at 300 DPI source.
    page_image.save(buf, format="JPEG", quality=85)
    img_bytes = buf.getvalue()
    log.info("    image payload %.1f KB", len(img_bytes) / 1024)

    prompt = bbox_prompt(candidates)
    delays = [3, 8, 20]
    last: Optional[Exception] = None
    for attempt in range(len(delays) + 1):
        try:
            resp = gem.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    genai_types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    prompt,
                ],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BBOX_SCHEMA,
                    temperature=0.1,
                    max_output_tokens=16384,
                ),
            )
            try:
                return json.loads(resp.text or "{}")
            except json.JSONDecodeError:
                last = RuntimeError(f"Non-JSON response: {(resp.text or '')[:200]}")
                if attempt == len(delays):
                    return {"boxes": [], "error": str(last)}
        except Exception as e:
            last = e
            msg = str(e)
            if any(t in msg for t in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "DEADLINE_EXCEEDED")):
                if attempt == len(delays):
                    return {"boxes": [], "error": str(e)[:300]}
                time.sleep(delays[attempt])
                continue
            return {"boxes": [], "error": str(e)[:300]}
    return {"boxes": [], "error": str(last) if last else "unknown"}


def crop_from_norm(page_image: Image.Image, ymin: float, xmin: float,
                   ymax: float, xmax: float, pad: int = 8) -> Image.Image:
    """Crop using Gemini's 0-1000 normalized coords."""
    W, H = page_image.size
    x0 = max(0, int(W * (xmin / 1000.0)) - pad)
    y0 = max(0, int(H * (ymin / 1000.0)) - pad)
    x1 = min(W, int(W * (xmax / 1000.0)) + pad)
    y1 = min(H, int(H * (ymax / 1000.0)) + pad)
    if x1 <= x0 or y1 <= y0:
        return None
    return page_image.crop((x0, y0, x1, y1))


def img_to_b64(img: Image.Image, fmt: str = "JPEG", quality: int = 80,
               max_side: int = 1400) -> str:
    """Resize-down for the preview HTML so the file isn't 50 MB."""
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def draw_overlay(page_image: Image.Image, boxes: list[dict]) -> Image.Image:
    """Draw rectangles + SKU labels on the page raster (for the preview)."""
    from PIL import ImageDraw, ImageFont
    img = page_image.copy()
    draw = ImageDraw.Draw(img)
    W, H = img.size
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    palette = ["#FF1744", "#00C853", "#2962FF", "#FF6F00", "#AA00FF", "#00B8D4"]
    for i, b in enumerate(boxes):
        if not b.get("found"):
            continue
        color = palette[i % len(palette)]
        ymin = b.get("ymin", 0) or 0
        xmin = b.get("xmin", 0) or 0
        ymax = b.get("ymax", 0) or 0
        xmax = b.get("xmax", 0) or 0
        x0, y0 = int(W * xmin / 1000.0), int(H * ymin / 1000.0)
        x1, y1 = int(W * xmax / 1000.0), int(H * ymax / 1000.0)
        draw.rectangle([x0, y0, x1, y1], outline=color, width=6)
        label = f"{b.get('sku','?')}  {b.get('confidence',0):.2f}"
        draw.rectangle([x0, max(0, y0 - 38), x0 + 320, y0], fill=color)
        draw.text((x0 + 6, max(0, y0 - 34)), label, fill="white", font=font)
    return img


PREVIEW_CSS = """
  body { font-family: Manrope, system-ui, sans-serif; margin: 0; padding: 24px; background: #FFF9E6; color: #182557; }
  h1 { color: #8003FF; }
  .page { background: white; border-radius: 16px; box-shadow: 0 2px 8px rgba(24,37,87,.08); margin: 24px 0; padding: 24px; }
  .page-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; }
  .grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px; align-items: start; }
  .full-page img { width: 100%; border: 1px solid #eee; border-radius: 8px; }
  .crops { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .crop { background: #FFF9E6; border-radius: 8px; padding: 8px; text-align: center; }
  .crop img { max-width: 100%; max-height: 220px; border-radius: 4px; background: white; }
  .crop .sku { font-weight: 700; margin-top: 6px; font-size: 0.9rem; }
  .crop .title { font-size: 0.78rem; opacity: 0.7; margin-top: 2px; }
  .crop .conf { font-size: 0.78rem; margin-top: 4px; }
  .crop .not-found { background: #ffebee; color: #c62828; padding: 4px 8px; border-radius: 4px; font-size: 0.78rem; }
  .crop .reasoning { font-size: 0.72rem; margin-top: 6px; color: #555; font-style: italic; }
  .summary { background: white; padding: 16px 24px; border-radius: 16px; margin-bottom: 24px; }
"""


def render_preview_html(worklist_meta: str, page_count: int, total_pages: int,
                        sku_count_total: int, sku_count_found: int,
                        mean_conf: float, pages_html: str) -> str:
    pct = round(100 * sku_count_found / max(1, sku_count_total))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Recrop preview</title>
<style>{PREVIEW_CSS}</style></head><body>
<h1>Recrop preview - Wisdom outdoor-play</h1>
<div class="summary">
  <p><strong>Worklist:</strong> {worklist_meta}</p>
  <p><strong>Pages rendered:</strong> {page_count} / {total_pages}</p>
  <p><strong>Total SKUs requested:</strong> {sku_count_total}</p>
  <p><strong>Gemini found:</strong> {sku_count_found} ({pct}%)</p>
  <p><strong>Mean confidence (found):</strong> {mean_conf:.2f}</p>
</div>
{pages_html}
</body></html>
"""


def render_page_block(page: int, pdf: str, n_found: int, n_total: int,
                      overlay_b64: str, crops_html: str) -> str:
    return f"""
<div class="page">
  <div class="page-header">
    <h2>Page {page} - {pdf}</h2>
    <span>{n_found}/{n_total} SKUs located</span>
  </div>
  <div class="grid">
    <div class="full-page">
      <img src="data:image/jpeg;base64,{overlay_b64}" alt="page overlay">
    </div>
    <div class="crops">{crops_html}</div>
  </div>
</div>
"""


def render_crop_block(crop_img_html: str, sku: str, title: str,
                      status_html: str, reasoning: str) -> str:
    return f"""
<div class="crop">
  {crop_img_html}
  <div class="sku">{sku}</div>
  <div class="title">{title}</div>
  {status_html}
  <div class="reasoning">{reasoning}</div>
</div>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worklist", default=WORKLIST_JSON)
    parser.add_argument("--pages", default="",
                        help="Comma-separated page numbers, or 'all' (default = all in worklist).")
    parser.add_argument("--results", default=RESULTS_JSON)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--limit-pages", type=int, default=0,
                        help="Process at most N pages from the worklist (after --pages filter).")
    args = parser.parse_args()

    os.makedirs(PAGE_DIR, exist_ok=True)
    os.makedirs(CROP_DIR, exist_ok=True)

    with open(args.worklist, "r", encoding="utf-8") as fh:
        wl = json.load(fh)

    work_units = wl["work_units"]
    if args.pages and args.pages != "all":
        wanted = {int(p.strip()) for p in args.pages.split(",") if p.strip()}
        work_units = [wu for wu in work_units if int(wu["page"]) in wanted]
    if args.limit_pages and len(work_units) > args.limit_pages:
        work_units = work_units[: args.limit_pages]
    log.info("Processing %d page work units.", len(work_units))

    gem = open_gemini()
    results = []
    pages_html = []
    sku_total = 0
    sku_found = 0
    confs = []

    for wu in work_units:
        pdf_name = wu["pdf"]
        page_num = int(wu["page"])
        pdf_path = find_pdf(pdf_name)
        if not pdf_path:
            log.error("PDF missing: %s (searched %s)", pdf_name, PDF_SEARCH_DIRS)
            continue
        log.info("Page %d (%s) — %d candidate SKUs", page_num, pdf_name,
                 len(wu["candidates"]))
        page_img = render_page(pdf_path, page_num, dpi=args.dpi)
        page_img_path = os.path.join(PAGE_DIR, f"p{page_num:03d}.png")
        page_img.save(page_img_path)
        log.info("    rendered → %s (%dx%d)", page_img_path, page_img.width, page_img.height)

        gem_resp = call_gemini_bbox(gem, page_img, wu["candidates"])
        boxes = gem_resp.get("boxes") or []

        # Index boxes by SKU
        by_sku = {b.get("sku", "").upper(): b for b in boxes}
        page_result = {
            "pdf": pdf_name,
            "page": page_num,
            "candidates": wu["candidates"],
            "boxes_raw": boxes,
            "gemini_error": gem_resp.get("error"),
            "crops": [],
        }

        crops_html = []
        n_found_this_page = 0
        for cand in wu["candidates"]:
            sku = cand["sku"]
            sku_total += 1
            b = by_sku.get(sku.upper(), {})
            crop_record: dict = {"sku": sku, "title": cand["title"],
                                 "found": bool(b.get("found")),
                                 "confidence": float(b.get("confidence") or 0),
                                 "reasoning": (b.get("reasoning") or "")[:300]}
            if b.get("found"):
                sku_found += 1
                confs.append(float(b.get("confidence") or 0))
                n_found_this_page += 1
                crop_img = crop_from_norm(page_img,
                                          b.get("ymin", 0), b.get("xmin", 0),
                                          b.get("ymax", 0), b.get("xmax", 0))
                if crop_img is not None:
                    crop_path = os.path.join(CROP_DIR, f"{sku}_p{page_num:03d}.jpeg")
                    crop_img.save(crop_path, "JPEG", quality=92)
                    crop_record["crop_path"] = crop_path
                    crop_record["bbox_norm"] = {k: b.get(k) for k in ("ymin", "xmin", "ymax", "xmax")}
                    crop_img_html = f'<img src="data:image/jpeg;base64,{img_to_b64(crop_img, quality=82, max_side=600)}" alt="{sku}">'
                    status_html = f'<div class="conf">conf {crop_record["confidence"]:.2f}</div>'
                else:
                    crop_img_html = '<div class="not-found">invalid bbox</div>'
                    status_html = ''
            else:
                crop_img_html = '<div class="not-found">not found on this page</div>'
                status_html = ''
            crops_html.append(render_crop_block(
                crop_img_html=crop_img_html,
                sku=sku,
                title=cand["title"].replace("<", "&lt;").replace(">", "&gt;")[:80],
                status_html=status_html,
                reasoning=crop_record["reasoning"].replace("<", "&lt;").replace(">", "&gt;"),
            ))
            page_result["crops"].append(crop_record)

        overlay = draw_overlay(page_img, boxes)
        pages_html.append(render_page_block(
            page=page_num,
            pdf=pdf_name,
            n_found=n_found_this_page,
            n_total=len(wu["candidates"]),
            overlay_b64=img_to_b64(overlay, quality=75, max_side=1600),
            crops_html="\n".join(crops_html),
        ))
        results.append(page_result)
        if page_result["gemini_error"]:
            log.warning("    Gemini error: %s", page_result["gemini_error"][:200])

    # Write outputs
    with open(args.results, "w", encoding="utf-8") as fh:
        json.dump({"pages": results,
                   "summary": {
                       "sku_total": sku_total,
                       "sku_found": sku_found,
                       "mean_confidence": (sum(confs) / len(confs)) if confs else 0.0,
                       "pages_rendered": len(results),
                   }}, fh, indent=2)
    log.info("Wrote %s", args.results)

    html = render_preview_html(
        worklist_meta=os.path.basename(args.worklist),
        page_count=len(results),
        total_pages=len(wl.get("work_units", [])),
        sku_count_total=sku_total,
        sku_count_found=sku_found,
        mean_conf=(sum(confs) / len(confs)) if confs else 0.0,
        pages_html="\n".join(pages_html),
    )
    with open(PREVIEW_HTML, "w", encoding="utf-8") as fh:
        fh.write(html)
    log.info("Wrote %s", PREVIEW_HTML)

    print()
    print("=" * 60)
    print(f"Pages rendered:  {len(results)}")
    print(f"SKUs requested:  {sku_total}")
    print(f"SKUs located:    {sku_found} ({round(100*sku_found/max(1,sku_total))}%)")
    print(f"Mean confidence: {(sum(confs)/len(confs)) if confs else 0:.2f}")
    print(f"Preview HTML:    {PREVIEW_HTML}")
    print(f"Crops dir:       {CROP_DIR}")


if __name__ == "__main__":
    main()
