"""Archimedes Water Play (Wenzhou Daosen) pricelist parser.

Source: Wenzhou Daosen factory pricelist (温州道森游乐戏水) — single sheet,
36 rows of children's water-play SKUs with Chinese names, raw dimensions,
and CNY (RMB) prices. Vendor: 桂书龙 (13676763303), Yongjia/Wenzhou.

Output:
  1. archimedes-water-play-catalog/data/pricelist_2026-05-29_parsed.csv
  2. Firestore vendors/archimedes-water-play/pricelists/2026-05-29 (audit doc)

Dimensions are kept as raw strings — the source mixes units (cm vs. mm),
formats (`a*b*c`, `a×b×c`, `直径220cm`, `定制`), and partial dims (diameter
+ length only). Normalizing would require per-SKU judgement and is left
for a follow-up landed-pricing pass.

Usage:
    python archimedes-water-play-catalog/import_pricelist.py --dry-run
    python archimedes-water-play-catalog/import_pricelist.py
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAND = "archimedes-water-play"
PRICELIST_DATE = "2026-05-29"
SOURCE_XLS = (
    REPO_ROOT / "archimedes-water-play-catalog" / "data" / "source"
    / "daosen_pricelist_2026-05-29.xls"
)
SOURCE_LABEL = "温州道森游乐戏水.xls"
SHEET_NAME = "儿童戏水"
VENDOR_META = {
    "vendor_name_zh": "温州道森游乐戏水",
    "vendor_name_en": "Wenzhou Daosen Water Play",
    "address_zh": "浙江省温州市永嘉县桥下镇洋湾工业区",
    "contact_name_zh": "桂书龙",
    "contact_phone": "13676763303",
    "contact_wechat": "13676763303",
    "contact_qq": "909753091",
    "currency": "CNY",
    "customizable": True,
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("archimedes-water-play")


def _slugify_sku(idx: int, name_zh: str) -> str:
    """SKU = AWP### (Archimedes Water Play, 1-based, zero-padded)."""
    return f"AWP{idx:03d}"


def _parse_dim_string(raw) -> dict:
    """Best-effort parse of a raw dimension cell.

    Returns: {raw, length, width, height, unit_guess, kind}
    where lengths are floats in the source unit (no normalization to cm/mm)
    and kind is one of: "lwh", "two-dim", "diameter", "length", "custom",
    "unknown". Mixed units in this pricelist (mm vs cm) make automated
    CBM calculation unsafe — caller should treat values as opaque.
    """
    out = {"raw": "", "length": None, "width": None, "height": None,
           "unit_guess": None, "kind": "unknown"}
    if raw is None:
        return out
    s = str(raw).strip()
    out["raw"] = s
    if not s:
        return out

    has_cm = "cm" in s.lower()
    out["unit_guess"] = "cm" if has_cm else None

    # 定制 = custom-made (no fixed size)
    if "定制" in s:
        out["kind"] = "custom"
        return out
    # 分离 = separate/modular
    if "分离" in s:
        out["kind"] = "custom"
        return out

    # 直径NNN[cm] — diameter only (circular product)
    m = re.search(r"直径\s*([\d.]+)", s)
    if m and "*" not in s and "×" not in s:
        out["length"] = float(m.group(1))
        out["kind"] = "diameter"
        return out

    # 长度NNNN — length only
    m = re.search(r"长度\s*([\d.]+)", s)
    if m and "*" not in s and "×" not in s:
        out["length"] = float(m.group(1))
        out["kind"] = "length"
        return out

    # Strip unit suffix and split on * or ×
    body = re.sub(r"\s*cm\s*", "", s, flags=re.IGNORECASE)
    parts = re.split(r"\s*[\*×]\s*", body)
    nums = []
    for p in parts:
        m = re.search(r"[\d.]+", p)
        if m:
            try:
                nums.append(float(m.group(0)))
            except ValueError:
                pass
    if len(nums) == 3:
        out["length"], out["width"], out["height"] = nums
        out["kind"] = "lwh"
    elif len(nums) == 2:
        out["length"], out["height"] = nums
        out["kind"] = "two-dim"  # likely diameter × height
    elif len(nums) == 1:
        out["length"] = nums[0]
        out["kind"] = "length"
    return out


def read_pricelist(path: Path) -> list[dict]:
    try:
        import pandas as pd
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pandas is required: pip install pandas xlrd") from e

    df = pd.read_excel(path, sheet_name=SHEET_NAME, header=None)
    log.info("Read sheet %r: %d rows", SHEET_NAME, len(df))

    rows: list[dict] = []
    idx = 0
    for _, row in df.iterrows():
        name = row[0]
        if name is None or (isinstance(name, float) and str(name) == "nan"):
            continue
        name_s = str(name).strip()
        # Skip header / metadata rows
        if not name_s or name_s.startswith("温州道森") or "地址" in name_s:
            continue
        if name_s == "产品名称":
            continue
        # Price must be numeric to be a real product row
        price_cell = row[3]
        try:
            price_cny = float(price_cell)
        except (TypeError, ValueError):
            continue
        if price_cny <= 0:
            continue

        idx += 1
        dim_raw = row[1] if row[1] is not None else ""
        dim_parsed = _parse_dim_string(dim_raw)
        notes_cell = row[4]
        notes = "" if (notes_cell is None or
                       (isinstance(notes_cell, float) and str(notes_cell) == "nan")) else str(notes_cell).strip()
        # Embedded parenthetical hints in the name column (e.g. "压水井 （新款）")
        name_clean = re.sub(r"\s+", " ", name_s)
        rec = {
            "sku": _slugify_sku(idx, name_clean),
            "row_index": idx,
            "name_zh": name_clean,
            "dimensions_raw": dim_parsed["raw"],
            "dimensions_length": dim_parsed["length"],
            "dimensions_width": dim_parsed["width"],
            "dimensions_height": dim_parsed["height"],
            "dimensions_unit_guess": dim_parsed["unit_guess"],
            "dimensions_kind": dim_parsed["kind"],
            "price_cny": price_cny,
            "notes": notes,
        }
        rows.append(rec)
    log.info("Parsed %d product rows", len(rows))
    return rows


def write_csv(rows: list[dict], out: Path) -> None:
    if not rows:
        log.warning("No rows to write")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    log.info("Wrote CSV %s", out)


# --- Firestore REST write ---------------------------------------------------
def _fs_value(v):
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: _fs_value(x) for k, x in v.items()}}}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_fs_value(x) for x in v]}}
    return {"stringValue": str(v)}


def _sa_access_token() -> str:
    tok = os.environ.get("LEKA_FIRESTORE_ACCESS_TOKEN")
    if tok:
        return tok
    try:
        import google.auth
        import google.auth.transport.requests
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/datastore"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    except Exception as e:
        raise RuntimeError(
            "No Firestore access token. Export LEKA_FIRESTORE_ACCESS_TOKEN="
            "$(gcloud auth print-access-token ...) or set up ADC."
        ) from e


def write_firestore(rows: list[dict]) -> None:
    variants_map: dict[str, dict] = {}
    for r in rows:
        key = r["sku"]
        variants_map[key] = {
            "sku": r["sku"],
            "row_index": r["row_index"],
            "name_zh": r["name_zh"],
            "dimensions_raw": r["dimensions_raw"],
            "dimensions_length": r["dimensions_length"],
            "dimensions_width": r["dimensions_width"],
            "dimensions_height": r["dimensions_height"],
            "dimensions_unit_guess": r["dimensions_unit_guess"],
            "dimensions_kind": r["dimensions_kind"],
            "price_cny": r["price_cny"],
            "notes": r["notes"],
        }

    payload = {
        "fields": {
            k: _fs_value(v)
            for k, v in {
                "brand": BRAND,
                "pricelist_date": PRICELIST_DATE,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "source_file": SOURCE_LABEL,
                "sheet_name": SHEET_NAME,
                "row_count": len(rows),
                "currency": "CNY",
                "vendor": VENDOR_META,
                "landed_pricing_status": "deferred — CNY→USD + dim normalization required",
                "variants": variants_map,
            }.items()
        }
    }

    token = _sa_access_token()
    url = (
        f"https://firestore.googleapis.com/v1/projects/ai-agents-go/"
        f"databases/vendors/documents/vendors/{BRAND}/pricelists/{PRICELIST_DATE}"
    )
    req = urllib.request.Request(
        url,
        method="PATCH",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        log.error("Firestore PATCH failed: %s\n%s", e, e.read().decode("utf-8", "replace"))
        raise
    log.info("Firestore: wrote %d variants to vendors/%s/pricelists/%s",
             len(variants_map), BRAND, PRICELIST_DATE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pricelist", type=Path, default=SOURCE_XLS)
    ap.add_argument("--dry-run", action="store_true",
                    help="Write CSV only; do not touch Firestore.")
    args = ap.parse_args()

    rows = read_pricelist(args.pricelist)
    csv_out = REPO_ROOT / "archimedes-water-play-catalog" / "data" / f"pricelist_{PRICELIST_DATE}_parsed.csv"
    write_csv(rows, csv_out)

    if args.dry_run:
        log.info("Dry-run: skipping Firestore write")
        return
    write_firestore(rows)
    log.info("Done. Audit doc: vendors/%s/pricelists/%s", BRAND, PRICELIST_DATE)


if __name__ == "__main__":
    sys.exit(main() or 0)
