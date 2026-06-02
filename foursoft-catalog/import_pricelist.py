"""4soft 2025 EPDM-graphics pricelist (.xls) → 15% EXW discount → landed cost → Firestore.

4soft, s.r.o. (Tanvald, Czech Republic) makes discrete moulded-EPDM play
elements — 3D animals/shapes/tunnels/furniture/fountains and 2D markings
(hopscotch, numbers, footprints). These are **per-item EUR SKUs**, NOT the
area-priced wet-pour surfacing handled by scripts/sync_epdm_pricelist.py
(products_epdm / products_infill, CFH contract). No overlap — see CHANGELOG
v2.38.0 reconciliation note.

This brand follows the Berliner pattern exactly (berliner-catalog/import_pricelist.py):
  * Trade terms = EXW (2020 "Price conditions" PDF): our cost = list * (1 - 0.15).
  * Origin = EU/Czech → 10% Thai duty, 7% import VAT, 7% TH customer VAT embedded.
  * Landed cost via shipping-automation cost_engine (LCL EU → THB, Baltic-rate
    calibration, tiered logistics floor/cap). Most 4soft items have no published
    dims → flat 35% uplift, then the tier floor re-bounds cheap SKUs.
  * Retail = landed_thb / (1 - 0.40)  (40% gross margin — user decision 2026-05-29).
  * Independent THB/USD/EUR/SGD prices → vendors/4soft/products/{handle}.pricing.

The source .xls is a single "POHODA" sheet (Czech accounting export). Columns:
  col B = code, col C = product name, col D = Target SALE price EUR.
Section-header rows (col B set, col C empty) carry the category, e.g.
"3D Products/K-3D animals/", "2D products/F-hopscotch/".

Usage:
    # Auth: GOOGLE_APPLICATION_CREDENTIALS → ai-agents-go SA key (or ADC).
    python foursoft-catalog/import_pricelist.py --dry-run --limit 10
    python foursoft-catalog/import_pricelist.py            # parse + price + Firestore
    python foursoft-catalog/import_pricelist.py --no-seed   # skip brand-config seed

Next: python scripts/sync_brand_prices_to_medusa.py --brand 4soft --dry-run
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "foursoft-catalog" / "data"
PRICELIST_DATE = "2025-03-01"          # .xls "Valid from: 1.3.2025"
PARSED_CSV = DATA_DIR / f"pricelist_{PRICELIST_DATE}.csv"
LANDED_CSV = DATA_DIR / f"pricelist_{PRICELIST_DATE}_landed.csv"

# Source .xls lives in the partner Drive folder (not committed — large/proprietary).
# The committed PARSED_CSV is the reproducible in-repo source of truth.
DEFAULT_XLS = Path(
    r"C:\Users\Eukrit\My Drive\Partners Playground\4soft"
    r"\2025-06-25 4soft_EPDM_graphics-price_list_2025.xls"
)

# Mount shipping-automation as a library (same resolution as shared/landed_pricing.py).
sys.path.insert(0, str(REPO_ROOT))
from shared.landed_pricing import _resolve_shipping_automation  # noqa: E402
_SHIP = _resolve_shipping_automation()
if str(_SHIP) not in sys.path:
    sys.path.insert(0, str(_SHIP))

import cost_engine  # noqa: E402
from cost_engine import estimate_landed_cost  # noqa: E402
from fx_rates import get_fx_rates  # noqa: E402

from shared.pricing_config import (  # noqa: E402
    FS_COLLECTION, FS_DATABASE, FS_DOCUMENT, FS_PROJECT, get_pricing_config,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("foursoft_pricelist")

SLUG = "4soft"
BRAND = "4soft"
SOURCE_URL = "https://4soft.cz/"
VENDORS_DB = "vendors"

# Module-level fallbacks. Source of truth = Firestore pricing_config/canonical
# (brands.4soft + global). Kept in sync with scripts/seed_pricing_config.py.
EXW_DISCOUNT = 0.15           # 2020 "Price conditions" PDF: basic reseller discount
GROSS_MARGIN = 0.40           # user decision 2026-05-29 (4soft-specific)
DUTY_RATE_NON_CHINA = 0.10    # EU/Czech import → 10% Thai duty
THAI_VAT_RATE = 0.07          # 7% Thai import VAT on (CIF + duty)
TH_CUSTOMER_VAT_RATE = 0.07   # 7% TH customer VAT embedded in retail_thb
UNMATCHED_LANDED_UPLIFT = 1.35  # 35% flat uplift on EUR-THB FOB when no CBM
PRODUCT_CATEGORY = "playground_equipment"
ORIGIN_ROUTE = "europe"
METHOD = "air"                  # 2026-05-30 pivot: 4soft is Czech, ships by air (was "lcl")

# Override the cost_engine's per-kg air rate for this run. None → use the engine
# default (see shipping-automation/mcp-server/cost_engine.py ROUTE_PROFILES.europe.air).
# Source the value from foursoft-catalog/data/air-freight-rates-2026-05-30.md; rerun
# with the median, low, and high for sensitivity before promoting to Firestore.
AIR_RATE_OVERRIDE_THB_PER_KG: float | None = None

# IATA general cargo volumetric divisor (kg/m³). 6000 cm³/kg = 167 kg/m³.
# Used by cost_engine when kg=0 and cbm>0 (per-SKU pricing).
VOLUMETRIC_DIVISOR = 167

# Sea-tuned clamps. Knowingly retained under the air pivot — the dry-run diff
# is supposed to surface where the cap dominates so a follow-up PR can retune
# with evidence (see ~/.claude/plans/goal-4soft-is-imported-hazy-mochi.md §4).
LOGISTICS_TIERS: list[tuple[float, float, float]] = [
    (500,          0.60, 1.20),
    (2_000,        0.50, 1.00),
    (10_000,       0.40, 0.80),
    (float("inf"), 0.30, 0.60),
]


def logistics_band(eur_fob: float) -> tuple[float, float]:
    for cap, lo, hi in LOGISTICS_TIERS:
        if eur_fob <= cap:
            return lo, hi
    return LOGISTICS_TIERS[-1][1], LOGISTICS_TIERS[-1][2]


def _foursoft_params() -> dict:
    cfg = get_pricing_config(BRAND)
    return {
        "exw_discount": float(cfg.get("exw_discount", EXW_DISCOUNT)),
        "gross_margin": float(cfg.get("gross_margin", GROSS_MARGIN)),
        "duty_rate_non_china": float(cfg.get("duty_rate_non_china", DUTY_RATE_NON_CHINA)),
        "thai_vat_rate": float(cfg.get("thai_vat_rate", THAI_VAT_RATE)),
        "th_customer_vat_rate": float(cfg.get("th_customer_vat_rate", TH_CUSTOMER_VAT_RATE)),
        "unmatched_landed_uplift": float(cfg.get("unmatched_landed_uplift", UNMATCHED_LANDED_UPLIFT)),
        "sg_customer_gst_rate": float(cfg.get("sg_customer_gst_rate", 0.09)),
        "sg_nubo_gst_registered": bool(cfg.get("sg_nubo_gst_registered", False)),
    }


def handle_for(code: str) -> str:
    """Match the scraper's handle scheme (scripts/scrape-4soft.ts):
    `4soft-${code.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`."""
    slug = re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")
    return f"4soft-{slug}"


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------
@dataclass
class RawRow:
    code: str
    name: str
    list_eur: float
    section: str          # full section header, e.g. "2D products/F-hopscotch/"
    dimension: str        # "3D" | "2D" | "accessory" | "packaging"
    product_group: str    # e.g. "F-hopscotch"
    unit: str             # "set" | "each"


def _classify(section: str) -> tuple[str, str]:
    s = section.lower()
    if s.startswith("3d products"):
        dim = "3D"
    elif s.startswith("2d products"):
        dim = "2D"
    elif "packaging" in s:
        dim = "packaging"
    else:
        dim = "accessory"
    # product_group = last non-empty path segment, e.g. "F-hopscotch"
    parts = [p for p in section.replace("\\", "/").split("/") if p.strip()]
    group = parts[-1].strip() if parts else section.strip()
    return dim, group


def parse_xls(path: Path) -> list[RawRow]:
    import xlrd  # local import so --help works without the dep
    sh = xlrd.open_workbook(str(path)).sheet_by_index(0)
    rows: list[RawRow] = []
    current = ""
    for r in range(sh.nrows):
        code = str(sh.cell_value(r, 1)).strip()
        name = str(sh.cell_value(r, 2)).strip()
        price = sh.cell_value(r, 3) if sh.ncols > 3 else ""
        if not code:
            continue
        # Section header: code cell holds the section title, no name, no price.
        if name == "" and not isinstance(price, (int, float)):
            # Skip the two banner rows (title + company/VAT line).
            if code.lower().startswith("code") or "4soft" in code.lower() \
               or code.lower().startswith("4soft epdm"):
                continue
            current = code
            continue
        if code.lower() == "code":   # header row variant
            continue
        if not isinstance(price, (int, float)) or price == "":
            log.warning("Row %d: code %s has no numeric price (%r) — skipping", r, code, price)
            continue
        dim, group = _classify(current)
        unit = "set" if "(set of" in name.lower() else "each"
        rows.append(RawRow(
            code=code, name=name, list_eur=float(price),
            section=current, dimension=dim, product_group=group, unit=unit,
        ))
    return rows


def write_parsed_csv(rows: list[RawRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def read_parsed_csv(path: Path) -> list[RawRow]:
    with path.open(encoding="utf-8") as f:
        out = []
        for d in csv.DictReader(f):
            out.append(RawRow(
                code=d["code"], name=d["name"], list_eur=float(d["list_eur"]),
                section=d["section"], dimension=d["dimension"],
                product_group=d["product_group"], unit=d["unit"],
            ))
        return out


# ----------------------------------------------------------------------------
# Pricing (mirrors berliner-catalog/import_pricelist.py)
# ----------------------------------------------------------------------------
@dataclass
class PricedRow:
    handle: str
    item_code: str
    name: str
    dimension: str
    product_group: str
    unit: str
    list_eur: float
    eur_fob: float
    cbm: float
    cbm_method: str
    landed_thb: float
    landed_thb_raw: float
    logistics_pct: float
    logistics_clamp: str
    retail_thb: float
    retail_usd: float
    retail_eur: float
    retail_sgd: float
    freight_thb: float
    duty_thb: float
    vat_thb: float


def calibrate_baltic_rate(fx: dict) -> dict:
    sources: list[dict] = []
    static = cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"]
    sources.append({"source": "cost_engine static EU LCL", "per_cbm_thb": static})
    try:
        from rate_feeds import get_fbx_index  # type: ignore
        feu = get_fbx_index().get("FBX_GLOBAL", {}).get("rate_usd_feu")
        if feu:
            usd_thb = fx.get("USD", 35.0)
            sources.append({"source": "FBX Global → LCL est",
                            "per_cbm_thb": round((feu * usd_thb / 50.0) * 1.8, 2)})
    except Exception as e:
        log.warning("FBX lookup failed (non-fatal): %s", e)
    avg = round(sum(s["per_cbm_thb"] for s in sources) / len(sources), 2)
    return {"per_cbm_thb": avg, "sources": sources, "method": "avg"}


def compute_cbm(dims: dict | None, packing_factor: float) -> float | None:
    if not dims:
        return None
    L, W, H = dims.get("length_cm"), dims.get("width_cm"), dims.get("height_cm")
    if not (L and W and H):
        return None
    return round((L * W * H) / 1_000_000.0 * packing_factor, 4)


def load_dim_index() -> dict[str, dict]:
    """Index dims from existing vendors/4soft docs by handle + item_code."""
    try:
        from google.cloud import firestore  # type: ignore
        db = firestore.Client(project=FS_PROJECT, database=VENDORS_DB)
        docs = list(db.collection("vendors").document(SLUG).collection("products").stream())
    except Exception as e:
        log.warning("Firestore dim read failed (flat_uplift everywhere): %s", e)
        return {}
    idx: dict[str, dict] = {}
    for d in docs:
        p = d.to_dict() or {}
        dims = p.get("dimensions") or {}
        if not (dims.get("length_cm") and dims.get("width_cm") and dims.get("height_cm")):
            continue
        entry = {
            "length_cm": float(dims["length_cm"]),
            "width_cm": float(dims["width_cm"]),
            "height_cm": float(dims["height_cm"]),
        }
        idx[d.id] = entry
        if p.get("item_code"):
            idx[p["item_code"]] = entry
    log.info("Firestore: indexed %d existing 4soft products with dimensions", len(idx))
    return idx


def price_row(row: RawRow, dim_index: dict, fx: dict, baltic: dict, packing_factor: float) -> PricedRow:
    p = _foursoft_params()
    handle = handle_for(row.code)
    eur_fob = round(row.list_eur * (1 - p["exw_discount"]), 2)

    dims = dim_index.get(handle) or dim_index.get(row.code)
    cbm = compute_cbm(dims, packing_factor) if dims else None

    if cbm and cbm > 0:
        # Per-SKU air-freight pricing. We override the engine's air method:
        #   1. per_kg → AIR_RATE_OVERRIDE_THB_PER_KG (when set; else engine default)
        #   2. min_charge → 0 (the 5000 THB shipment minimum doesn't apply to
        #      per-SKU economics; it's amortized across the whole shipment)
        # The engine derives chargeable kg from cbm via volumetric_divisor_kg_per_m3
        # when kg=0 is passed.
        air = cost_engine.ROUTE_PROFILES["europe"]["methods"]["air"]
        original_rate = air["rates"]["per_kg"]
        original_min = air["rates"].get("min_charge", 0)
        try:
            if AIR_RATE_OVERRIDE_THB_PER_KG is not None:
                air["rates"]["per_kg"] = AIR_RATE_OVERRIDE_THB_PER_KG
            air["rates"]["min_charge"] = 0
            est = estimate_landed_cost(
                origin=ORIGIN_ROUTE, method=METHOD,
                goods_value=eur_fob, goods_currency="EUR",
                cbm=cbm, kg=0, product_category=PRODUCT_CATEGORY,
                fx_rates=fx, duty_rate=p["duty_rate_non_china"],
            )
        finally:
            air["rates"]["per_kg"] = original_rate
            air["rates"]["min_charge"] = original_min
        landed_thb = est["total_landed_thb"]
        freight_thb = est["freight"]["thb"]
        duty_thb = est["customs"]["duty_thb"]
        vat_thb = est["customs"]["vat_thb"]
        cbm_method = "dims_scaled"
    else:
        eur_thb = fx.get("EUR", 38.0)
        fob_thb = eur_fob * eur_thb
        cif_thb = fob_thb * p["unmatched_landed_uplift"]
        freight_thb = cif_thb - fob_thb
        duty_thb = round(cif_thb * p["duty_rate_non_china"], 2)
        vat_thb = round((cif_thb + duty_thb) * p["thai_vat_rate"], 2)
        landed_thb = round(cif_thb + duty_thb + vat_thb, 2)
        cbm = 0.0
        cbm_method = "flat_uplift"

    fob_thb = eur_fob * fx.get("EUR", 38.0)
    landed_thb_raw = landed_thb
    lo_pct, hi_pct = logistics_band(eur_fob)
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

    gm = p["gross_margin"]
    th_cust_vat = p["th_customer_vat_rate"]
    usd_thb = fx.get("USD", 35.0)
    eur_thb = fx.get("EUR", 38.0)
    sgd_thb = fx.get("SGD", 25.0)
    retail_thb = round((landed_thb / (1 - gm)) * (1 + th_cust_vat), 2)
    retail_usd = round((landed_thb / usd_thb) / (1 - gm), 2)   # no TH VAT on USD
    retail_eur = round((landed_thb / eur_thb) / (1 - gm), 2)
    sg_gst_mult = (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    retail_sgd = round(((landed_thb / sgd_thb) / (1 - gm)) * sg_gst_mult, 2)

    return PricedRow(
        handle=handle, item_code=row.code, name=row.name,
        dimension=row.dimension, product_group=row.product_group, unit=row.unit,
        list_eur=row.list_eur, eur_fob=eur_fob,
        cbm=cbm or 0.0, cbm_method=cbm_method,
        landed_thb=landed_thb, landed_thb_raw=round(landed_thb_raw, 2),
        logistics_pct=logistics_pct, logistics_clamp=logistics_clamp,
        retail_thb=retail_thb, retail_usd=retail_usd, retail_eur=retail_eur,
        retail_sgd=retail_sgd, freight_thb=freight_thb, duty_thb=duty_thb, vat_thb=vat_thb,
    )


# ----------------------------------------------------------------------------
# Firestore writes
# ----------------------------------------------------------------------------
def ensure_brand_config() -> None:
    """Add brands.4soft to pricing_config/canonical via a safe read-modify-write
    merge (never a full reseed — that would regress live global keys)."""
    from google.cloud import firestore  # type: ignore
    db = firestore.Client(project=FS_PROJECT, database=FS_DATABASE)
    ref = db.collection(FS_COLLECTION).document(FS_DOCUMENT)
    snap = ref.get()
    doc = snap.to_dict() if snap.exists else {}
    brands = dict(doc.get("brands") or {})
    brands["4soft"] = {
        "gross_margin": GROSS_MARGIN,
        "exw_discount": EXW_DISCOUNT,
        "trade_terms": "EXW",
        "origin": "EU/Czech",
        "source_pricelist_url": "foursoft-catalog/data/pricelist_2025-03-01.csv",
        "source_pricelist_label": "4soft 2025 EPDM-graphics pricelist (.xls, valid 2025-03-01)",
    }
    ref.set({
        "brands": brands,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "foursoft-catalog/import_pricelist.py (brands.4soft seed)",
    }, merge=True)
    log.info("pricing_config/canonical: ensured brands.4soft (gm=%.2f exw=%.2f)",
             GROSS_MARGIN, EXW_DISCOUNT)


def write_firestore(rows: list[PricedRow], fx: dict, baltic: dict) -> None:
    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
        raise RuntimeError("Set GOOGLE_APPLICATION_CREDENTIALS to the ai-agents-go SA key.")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", FS_PROJECT)
    from google.cloud import firestore  # type: ignore

    p = _foursoft_params()
    db = firestore.Client(project=FS_PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    now = datetime.now(timezone.utc).isoformat()
    fx_snapshot = {k: fx.get(k) for k in ("USD", "EUR", "THB", "SGD")}
    tiers_meta = [{"fob_eur_max": (t[0] if t[0] != float("inf") else None),
                   "min_pct": t[1], "max_pct": t[2]} for t in LOGISTICS_TIERS]

    written = created = 0
    batch = db.batch()
    batch_count = 0
    for r in rows:
        ref = coll.document(r.handle)
        snap = ref.get()
        existing = (snap.to_dict() or {}) if snap.exists else {}

        pricing = {
            "list_eur": r.list_eur, "eur_fob": r.eur_fob,
            "exw_discount": p["exw_discount"], "trade_terms": "EXW",
            "gross_margin": p["gross_margin"], "pricelist_date": PRICELIST_DATE,
            "calculated_at": now, "fx_snapshot": fx_snapshot, "fx_source": fx.get("_source"),
            "landed_thb": r.landed_thb, "landed_thb_raw": r.landed_thb_raw,
            "logistics_pct": r.logistics_pct, "logistics_clamp": r.logistics_clamp,
            "retail_thb": r.retail_thb, "retail_usd": r.retail_usd,
            "retail_eur": r.retail_eur, "retail_sgd": r.retail_sgd,
            "cbm_used": r.cbm, "cbm_method": r.cbm_method,
            "freight_thb": r.freight_thb, "duty_thb": r.duty_thb, "vat_thb": r.vat_thb,
            "baltic_rate_snapshot": baltic, "logistics_tiers": tiers_meta,
        }
        doc_payload = {
            "handle": r.handle,
            "name": r.name or existing.get("name") or r.item_code,
            "item_code": r.item_code,
            "slug": SLUG,
            "category": "playground",
            "source_url": SOURCE_URL,
            "status": "active",
            "pricing": pricing,
            "metadata": {
                "dimension": r.dimension,
                "product_group": r.product_group,
                "unit": r.unit,
                "pricelist_date": PRICELIST_DATE,
            },
        }
        if existing.get("dimensions"):
            doc_payload["dimensions"] = existing["dimensions"]
        if existing.get("images"):
            doc_payload["images"] = existing["images"]

        if snap.exists:
            batch.set(ref, doc_payload, merge=True)
        else:
            batch.set(ref, doc_payload)
            created += 1
        batch_count += 1
        written += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count:
        batch.commit()

    db.collection("vendors").document(SLUG).set({
        "name": "4soft", "slug": SLUG, "source_url": SOURCE_URL,
        "product_count": written, "last_pricelist_load": now,
        "last_pricelist_date": PRICELIST_DATE,
    }, merge=True)
    log.info("Firestore vendors/%s: wrote %d docs (created %d new)", SLUG, written, created)


def main() -> int:
    global AIR_RATE_OVERRIDE_THB_PER_KG
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xls", type=Path, default=DEFAULT_XLS,
                    help="Source .xls. Falls back to the committed parsed CSV if absent.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse + write landed CSV only; do not touch Firestore.")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--packing-factor", type=float, default=0.15)
    ap.add_argument("--no-seed", action="store_true",
                    help="Skip ensuring brands.4soft in pricing_config/canonical.")
    ap.add_argument("--air-rate", type=float, default=None,
                    help="Override THB/kg chargeable for the air method (engine default if unset).")
    ap.add_argument("--landed-csv", type=Path, default=None,
                    help="Override the output landed CSV path (default: data/pricelist_*_landed.csv).")
    ap.add_argument("--load-dims", action="store_true",
                    help="Load dim_index from Firestore even in --dry-run (read-only; needed for air-freight dry-run validation).")
    args = ap.parse_args()

    if args.air_rate is not None:
        AIR_RATE_OVERRIDE_THB_PER_KG = args.air_rate
        log.info("Air rate override: %.2f THB/kg chargeable (was engine default)", args.air_rate)

    if args.xls.exists():
        log.info("Parsing .xls: %s", args.xls)
        raw = parse_xls(args.xls)
        write_parsed_csv(raw, PARSED_CSV)
        log.info("Wrote parsed CSV: %s (%d rows)", PARSED_CSV, len(raw))
    elif PARSED_CSV.exists():
        log.info(".xls not found; reading committed parsed CSV: %s", PARSED_CSV)
        raw = read_parsed_csv(PARSED_CSV)
    else:
        log.error("Neither --xls (%s) nor parsed CSV (%s) found.", args.xls, PARSED_CSV)
        return 2

    if args.limit:
        raw = raw[: args.limit]
    log.info("Loaded %d product rows", len(raw))

    fx = get_fx_rates(buffer_pct=2)
    log.info("FX: USD=%.4f EUR=%.4f SGD=%.4f source=%s",
             fx.get("USD", 0), fx.get("EUR", 0), fx.get("SGD", 0), fx.get("_source"))
    baltic = calibrate_baltic_rate(fx)
    log.info("Baltic LCL rate: %.2f THB/CBM", baltic["per_cbm_thb"])

    if args.dry_run and not args.load_dims:
        dim_index = {}
    else:
        dim_index = load_dim_index()
    priced = [price_row(r, dim_index, fx, baltic, args.packing_factor) for r in raw]

    by_dim: dict[str, int] = {}
    by_cbm: dict[str, int] = {}
    by_clamp: dict[str, int] = {}
    for r in priced:
        by_dim[r.dimension] = by_dim.get(r.dimension, 0) + 1
        by_cbm[r.cbm_method] = by_cbm.get(r.cbm_method, 0) + 1
        by_clamp[r.logistics_clamp or "none"] = by_clamp.get(r.logistics_clamp or "none", 0) + 1
    log.info("By dimension: %s", by_dim)
    log.info("By CBM method: %s", by_cbm)
    log.info("By logistics clamp: %s", by_clamp)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = args.landed_csv if args.landed_csv else LANDED_CSV
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(priced[0]).keys()))
        w.writeheader()
        for r in priced:
            w.writerow(asdict(r))
    log.info("Wrote landed CSV: %s (%d rows)", out_csv, len(priced))

    for r in priced[:6]:
        log.info("  %s | %-32s | list €%.0f → EXW €%.0f → landed ฿%.0f → retail ฿%.0f / $%.0f / €%.0f",
                 r.item_code, r.name[:32], r.list_eur, r.eur_fob,
                 r.landed_thb, r.retail_thb, r.retail_usd, r.retail_eur)

    if args.dry_run:
        log.info("DRY RUN complete — Firestore untouched.")
        return 0

    if not args.no_seed:
        ensure_brand_config()
    write_firestore(priced, fx, baltic)
    log.info("Done. Next: python scripts/sync_brand_prices_to_medusa.py --brand 4soft --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
