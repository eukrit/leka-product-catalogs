"""Berliner pricelist CSV → 15% EXW discount → landed cost → Firestore.

Mirrors vinci-catalog/import_pricelist.py:
  * Trade terms = EXW; our EXW cost = list price * 0.85.
  * Landed cost via shipping-automation/mcp-server cost_engine (LCL EU → THB,
    Baltic-rate calibration, tiered logistics floor/cap).
  * Retail = landed_thb / (1 - 0.40)  (40% gross margin).
  * THB/USD/EUR retail prices written to vendors/berliner/products/{handle}.pricing.

If existing vendor docs already carry dimensions (from a prior website scrape),
we use them to compute real CBM-driven landed cost. Otherwise every row falls
back to a flat 35 % EUR-THB uplift (which the tier clamp then re-bounds).

Usage:
    # Auth: set GOOGLE_APPLICATION_CREDENTIALS to the current ai-agents-go SA key.
    python berliner-catalog/import_pricelist.py --dry-run --limit 10
    python berliner-catalog/import_pricelist.py
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "berliner-catalog" / "data" / "pricelist_2026-01-01.csv"
OUTPUT_DIR = REPO_ROOT / "berliner-catalog" / "data"

# Mount shipping-automation as a library (same as vinci-catalog/import_pricelist.py).
SHIPPING_AUTO = Path(
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\shipping-automation\mcp-server"
)
sys.path.insert(0, str(SHIPPING_AUTO))

import cost_engine  # noqa: E402
from cost_engine import estimate_landed_cost  # noqa: E402
from fx_rates import get_fx_rates  # noqa: E402

# Repo root may not be on sys.path when this script runs standalone.
sys.path.insert(0, str(REPO_ROOT))
from shared.pricing_config import get_pricing_config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("berliner_pricelist")

# Module-level fallbacks. Source of truth lives in Firestore
# (pricing_config/canonical, brands.berliner + global). Keep these in
# sync with scripts/seed_pricing_config.py — they are only consulted
# when Firestore is unreachable.
EXW_DISCOUNT = 0.15           # our cost = list * (1 - 0.15)
GROSS_MARGIN = 0.25           # retail = landed / (1 - 0.25); Berliner-specific (Vinci 0.35)
DUTY_RATE_NON_CHINA = 0.10    # User 2026-05-14: 10% Thai duty for EU imports
THAI_VAT_RATE = 0.07          # User 2026-05-14: 7% Thai VAT on (CIF + duty)
PRODUCT_CATEGORY = "playground_equipment"
ORIGIN_ROUTE = "europe"
METHOD = "lcl"
UNMATCHED_LANDED_UPLIFT = 1.35  # 35% flat uplift on EUR-THB FOB when no CBM
PRICELIST_DATE = "2026-01-01"


def _berliner_params() -> dict:
    """Merge Firestore overrides on top of module-level defaults."""
    cfg = get_pricing_config("berliner")
    return {
        "exw_discount": float(cfg.get("exw_discount", EXW_DISCOUNT)),
        "gross_margin": float(cfg.get("gross_margin", GROSS_MARGIN)),
        "duty_rate_non_china": float(cfg.get("duty_rate_non_china", DUTY_RATE_NON_CHINA)),
        "thai_vat_rate": float(cfg.get("thai_vat_rate", THAI_VAT_RATE)),
        "th_customer_vat_rate": float(cfg.get("th_customer_vat_rate", 0.07)),
        "unmatched_landed_uplift": float(cfg.get("unmatched_landed_uplift", UNMATCHED_LANDED_UPLIFT)),
        "sg_customer_gst_rate": float(cfg.get("sg_customer_gst_rate", 0.09)),
        "sg_nubo_gst_registered": bool(cfg.get("sg_nubo_gst_registered", False)),
    }

# Tiered logistics-cost band (% of FOB-in-THB). Identical to Vinci.
LOGISTICS_TIERS: list[tuple[float, float, float]] = [
    (500,         0.60, 1.20),
    (2_000,       0.50, 1.00),
    (10_000,      0.40, 0.80),
    (float("inf"),0.30, 0.60),
]


def logistics_band(eur_fob: float) -> tuple[float, float]:
    for cap, lo, hi in LOGISTICS_TIERS:
        if eur_fob <= cap:
            return lo, hi
    return LOGISTICS_TIERS[-1][1], LOGISTICS_TIERS[-1][2]


@dataclass
class PricedRow:
    handle: str
    item_code: str
    name: str
    page: str
    status: str                  # active | on_request | name_only_active | name_only_on_request
    list_eur: float | None       # published list price
    eur_fob: float | None        # our EXW cost = list * (1 - EXW_DISCOUNT)
    cbm: float
    cbm_method: str              # "dims_scaled" | "flat_uplift" | "n/a"
    landed_thb: float | None
    landed_thb_raw: float | None
    logistics_pct: float | None
    logistics_clamp: str
    retail_thb: float | None
    retail_usd: float | None
    retail_eur: float | None
    retail_sgd: float | None
    freight_thb: float | None
    duty_thb: float | None
    vat_thb: float | None
    remarks: str = ""


def read_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_dim_index_from_firestore() -> dict[str, dict]:
    """Read vendors/berliner/products and index dimensions by handle + item_code.

    Returns {} if the collection is empty, ADC is unavailable, or any error
    occurs — the importer then falls back to flat_uplift on every row.
    """
    try:
        from google.cloud import firestore  # type: ignore
        db = firestore.Client(project="ai-agents-go", database="vendors")
        docs = list(db.collection("vendors").document("berliner").collection("products").stream())
    except Exception as e:
        log.warning("Firestore read failed (will use flat_uplift everywhere): %s", e)
        return {}

    index: dict[str, dict] = {}
    for d in docs:
        p = d.to_dict() or {}
        dims = p.get("dimensions") or {}
        if not (dims.get("length_cm") and dims.get("width_cm") and dims.get("height_cm")):
            continue
        entry = {
            "length_cm": float(dims["length_cm"]),
            "width_cm": float(dims["width_cm"]),
            "height_cm": float(dims["height_cm"]),
            "images": p.get("images") or [],
        }
        index[d.id] = entry
        ic = p.get("item_code")
        if ic:
            index[ic] = entry
    log.info("Firestore: indexed %d existing Berliner products with dimensions", len(index))
    return index


def calibrate_baltic_rate(fx: dict) -> dict:
    """Match Vinci's Baltic LCL THB/CBM calibration."""
    sources: list[dict] = []
    static_per_cbm = cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"]
    sources.append({"source": "cost_engine static EU LCL", "per_cbm_thb": static_per_cbm})

    try:
        from rate_feeds import get_fbx_index  # type: ignore
        fbx = get_fbx_index()
        feu = fbx.get("FBX_GLOBAL", {}).get("rate_usd_feu")
        if feu:
            usd_thb = fx.get("USD", 35.0)
            per_cbm_thb = (feu * usd_thb / 50.0) * 1.8
            sources.append({"source": "FBX Global → LCL est", "per_cbm_thb": round(per_cbm_thb, 2)})
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
    raw_m3 = (L * W * H) / 1_000_000.0
    return round(raw_m3 * packing_factor, 4)


def price_row(
    row: dict,
    dim_index: dict,
    fx: dict,
    baltic: dict,
    packing_factor: float,
) -> PricedRow:
    handle = row["handle"]
    item_code = row.get("item_code") or ""
    name = row.get("name") or ""
    status = row.get("status") or "active"
    page = row.get("page") or ""
    remarks = row.get("remarks") or ""

    list_raw = (row.get("list_eur") or "").strip()
    list_eur = float(list_raw) if list_raw else None

    # On-request / no-price → write product with status only, no pricing computed.
    if list_eur is None:
        return PricedRow(
            handle=handle, item_code=item_code, name=name, page=page, status=status,
            list_eur=None, eur_fob=None,
            cbm=0.0, cbm_method="n/a",
            landed_thb=None, landed_thb_raw=None,
            logistics_pct=None, logistics_clamp="",
            retail_thb=None, retail_usd=None, retail_eur=None, retail_sgd=None,
            freight_thb=None, duty_thb=None, vat_thb=None,
            remarks=remarks,
        )

    p = _berliner_params()
    eur_fob = round(list_eur * (1 - p["exw_discount"]), 2)

    # Look up dims by handle, then by item_code.
    dims = dim_index.get(handle) or (dim_index.get(item_code) if item_code else None)
    cbm = compute_cbm(dims, packing_factor) if dims else None

    if cbm and cbm > 0:
        original = cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"]
        try:
            cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"] = baltic["per_cbm_thb"]
            est = estimate_landed_cost(
                origin=ORIGIN_ROUTE, method=METHOD,
                goods_value=eur_fob, goods_currency="EUR",
                cbm=cbm, kg=0,
                product_category=PRODUCT_CATEGORY,
                fx_rates=fx,
                # User 2026-05-14: 10% duty for non-China origins.
                duty_rate=p["duty_rate_non_china"],
            )
        finally:
            cost_engine.ROUTE_PROFILES["europe"]["methods"]["lcl"]["rates"]["per_cbm"] = original
        landed_thb = est["total_landed_thb"]
        freight_thb = est["freight"]["thb"]
        duty_thb = est["customs"]["duty_thb"]
        vat_thb = est["customs"]["vat_thb"]
        cbm_method = "dims_scaled"
    else:
        # User 2026-05-14: flat 35% logistics + 10% duty + 7% VAT.
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

    # Retail: independent per-currency (Task 10). TH customer VAT only on THB.
    gm = p["gross_margin"]
    th_cust_vat = p.get("th_customer_vat_rate", 0.07)
    retail_thb = round((landed_thb / (1 - gm)) * (1 + th_cust_vat), 2)
    usd_thb = fx.get("USD", 35.0)
    eur_thb = fx.get("EUR", 38.0)
    sgd_thb = fx.get("SGD", 25.0)
    retail_usd = round((landed_thb / usd_thb) / (1 - gm), 2)   # no TH customer VAT
    retail_eur = round((landed_thb / eur_thb) / (1 - gm), 2)
    sg_gst_mult = (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    retail_sgd = round(((landed_thb / sgd_thb) / (1 - gm)) * sg_gst_mult, 2)

    return PricedRow(
        handle=handle, item_code=item_code, name=name, page=page, status=status,
        list_eur=list_eur, eur_fob=eur_fob,
        cbm=cbm or 0.0, cbm_method=cbm_method,
        landed_thb=landed_thb, landed_thb_raw=round(landed_thb_raw, 2),
        logistics_pct=logistics_pct, logistics_clamp=logistics_clamp,
        retail_thb=retail_thb, retail_usd=retail_usd, retail_eur=retail_eur,
        retail_sgd=retail_sgd,
        freight_thb=freight_thb, duty_thb=duty_thb, vat_thb=vat_thb,
        remarks=remarks,
    )


def write_csv(rows: list[PricedRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def write_firestore(rows: list[PricedRow], fx: dict, baltic: dict) -> None:
    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
        raise RuntimeError(
            "Set GOOGLE_APPLICATION_CREDENTIALS to the current ai-agents-go SA key "
            "before running without --dry-run."
        )
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")
    from google.cloud import firestore  # type: ignore

    p = _berliner_params()
    db = firestore.Client(project="ai-agents-go", database="vendors")
    coll = db.collection("vendors").document("berliner").collection("products")
    now = datetime.now(timezone.utc).isoformat()

    fx_snapshot = {k: fx.get(k) for k in ("USD", "EUR", "THB")}
    fx_source = fx.get("_source")
    tiers_meta = [
        {"fob_eur_max": (t[0] if t[0] != float("inf") else None),
         "min_pct": t[1], "max_pct": t[2]} for t in LOGISTICS_TIERS
    ]

    written = created = 0
    batch = db.batch()
    batch_count = 0
    for r in rows:
        ref = coll.document(r.handle)
        snap = ref.get()
        existing = snap.to_dict() or {} if snap.exists else {}

        pricing: dict = {
            "list_eur": r.list_eur,
            "eur_fob": r.eur_fob,
            "exw_discount": p["exw_discount"],
            "trade_terms": "EXW",
            "gross_margin": p["gross_margin"],
            "pricelist_date": PRICELIST_DATE,
            "calculated_at": now,
            "fx_snapshot": fx_snapshot,
            "fx_source": fx_source,
        }
        if r.list_eur is not None:
            pricing.update({
                "landed_thb": r.landed_thb,
                "landed_thb_raw": r.landed_thb_raw,
                "logistics_pct": r.logistics_pct,
                "logistics_clamp": r.logistics_clamp,
                "retail_thb": r.retail_thb,
                "retail_usd": r.retail_usd,
                "retail_eur": r.retail_eur,
                "retail_sgd": r.retail_sgd,
                "cbm_used": r.cbm,
                "cbm_method": r.cbm_method,
                "freight_thb": r.freight_thb,
                "duty_thb": r.duty_thb,
                "vat_thb": r.vat_thb,
                "baltic_rate_snapshot": baltic,
                "logistics_tiers": tiers_meta,
            })

        is_on_request = r.list_eur is None
        # active|on_request maps to Medusa published/draft via sync_vendors_to_medusa.
        doc_status = "active" if (not is_on_request) else "draft"

        doc_payload: dict = {
            "handle": r.handle,
            "name": r.name or r.item_code or r.handle,
            "item_code": r.item_code,
            "slug": "berliner",
            "category": "playground",
            "source_url": "https://www.berliner-seilfabrik.com/",
            "status": doc_status,
            "pricing": pricing,
            "metadata": {
                "page": r.page,
                "remarks": r.remarks,
                "row_status": r.status,
                "pricelist_date": PRICELIST_DATE,
            },
        }
        # Preserve existing dimensions/images on update.
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

    # Refresh vendor root doc count.
    db.collection("vendors").document("berliner").set(
        {
            "name": "Berliner Seilfabrik",
            "slug": "berliner",
            "source_url": "https://www.berliner-seilfabrik.com/",
            "product_count": written,
            "last_pricelist_load": now,
            "last_pricelist_date": PRICELIST_DATE,
        },
        merge=True,
    )
    log.info("Firestore: wrote %d docs (created %d new)", written, created)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                    help="Parsed pricelist CSV (produced by parse_pricelist.py).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Write landed-cost CSV only; do not touch Firestore.")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--packing-factor", type=float, default=0.15)
    args = ap.parse_args()

    if not args.csv.exists():
        log.error("CSV not found: %s — run parse_pricelist.py first.", args.csv)
        return 2

    rows_raw = read_rows(args.csv)
    if args.limit:
        rows_raw = rows_raw[: args.limit]
    log.info("Loaded %d rows from %s", len(rows_raw), args.csv.name)

    fx = get_fx_rates(buffer_pct=2)
    log.info("FX: USD=%.4f EUR=%.4f source=%s",
             fx.get("USD", 0), fx.get("EUR", 0), fx.get("_source"))

    baltic = calibrate_baltic_rate(fx)
    log.info("Baltic LCL rate: %.2f THB/CBM (sources=%d)",
             baltic["per_cbm_thb"], len(baltic["sources"]))

    if args.dry_run:
        dim_index: dict[str, dict] = {}
        log.info("DRY RUN — skipping Firestore dim-index lookup.")
    else:
        dim_index = load_dim_index_from_firestore()

    priced = [
        price_row(r, dim_index, fx, baltic, args.packing_factor)
        for r in rows_raw
    ]

    # Breakdown
    by_status: dict[str, int] = {}
    by_cbm: dict[str, int] = {}
    for r in priced:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_cbm[r.cbm_method] = by_cbm.get(r.cbm_method, 0) + 1
    log.info("Status counts: %s", by_status)
    log.info("CBM method counts: %s", by_cbm)

    out_csv = OUTPUT_DIR / f"pricelist_{PRICELIST_DATE}_landed.csv"
    write_csv(priced, out_csv)
    log.info("Wrote landed-cost CSV: %s (%d rows)", out_csv, len(priced))

    # Sample dump
    for r in priced[:5]:
        if r.list_eur is None:
            log.info("  %s | %s | on_request", r.handle, r.name[:40])
        else:
            log.info("  %s | %s | list EUR %.0f → EXW EUR %.0f → landed THB %.0f → retail THB %.0f / $%.0f / €%.0f",
                     r.handle, r.name[:30], r.list_eur, r.eur_fob,
                     r.landed_thb or 0, r.retail_thb or 0, r.retail_usd or 0, r.retail_eur or 0)

    if args.dry_run:
        log.info("DRY RUN complete — Firestore not touched.")
        return 0

    write_firestore(priced, fx, baltic)
    log.info("Done. Next: python scripts/sync_vendors_to_medusa.py --brand=berliner --dry-run --limit 5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
