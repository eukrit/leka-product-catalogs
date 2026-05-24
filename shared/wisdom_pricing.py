"""
Canonical landed-cost + retail pricing for China-origin (FOB USD) brands.

Covers: Wisdom, and any future brand imported on China FOB terms.

Formula per SKU (revised 2026-05-22 v2.29.0):
  cif_thb    = fob_usd × usd_thb        (China consolidated sea: CIF ≈ FOB)
  duty_thb   = cif_thb × IMPORT_DUTY_RATE
  vat_thb    = (cif_thb + duty_thb) × THAI_VAT_RATE
  landed_thb = cif_thb + duty_thb + vat_thb
  retail_thb = (landed_thb / (1 - GROSS_MARGIN)) × (1 + TH_CUSTOMER_VAT_RATE)

Constants:
  IMPORT_DUTY_RATE    = 0.00   # ASEAN-China FTA Form E — 0% duty (fixed v2.29.0;
                                # was incorrectly 0.07 — China is covered by FTA)
  THAI_VAT_RATE       = 0.07   # Thai import VAT, applied on (CIF + duty) at customs
  TH_CUSTOMER_VAT_RATE = 0.07  # 7% customer VAT embedded in retail price (v2.29.0)
  GROSS_MARGIN        = 0.50

Exchange rate: live via shipping-automation/fx_rates.py if available,
otherwise from USD_THB_RATE env var, otherwise DEFAULT_USD_THB fallback.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from shared.pricing_config import get_pricing_config

log = logging.getLogger(__name__)

# Module-level fallbacks. Source of truth lives in Firestore
# (pricing_config/canonical, brands.wisdom + global). These constants are
# only consulted when Firestore is unreachable — keep them in sync with
# scripts/seed_pricing_config.py.
IMPORT_DUTY_RATE: float = 0.00         # ASEAN-China FTA 0% (fixed v2.29.0; was 0.07)
THAI_VAT_RATE: float = 0.07            # Import VAT at customs on (CIF + duty)
TH_CUSTOMER_VAT_RATE: float = 0.07    # Customer VAT embedded in retail price (v2.29.0)
GROSS_MARGIN: float = 0.50
DEFAULT_USD_THB: float = 35.0
DEFAULT_SGD_THB: float = 25.0
# SG GST stacks on SG retail only when Nubo is GST-registered (currently off).
SG_CUSTOMER_GST_RATE: float = 0.09
SG_NUBO_GST_REGISTERED: bool = False


def _params() -> dict:
    cfg = get_pricing_config("wisdom")
    return {
        "import_duty_rate": float(cfg.get("import_duty_rate", IMPORT_DUTY_RATE)),
        "thai_vat_rate": float(cfg.get("thai_vat_rate", THAI_VAT_RATE)),
        "th_customer_vat_rate": float(cfg.get("th_customer_vat_rate", TH_CUSTOMER_VAT_RATE)),
        "gross_margin": float(cfg.get("gross_margin", GROSS_MARGIN)),
        "default_usd_thb": float(cfg.get("default_usd_thb", DEFAULT_USD_THB)),
        "sg_customer_gst_rate": float(cfg.get("sg_customer_gst_rate", SG_CUSTOMER_GST_RATE)),
        "sg_nubo_gst_registered": bool(cfg.get("sg_nubo_gst_registered", SG_NUBO_GST_REGISTERED)),
    }


def get_usd_thb() -> float:
    """Return USD→THB rate: env override → shipping-automation live → default."""
    env = os.environ.get("USD_THB_RATE")
    if env:
        try:
            return float(env)
        except ValueError:
            pass

    try:
        import sys
        from pathlib import Path

        candidates = [
            Path.home() / "OneDrive" / "Documents" / "Claude Code"
            / "shipping-automation" / "mcp-server",
            Path(r"C:\Users\Eukrit\OneDrive\Documents\Claude Code"
                 r"\shipping-automation\mcp-server"),
            Path(r"C:\Users\eukri\OneDrive\Documents\Claude Code"
                 r"\shipping-automation\mcp-server"),
        ]
        mcp = next((c for c in candidates if c.exists()), None)
        if mcp and str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from fx_rates import get_fx_rates
        rates = get_fx_rates()
        usd = rates.get("USD")
        if usd and usd > 0:
            return float(usd)
    except Exception as e:
        fallback = _params()["default_usd_thb"]
        log.warning("FX lookup failed (non-fatal): %s — using %.2f", e, fallback)

    return _params()["default_usd_thb"]


def get_sgd_thb() -> float:
    """Return SGD→THB rate: env override → shipping-automation live → default."""
    env = os.environ.get("SGD_THB_RATE")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    try:
        import sys
        from pathlib import Path

        candidates = [
            Path.home() / "OneDrive" / "Documents" / "Claude Code"
            / "shipping-automation" / "mcp-server",
            Path(r"C:\Users\Eukrit\OneDrive\Documents\Claude Code"
                 r"\shipping-automation\mcp-server"),
            Path(r"C:\Users\eukri\OneDrive\Documents\Claude Code"
                 r"\shipping-automation\mcp-server"),
        ]
        mcp = next((c for c in candidates if c.exists()), None)
        if mcp and str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from fx_rates import get_fx_rates
        sgd = get_fx_rates().get("SGD")
        if sgd and sgd > 0:
            return float(sgd)
    except Exception as e:
        log.warning("SGD FX lookup failed (non-fatal): %s — using %.2f", e, DEFAULT_SGD_THB)
    return DEFAULT_SGD_THB


@dataclass
class WisdomPricedRow:
    item_code: str
    fob_usd: float
    usd_thb: float
    fob_thb: float
    duty_thb: float
    vat_thb: float = 0.0
    landed_thb: float = 0.0
    retail_thb: float = 0.0
    retail_usd: float = 0.0
    retail_sgd: float = 0.0
    sgd_thb: float = 0.0
    cbm_used: float = 0.0
    cbm_method: str = "china_flat"    # "china_lcl_cbm" | "china_flat" | "tier_fallback"
    logistics_clamp: str = ""


def _wisdom_lcl_estimate(fob_usd: float, cbm: float, kg: float, fx: dict, p: dict) -> dict | None:
    """Best-effort China LCL landed estimate via shipping-automation cost_engine.

    Uses china_thai_sea (consolidated, includes duty+VAT). Falls back to None on
    any error so the caller reverts to flat-uplift.

    China consolidated rate: ~4,600 THB/CBM (China-Thai Khun Gift rate card 2025).
    All-inclusive: freight + clearance + duty + VAT + last-mile.
    """
    try:
        import sys
        from pathlib import Path
        candidates = [
            Path.home() / "OneDrive" / "Documents" / "Claude Code"
            / "shipping-automation" / "mcp-server",
            Path(r"C:\Users\Eukrit\OneDrive\Documents\Claude Code"
                 r"\shipping-automation\mcp-server"),
            Path(r"C:\Users\eukri\OneDrive\Documents\Claude Code"
                 r"\shipping-automation\mcp-server"),
        ]
        mcp = next((c for c in candidates if c.exists()), None)
        if mcp and str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        import cost_engine as _ce  # noqa: F401
        # Use LCL (not china_thai_sea) so duty_rate override works.
        # china_thai_sea is all-inclusive and ignores duty_rate parameter.
        est = _ce.estimate_landed_cost(
            origin="china",
            method="lcl",
            goods_value=fob_usd,
            goods_currency="USD",
            cbm=cbm,
            kg=kg,
            duty_rate=p["import_duty_rate"],   # 0.0 for China FTA
            fx_rates=fx,
        )
        return est
    except Exception as e:
        log.warning("China LCL CBM estimate failed (non-fatal): %s — using flat-uplift", e)
        return None


def compute_wisdom_retail(fob_usd: float, usd_thb: float | None = None,
                          sgd_thb: float | None = None,
                          cbm: float = 0.0, kg: float = 0.0,
                          fx: dict | None = None) -> WisdomPricedRow | None:
    """Compute landed cost and retail price for a single Wisdom SKU.

    Args:
        fob_usd:  FOB Shanghai price in USD (from catalog).
        usd_thb:  USD→THB rate to use; fetched live if None.
        sgd_thb:  SGD→THB rate to use; fetched live if None.
        cbm:      Packed CBM (optional). When > 0, routes through
                  shipping-automation China LCL engine. Falls back to
                  the Vinci-style tier system when CBM estimate fails.
        kg:       Weight in kg (optional, used alongside CBM).
        fx:       Full FX dict (optional, used for shipping-automation call).

    Returns:
        WisdomPricedRow, or None if fob_usd is falsy.
    """
    if not fob_usd or fob_usd <= 0:
        return None

    p = _params()
    rate = usd_thb if usd_thb and usd_thb > 0 else get_usd_thb()
    sgd_rate = sgd_thb if sgd_thb and sgd_thb > 0 else get_sgd_thb()
    fob_thb = fob_usd * rate

    # Build an FX dict for the cost_engine call if not provided
    if fx is None:
        fx = {"USD": rate, "SGD": sgd_rate}

    cbm_method = "china_flat"
    logistics_clamp = ""
    est = None
    if cbm and cbm > 0:
        est = _wisdom_lcl_estimate(fob_usd, cbm, kg, fx, p)

    if est is not None:
        # CBM-based China LCL via shipping-automation
        landed_thb_raw = est["total_landed_thb"]
        duty_thb = round(est["customs"]["duty_thb"], 2)
        vat_thb = round(est["customs"]["vat_thb"], 2)
        cbm_method = "china_lcl_cbm"

        # Apply Vinci-style tier clamp using EUR-equivalent FOB band
        eur_thb = fx.get("EUR", 38.0)
        eur_fob_equiv = fob_usd * rate / eur_thb
        try:
            from shared.landed_pricing import logistics_band, LOGISTICS_TIERS
            lo_pct, hi_pct = logistics_band(eur_fob_equiv)
        except Exception:
            lo_pct, hi_pct = 0.35, 0.80  # Tier 3 fallback
        floor_landed = fob_thb * (1 + lo_pct)
        cap_landed = fob_thb * (1 + hi_pct)
        if landed_thb_raw < floor_landed:
            landed_thb = floor_landed
            logistics_clamp = "floored"
        elif landed_thb_raw > cap_landed:
            landed_thb = cap_landed
            logistics_clamp = "capped"
        else:
            landed_thb = landed_thb_raw
        landed_thb = round(landed_thb, 2)
    else:
        # Flat path: China consolidated CIF ≈ FOB (no separate freight charge)
        # import_duty_rate = 0.0 (ASEAN-China FTA Form E); retained for correctness
        duty_thb = round(fob_thb * p["import_duty_rate"], 2)
        vat_thb = round((fob_thb + duty_thb) * p["thai_vat_rate"], 2)
        landed_thb = round(fob_thb + duty_thb + vat_thb, 2)
        cbm_method = "china_flat"

    # Retail: independent per-currency derivation (Task 10).
    # TH customer VAT (7%) embedded in retail_thb only — it is a Thai domestic tax.
    # USD and SGD retail are international prices without TH customer VAT.
    gm = p["gross_margin"]
    th_customer_vat_mult = 1.0 + p["th_customer_vat_rate"]
    retail_thb = round((landed_thb / (1 - gm)) * th_customer_vat_mult, 2)
    # USD and SGD derived from their own landed costs (landed_thb / FX at same snapshot)
    retail_usd = round((landed_thb / rate) / (1 - gm), 2)
    sg_gst_mult = (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    retail_sgd = round(((landed_thb / sgd_rate) / (1 - gm)) * sg_gst_mult, 2)

    return WisdomPricedRow(
        item_code="",          # caller fills this in
        fob_usd=fob_usd,
        usd_thb=rate,
        fob_thb=round(fob_thb, 2),
        duty_thb=duty_thb,
        vat_thb=vat_thb,
        landed_thb=landed_thb,
        retail_thb=retail_thb,
        retail_usd=retail_usd,
        retail_sgd=retail_sgd,
        sgd_thb=sgd_rate,
        cbm_used=cbm or 0.0,
        cbm_method=cbm_method,
        logistics_clamp=logistics_clamp,
    )


def compute_wisdom_retail_batch(
    products: list[dict],
    usd_thb: float | None = None,
    fx: dict | None = None,
) -> list[WisdomPricedRow]:
    """Price a list of product dicts (each must have 'item_code' and 'fob_usd').

    When a product has dimension data (dimensions.length_cm/width_cm/height_cm),
    uses shipping-automation China LCL for a CBM-based estimate. Falls back to
    flat China CIF ≈ FOB path when no dims.

    Args:
        products:  List of dicts with keys 'item_code' and 'fob_usd'.
                   Optional: 'dimensions' dict with length/width/height_cm and
                   'weight_kg' for CBM-based pricing.
        usd_thb:   Exchange rate; fetched once if None.
        fx:        Full FX dict (optional, passed to cost_engine).

    Returns:
        List of WisdomPricedRow for every product that has a valid fob_usd.
    """
    rate = usd_thb if usd_thb and usd_thb > 0 else get_usd_thb()
    sgd_rate = get_sgd_thb()
    if fx is None:
        fx = {"USD": rate, "SGD": sgd_rate}
    results = []
    for prod in products:
        fob = prod.get("fob_usd") or (prod.get("pricing") or {}).get("fob_usd")
        code = prod.get("item_code", "")
        # Extract CBM from stored dimensions if available
        cbm = 0.0
        kg = float(prod.get("weight_kg") or 0.0)
        dims = prod.get("dimensions") or {}
        try:
            l_cm = float(dims.get("length_cm") or 0)
            w_cm = float(dims.get("width_cm") or 0)
            h_cm = float(dims.get("height_cm") or 0)
            if l_cm > 0 and w_cm > 0 and h_cm > 0:
                pf = 0.15  # default packing factor
                cbm = round(l_cm * w_cm * h_cm / 1_000_000.0 * pf, 4)
        except (TypeError, ValueError):
            pass
        row = compute_wisdom_retail(fob, rate, sgd_rate, cbm=cbm, kg=kg, fx=fx)
        if row:
            row.item_code = code
            results.append(row)
    return results


def pricing_metadata(row: WisdomPricedRow, price_date: str) -> dict:
    """Return the Firestore pricing sub-map for a priced row."""
    p = _params()
    return {
        "fob_usd": row.fob_usd,
        "usd_thb": row.usd_thb,
        "sgd_thb": row.sgd_thb,
        "duty_thb": row.duty_thb,
        "vat_thb": row.vat_thb,
        "landed_thb": row.landed_thb,
        "retail_thb": row.retail_thb,
        "retail_usd": row.retail_usd,
        "retail_sgd": row.retail_sgd,
        "import_duty_rate": p["import_duty_rate"],
        "thai_vat_rate": p["thai_vat_rate"],
        "th_customer_vat_rate": p["th_customer_vat_rate"],
        "gross_margin": p["gross_margin"],
        "sg_nubo_gst_registered": p["sg_nubo_gst_registered"],
        "cbm_used": row.cbm_used,
        "cbm_method": row.cbm_method,
        "logistics_clamp": row.logistics_clamp,
        "price_date": price_date,
        "currency": "USD",
    }
