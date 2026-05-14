"""
Canonical landed-cost + retail pricing for China-origin (FOB USD) brands.

Covers: Wisdom, and any future brand imported on China FOB terms.

Formula per SKU (revised 2026-05-14 to add 7% Thai VAT layer):
  cif_thb    = fob_usd × usd_thb
  duty_thb   = cif_thb × IMPORT_DUTY_RATE
  vat_thb    = (cif_thb + duty_thb) × THAI_VAT_RATE
  landed_thb = cif_thb + duty_thb + vat_thb
  retail_thb = landed_thb / (1 - GROSS_MARGIN)

Constants:
  IMPORT_DUTY_RATE = 0.07   # Thai import duty (playground equipment HS 9506)
  THAI_VAT_RATE    = 0.07   # Thai VAT, applied on (CIF + duty)
  GROSS_MARGIN     = 0.50

Exchange rate: live via shipping-automation/fx_rates.py if available,
otherwise from USD_THB_RATE env var, otherwise DEFAULT_USD_THB fallback.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

IMPORT_DUTY_RATE: float = 0.07
THAI_VAT_RATE: float = 0.07
GROSS_MARGIN: float = 0.50
DEFAULT_USD_THB: float = 35.0


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
        log.warning("FX lookup failed (non-fatal): %s — using %.2f", e, DEFAULT_USD_THB)

    return DEFAULT_USD_THB


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


def compute_wisdom_retail(fob_usd: float, usd_thb: float | None = None) -> WisdomPricedRow | None:
    """Compute landed cost and retail price for a single Wisdom SKU.

    Args:
        fob_usd:  FOB Shanghai price in USD (from catalog).
        usd_thb:  Exchange rate to use; fetched live if None.

    Returns:
        WisdomPricedRow, or None if fob_usd is falsy.
    """
    if not fob_usd or fob_usd <= 0:
        return None

    rate = usd_thb if usd_thb and usd_thb > 0 else get_usd_thb()
    fob_thb = fob_usd * rate
    duty_thb = round(fob_thb * IMPORT_DUTY_RATE, 2)
    vat_thb = round((fob_thb + duty_thb) * THAI_VAT_RATE, 2)
    landed_thb = round(fob_thb + duty_thb + vat_thb, 2)
    retail_thb = round(landed_thb / (1 - GROSS_MARGIN), 2)
    retail_usd = round(retail_thb / rate, 2)

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
    )


def compute_wisdom_retail_batch(
    products: list[dict],
    usd_thb: float | None = None,
) -> list[WisdomPricedRow]:
    """Price a list of product dicts (each must have 'item_code' and 'fob_usd').

    Args:
        products:  List of dicts with keys 'item_code' and 'fob_usd'.
        usd_thb:   Exchange rate; fetched once if None.

    Returns:
        List of WisdomPricedRow for every product that has a valid fob_usd.
    """
    rate = usd_thb if usd_thb and usd_thb > 0 else get_usd_thb()
    results = []
    for p in products:
        fob = p.get("fob_usd") or (p.get("pricing") or {}).get("fob_usd")
        code = p.get("item_code", "")
        row = compute_wisdom_retail(fob, rate)
        if row:
            row.item_code = code
            results.append(row)
    return results


def pricing_metadata(row: WisdomPricedRow, price_date: str) -> dict:
    """Return the Firestore pricing sub-map for a priced row."""
    return {
        "fob_usd": row.fob_usd,
        "usd_thb": row.usd_thb,
        "duty_thb": row.duty_thb,
        "vat_thb": row.vat_thb,
        "landed_thb": row.landed_thb,
        "retail_thb": row.retail_thb,
        "retail_usd": row.retail_usd,
        "import_duty_rate": IMPORT_DUTY_RATE,
        "thai_vat_rate": THAI_VAT_RATE,
        "gross_margin": GROSS_MARGIN,
        "price_date": price_date,
        "currency": "USD",
    }
