"""
Sync 'EPDM 2024 / Pricelist' Google Sheet -> JSON snapshot + Firestore upsert.

Pulls every row from the Pricelist tab, parses section headers into product groups,
re-implements the sheet's formula chain locally so we capture computed Quote/Cost,
then:
  1) Writes docs/forms/data/epdm-pricelist.json (consumed by docs/forms/epdm-pricer.html).
  2) Upserts each row to Firestore database `leka-product-catalogs`:
       - products_epdm  (category=epdm)
       - products_infill (category=infill)
     CFH (`cfh_m`) is a top-level numeric field, queryable by other projects.

Run manually whenever the sheet changes. Idempotent.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import firestore
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = "1wXGZoseE4PWEiY14BmtrYaHkkCJJEPyLQnUte7qUGrg"
SHEET_NAME = "Pricelist"
FIRESTORE_DB = "leka-product-catalogs"

SA_KEY = Path(
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code"
    r"\GCP Credentials\ai-agents-go-claude.json"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = REPO_ROOT / "docs" / "forms" / "data" / "epdm-pricelist.json"

# Globals from the sheet (rows 2-3, 1-indexed)
DEFAULTS = {
    "freight_markup_pct": 0.20,   # L2
    "wastage_pct": 0.02,          # Q3
    "install_thb_sqm": 280.0,     # T3 (default; rows can override via column S)
    "interest_months": 3.0,       # U3
    "annual_interest_pct": 0.0875,  # V3
    "margin_pct": 0.35,           # X3 (rows can override; sand/rubber infill use 0.10)
    "markup_pct": 0.05,           # Z3
    "ceiling_step": 5.0,          # AA2
    "fx_thb": 1.0,                # column N default for THB rows
    "usd_to_thb": 36.0,           # used for USD-priced rows (sheet uses GOOGLEFINANCE)
}

# Section-header -> (category, system, default margin override)
# section text is column B (index 1) on a row where column A (index 0) is blank
SECTIONS = [
    ("SBR Layer Granule",                                ("epdm",   "SBR Granule",      0.35)),
    ("Sand Infill Soccer Field",                         ("infill", "Sand Infill",      0.10)),
    ("Rubber Infill Soccer Field",                       ("infill", "Rubber Infill",    0.10)),
    ("SBR Layer Shreded",                                ("epdm",   "SBR Shreded",      0.35)),
    ("EPDM Wet-pour Technical Rubber Black Miroad",      ("epdm",   "Miroad",           0.35)),
    ("EPDM Wet-pour System Eurosia (Non-UV)",            ("epdm",   "Eurosia Non-UV",   0.35)),
    ("EPDM Wet-pour System Eurosia (UV)",                ("epdm",   "Eurosia UV",       0.35)),
    ("EPDM Wet-pour System Eurosia (Non-UV) - Custom Graphic", ("epdm", "Custom Graphic", 0.35)),
    ("TPV UV",                                            ("epdm",   "TPV UV",          0.35)),
]


def _to_float(v, default=None):
    if v in (None, "", " ", "  "):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("THB", "").replace("$", "")
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except ValueError:
            return default
    s = s.replace(" m", "").strip()
    try:
        return float(s)
    except ValueError:
        return default


def compute_row(row, globals_=DEFAULTS, sbr_backing_w=0.0):
    """Replicate the sheet's formula chain. Returns dict of computed numbers.

    sbr_backing_w: pre-computed W (Cost) of the SBR-Shreded row whose thickness equals
    this row's sbr_mm. 0 for non-layered rows (SBR Shreded itself, infill, granules).
    """
    C = row["thickness_mm"]
    G = row["density"]
    I = row["exw_per_kg"]
    K = row["freight_pct"]
    N = row["fx_rate"]
    O = row["tax_pct"]
    T_install = row["install_thb_sqm"]   # already cumulative for SBR Shreded section
    U = globals_["interest_months"]
    V3 = globals_["annual_interest_pct"]
    Q = globals_["wastage_pct"]
    X = row.get("margin_pct") or globals_["margin_pct"]
    Z = globals_["markup_pct"]
    AA2 = globals_["ceiling_step"]
    AB = row.get("binder_ratio") or 0.0
    AC = row.get("binder_unit_cost_thb") or 0.0

    H = G * C if (G and C) else 0.0
    J = H * I if (H and I) else 0.0
    L = J * K if (J and K) else 0.0
    P = (J + L) * (1.0 + (O or 0.0)) * N if (J or L) else 0.0
    R_wastage = P * Q
    V_interest = P * (V3 / 12.0) * U
    AD_binder = H * AB * AC if (AB and AC) else 0.0
    AE_backing = sbr_backing_w or 0.0
    W = P + R_wastage + T_install + V_interest + AD_binder + AE_backing
    Y = W / (1.0 - X) if 0 < X < 1 else W
    quote = math.ceil(Y / (1.0 - Z) / AA2) * AA2 if Y else 0.0
    return {
        "kg_per_sqm": round(H, 4),
        "exw_per_sqm": round(J, 4),
        "freight_per_sqm": round(L, 4),
        "landed_thb_per_sqm": round(P, 2),
        "wastage_thb_per_sqm": round(R_wastage, 4),
        "install_thb_per_sqm": round(T_install, 2),
        "interest_thb_per_sqm": round(V_interest, 4),
        "binder_thb_per_sqm": round(AD_binder, 2),
        "sbr_backing_thb_per_sqm": round(AE_backing, 2),
        "cost_thb_per_sqm": round(W, 2),
        "cost_plus_margin_thb_per_sqm": round(Y, 2),
        "quote_thb_per_sqm": round(quote, 2),
    }


def fetch_sheet():
    creds = service_account.Credentials.from_service_account_file(
        str(SA_KEY), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    rows = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=SHEET_NAME, valueRenderOption="FORMATTED_VALUE")
        .execute()
        .get("values", [])
    )
    return rows


def parse_rows(rows):
    """Walk rows, track current section, emit one record per product row.

    A 'product row' is one with a non-empty model code in column A (index 0).
    A 'section header' is a row where col A is blank but col B has a known section title.
    """
    out = []
    current = None
    for idx, row in enumerate(rows):
        if not row:
            continue
        col_a = (row[0] if len(row) > 0 else "") or ""
        col_b = (row[1] if len(row) > 1 else "") or ""
        if not col_a.strip() and col_b.strip():
            # Try to match a section header
            for prefix, sect in SECTIONS:
                if col_b.strip().startswith(prefix):
                    current = sect
                    break
            continue
        if not col_a.strip():
            continue
        if current is None:
            continue
        category, system, margin_override = current

        def cell(i):
            return row[i] if i < len(row) else ""

        thickness_mm = _to_float(cell(2), 0.0)
        sbr_raw = cell(3)
        # For infill, col D is sometimes the literal "kg/sq.m." unit string -> treat as zero "mm"
        # and use thickness_mm as kg/sqm (sheet repurposes columns).
        if isinstance(sbr_raw, str) and "kg" in sbr_raw.lower():
            sbr_mm = 0.0
            is_infill_unit = True
        else:
            sbr_mm = _to_float(sbr_raw, 0.0)
            is_infill_unit = False

        cfh_m = _to_float(cell(4), None)
        density = _to_float(cell(6), 0.0)
        exw_per_kg = _to_float(cell(8), 0.0)
        freight_pct = _to_float(cell(10), 0.0)
        currency = (cell(12) or "THB").strip() or "THB"
        fx_rate = _to_float(cell(13), 1.0) or 1.0
        tax_pct = _to_float(cell(14), 0.0)
        # Per-row installation override (col S, index 18) used in SBR Shreded section
        install_override = _to_float(cell(18), None)
        margin_pct = _to_float(cell(23), None)  # col X
        binder_ratio = _to_float(cell(27), None)  # col AB
        binder_unit = _to_float(cell(28), None)  # col AC

        if margin_pct is None:
            margin_pct = margin_override

        # For TPB sheet rows that price in USD (col M reads literally "THB" so fx_rate=1
        # via FX-Rate lookup; the few USD rows show currency cell as something else).
        # Sheet hardcodes EXW in foreign currency; we keep currency string for ref.

        # Installation cost is the total in col T (index 19). For the SBR-Shreded section
        # the sheet stacks per-row increments via T=T(prev)+S; we just read the already-stacked
        # value to stay faithful to the sheet. Col S (index 18) is the per-unit increment and
        # we keep it for reference.
        inst = _to_float(cell(19), None) or DEFAULTS["install_thb_sqm"]

        # Group: section system
        # For Infill, the "thickness" is actually kg/sqm
        sbr_kg_per_sqm = None
        if is_infill_unit:
            sbr_kg_per_sqm = thickness_mm

        record_input = {
            "thickness_mm": thickness_mm,
            "sbr_mm": sbr_mm,
            "cfh_m": cfh_m,
            "density": density,
            "exw_per_kg": exw_per_kg,
            "freight_pct": freight_pct,
            "currency": currency,
            "fx_rate": fx_rate,
            "tax_pct": tax_pct,
            "install_thb_sqm": inst,
            "margin_pct": margin_pct,
            "binder_ratio": binder_ratio,
            "binder_unit_cost_thb": binder_unit,
        }
        # 1st pass: compute without SBR backing lookup (gets correct W for SBR-Shreded rows)
        computed = compute_row(record_input)

        out.append({
            "item_code": col_a.strip(),
            "description": col_b.strip(),
            "brand": None,
            "category": category,
            "system": system,
            "thickness_mm": thickness_mm,
            "sbr_mm": sbr_mm,
            "sbr_kg_per_sqm": sbr_kg_per_sqm,
            "cfh_m": cfh_m,
            "density_kg_per_litre": density,
            "exw_usd_per_kg": exw_per_kg,
            "freight_pct": freight_pct,
            "currency": currency,
            "fx_rate": fx_rate,
            "tax_pct": tax_pct,
            "install_thb_per_sqm": inst,
            "margin_pct": margin_pct,
            "markup_pct": DEFAULTS["markup_pct"],
            "binder_ratio": binder_ratio,
            "binder_unit_cost_thb": binder_unit,
            "pricing": {
                **computed,
                "currency": "THB",
                "price_date": "2024",
                "assumes_globals": DEFAULTS,
            },
            "source": {
                "spreadsheet_id": SPREADSHEET_ID,
                "sheet": SHEET_NAME,
                "row": idx + 1,  # 1-indexed
            },
            "status": "active",
            "_inputs": record_input,  # kept for the 2nd pass; stripped before output
        })

    # 2nd pass: SBR-Shreded backing lookup. The sheet's AE formula reads
    # =INDEX(W:W, MATCH(D, C:C)) — find the SBR-Shreded row whose C (thickness)
    # equals this row's D (sbr_mm) and re-add its W. Applies to Miroad / Eurosia /
    # Custom Graphic / TPV — i.e. layered systems with a non-zero sbr_mm.
    shreded_w_by_thickness = {
        p["thickness_mm"]: p["pricing"]["cost_thb_per_sqm"]
        for p in out if p["system"] == "SBR Shreded" and p["thickness_mm"] > 0
    }
    for p in out:
        if p["system"] in ("Miroad", "Eurosia Non-UV", "Eurosia UV", "Custom Graphic", "TPV UV"):
            backing_thk = p["sbr_mm"]
            if backing_thk and backing_thk in shreded_w_by_thickness:
                backing_w = shreded_w_by_thickness[backing_thk]
                p["pricing"] = compute_row(p["_inputs"], sbr_backing_w=backing_w)
                p["pricing"].update({
                    "currency": "THB", "price_date": "2024",
                    "assumes_globals": DEFAULTS,
                })

    for p in out:
        p.pop("_inputs", None)
    return out


def write_json(products):
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "spreadsheet_id": SPREADSHEET_ID,
            "sheet": SHEET_NAME,
            "url": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit",
        },
        "defaults": DEFAULTS,
        "products": products,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)} ({len(products)} products)")


def upsert_firestore(products, skip=False):
    if skip:
        print("Skipping Firestore upsert (--no-firestore)")
        return
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(SA_KEY)
    db = firestore.Client(project="ai-agents-go", database=FIRESTORE_DB)
    epdm_count = 0
    infill_count = 0
    now = datetime.now(timezone.utc)
    for p in products:
        col = f"products_{p['category']}"
        doc_id = p["item_code"].replace("/", "_").replace(" ", "_")
        doc = {**p, "updated_at": now}
        # Set created_at only on insert
        ref = db.collection(col).document(doc_id)
        snap = ref.get()
        if not snap.exists:
            doc["created_at"] = now
        ref.set(doc, merge=True)
        if p["category"] == "epdm":
            epdm_count += 1
        else:
            infill_count += 1
    print(f"Firestore upsert: products_epdm={epdm_count}, products_infill={infill_count}")


def main():
    skip_fs = "--no-firestore" in sys.argv
    print("Fetching sheet...")
    rows = fetch_sheet()
    print(f"  {len(rows)} raw rows")
    products = parse_rows(rows)
    print(f"  {len(products)} product rows parsed")
    write_json(products)
    upsert_firestore(products, skip=skip_fs)
    print("Done.")


if __name__ == "__main__":
    main()
