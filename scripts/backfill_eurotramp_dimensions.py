"""Backfill core dimensions (length/width/height in cm) onto Eurotramp Medusa
products in the competition/performance scope.

The storefront spec table renders Weight + Country but no Dimensions, because
metadata.length_cm/width_cm/height_cm are all 0. The real OPEN-frame dimensions
(the footprint a buyer cares about, e.g. Ultimate 520×305×115 cm) live in the
pricelist description text; the folded/packed dims live in metadata.vendor_data.

Source cascade per scoped product:
  1. Open-frame "A×B×C cm" from the current 2025 (1E) pricelist description.
  2. "A×B cm" (+ separate "height N cm") from the same description.
  3. metadata.vendor_data length/width/height (folded) as a last resort.

Writes metadata.length_cm/width_cm/height_cm (ints, cm) and a metadata.dimensions
dict; stashes metadata.previous_dimensions + dimensions_source for rollback/audit.

Read-only unless --write. Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.

Usage:
    python scripts/backfill_eurotramp_dimensions.py --pricelist "<xlsx>" --dry-run
    python scripts/backfill_eurotramp_dimensions.py --pricelist "<xlsx>" --write
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import openpyxl
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SC_EUROTRAMP = "sc_01KNQAA3Y72W17B7CP2VQ93T3M"
SCOPE_FILE = REPO_ROOT / "data" / "curated" / "eurotramp_performance_line.json"

DIM3 = re.compile(r"(\d{2,4})\s*[x×]\s*(\d{2,4})\s*[x×]\s*(\d{2,4})\s*cm", re.I)
DIM2 = re.compile(r"(\d{2,4})\s*[x×]\s*(\d{2,4})\s*cm", re.I)
HEIGHT = re.compile(r"height\s*(\d{1,3})(?:[.,]\d+)?\s*(?:-\s*\d+)?\s*cm", re.I)


def load_scope() -> list[str]:
    data = json.loads(SCOPE_FILE.read_text(encoding="utf-8"))
    return [h for v in data["groups"].values() for h in v]


def article_of(item_code: str) -> str:
    a = (item_code or "").strip()
    if a.upper().startswith("ET-"):
        a = a[3:]
    return a.split("-eurotramp")[0].strip()


def pricelist_descriptions(xlsx: Path) -> dict[str, str]:
    wb = openpyxl.load_workbook(str(xlsx), data_only=True)
    ws = wb.active
    out: dict[str, str] = {}
    for r in ws.iter_rows(min_row=7, values_only=True):
        art, desc = r[0], r[1]
        if art is None:
            continue
        a = str(art).strip()
        if a not in out and desc:
            out[a] = str(desc)
    return out


def _to_int(x) -> int:
    try:
        return int(round(float(str(x).replace(",", ".").split()[0])))
    except (TypeError, ValueError, IndexError):
        return 0


def dims_from_desc(desc: str) -> tuple[tuple[int, int, int] | None, str]:
    if not desc:
        return None, ""
    m = DIM3.search(desc)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3))), "pricelist-frame-LxWxH"
    m = DIM2.search(desc)
    if m:
        h = HEIGHT.search(desc)
        return (int(m.group(1)), int(m.group(2)), int(h.group(1)) if h else 0), "pricelist-LxW(+H)"
    return None, ""


def dims_from_vendor_data(vd: dict) -> tuple[tuple[int, int, int] | None, str]:
    if not vd:
        return None, ""
    l, w, h = _to_int(vd.get("length")), _to_int(vd.get("width")), _to_int(vd.get("height"))
    if l or w or h:
        return (l, w, h), "vendor_data-folded"
    return None, ""


def medusa_session() -> tuple[requests.Session, dict]:
    s = requests.Session()
    tok = s.post(BACKEND + "/auth/user/emailpass", json={
        "email": os.environ["LEKA_MEDUSA_ADMIN_EMAIL"],
        "password": os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]}, timeout=30).json()["token"]
    return s, {"Authorization": "Bearer " + tok}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pricelist", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    scope = load_scope()
    desc = pricelist_descriptions(Path(args.pricelist))
    s, H = medusa_session()

    # fetch scoped products (id, handle, item_code, vendor_data, current dims)
    prods: dict[str, dict] = {}
    off = 0
    while True:
        r = s.get(BACKEND + "/admin/products", headers=H, params={
            "limit": 100, "offset": off, "sales_channel_id[]": SC_EUROTRAMP,
            "fields": "id,handle,metadata"}, timeout=60).json()
        b = r.get("products", [])
        for p in b:
            prods[p["handle"]] = p
        off += 100
        if len(b) < 100:
            break

    results, written = [], 0
    for h in scope:
        p = prods.get(h)
        if not p:
            results.append((h, "MISSING", None, "")); continue
        md = p.get("metadata") or {}
        art = article_of(md.get("item_code", ""))
        dims, src = dims_from_desc(desc.get(art, ""))
        if not dims:
            dims, src = dims_from_vendor_data(md.get("vendor_data") or {})
        # Require a sane footprint: length & width > 0 (height may be 0 for
        # in-ground trampolines / flat tracks). Skip jumbled rows (e.g. 0×W×H).
        if not dims or dims[0] <= 0 or dims[1] <= 0:
            results.append((h, "NO-DIMS", None, "")); continue
        results.append((h, "ok", dims, src))

        if args.write:
            l, w, ht = dims
            prev = {"length_cm": md.get("length_cm"), "width_cm": md.get("width_cm"),
                    "height_cm": md.get("height_cm")}
            payload = {"metadata": {
                "length_cm": l, "width_cm": w, "height_cm": ht,
                "dimensions": {"length_cm": l, "width_cm": w, "height_cm": ht},
                "dimensions_source": src,
                "previous_dimensions": prev,
            }}
            rr = s.post(BACKEND + f"/admin/products/{p['id']}", headers=H, json=payload, timeout=60)
            rr.raise_for_status()
            written += 1

    ok = [r for r in results if r[1] == "ok"]
    nod = [r for r in results if r[1] == "NO-DIMS"]
    print(f"scope={len(scope)}  with-dims={len(ok)}  no-dims={len(nod)}  written={written}")
    for h, st, dims, src in results:
        if st == "ok":
            print(f"  {h:55} {dims[0]}x{dims[1]}x{dims[2]} cm   [{src}]")
        else:
            print(f"  {h:55} -- {st}")
    if not args.write:
        print("DRY-RUN — no Medusa writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
