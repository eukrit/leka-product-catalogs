"""Vinci Play pricelist → landed cost → retail (THB/USD) → Firestore.

Reads the latest Vinci EUR pricelist, joins with scraped dimensions, computes
THB landed cost using the shipping-automation cost engine (LCL Gdynia → LCB
with Baltic-rate calibration when available), marks up to 40% GM and writes
retail prices to vendors/vinci/products/{item_code}.pricing.

Then run scripts/sync_vendors_to_medusa.py --brand=vinci to push to Medusa.

Usage:
    python vinci-catalog/import_pricelist.py --dry-run --limit 10
    python vinci-catalog/import_pricelist.py
    python vinci-catalog/import_pricelist.py \\
        --pricelist "C:/path/to/pricelist.xlsx" --packing-factor 0.15

Assumptions (revisit when better data lands):
  * Shipping method: LCL Gdynia (PLGDY) → Laem Chabang (THLCH).
  * Packing CBM = installed L*W*H (cm) / 1e6 * packing_factor (default 0.15)
    because Vinci installed dimensions include air gaps. Replace with packing
    manifests when available.
  * Unmatched SKUs (no dimensions): flat 35% landed-cost uplift over EUR FOB.
  * Retail = landed_thb / 0.60 (40% GM); USD derived from THB at live FX.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VINCI_DATA = REPO_ROOT / "vinci-catalog" / "web-app" / "public" / "data" / "products_all.json"
OUTPUT_DIR = REPO_ROOT / "vinci-catalog" / "data"
DEFAULT_PRICELIST = Path(
    r"C:\Users\Eukrit\My Drive\Partners Playground\Vinci\Vinci Play Prices"
    r"\2026-05-11 Vinci pricelist_export_1778483593.xlsx"
)

# Shared landed-cost + retail pricing pipeline (mounts shipping-automation lib).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from shared.landed_pricing import (  # noqa: E402
    GROSS_MARGIN,
    LOGISTICS_TIERS,
    PricedRow,
    calibrate_baltic_rate,
    get_fx_rates,
    parse_dim,
    price_row,
)
from shared.pricing_config import get_pricing_config  # noqa: E402


def _vinci_gross_margin() -> float:
    """Live GM for the Firestore writes; falls back to the shared default."""
    return float(get_pricing_config("vinci").get("gross_margin", GROSS_MARGIN))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("vinci_pricelist")

PRICELIST_DATE = "2026-05-11"


def load_dim_index() -> dict[str, dict]:
    products = json.loads(VINCI_DATA.read_text(encoding="utf-8"))
    index: dict[str, dict] = {}
    for p in products:
        code = (p.get("item_code") or "").strip()
        if not code:
            continue
        dims = p.get("dimensions") or {}
        index[code] = {
            "length_cm": parse_dim(dims.get("length_cm")),
            "width_cm": parse_dim(dims.get("width_cm")),
            "height_cm": parse_dim(dims.get("height_cm")),
        }
    return index


def read_pricelist(path: Path) -> list[tuple[str, float]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or r[1] is None or r[2] is None:
            continue
        code = str(r[1]).strip()
        price = float(r[2])
        ccy = (r[3] or "").upper()
        if ccy not in ("EURO", "EUR"):
            log.warning("Skipping non-EUR row: %s %s %s", code, price, ccy)
            continue
        rows.append((code, price))
    return rows


def write_csv(rows: list[PricedRow], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def write_firestore(rows: list[PricedRow], fx: dict, baltic: dict):
    _sa = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.exists(_sa):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _sa
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")
    from google.cloud import firestore

    db = firestore.Client(project="ai-agents-go", database="vendors")
    coll = db.collection("vendors").document("vinci").collection("products")
    now = datetime.now(timezone.utc).isoformat()

    written = 0
    missing = 0
    batch = db.batch()
    batch_count = 0
    for r in rows:
        doc_id = f"vinci-{r.item_code.lower()}"
        snap = coll.document(doc_id).get()
        if not snap.exists:
            missing += 1
            continue
        batch.update(coll.document(doc_id), {
            "pricing.eur_fob": r.eur_fob,
            "pricing.landed_thb": r.landed_thb,
            "pricing.landed_thb_raw": r.landed_thb_raw,
            "pricing.logistics_pct": r.logistics_pct,
            "pricing.logistics_clamp": r.logistics_clamp,
            "pricing.retail_thb": r.retail_thb,
            "pricing.retail_usd": r.retail_usd,
            "pricing.retail_eur": r.retail_eur,
            "pricing.cbm_used": r.cbm,
            "pricing.cbm_method": r.cbm_method,
            "pricing.freight_thb": r.freight_thb,
            "pricing.duty_thb": r.duty_thb,
            "pricing.vat_thb": r.vat_thb,
            "pricing.match_strategy": r.match_strategy,
            "pricing.gross_margin": _vinci_gross_margin(),
            "pricing.fx_snapshot": {k: fx.get(k) for k in ("USD", "EUR", "THB")},
            "pricing.fx_source": fx.get("_source"),
            "pricing.baltic_rate_snapshot": baltic,
            "pricing.logistics_tiers": [
                {"fob_eur_max": t[0] if t[0] != float("inf") else None,
                 "min_pct": t[1], "max_pct": t[2]} for t in LOGISTICS_TIERS
            ],
            "pricing.pricelist_date": PRICELIST_DATE,
            "pricing.calculated_at": now,
        })
        batch_count += 1
        written += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count:
        batch.commit()
    log.info("Firestore: wrote %d, missing-product-doc %d", written, missing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pricelist", type=Path, default=DEFAULT_PRICELIST)
    ap.add_argument("--dry-run", action="store_true",
                    help="Write CSV only; do not touch Firestore.")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--packing-factor", type=float, default=0.15)
    args = ap.parse_args()

    log.info("Pricelist: %s", args.pricelist)
    rows_raw = read_pricelist(args.pricelist)
    if args.limit:
        rows_raw = rows_raw[: args.limit]
    log.info("Loaded %d pricelist rows", len(rows_raw))

    dim_index = load_dim_index()
    log.info("Loaded %d scraped Vinci products with dims", len(dim_index))

    fx = get_fx_rates(buffer_pct=2)
    log.info("FX (USD=%.4f EUR=%.4f) source=%s", fx.get("USD", 0), fx.get("EUR", 0), fx.get("_source"))

    baltic = calibrate_baltic_rate(fx)
    log.info("Baltic LCL rate: %.2f THB/CBM (sources=%d)",
             baltic["per_cbm_thb"], len(baltic["sources"]))
    for s in baltic["sources"]:
        log.info("  - %s: %.2f", s["source"], s["per_cbm_thb"])

    priced = [
        price_row(c, p, dim_index, fx, baltic, args.packing_factor, brand="vinci")
        for c, p in rows_raw
    ]

    by_strategy = {}
    for r in priced:
        by_strategy[r.match_strategy] = by_strategy.get(r.match_strategy, 0) + 1
    log.info("Match strategy counts: %s", by_strategy)

    out_csv = OUTPUT_DIR / f"pricelist_{PRICELIST_DATE}_landed.csv"
    write_csv(priced, out_csv)
    log.info("Wrote CSV: %s (%d rows)", out_csv, len(priced))

    if args.dry_run:
        log.info("DRY RUN — Firestore not touched.")
        # Print a few sample rows for human sanity check
        for r in priced[:5]:
            log.info("  %s  EUR %.2f  CBM %.3f  landed %.0f THB  retail %.0f THB / $%.2f",
                     r.item_code, r.eur_fob, r.cbm, r.landed_thb, r.retail_thb, r.retail_usd)
        return

    write_firestore(priced, fx, baltic)
    log.info("Done. Next: python scripts/sync_vendors_to_medusa.py --brand=vinci --dry-run")


if __name__ == "__main__":
    main()
