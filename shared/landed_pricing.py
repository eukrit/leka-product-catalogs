"""Shared landed-cost + retail pricing pipeline for European-sourced brands.

Extracted verbatim from vinci-catalog/import_pricelist.py so multiple brands
(Vinci Play, Rampline, future EU brands) compute landed cost and retail price
through one canonical formula.

Pipeline per SKU:
  1. CBM = L*W*H_cm / 1e6 * packing_factor (default 0.15). No dims → flat 35%
     landed uplift on EUR-THB FOB.
  2. Landed THB via shipping-automation cost_engine.estimate_landed_cost,
     origin=europe (Gdynia → Laem Chabang), method=lcl, with Baltic-rate
     calibration when FBX index is reachable.
  3. Tiered logistics clamp (floor + cap as % of FOB-in-THB) by EUR FOB band.
  4. Retail = landed / (1 - GROSS_MARGIN). USD/EUR derived at live FX.

Brand files own pricelist parsing, dim-index loading, and Firestore writes —
this module is brand-agnostic.
"""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# --- Cross-machine shipping-automation resolution ---------------------------
# Locate shipping-automation/mcp-server under the user's OneDrive root so this
# works on both NUC9 (Users/eukri) and NCORE100 (Users/Eukrit). Caller can
# override via SHIPPING_AUTOMATION_MCP env var.
def _resolve_shipping_automation() -> Path:
    import os
    env = os.environ.get("SHIPPING_AUTOMATION_MCP")
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        Path.home() / "OneDrive" / "Documents" / "Claude Code" / "shipping-automation" / "mcp-server",
        # Legacy hardcoded fallback (NCORE100):
        Path(r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\shipping-automation\mcp-server"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise RuntimeError(
        "shipping-automation/mcp-server not found. Set SHIPPING_AUTOMATION_MCP "
        f"or place it under one of: {[str(c) for c in candidates]}"
    )


_SHIPPING_AUTO = _resolve_shipping_automation()
if str(_SHIPPING_AUTO) not in sys.path:
    sys.path.insert(0, str(_SHIPPING_AUTO))

import cost_engine  # noqa: E402  shipping-automation/mcp-server/cost_engine.py
from cost_engine import estimate_landed_cost  # noqa: E402
from fx_rates import get_fx_rates as _get_fx_rates_impl  # noqa: E402

from shared.pricing_config import get_pricing_config  # noqa: E402

# Re-export so brand files import everything from this module.
get_fx_rates = _get_fx_rates_impl


# --- Module-level fallback constants ---------------------------------------
# Source of truth lives in Firestore (`pricing_config/canonical`, edited via
# the gateway-served form `docs/forms/pricing-config.html`). These are only
# used when Firestore is unreachable (no ADC / offline / PRICING_CONFIG_DISABLE=1)
# or when a brand has no override. They MUST stay in sync with the seed in
# scripts/seed_pricing_config.py — otherwise `--force` re-seed would drift.
#
# User revision 2026-05-14:
#   Vinci moves 40% → 35% GM; non-China duty fixed at 10%; 7% Thai VAT layer added.
GROSS_MARGIN = 0.35                    # Vinci default; brands override
DUTY_RATE_NON_CHINA = 0.10             # Thai import duty for non-China origins
DUTY_RATE_CHINA = 0.0                  # ASEAN-China FTA Form E
THAI_VAT_RATE = 0.07                   # Thai VAT applied on (CIF + duty)
DEFAULT_PRODUCT_CATEGORY = "playground_equipment"
ORIGIN_ROUTE = "europe"
METHOD = "lcl"
UNMATCHED_LANDED_UPLIFT = 1.35         # 35% flat uplift on EUR-THB FOB when no CBM
DEFAULT_PACKING_FACTOR = 0.15

# Tiered minimum/maximum logistics cost as a % of FOB-in-THB.
# Floor ensures every SKU carries a reasonable share of fixed costs (clearance,
# last-mile, insurance). Ceiling clamps outliers where installed dimensions
# wildly overstate packing CBM.
# Tuple = (fob_eur_max_inclusive, min_logistics_pct, max_logistics_pct)
LOGISTICS_TIERS: list[tuple[float, float, float]] = [
    (500,          0.80, 2.50),
    (2_000,        0.60, 1.80),
    (10_000,       0.45, 1.20),
    (float("inf"), 0.35, 0.80),
]


def _resolve_params(brand: str) -> dict:
    """Merge Firestore overrides on top of module-level defaults.

    Returns a dict with every key the price_row() pipeline needs. Brand
    is required ("vinci" / "berliner" / "rampline") so we pull the right
    GROSS_MARGIN even though most other knobs are global.
    """
    cfg = get_pricing_config(brand)
    tiers_raw = cfg.get("logistics_tiers")
    tiers: list[tuple[float, float, float]]
    if tiers_raw:
        tiers = [
            (
                float("inf") if t.get("fob_eur_max") in (None, "inf") else float(t["fob_eur_max"]),
                float(t["min_pct"]),
                float(t["max_pct"]),
            )
            for t in tiers_raw
        ]
    else:
        tiers = LOGISTICS_TIERS
    return {
        "gross_margin": float(cfg.get("gross_margin", GROSS_MARGIN)),
        "duty_rate_non_china": float(cfg.get("duty_rate_non_china", DUTY_RATE_NON_CHINA)),
        "duty_rate_china": float(cfg.get("duty_rate_china", DUTY_RATE_CHINA)),
        "thai_vat_rate": float(cfg.get("thai_vat_rate", THAI_VAT_RATE)),
        "unmatched_landed_uplift": float(cfg.get("unmatched_landed_uplift", UNMATCHED_LANDED_UPLIFT)),
        "logistics_tiers": tiers,
    }


def logistics_band(eur_fob: float, tiers: list[tuple[float, float, float]] | None = None) -> tuple[float, float]:
    t = tiers if tiers is not None else LOGISTICS_TIERS
    for cap, lo, hi in t:
        if eur_fob <= cap:
            return lo, hi
    return t[-1][1], t[-1][2]


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

    Handles ints, floats, strings with ranges ('390, 540 cm'), and concatenated
    digit blobs (90120180210 = 90, 120, 180, 210 cm). Takes MIN for multi-value
    cases (packing CBM should be the minimum rectangular envelope). Values
    > 1500 cm (15 m) treated as unparseable → returns None so caller falls back
    to flat-uplift pricing.
    """
    MAX_CM = 1500
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if 0 < v <= MAX_CM:
            return v
        s = str(int(v))
        for chunk in (3, 2):
            parts = [s[i:i + chunk] for i in range(0, len(s), chunk)]
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
    packing_factor: float = DEFAULT_PACKING_FACTOR,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    brand: str = "vinci",
) -> PricedRow:
    p = _resolve_params(brand)
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
                product_category=product_category,
                fx_rates=fx,
                # User 2026-05-14 rule: 10% duty for non-China origins.
                # Overrides the cost_engine's Europe-playground default.
                duty_rate=p["duty_rate_non_china"],
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
        # No dimensions: flat 35% logistics + non-China 10% duty + 7% Thai VAT
        # (user 2026-05-14 rule). VAT applied on (CIF + duty).
        eur_thb = fx.get("EUR", 38.0)
        fob_thb = eur * eur_thb
        cif_thb = fob_thb * p["unmatched_landed_uplift"]
        freight_thb = cif_thb - fob_thb
        duty_thb = round(cif_thb * p["duty_rate_non_china"], 2)
        vat_thb = round((cif_thb + duty_thb) * p["thai_vat_rate"], 2)
        landed_thb = round(cif_thb + duty_thb + vat_thb, 2)
        cbm = 0.0
        cbm_method = "flat_uplift"
        matched = False
        match_strategy = "flat_uplift"

    # Tiered logistics clamp: floor + cap as % of FOB-in-THB.
    fob_thb = eur * fx.get("EUR", 38.0)
    landed_thb_raw = landed_thb
    lo_pct, hi_pct = logistics_band(eur, p["logistics_tiers"])
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

    retail_thb = round(landed_thb / (1 - p["gross_margin"]), 2)
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
