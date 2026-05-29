"""
Canonical landed-cost + retail pricing for China-origin (FOB USD) brands.

Covers: Wisdom, and any future brand imported on China FOB terms.

═══ Thailand channel (default) ═══════════════════════════════════════════
Function: compute_wisdom_retail()
Formula per SKU (revised 2026-05-22 v2.29.0):
  cif_thb    = fob_usd × usd_thb        (China consolidated sea: CIF ≈ FOB)
  duty_thb   = cif_thb × IMPORT_DUTY_RATE
  vat_thb    = (cif_thb + duty_thb) × THAI_VAT_RATE
  landed_thb = cif_thb + duty_thb + vat_thb
  retail_thb = (landed_thb / (1 - GROSS_MARGIN)) × (1 + TH_CUSTOMER_VAT_RATE)

TH constants:
  IMPORT_DUTY_RATE    = 0.00   # ASEAN-China FTA Form E — 0% duty (fixed v2.29.0;
                                # was incorrectly 0.07 — China is covered by FTA)
  THAI_VAT_RATE       = 0.07   # Thai import VAT, applied on (CIF + duty) at customs
  TH_CUSTOMER_VAT_RATE = 0.07  # 7% customer VAT embedded in retail price (v2.29.0)
  GROSS_MARGIN        = 0.50

═══ Singapore channel (Nubo SG, added 2026-05-30) ════════════════════════
Function: compute_wisdom_retail_sg()
For SKUs that actually ship China→Singapore via Nubo SG, the Thai-landed
cost above is the wrong basis: freight, duty, and consumption tax all
differ. The SG path computes a real Xiamen→Singapore landed cost via
shipping-automation/cost_engine ROUTE_PROFILES["china_to_singapore"], then
applies a configurable SG gross margin and an optional SG GST stack.

SG rules — confirm at implementation (sources cited in BUILD_LOG):
  - Duty: 0% on HS 9503 (educational toys) and HS 9506 (playground
    equipment). Singapore is a near-free port; only liquor, tobacco,
    motor vehicles, and petroleum are dutiable. Form E irrelevant.
    Source: Singapore Customs.
  - GST: 9% since 2024-01-01 (was 8% in 2023). Applied on CIF + duty at
    customs — identical mechanics to Thai import VAT. Source: IRAS.

SG constants (fallbacks; Firestore overrides via pricing_config):
  SG_IMPORT_DUTY_RATE = 0.00   # SG duty on toys/playground equipment
  SG_GST_RATE         = 0.09   # SG customs GST since 2024-01-01
  SG_GROSS_MARGIN     = 0.50   # separate from TH gross_margin
  SG_FREIGHT_METHOD   = "lcl"  # one of "lcl" | "fcl_20" | "fcl_40"
  DEFAULT_USD_SGD     = 1.33   # FOB-USD to SGD when FX lookup fails

Out of scope this round: Medusa SG sales-channel push (Firestore-only).

═══ Exchange rates ═══════════════════════════════════════════════════════
Live via shipping-automation/fx_rates.py if available, otherwise from
the matching `*_RATE` env var, otherwise the module-level DEFAULT_*
fallbacks below.
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

# ── Singapore landed-cost path (Nubo SG channel, added 2026-05-30) ──────
# Used by compute_wisdom_retail_sg(). These are the *import-side* SG
# constants — distinct from sg_customer_gst_rate above (which is the
# *retail-side* GST stack toggled by sg_nubo_gst_registered).
SG_IMPORT_DUTY_RATE: float = 0.00   # SG 0% on HS 9503/9506
SG_GST_RATE: float = 0.09           # SG customs GST since 2024-01-01
SG_GROSS_MARGIN: float = 0.50       # exposed as separate key so it can diverge
SG_FREIGHT_METHOD: str = "lcl"      # "lcl" | "fcl_20" | "fcl_40"
DEFAULT_USD_SGD: float = 1.33       # fallback when FX lookup fails


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


def _sg_params() -> dict:
    """Singapore-channel parameters (Nubo SG). Mirrors _params() shape."""
    cfg = get_pricing_config("wisdom")
    return {
        "sg_import_duty_rate": float(cfg.get("sg_import_duty_rate", SG_IMPORT_DUTY_RATE)),
        "sg_gst_rate":         float(cfg.get("sg_gst_rate",         SG_GST_RATE)),
        "sg_gross_margin":     float(cfg.get("sg_gross_margin",     SG_GROSS_MARGIN)),
        "sg_freight_method":   str(cfg.get("sg_freight_method",     SG_FREIGHT_METHOD)),
        "default_usd_sgd":     float(cfg.get("default_usd_sgd",     DEFAULT_USD_SGD)),
        # Retail-side stack (shared with TH module-level _params for symmetry).
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


def get_usd_sgd() -> float:
    """Return USD→SGD rate.

    Derived from the same fx_rates source as USD/THB and SGD/THB so all
    three currencies stay on a consistent FX snapshot:
        usd_sgd = (THB-per-USD) / (THB-per-SGD)
    Order of preference: env override → live cross-rate → fallback.
    """
    env = os.environ.get("USD_SGD_RATE")
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
        usd_thb = rates.get("USD")
        sgd_thb = rates.get("SGD")
        if usd_thb and sgd_thb and usd_thb > 0 and sgd_thb > 0:
            return float(usd_thb) / float(sgd_thb)
    except Exception as e:
        log.warning("USD/SGD cross-rate lookup failed (non-fatal): %s — "
                    "using %.4f", e, DEFAULT_USD_SGD)
    return DEFAULT_USD_SGD


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


# ══ Singapore channel (Nubo SG) ══════════════════════════════════════════
# Parallel landed-cost path for SKUs that ship China→Singapore. See module
# docstring for rules / sources.

@dataclass
class WisdomSgPricedRow:
    item_code: str
    fob_usd: float
    usd_sgd: float
    sgd_thb: float
    fob_sgd: float
    freight_sgd: float = 0.0
    insurance_sgd: float = 0.0
    duty_sgd: float = 0.0
    gst_sgd: float = 0.0
    clearance_sgd: float = 0.0
    last_mile_sgd: float = 0.0
    landed_sgd: float = 0.0
    retail_sgd: float = 0.0
    cbm_used: float = 0.0
    cbm_method: str = "china_sg_flat"   # "china_sg_lcl_cbm" | "china_sg_flat"
    freight_method: str = "lcl"          # "lcl" | "fcl_20" | "fcl_40"
    logistics_clamp: str = ""


def _wisdom_sg_lcl_estimate(fob_usd: float, cbm: float, kg: float,
                            fx: dict, method: str,
                            sg_duty_rate: float,
                            sg_gst_rate: float) -> dict | None:
    """Best-effort China→Singapore landed estimate via shipping-automation.

    Routes through the china_to_singapore profile with explicit
    duty_rate / vat_rate overrides so we don't accidentally inherit
    Thailand's 7%. Result is THB-denominated; caller converts to SGD.
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
        est = _ce.estimate_landed_cost(
            origin="china_to_singapore",
            method=method,
            goods_value=fob_usd,
            goods_currency="USD",
            cbm=cbm,
            kg=kg,
            duty_rate=sg_duty_rate,
            vat_rate=sg_gst_rate,
            fx_rates=fx,
        )
        return est
    except Exception as e:
        log.warning("SG LCL CBM estimate failed (non-fatal): %s — "
                    "falling back to flat path", e)
        return None


def compute_wisdom_retail_sg(
    fob_usd: float,
    cbm: float = 0.0,
    kg: float = 0.0,
    usd_sgd: float | None = None,
    sgd_thb: float | None = None,
    freight_method: str | None = None,
    fx: dict | None = None,
) -> WisdomSgPricedRow | None:
    """Compute Singapore-channel landed cost + retail for one Wisdom SKU.

    Independent of compute_wisdom_retail() (TH path). Uses the
    china_to_singapore route profile from shipping-automation/cost_engine
    when CBM is supplied, otherwise a flat CIF≈FOB path.

    Args:
        fob_usd:         FOB China price in USD (from catalog).
        cbm:             Packed CBM. >0 → CBM path; 0 → flat path.
        kg:              Weight in kg (CBM path only, optional).
        usd_sgd:         USD→SGD rate (live if None).
        sgd_thb:         SGD→THB rate (live if None) — used to convert the
                         engine's THB total back to SGD.
        freight_method:  "lcl" | "fcl_20" | "fcl_40" (config default if None).
        fx:              Full FX dict (optional, passed to cost_engine).

    Returns:
        WisdomSgPricedRow, or None if fob_usd is falsy.
    """
    if not fob_usd or fob_usd <= 0:
        return None

    p = _sg_params()
    usd_sgd_rate = usd_sgd if usd_sgd and usd_sgd > 0 else get_usd_sgd()
    sgd_thb_rate = sgd_thb if sgd_thb and sgd_thb > 0 else get_sgd_thb()
    fob_sgd = fob_usd * usd_sgd_rate
    method = freight_method or p["sg_freight_method"]

    # Build an FX dict for the cost_engine call if not provided. Engine
    # needs USD (goods currency) — SGD is included so the SG dest
    # conversion stays consistent. THB-per-USD = THB-per-SGD × USD-per-SGD.
    if fx is None:
        usd_thb = sgd_thb_rate * usd_sgd_rate
        fx = {"USD": usd_thb, "SGD": sgd_thb_rate}

    cbm_method = "china_sg_flat"
    logistics_clamp = ""
    est = None
    if cbm and cbm > 0:
        est = _wisdom_sg_lcl_estimate(
            fob_usd, cbm, kg, fx, method,
            sg_duty_rate=p["sg_import_duty_rate"],
            sg_gst_rate=p["sg_gst_rate"],
        )

    if est is not None:
        # CBM path: convert engine's THB breakdown back to SGD.
        landed_thb_raw = est["total_landed_thb"]
        landed_sgd_raw = landed_thb_raw / sgd_thb_rate
        freight_sgd   = est["freight"]["thb"]      / sgd_thb_rate
        insurance_sgd = est["insurance"]["thb"]    / sgd_thb_rate
        duty_sgd      = est["customs"]["duty_thb"] / sgd_thb_rate
        gst_sgd       = est["customs"]["vat_thb"]  / sgd_thb_rate
        clearance_sgd = est["clearance_thb"]       / sgd_thb_rate
        last_mile_sgd = est["last_mile_thb"]       / sgd_thb_rate
        cbm_method = "china_sg_lcl_cbm"

        # Apply Vinci-style tier clamp using EUR-equivalent FOB band
        # (same heuristic as the TH path — keeps SG and TH symmetric).
        eur_thb = fx.get("EUR", 38.0)
        eur_fob_equiv = fob_usd * fx["USD"] / eur_thb
        try:
            from shared.landed_pricing import logistics_band, LOGISTICS_TIERS  # noqa: F401
            lo_pct, hi_pct = logistics_band(eur_fob_equiv)
        except Exception:
            lo_pct, hi_pct = 0.35, 0.80   # Tier 3 fallback
        floor_landed = fob_sgd * (1 + lo_pct)
        cap_landed = fob_sgd * (1 + hi_pct)
        if landed_sgd_raw < floor_landed:
            landed_sgd = floor_landed
            logistics_clamp = "floored"
        elif landed_sgd_raw > cap_landed:
            landed_sgd = cap_landed
            logistics_clamp = "capped"
        else:
            landed_sgd = landed_sgd_raw
        landed_sgd = round(landed_sgd, 2)
    else:
        # Flat path: SG consolidated CIF ≈ FOB (no separate freight charge).
        # Used when CBM unknown or CBM call fails.
        freight_sgd = 0.0
        insurance_sgd = 0.0
        duty_sgd = round(fob_sgd * p["sg_import_duty_rate"], 2)
        gst_sgd = round((fob_sgd + duty_sgd) * p["sg_gst_rate"], 2)
        clearance_sgd = 0.0
        last_mile_sgd = 0.0
        landed_sgd = round(fob_sgd + duty_sgd + gst_sgd, 2)
        cbm_method = "china_sg_flat"

    # Retail derivation — SG gross margin + optional SG customer GST stack
    # (only when Nubo is GST-registered, matching the existing TH pattern).
    gm = p["sg_gross_margin"]
    sg_customer_gst_mult = (
        (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    )
    retail_sgd = round((landed_sgd / (1 - gm)) * sg_customer_gst_mult, 2)

    return WisdomSgPricedRow(
        item_code="",
        fob_usd=fob_usd,
        usd_sgd=round(usd_sgd_rate, 6),
        sgd_thb=round(sgd_thb_rate, 4),
        fob_sgd=round(fob_sgd, 2),
        freight_sgd=round(freight_sgd, 2),
        insurance_sgd=round(insurance_sgd, 2),
        duty_sgd=round(duty_sgd, 2),
        gst_sgd=round(gst_sgd, 2),
        clearance_sgd=round(clearance_sgd, 2),
        last_mile_sgd=round(last_mile_sgd, 2),
        landed_sgd=landed_sgd,
        retail_sgd=retail_sgd,
        cbm_used=cbm or 0.0,
        cbm_method=cbm_method,
        freight_method=method,
        logistics_clamp=logistics_clamp,
    )


def compute_wisdom_retail_sg_batch(
    products: list[dict],
    usd_sgd: float | None = None,
    sgd_thb: float | None = None,
    freight_method: str | None = None,
    fx: dict | None = None,
) -> list[WisdomSgPricedRow]:
    """Batch SG pricing. Mirrors compute_wisdom_retail_batch() shape."""
    usd_sgd_rate = usd_sgd if usd_sgd and usd_sgd > 0 else get_usd_sgd()
    sgd_thb_rate = sgd_thb if sgd_thb and sgd_thb > 0 else get_sgd_thb()
    if fx is None:
        usd_thb = sgd_thb_rate * usd_sgd_rate
        fx = {"USD": usd_thb, "SGD": sgd_thb_rate}
    results: list[WisdomSgPricedRow] = []
    for prod in products:
        fob = prod.get("fob_usd") or (prod.get("pricing") or {}).get("fob_usd")
        code = prod.get("item_code", "")
        cbm = 0.0
        kg = float(prod.get("weight_kg") or 0.0)
        dims = prod.get("dimensions") or {}
        try:
            l_cm = float(dims.get("length_cm") or 0)
            w_cm = float(dims.get("width_cm") or 0)
            h_cm = float(dims.get("height_cm") or 0)
            if l_cm > 0 and w_cm > 0 and h_cm > 0:
                pf = 0.15
                cbm = round(l_cm * w_cm * h_cm / 1_000_000.0 * pf, 4)
        except (TypeError, ValueError):
            pass
        row = compute_wisdom_retail_sg(
            fob, cbm=cbm, kg=kg,
            usd_sgd=usd_sgd_rate, sgd_thb=sgd_thb_rate,
            freight_method=freight_method, fx=fx,
        )
        if row:
            row.item_code = code
            results.append(row)
    return results


def pricing_metadata_sg(row: WisdomSgPricedRow, price_date: str) -> dict:
    """Return the Firestore pricing.sg sub-map for an SG-priced row.

    Keys are dotted-paths (pricing.sg.*) ready to merge into a Firestore
    `.update()` call. Coexists with pricing_metadata() — neither overlaps.
    """
    p = _sg_params()
    return {
        "pricing.sg.fob_usd":             row.fob_usd,
        "pricing.sg.usd_sgd":             row.usd_sgd,
        "pricing.sg.sgd_thb":             row.sgd_thb,
        "pricing.sg.fob_sgd":             row.fob_sgd,
        "pricing.sg.freight_sgd":         row.freight_sgd,
        "pricing.sg.insurance_sgd":       row.insurance_sgd,
        "pricing.sg.duty_sgd":            row.duty_sgd,
        "pricing.sg.gst_sgd":             row.gst_sgd,
        "pricing.sg.clearance_sgd":       row.clearance_sgd,
        "pricing.sg.last_mile_sgd":       row.last_mile_sgd,
        "pricing.sg.landed_sgd":          row.landed_sgd,
        "pricing.sg.retail_sgd":          row.retail_sgd,
        "pricing.sg.sg_import_duty_rate": p["sg_import_duty_rate"],
        "pricing.sg.sg_gst_rate":         p["sg_gst_rate"],
        "pricing.sg.sg_gross_margin":     p["sg_gross_margin"],
        "pricing.sg.sg_nubo_gst_registered": p["sg_nubo_gst_registered"],
        "pricing.sg.freight_method":      row.freight_method,
        "pricing.sg.cbm_used":            row.cbm_used,
        "pricing.sg.cbm_method":          row.cbm_method,
        "pricing.sg.logistics_clamp":     row.logistics_clamp,
        "pricing.sg.price_date":          price_date,
        "pricing.sg.currency":            "SGD",
    }
