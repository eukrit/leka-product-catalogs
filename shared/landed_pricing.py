"""Shared landed-cost + retail pricing pipeline for European-sourced brands.

Extracted verbatim from vinci-catalog/import_pricelist.py so multiple brands
(Vinci Play, Rampline, future EU brands) compute landed cost and retail price
through one canonical formula.

Pipeline per SKU (freight source chosen by precedence):
  0. VENDOR FREIGHT (highest priority): when the caller passes a real per-SKU
     `pricing.freight_thb` sourced from `vendors/<brand>/products` (written by
     the vendors repo's sync_freight.py, gated to confirmed vendor packing data),
     use it verbatim as the freight line — CIF = FOB + vendor_freight, then the
     same duty/VAT treatment as the flat-uplift branch. This bypasses both the
     CBM estimate and the 1.35x flat uplift. Gated on `vendor_packing_source`
     being a real vendor source (vendor_email/vendor_attachment/vendor_pricelist)
     so estimate/none rows never trigger it.
  1. CBM = L*W*H_cm / 1e6 * packing_factor (default 0.15). No dims → flat 35%
     landed uplift on EUR-THB FOB.
  2. Landed THB via shipping-automation cost_engine.estimate_landed_cost,
     origin=europe (Gdynia → Laem Chabang), method=lcl, with Baltic-rate
     calibration when FBX index is reachable.
  3. Tiered logistics clamp (floor + cap as % of FOB-in-THB) by EUR FOB band —
     applied to every freight source above, vendor freight included.
  4. Retail = landed / (1 - GROSS_MARGIN). USD/EUR/SGD derived independently at
     live FX; 7% TH customer VAT embedded in retail_thb only.

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
# User revision 2026-05-14: Vinci 40%→35% GM; non-China duty 10%; 7% Thai import VAT.
# User revision 2026-05-22 (v2.29.0): Add 7% TH customer VAT embedded in retail price.
GROSS_MARGIN = 0.35                    # Vinci default; brands override
DUTY_RATE_NON_CHINA = 0.10             # Thai import duty for non-China origins
DUTY_RATE_CHINA = 0.0                  # ASEAN-China FTA Form E
THAI_VAT_RATE = 0.07                   # Thai import VAT applied on (CIF + duty)
TH_CUSTOMER_VAT_RATE = 0.07           # Thai customer VAT embedded in retail (v2.29.0)
# Destination customer-tax fallbacks (Firestore global keys are authoritative).
# Nubo is not yet GST-registered in Singapore → SG retail ships GST-free.
SG_CUSTOMER_GST_RATE = 0.09            # applied to SG retail only when Nubo registered
SG_NUBO_GST_REGISTERED = False
DEFAULT_PRODUCT_CATEGORY = "playground_equipment"
ORIGIN_ROUTE = "europe"
METHOD = "lcl"
UNMATCHED_LANDED_UPLIFT = 1.35         # 35% flat uplift on EUR-THB FOB when no CBM
DEFAULT_PACKING_FACTOR = 0.15

# Packing-data sources the vendors repo's sync_freight.py tags as real (vendor)
# vs estimated. Only these make a per-SKU `pricing.freight_thb` trustworthy enough
# to override the CBM estimate / flat uplift. Must match the sync-eligible set in
# vendors/scripts/{ingest_packing,sync_freight}.py.
VENDOR_PACKING_SOURCES = frozenset({"vendor_email", "vendor_attachment", "vendor_pricelist"})

# Tiered minimum/maximum logistics cost as a % of FOB-in-THB.
# Floor ensures every SKU carries a reasonable share of fixed costs (clearance,
# last-mile, insurance). Ceiling clamps outliers where installed dimensions
# wildly overstate packing CBM.
# Tuple = (fob_eur_max_inclusive, min_logistics_pct, max_logistics_pct)
# Revised 2026-06-02 (v2.67.0): tightened bands per user direction — applies to
# every brand (Wisdom, Vinci, Berliner, Rampline, Vortex, WePlay, 4soft,
# Archimedes) since they all clamp against this shared table by EUR-equivalent
# FOB band.
LOGISTICS_TIERS: list[tuple[float, float, float]] = [
    (500,          0.60, 1.20),
    (2_000,        0.50, 1.00),
    (10_000,       0.40, 0.80),
    (float("inf"), 0.30, 0.60),
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
        "th_customer_vat_rate": float(cfg.get("th_customer_vat_rate", TH_CUSTOMER_VAT_RATE)),
        "unmatched_landed_uplift": float(cfg.get("unmatched_landed_uplift", UNMATCHED_LANDED_UPLIFT)),
        "logistics_tiers": tiers,
        # Destination customer taxes (v2.21.0 schema). SG GST only applies when
        # Nubo is GST-registered; otherwise the SG sale is a zero-rated export
        # and retail_sgd is the pre-tax base converted at live FX.
        "sg_customer_gst_rate": float(cfg.get("sg_customer_gst_rate", SG_CUSTOMER_GST_RATE)),
        "sg_nubo_gst_registered": bool(cfg.get("sg_nubo_gst_registered", SG_NUBO_GST_REGISTERED)),
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
    retail_sgd: float
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
    vendor_freight_thb: float | None = None,
    vendor_freight_method: str | None = None,
    vendor_packing_source: str | None = None,
) -> PricedRow:
    """Price one SKU. `vendor_freight_thb` (+ `vendor_packing_source` in
    VENDOR_PACKING_SOURCES) takes precedence over the CBM estimate / flat uplift —
    see the module docstring. When no vendor freight is supplied the behaviour is
    identical to before, so existing callers are unaffected."""
    p = _resolve_params(brand)
    dims, strategy = fuzzy_lookup(code, dim_index)
    cbm = compute_cbm(dims, packing_factor) if dims else None
    note = ""

    use_vendor_freight = (
        vendor_freight_thb is not None
        and float(vendor_freight_thb) > 0
        and (vendor_packing_source or "") in VENDOR_PACKING_SOURCES
    )

    if use_vendor_freight:
        # Real per-SKU DDP freight from vendors/<brand>/products. Same CIF→duty→VAT
        # structure as the flat-uplift branch below — only the freight number is
        # real (vendor-confirmed) instead of a 0.35x estimate. cost_engine bills
        # duty on CIF (goods+freight) and VAT on (CIF+duty); we mirror that here.
        eur_thb = fx.get("EUR", 38.0)
        fob_thb = eur * eur_thb
        freight_thb = round(float(vendor_freight_thb), 2)
        cif_thb = fob_thb + freight_thb
        duty_thb = round(cif_thb * p["duty_rate_non_china"], 2)
        vat_thb = round((cif_thb + duty_thb) * p["thai_vat_rate"], 2)
        landed_thb = round(cif_thb + duty_thb + vat_thb, 2)
        cbm = 0.0
        cbm_method = vendor_freight_method or "vendor_freight"
        matched = True
        match_strategy = "vendor_freight"
        note = f"vendor_freight {vendor_freight_method or ''} src={vendor_packing_source}".strip()
    elif cbm and cbm > 0:
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

    # --- Retail price derivation (Task 10 — independent per-currency calc) ---
    #
    # Each currency's retail is derived directly from its own landed cost, NOT
    # from retail_thb converted at spot FX. This prevents FX rounding from
    # cascading and ensures retail_usd/sgd are correct even if THB/USD spot
    # fluctuates after the pricing run.
    #
    # TH customer VAT (7%) is embedded in retail_thb ONLY — it is a Thai
    # domestic tax. USD and SGD prices are pre-TH-VAT international prices.
    # SG GST stacks on retail_sgd only when Nubo is GST-registered.
    gm = p["gross_margin"]
    th_customer_vat_mult = 1.0 + p["th_customer_vat_rate"]
    retail_thb = round((landed_thb / (1 - gm)) * th_customer_vat_mult, 2)

    # USD: recompute landed cost in USD terms from the same EUR FOB.
    # For FOB-in-EUR brands: landed_usd ≈ landed_thb / USD_THB only if the
    # entire pipeline (freight, duty, VAT) were in THB. To be truly independent
    # we recompute the pipeline in USD: duty and VAT are proportional to the
    # goods value, and freight was already in THB (so we de-convert it).
    # Pragmatic approach that avoids double-running the full engine:
    #   landed_usd = landed_thb / USD_THB_fx  (same snapshot used for all calcs)
    # This is mathematically equivalent to running the full pipeline in USD when
    # the FX snapshot is consistent within a single run. Both approaches produce
    # the same result since all cost_engine outputs are proportional to THB rates.
    usd_thb = fx.get("USD", 35.0)
    eur_thb = fx.get("EUR", 38.0)
    sgd_thb = fx.get("SGD", 25.0)
    # landed_usd and landed_sgd computed from the same THB landed cost at
    # the run's FX snapshot — coherent because the entire engine runs in THB.
    landed_usd = landed_thb / usd_thb
    landed_sgd = landed_thb / sgd_thb
    retail_usd = round(landed_usd / (1 - gm), 2)   # no TH customer VAT on USD price
    retail_eur = round((landed_thb / eur_thb) / (1 - gm), 2)
    # SG retail: GST stacks only when Nubo is GST-registered; otherwise the
    # SG sale is a zero-rated export and SGD is just the pre-tax base at live FX.
    sg_gst_mult = (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    retail_sgd = round((landed_sgd / (1 - gm)) * sg_gst_mult, 2)

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
        retail_sgd=retail_sgd,
        freight_thb=freight_thb,
        duty_thb=duty_thb,
        vat_thb=vat_thb,
        note=note,
    )
