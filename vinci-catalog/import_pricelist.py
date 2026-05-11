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
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VINCI_DATA = REPO_ROOT / "vinci-catalog" / "web-app" / "public" / "data" / "products_all.json"
OUTPUT_DIR = REPO_ROOT / "vinci-catalog" / "data"
DEFAULT_PRICELIST = Path(
    r"C:\Users\Eukrit\My Drive\Partners Playground\Vinci\Vinci Play Prices"
    r"\2026-05-11 Vinci pricelist_export_1778483593.xlsx"
)

# Mount shipping-automation as a library (read-only this run).
SHIPPING_AUTO = Path(
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\shipping-automation\mcp-server"
)
sys.path.insert(0, str(SHIPPING_AUTO))

import cost_engine  # noqa: E402  shipping-automation/mcp-server/cost_engine.py
from cost_engine import estimate_landed_cost  # noqa: E402
from fx_rates import get_fx_rates  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("vinci_pricelist")

GROSS_MARGIN = 0.40  # 40% GM → divide landed by (1 - 0.40)
PRODUCT_CATEGORY = "playground_equipment"
ORIGIN_ROUTE = "europe"
METHOD = "lcl"
UNMATCHED_LANDED_UPLIFT = 1.35  # 35% flat uplift on EUR-THB FOB when no CBM
PRICELIST_DATE = "2026-05-11"

# Tiered minimum/maximum logistics cost as a % of FOB-in-THB.
# Floor ensures every SKU carries a reasonable share of fixed costs
# (clearance, last-mile, insurance). Ceiling clamps outliers where installed
# dimensions wildly overstate packing CBM.
#
# Tuple = (fob_eur_max_inclusive, min_logistics_pct, max_logistics_pct)
LOGISTICS_TIERS: list[tuple[float, float, float]] = [
    (500,         0.80, 2.50),   # < EUR 500 FOB  → logistics 80–250% (small parts dominated by fixed costs)
    (2_000,       0.60, 1.80),   # < EUR 2,000    → 60–180%
    (10_000,      0.45, 1.20),   # < EUR 10,000   → 45–120%
    (float("inf"),0.35, 0.80),   # ≥ EUR 10,000   → 35–80% (large structures, fixed costs amortized)
]


def logistics_band(eur_fob: float) -> tuple[float, float]:
    for cap, lo, hi in LOGISTICS_TIERS:
        if eur_fob <= cap:
            return lo, hi
    return LOGISTICS_TIERS[-1][1], LOGISTICS_TIERS[-1][2]


@dataclass
class PricedRow:
    item_code: str
    eur_fob: float
    matched: bool
    match_strategy: str          # "exact" | "fuzzy_alpha" | "flat_uplift"
    cbm: float
    cbm_method: str              # "dims_scaled" | "flat_uplift"
    landed_thb: float
    landed_thb_raw: float        # before tier clamp (audit trail)
    logistics_pct: float         # final logistics_thb / fob_thb
    logistics_clamp: str         # "" | "floored" | "capped"
    retail_thb: float
    retail_usd: float
    retail_eur: float
    freight_thb: float
    duty_thb: float
    vat_thb: float
    note: str = ""


def parse_dim(value):
    """Coerce a length/width/height_cm field into a sane single cm value.

    Vinci scrape produces several formats:
      * int/float (clean): 950
      * string range: '390, 540 cm' (multiple platform heights)
      * int with concatenated heights: 90120180210 (= 90, 120, 180, 210 cm)
    For multi-value cases we take the MIN — packing CBM should be the minimum
    rectangular envelope. Anything > 1500 cm (15 m) is treated as unparseable
    and returned as None so the caller falls back to flat-uplift pricing.
    """
    MAX_CM = 1500
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if 0 < v <= MAX_CM:
            return v
        # Concatenated digits like 90120180210 — try splitting into 2/3-digit chunks.
        s = str(int(v))
        for chunk in (3, 2):
            parts = [s[i:i+chunk] for i in range(0, len(s), chunk)]
            try:
                nums = [int(p) for p in parts if p]
                if nums and all(0 < n <= MAX_CM for n in nums):
                    return float(min(nums))
            except ValueError:
                continue
        return None
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(value))]
    nums = [n for n in nums if 0 < n <= MAX_CM]
    return min(nums) if nums else None


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


def fuzzy_lookup(code: str, index: dict[str, dict]) -> tuple[dict | None, str]:
    if code in index:
        return index[code], "exact"
    stripped = re.sub(r"[A-Za-z]+$", "", code)
    if stripped and stripped != code and stripped in index:
        return index[stripped], "fuzzy_alpha"
    if code.lstrip("0") in index:
        return index[code.lstrip("0")], "fuzzy_alpha"
    upper = code.upper()
    if upper in index:
        return index[upper], "fuzzy_alpha"
    return None, "flat_uplift"


def compute_cbm(dims: dict | None, packing_factor: float) -> float | None:
    if not dims:
        return None
    L, W, H = dims.get("length_cm"), dims.get("width_cm"), dims.get("height_cm")
    if not (L and W and H):
        return None
    raw_m3 = (L * W * H) / 1_000_000.0
    return round(raw_m3 * packing_factor, 4)


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


def calibrate_baltic_rate(fx: dict) -> dict:
    """Best-effort live Baltic LCL THB/CBM. Falls back to static 5,500 THB/CBM."""
    sources: list[dict] = []
    static_per_cbm = cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"]
    sources.append({"source": "cost_engine static EU LCL", "per_cbm_thb": static_per_cbm})

    try:
        from rate_feeds import get_fbx_index
        fbx = get_fbx_index()
        feu = fbx.get("FBX_GLOBAL", {}).get("rate_usd_feu")
        if feu:
            usd_thb = fx.get("USD", 35.0)
            # FCL FEU → LCL per-CBM rule of thumb: ~50 CBM/FEU, LCL premium ≈ 1.8x.
            per_cbm_thb = (feu * usd_thb / 50.0) * 1.8
            sources.append({"source": "FBX Global → LCL est", "per_cbm_thb": round(per_cbm_thb, 2)})
    except Exception as e:
        log.warning("FBX lookup failed (non-fatal): %s", e)

    avg = round(sum(s["per_cbm_thb"] for s in sources) / len(sources), 2)
    return {"per_cbm_thb": avg, "sources": sources, "method": "avg"}


def price_row(
    code: str,
    eur: float,
    dim_index: dict,
    fx: dict,
    baltic: dict,
    packing_factor: float,
) -> PricedRow:
    dims, strategy = fuzzy_lookup(code, dim_index)
    cbm = compute_cbm(dims, packing_factor) if dims else None

    if cbm and cbm > 0:
        # Monkey-patched per-CBM rate for this call (Baltic calibration).
        original = cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"]
        try:
            cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"] = baltic["per_cbm_thb"]
            est = estimate_landed_cost(
                origin=ORIGIN_ROUTE, method=METHOD,
                goods_value=eur, goods_currency="EUR",
                cbm=cbm, kg=0,
                product_category=PRODUCT_CATEGORY,
                fx_rates=fx,
            )
        finally:
            cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"] = original

        landed_thb = est["total_landed_thb"]
        freight_thb = est["freight"]["thb"]
        duty_thb = est["customs"]["duty_thb"]
        vat_thb = est["customs"]["vat_thb"]
        cbm_method = "dims_scaled"
        matched = strategy != "flat_uplift"
        match_strategy = strategy
    else:
        # No dimensions: flat 35% landed uplift on EUR-THB FOB.
        eur_thb = fx.get("EUR", 38.0)
        landed_thb = round(eur * eur_thb * UNMATCHED_LANDED_UPLIFT, 2)
        freight_thb = 0.0
        duty_thb = 0.0
        vat_thb = 0.0
        cbm = 0.0
        cbm_method = "flat_uplift"
        matched = False
        match_strategy = "flat_uplift"

    # Tiered logistics clamp: floor + cap as % of FOB-in-THB.
    fob_thb = eur * fx.get("EUR", 38.0)
    landed_thb_raw = landed_thb
    lo_pct, hi_pct = logistics_band(eur)
    floor_landed = fob_thb * (1 + lo_pct)
    cap_landed = fob_thb * (1 + hi_pct)
    logistics_clamp = ""
    if landed_thb < floor_landed:
        landed_thb = floor_landed
        logistics_clamp = "floored"
    elif landed_thb > cap_landed:
        landed_thb = cap_landed
        logistics_clamp = "capped"
    landed_thb = round(landed_thb, 2)
    logistics_pct = round((landed_thb - fob_thb) / fob_thb, 4) if fob_thb else 0.0

    retail_thb = round(landed_thb / (1 - GROSS_MARGIN), 2)
    retail_usd = round(retail_thb / fx.get("USD", 35.0), 2)
    retail_eur = round(retail_thb / fx.get("EUR", 38.0), 2)

    return PricedRow(
        item_code=code,
        eur_fob=eur,
        matched=matched,
        match_strategy=match_strategy,
        cbm=cbm or 0.0,
        cbm_method=cbm_method,
        landed_thb=landed_thb,
        landed_thb_raw=round(landed_thb_raw, 2),
        logistics_pct=logistics_pct,
        logistics_clamp=logistics_clamp,
        retail_thb=retail_thb,
        retail_usd=retail_usd,
        retail_eur=retail_eur,
        freight_thb=freight_thb,
        duty_thb=duty_thb,
        vat_thb=vat_thb,
    )


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
            "pricing.gross_margin": GROSS_MARGIN,
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
        price_row(c, p, dim_index, fx, baltic, args.packing_factor)
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
