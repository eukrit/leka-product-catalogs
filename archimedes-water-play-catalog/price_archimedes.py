"""Archimedes Water Play landed-pricing pass (the deferred Task 2 work).

Mirrors the Wisdom China-FOB pipeline (`shared/wisdom_pricing.py`) but works
in CNY (the Wenzhou Daosen pricelist currency) instead of USD:

    fob_thb    = price_cny × cny_thb
    cif_thb    = fob_thb                       (China consolidated sea: CIF ≈ FOB)
                 OR via shipping-automation China LCL when CBM is available
    duty_thb   = cif_thb × import_duty_rate    (0% — ASEAN-China FTA Form E)
    vat_thb    = (cif_thb + duty_thb) × thai_vat_rate   (7% import VAT)
    landed_thb = cif_thb + duty_thb + vat_thb  (+ tier clamp on the CBM path)
    retail_thb = (landed_thb / (1 - gm)) × (1 + th_customer_vat_rate)
    retail_usd = (landed_thb / usd_thb) / (1 - gm)          (no TH customer VAT)
    retail_sgd = (landed_thb / sgd_thb) / (1 - gm) × sg_gst_mult

Gross margin defaults to 0.50 (same as the other China-origin brand, Wisdom);
editable via the pricing-config form (brands.archimedes-water-play.gross_margin).

Dimension normalization for CBM (documented, conservative):
  * Only `kind == "lwh"` rows get a CBM (a real 3-axis box). custom / diameter /
    two-dim / length / unknown rows fall back to the flat CIF ≈ FOB path.
  * Units are mixed in the source. Resolution per lwh row:
      - explicit "cm" marker in the cell  → cm
      - else any axis > 1000              → mm  (e.g. 2000*1100*1250)
      - else                              → cm  (e.g. 95×45×95)
  * CBM = L_m × W_m × H_m × default_packing_factor (0.15).
  * lwh rows route through the China LCL cost_engine + Vinci-style tier clamp
    (floor/cap on FOB band), which bounds any cm/mm mis-guess. Non-lwh rows use
    the flat China CIF ≈ FOB path (no freight uplift), exactly like Wisdom.

FX: live THB-per-unit rates from shipping-automation `fx_rates.get_fx_rates`
(+2% buffer) for CNY / USD / SGD. Falls back to module constants offline.

Writes:
  1. archimedes-water-play-catalog/data/pricelist_2026-05-29_priced.csv
  2. vendors/archimedes-water-play/products/<sku>  (vendors DB, merge-write)
  3. Updates the audit doc's landed_pricing_status to "completed".

Usage:
    python archimedes-water-play-catalog/price_archimedes.py --dry-run
    python archimedes-water-play-catalog/price_archimedes.py --apply
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

# Importing shared.landed_pricing nudges sys.path to shipping-automation/mcp-server
# so `cost_engine` and `fx_rates` resolve.
from shared.landed_pricing import (  # noqa: E402
    DEFAULT_PACKING_FACTOR,
    THAI_VAT_RATE,
    TH_CUSTOMER_VAT_RATE,
    DUTY_RATE_CHINA,
    SG_CUSTOMER_GST_RATE,
    SG_NUBO_GST_REGISTERED,
    LOGISTICS_TIERS,
    get_fx_rates,
    logistics_band,
)
from shared.pricing_config import get_pricing_config  # noqa: E402
import cost_engine  # noqa: E402 — resolved via shared.landed_pricing's sys.path nudge

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("price_archimedes")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "archimedes-water-play"
PRICELIST_DATE = "2026-05-29"
SHEET_NAME = "儿童戏水"
SOURCE_LABEL = "daosen_pricelist_2026-05-29.xls"
FORMULA_VERSION = "archimedes-v1-2026-05-29"
GROSS_MARGIN = 0.50                 # China-origin default (matches Wisdom)
DEFAULT_CNY_THB = 4.80              # offline FX fallback (THB per CNY)
DEFAULT_USD_THB = 35.0
DEFAULT_SGD_THB = 25.0

PARSED_CSV = REPO_ROOT / "archimedes-water-play-catalog" / "data" / f"pricelist_{PRICELIST_DATE}_parsed.csv"
PRICED_CSV = REPO_ROOT / "archimedes-water-play-catalog" / "data" / f"pricelist_{PRICELIST_DATE}_priced.csv"

VENDOR_NAME_ZH = "温州道森游乐戏水"


def _params() -> dict:
    """Merge Firestore overrides on top of module defaults (Wisdom pattern)."""
    cfg = get_pricing_config(SLUG)
    tiers_raw = cfg.get("logistics_tiers")
    if tiers_raw:
        tiers = [
            (float("inf") if t.get("fob_eur_max") in (None, "inf") else float(t["fob_eur_max"]),
             float(t["min_pct"]), float(t["max_pct"]))
            for t in tiers_raw
        ]
    else:
        tiers = LOGISTICS_TIERS
    return {
        "gross_margin": float(cfg.get("gross_margin", GROSS_MARGIN)),
        "import_duty_rate": float(cfg.get("import_duty_rate", DUTY_RATE_CHINA)),
        "thai_vat_rate": float(cfg.get("thai_vat_rate", THAI_VAT_RATE)),
        "th_customer_vat_rate": float(cfg.get("th_customer_vat_rate", TH_CUSTOMER_VAT_RATE)),
        "default_packing_factor": float(cfg.get("default_packing_factor", DEFAULT_PACKING_FACTOR)),
        "default_cny_thb": float(cfg.get("default_cny_thb", DEFAULT_CNY_THB)),
        "sg_customer_gst_rate": float(cfg.get("sg_customer_gst_rate", SG_CUSTOMER_GST_RATE)),
        "sg_nubo_gst_registered": bool(cfg.get("sg_nubo_gst_registered", SG_NUBO_GST_REGISTERED)),
        "logistics_tiers": tiers,
    }


def resolve_fx() -> tuple[dict, str]:
    """Return (fx dict THB-per-unit, source label). Falls back to constants."""
    try:
        fx = get_fx_rates()
        if fx and fx.get("CNY"):
            return fx, "shipping-automation fx_rates (live, +2% buffer)"
    except Exception as e:
        log.warning("Live FX lookup failed (non-fatal): %s — using fallback constants", e)
    return ({"CNY": DEFAULT_CNY_THB, "USD": DEFAULT_USD_THB, "SGD": DEFAULT_SGD_THB,
             "EUR": 38.0}, "module fallback constants (offline)")


def _cbm_for_row(row: dict, packing_factor: float) -> tuple[float, str]:
    """CBM (m³) and resolved unit for an lwh row; (0.0, reason) otherwise."""
    if row.get("dimensions_kind") != "lwh":
        return 0.0, f"non-lwh ({row.get('dimensions_kind')})"
    try:
        L = float(row.get("dimensions_length") or 0)
        W = float(row.get("dimensions_width") or 0)
        H = float(row.get("dimensions_height") or 0)
    except (TypeError, ValueError):
        return 0.0, "unparseable"
    if not (L > 0 and W > 0 and H > 0):
        return 0.0, "incomplete-lwh"
    unit_guess = (row.get("dimensions_unit_guess") or "").strip().lower()
    if unit_guess == "cm":
        unit = "cm"
    elif max(L, W, H) > 1000:
        unit = "mm"
    else:
        unit = "cm"
    div = 100.0 if unit == "cm" else 1000.0
    vol_m3 = (L / div) * (W / div) * (H / div)
    return round(vol_m3 * packing_factor, 4), unit


def compute_pricing(price_cny: float, fx: dict, p: dict, cbm: float = 0.0,
                    kg: float = 0.0, dim_unit: str = "") -> dict | None:
    """Landed + retail for one SKU. Mirrors wisdom_pricing.compute_wisdom_retail."""
    if not price_cny or price_cny <= 0:
        return None
    cny_thb = fx.get("CNY", DEFAULT_CNY_THB)
    usd_thb = fx.get("USD", DEFAULT_USD_THB)
    sgd_thb = fx.get("SGD", DEFAULT_SGD_THB)
    fob_thb = price_cny * cny_thb

    cbm_method = "china_flat"
    logistics_clamp = ""
    est = None
    if cbm and cbm > 0:
        try:
            est = cost_engine.estimate_landed_cost(
                origin="china", method="lcl",
                goods_value=price_cny, goods_currency="CNY",
                cbm=cbm, kg=kg,
                duty_rate=p["import_duty_rate"],   # 0.0 for China FTA
                fx_rates=fx,
            )
        except Exception as e:
            log.warning("China LCL CBM estimate failed (non-fatal): %s — flat-uplift", e)
            est = None

    if est is not None:
        landed_raw = est["total_landed_thb"]
        duty_thb = round(est["customs"]["duty_thb"], 2)
        vat_thb = round(est["customs"]["vat_thb"], 2)
        cbm_method = "china_lcl_cbm"
        # Vinci-style tier clamp in EUR-equivalent FOB band (bounds dim mis-guess).
        eur_thb = fx.get("EUR", 38.0)
        eur_fob_equiv = fob_thb / eur_thb
        lo_pct, hi_pct = logistics_band(eur_fob_equiv, p["logistics_tiers"])
        floor_landed = fob_thb * (1 + lo_pct)
        cap_landed = fob_thb * (1 + hi_pct)
        if landed_raw < floor_landed:
            landed_thb = floor_landed
            logistics_clamp = "floored"
        elif landed_raw > cap_landed:
            landed_thb = cap_landed
            logistics_clamp = "capped"
        else:
            landed_thb = landed_raw
        landed_thb = round(landed_thb, 2)
    else:
        # Flat path: China consolidated CIF ≈ FOB (no separate freight charge).
        duty_thb = round(fob_thb * p["import_duty_rate"], 2)
        vat_thb = round((fob_thb + duty_thb) * p["thai_vat_rate"], 2)
        landed_thb = round(fob_thb + duty_thb + vat_thb, 2)

    gm = p["gross_margin"]
    th_vat_mult = 1.0 + p["th_customer_vat_rate"]
    retail_thb = round((landed_thb / (1 - gm)) * th_vat_mult, 2)
    retail_usd = round((landed_thb / usd_thb) / (1 - gm), 2)
    sg_gst_mult = (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    retail_sgd = round(((landed_thb / sgd_thb) / (1 - gm)) * sg_gst_mult, 2)

    return {
        "fob_cny": round(price_cny, 2),
        "cny_thb": round(cny_thb, 4),
        "usd_thb": round(usd_thb, 4),
        "sgd_thb": round(sgd_thb, 4),
        "fob_thb": round(fob_thb, 2),
        "duty_thb": duty_thb,
        "vat_thb": vat_thb,
        "landed_thb": landed_thb,
        "retail_thb": retail_thb,
        "retail_usd": retail_usd,
        "retail_sgd": retail_sgd,
        "gross_margin": gm,
        "import_duty_rate": p["import_duty_rate"],
        "thai_vat_rate": p["thai_vat_rate"],
        "th_customer_vat_rate": p["th_customer_vat_rate"],
        "sg_nubo_gst_registered": p["sg_nubo_gst_registered"],
        "cbm_used": round(cbm or 0.0, 4),
        "cbm_method": cbm_method,
        "dim_unit_resolved": dim_unit,
        "logistics_clamp": logistics_clamp,
        "price_date": PRICELIST_DATE,
        "currency": "CNY",
        "formula_version": FORMULA_VERSION,
    }


def read_parsed_rows() -> list[dict]:
    if not PARSED_CSV.exists():
        raise FileNotFoundError(f"parsed CSV not found: {PARSED_CSV} — run import_pricelist.py first")
    with PARSED_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_product_doc(row: dict, pricing: dict, dim_unit: str) -> dict:
    sku = row["sku"]
    def _f(k):
        v = row.get(k)
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    return {
        "sku": sku,
        "item_code": sku,
        "handle": f"{SLUG}-{sku.lower()}",
        "slug": SLUG,
        "name": row.get("name_zh") or sku,
        "name_zh": row.get("name_zh") or "",
        "dimensions_raw": row.get("dimensions_raw") or "",
        "dimensions": {
            "length": _f("dimensions_length"),
            "width": _f("dimensions_width"),
            "height": _f("dimensions_height"),
            "unit": dim_unit or (row.get("dimensions_unit_guess") or ""),
            "kind": row.get("dimensions_kind") or "",
        },
        "notes": row.get("notes") or "",
        "vendor": VENDOR_NAME_ZH,
        "source_pricelist": f"{SOURCE_LABEL}:{SHEET_NAME}:row{row.get('row_index')}",
        "pricing": pricing,
        "status": "draft_no_images",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_priced_csv(docs: list[dict]) -> None:
    fields = ["sku", "name_zh", "dimensions_kind", "dim_unit", "cbm_method",
              "fob_cny", "fob_thb", "landed_thb", "retail_thb", "retail_usd",
              "retail_sgd", "logistics_clamp"]
    PRICED_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PRICED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in docs:
            p = d["pricing"]
            w.writerow({
                "sku": d["sku"], "name_zh": d["name_zh"],
                "dimensions_kind": d["dimensions"]["kind"],
                "dim_unit": p.get("dim_unit_resolved", ""),
                "cbm_method": p.get("cbm_method"),
                "fob_cny": p.get("fob_cny"), "fob_thb": p.get("fob_thb"),
                "landed_thb": p.get("landed_thb"), "retail_thb": p.get("retail_thb"),
                "retail_usd": p.get("retail_usd"), "retail_sgd": p.get("retail_sgd"),
                "logistics_clamp": p.get("logistics_clamp"),
            })
    log.info("wrote priced CSV: %s", PRICED_CSV)


def write_firestore(docs: list[dict], fx_source: str, fx: dict) -> None:
    from google.cloud import firestore  # type: ignore
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    batch = db.batch()
    pending = 0
    for d in docs:
        batch.set(coll.document(d["sku"]), d, merge=True)
        pending += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()
    log.info("wrote %d priced docs → vendors/%s/products", len(docs), SLUG)

    # Update the audit doc status so the deferred work is no longer "deferred".
    db.document(f"vendors/{SLUG}/pricelists/{PRICELIST_DATE}").set({
        "landed_pricing_status": "completed (v2.38.0)",
        "landed_pricing_formula_version": FORMULA_VERSION,
        "landed_pricing_calculated_at": datetime.now(timezone.utc).isoformat(),
        "fx_source": fx_source,
        "fx_snapshot": {k: float(fx[k]) for k in ("CNY", "USD", "SGD") if fx.get(k)},
    }, merge=True)
    log.info("updated audit doc landed_pricing_status → completed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    p = _params()
    fx, fx_source = resolve_fx()
    cny_thb, usd_thb, sgd_thb = fx.get("CNY"), fx.get("USD"), fx.get("SGD")
    log.info("FX (%s): CNY=%.4f USD=%.4f SGD=%.4f THB/unit", fx_source, cny_thb, usd_thb, sgd_thb)
    log.info("Derived: CNY→USD=%.4f  CNY→SGD=%.4f", cny_thb / usd_thb, cny_thb / sgd_thb)
    log.info("Params: gm=%.2f duty=%.2f thai_vat=%.2f th_cust_vat=%.2f packing=%.2f",
             p["gross_margin"], p["import_duty_rate"], p["thai_vat_rate"],
             p["th_customer_vat_rate"], p["default_packing_factor"])

    rows = read_parsed_rows()
    docs: list[dict] = []
    n_cbm = n_flat = 0
    for row in rows:
        try:
            price_cny = float(row.get("price_cny") or 0)
        except (TypeError, ValueError):
            price_cny = 0.0
        cbm, dim_unit = _cbm_for_row(row, p["default_packing_factor"])
        pricing = compute_pricing(price_cny, fx, p, cbm=cbm, dim_unit=dim_unit)
        if not pricing:
            log.warning("skipping %s — no valid price", row.get("sku"))
            continue
        if pricing["cbm_method"] == "china_lcl_cbm":
            n_cbm += 1
        else:
            n_flat += 1
        docs.append(build_product_doc(row, pricing, dim_unit))

    log.info("priced %d SKUs (CBM/China-LCL=%d, flat CIF≈FOB=%d)", len(docs), n_cbm, n_flat)
    write_priced_csv(docs)

    # Show a representative sample.
    for d in docs[:6]:
        pr = d["pricing"]
        log.info("  %s %-22.22s kind=%-8s %-13s fob=%.0f฿ landed=%.0f฿ retail_thb=%.0f฿ usd=%.2f$ clamp=%s",
                 d["sku"], d["name_zh"], d["dimensions"]["kind"], pr["cbm_method"],
                 pr["fob_thb"], pr["landed_thb"], pr["retail_thb"], pr["retail_usd"],
                 pr["logistics_clamp"] or "-")

    if args.dry_run:
        log.info("[DRY] would write %d docs to vendors/%s/products + update audit doc", len(docs), SLUG)
        return 0

    write_firestore(docs, fx_source, fx)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
