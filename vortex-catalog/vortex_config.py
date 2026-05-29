"""Canonical Vortex pricing configuration (single source of truth).

Imported by both `vortex-catalog/import_pricelist.py` (the pricelist ingester)
and `scripts/seed_pricing_config.py` (the Firestore config seeder) so the
per-product-line reseller-discount map never drifts between code and the
Firestore `pricing_config/canonical.brands.vortex` document.

Vortex Aquatic Structures International — Pointe-Claire, Quebec, Canada.
Trade terms: **EXW Canada, USD** (confirmed from the supplier thread + the
ECU Worldwide freight quote "EXW. Term", shipper VORTEX Pointe-Claire). Canada
is non-China origin → 10% Thai import duty (global `duty_rate_non_china`).

Reseller discount is **per product LINE**, not a flat brand discount. The 2026
USD pricelist groups SKUs into ~22 fine-grained "Collections"; each collection
rolls up to one of Vortex's top-level product lines, and each line carries its
own confirmed reseller discount (USD). Source: the discount table Vortex shared
in the "Pricelist 2026" thread (Apr–May 2026), cross-checked 2026-05-29.

    Splashpad      25%   Spraypoint     25%
    Poolplay       15%   Elevations     15%
    WQMS           15%   Water Journey  20%
    Water Slides   15%   CoolHub         0%  (user decision 2026-05-29: not
                                              covered by the reseller agreement)

User mapping decisions (2026-05-29):
  - CoolHub™ → its own line, **0% discount** (our cost = full list price).
  - SmartPoint / Smartpoint N°4 → classified under **Splashpad (25%)**.
  - PlayNuk™ → grouped with **Elevations (15%)** per Vortex's own taxonomy
    ("Elevations™ & PlayNuk™" is one product line on vortex-intl.com).
"""
from __future__ import annotations

import re

# Our retail mark-up on landed cost. Matches the other USD-FOB import brands
# (DesignPark 0.35, global default). Editable via the pricing-config form.
GROSS_MARGIN = 0.35

# Per-line reseller discount applied to the USD list price to get our EXW cost:
#   our_cost_usd = list_usd * (1 - line_discount)
LINE_DISCOUNTS: dict[str, float] = {
    "splashpad": 0.25,
    "poolplay": 0.15,
    "spraypoint": 0.25,
    "elevations": 0.15,
    "wqms": 0.15,
    "water_journey": 0.20,
    "water_slides": 0.15,
    "coolhub": 0.0,          # user decision 2026-05-29: no reseller discount
}

# Fallback line for any collection not in the map below. Splashpad is by far
# the largest family; an unknown collection is logged by the importer.
DEFAULT_LINE = "splashpad"

# Maps each pricelist "Collection" (normalised: lower-cased, ™/®/° stripped,
# whitespace collapsed) → top-level product line key in LINE_DISCOUNTS.
COLLECTION_TO_LINE: dict[str, str] = {
    # --- Splashpad family (25%) ---
    "essentials": "splashpad",
    "classic": "splashpad",
    "contemporary": "splashpad",
    "toons": "splashpad",
    "vectory": "splashpad",
    "explora": "splashpad",
    "watergarden": "splashpad",
    "ground sprays": "splashpad",
    "spraylink": "splashpad",
    "sea silhouette": "splashpad",
    "nautical": "splashpad",
    "fine mist": "splashpad",
    "playable fountain": "splashpad",
    "custom items": "splashpad",
    "smartpoint": "splashpad",        # user 2026-05-29: treat Spraypoint/Smartpoint as Splashpad 25%
    "smartpoint n4": "splashpad",
    # --- Poolplay (15%) ---
    "poolplay": "poolplay",
    # --- Elevations + PlayNuk (15%) ---
    "elevations": "elevations",
    "playnuk": "elevations",
    # --- Water Journey + Lazy River (20%) ---
    "water journey": "water_journey",
    "lazy river": "water_journey",
    # --- CoolHub (0%) ---
    "coolhub": "coolhub",
}

ORIGIN = "canada"            # EXW Pointe-Claire, Quebec — non-China → 10% duty
CURRENCY = "USD"
TRADE_TERMS = "EXW Pointe-Claire, Quebec, Canada (USD)"
SOURCE_PRICELIST_LABEL = "Vortex 2026 USD Price List R2 (released Feb 2026)"
SOURCE_PRICELIST_URL = (
    "Google Drive: Partners Playground/Vortex/"
    "2026-04-22 Vortex 2026_USD_Price List_R2 (1).pdf"
)

_TM = re.compile(r"[™®®™]")
_NUMSIGN = re.compile(r"[°º#]")


def normalize_collection(coll: str) -> str:
    """Normalise a pricelist Collection label to a COLLECTION_TO_LINE key."""
    s = (coll or "").strip().lower()
    s = _TM.sub("", s)
    s = _NUMSIGN.sub("", s)        # 'Smartpoint N°4' → 'smartpoint n4'
    s = re.sub(r"\s+", " ", s).strip()
    return s


def line_for_collection(coll: str) -> str:
    """Return the product-line key for a pricelist Collection (DEFAULT_LINE if
    unknown). The importer logs a warning for unknown collections."""
    return COLLECTION_TO_LINE.get(normalize_collection(coll), DEFAULT_LINE)


def discount_for_collection(coll: str) -> float:
    return LINE_DISCOUNTS.get(line_for_collection(coll), 0.0)


def brand_config() -> dict:
    """The `pricing_config/canonical.brands.vortex` document body."""
    return {
        "gross_margin": GROSS_MARGIN,
        "origin": ORIGIN,
        "currency": CURRENCY,
        "trade_terms": TRADE_TERMS,
        "line_discounts": dict(LINE_DISCOUNTS),
        "collection_to_line": dict(COLLECTION_TO_LINE),
        "default_line": DEFAULT_LINE,
        "source_pricelist_url": SOURCE_PRICELIST_URL,
        "source_pricelist_label": SOURCE_PRICELIST_LABEL,
    }
