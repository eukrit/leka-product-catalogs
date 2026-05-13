"""Parse Berliner Seilfabrik 2026 pricelist PDF → CSV.

The pricelist is a tabular PDF with columns:
    Page | Item number | Name | Price in EUR | Remarks

Prices are formatted German-style: "34.333,00 €" → 34333.00.
Some rows have "Price depends on individual project" instead of a numeric price.
Some sub-feature/accessory rows have a Name but no Item number — we synthesize
a handle from the slugified name (with a parent-page disambiguator).

Usage:
    python berliner-catalog/parse_pricelist.py \\
        --pdf "C:/path/to/2025-12-17 20251217_Preisliste_Compendium 11_EN_Ausland.pdf" \\
        --out berliner-catalog/data/pricelist_2026-01-01.csv

Output columns:
    item_code, name, page, list_eur, remarks, status, handle
where status ∈ {active, on_request, name_only_active, name_only_on_request}.
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("berliner_parse")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path(
    r"C:\Users\Eukrit\OneDrive\Documents\Documents GO"
    r"\2025-12-17 Berliner Pricelist 2026"
    r"\2025-12-17 20251217_Preisliste_Compendium 11_EN_Ausland.pdf"
)
DEFAULT_OUT = REPO_ROOT / "berliner-catalog" / "data" / "pricelist_2026-01-01.csv"

POA_MARKER = "Price depends on individual project"
UPON_REQUEST_MARKERS = ("upon request", "price depends on individual project")


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_eur(cell: str) -> float | None:
    """'34.333,00 €' → 34333.00, '1.063,00 €' → 1063.00. Returns None if no number."""
    if not cell:
        return None
    # Strip currency mark and whitespace
    s = re.sub(r"[^\d,.\-]", "", cell)
    if not s:
        return None
    # German format: thousand sep '.', decimal ','
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def detect_schema(header_row: list[str]) -> dict[str, int] | None:
    """Return {field: col_index} for {page?, item_code, name, price, remarks}.

    Returns None if this row isn't a recognizable header.
    """
    cells = [str(c or "").strip().lower() for c in header_row]
    schema: dict[str, int] = {}
    for i, c in enumerate(cells):
        if c.startswith("page"):
            schema["page"] = i
        elif "item" in c and "number" in c:
            schema["item_code"] = i
        elif c in ("name", "nom"):
            schema["name"] = i
        elif "price" in c:
            schema["price"] = i
        elif "remark" in c:
            schema["remarks"] = i
    if "item_code" in schema and "name" in schema and "price" in schema:
        return schema
    return None


def extract_rows(pdf_path: Path) -> list[dict]:
    """Walk every page, find every table, yield normalized row dicts.

    Each table can have 4 or 5 columns (some tables drop the leading Page col).
    We detect the column layout from each table's header row and map cells
    accordingly. Tables without a recognizable header are skipped.
    """
    doc = fitz.open(pdf_path)
    out: list[dict] = []
    seen: set[str] = set()
    for pi in range(doc.page_count):
        page = doc[pi]
        tabs = page.find_tables()
        if not tabs.tables:
            continue
        for ti, t in enumerate(tabs.tables):
            try:
                rows = t.extract()
            except Exception as e:
                log.warning("page %d table %d extract failed: %s", pi + 1, ti, e)
                continue
            if not rows:
                continue

            # Detect schema from the first row that looks like a header.
            schema = None
            data_start = 0
            for idx, r in enumerate(rows[:3]):
                s = detect_schema(r)
                if s:
                    schema = s
                    data_start = idx + 1
                    break
            if not schema:
                log.warning("page %d table %d: no recognizable header, skipping (first row: %s)",
                            pi + 1, ti, rows[0])
                continue

            def cell(r: list, key: str) -> str:
                i = schema.get(key) if schema else None  # noqa: B023
                if i is None or i >= len(r):
                    return ""
                return str(r[i] or "").strip()

            for r in rows[data_start:]:
                item_code = cell(r, "item_code")
                name = cell(r, "name")
                price_cell = cell(r, "price")
                remarks = cell(r, "remarks")
                page_no = cell(r, "page")
                if not item_code and not name:
                    continue
                # Skip mis-detected header lines further down in the table.
                if (item_code.lower() == "item number"
                        or name.lower() in ("name", "nom")):
                    continue

                list_eur = parse_eur(price_cell)
                cell_lc = price_cell.lower()
                is_on_request = (
                    list_eur is None and
                    any(m in cell_lc for m in UPON_REQUEST_MARKERS)
                )
                is_poa = POA_MARKER.lower() in cell_lc

                if item_code and list_eur is not None:
                    status = "active"
                elif item_code:
                    status = "on_request"
                elif name and list_eur is not None:
                    status = "name_only_active"
                else:
                    status = "name_only_on_request"

                if item_code:
                    handle = f"berliner-{slugify(item_code)}"
                else:
                    handle = f"berliner-{slugify(name)}"

                base_handle = handle
                n = 1
                while handle in seen:
                    n += 1
                    handle = f"{base_handle}-{n}"
                seen.add(handle)

                # Normalize remarks: surface PoA/upon-request reason when no number.
                if list_eur is None and not remarks:
                    if is_poa:
                        remarks = POA_MARKER
                    elif is_on_request:
                        remarks = "Upon request"

                out.append({
                    "handle": handle,
                    "item_code": item_code,
                    "name": name or item_code,
                    "page": page_no,
                    "list_eur": list_eur if list_eur is not None else "",
                    "remarks": remarks,
                    "status": status,
                })
    return out


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["handle", "item_code", "name", "page", "list_eur", "remarks", "status"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def summarize(rows: list[dict]) -> dict:
    s: dict[str, int] = {}
    for r in rows:
        s[r["status"]] = s.get(r["status"], 0) + 1
    s["total"] = len(rows)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.pdf.exists():
        log.error("PDF not found: %s", args.pdf)
        return 2

    log.info("Parsing %s", args.pdf)
    rows = extract_rows(args.pdf)
    write_csv(rows, args.out)
    log.info("Wrote %d rows → %s", len(rows), args.out)
    log.info("Breakdown: %s", summarize(rows))

    for r in rows[:5] + rows[-3:]:
        log.info("  %s | %s | EUR %s | %s", r["handle"], r["name"][:40], r["list_eur"], r["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
