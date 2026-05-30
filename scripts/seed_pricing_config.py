"""Seed pricing_config/canonical from the current module-level constants.

One-shot. After this runs, the Firestore doc is the source of truth and
the editor UI at https://gateway.goco.bz/leka-product-catalogs/forms/pricing-config
takes over.

Usage:
    python scripts/seed_pricing_config.py            # writes if doc missing
    python scripts/seed_pricing_config.py --force    # overwrites existing

Reads:
    shared/landed_pricing.py     (Vinci defaults + global rates + tiers)
    shared/wisdom_pricing.py     (Wisdom-specific rates)
    berliner-catalog/import_pricelist.py  (Berliner GROSS_MARGIN, EXW_DISCOUNT)
    rampline-catalog/import_pricelist.py  (Rampline GROSS_MARGIN)

Auth: ADC (`gcloud auth application-default login`) or
GOOGLE_APPLICATION_CREDENTIALS pointed at the ai-agents-go SA key.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared import landed_pricing as _lp  # noqa: E402
from shared import wisdom_pricing as _wp  # noqa: E402

# Vortex canonical maps live in vortex-catalog/vortex_config.py (pure dicts,
# no heavy deps) — single source of truth shared with its import_pricelist.py.
sys.path.insert(0, str(REPO_ROOT / "vortex-catalog"))
import vortex_config as _vortex  # noqa: E402
from shared.pricing_config import (  # noqa: E402
    FS_COLLECTION, FS_DATABASE, FS_DOCUMENT, FS_PROJECT,
)


def _berliner_constants() -> dict[str, float]:
    """Parse Berliner's local override constants without importing the
    module (which insists on a hard-coded shipping-automation path)."""
    src = (REPO_ROOT / "berliner-catalog" / "import_pricelist.py").read_text(encoding="utf-8")
    out: dict[str, float] = {}
    for name in ("GROSS_MARGIN", "EXW_DISCOUNT"):
        for line in src.splitlines():
            if line.startswith(f"{name} = "):
                # Strip trailing comments. e.g. "GROSS_MARGIN = 0.25  # ..."
                value = line.split("=", 1)[1].split("#", 1)[0].strip()
                out[name.lower()] = float(value)
                break
    return out


def _rampline_constants() -> dict[str, float]:
    src = (REPO_ROOT / "rampline-catalog" / "import_pricelist.py").read_text(encoding="utf-8")
    out: dict[str, float] = {}
    for line in src.splitlines():
        if line.startswith("GROSS_MARGIN = "):
            value = line.split("=", 1)[1].split("#", 1)[0].strip()
            out["gross_margin"] = float(value)
            break
    return out


def build_seed_doc() -> dict:
    berliner = _berliner_constants()
    rampline = _rampline_constants()
    tiers = [
        {
            "fob_eur_max": (None if cap == float("inf") else cap),
            "min_pct": lo,
            "max_pct": hi,
        }
        for (cap, lo, hi) in _lp.LOGISTICS_TIERS
    ]
    return {
        "global": {
            "thai_vat_rate": _lp.THAI_VAT_RATE,
            "duty_rate_non_china": _lp.DUTY_RATE_NON_CHINA,
            "duty_rate_china": _lp.DUTY_RATE_CHINA,
            "unmatched_landed_uplift": _lp.UNMATCHED_LANDED_UPLIFT,
            "default_packing_factor": _lp.DEFAULT_PACKING_FACTOR,
            # Customer-facing destination taxes (v2.21.0 schema additions).
            # Per user 2026-05-17: retail is always quoted VAT-inclusive in
            # TH, so the customer-VAT line stays at 0 (the 7% import VAT is
            # already inside landed_thb). SG GST is gated on a Nubo
            # registration flag — ships off.
            "th_customer_vat_rate": 0.0,
            "sg_customer_gst_rate": 0.09,
            "sg_nubo_gst_registered": False,
        },
        "brands": {
            "vinci":    {
                "gross_margin": _lp.GROSS_MARGIN,
                "source_pricelist_url": "https://drive.google.com/drive/folders/1ZiRZknbz0XlE9RMIbDwe9MC1oXegMyfl",
                "source_pricelist_label": "Vinci Play master folder (Google Drive)",
            },
            "berliner": {
                "gross_margin": berliner.get("gross_margin", 0.25),
                "exw_discount": berliner.get("exw_discount", 0.15),
                "source_pricelist_url": "berliner-catalog/data/pricelist_2026-01-01.csv",
                "source_pricelist_label": "Berliner pricelist 2026-01-01 (in-repo CSV)",
            },
            "rampline": {
                "gross_margin": rampline.get("gross_margin", 0.30),
                "source_pricelist_url": "https://drive.google.com/drive/folders/Rampline%20Price%20list%202025",
                "source_pricelist_label": "Rampline 2025 NOK pricelist (Google Drive)",
            },
            "wisdom": {
                "gross_margin": _wp.GROSS_MARGIN,
                "import_duty_rate": _wp.IMPORT_DUTY_RATE,
                "default_usd_thb": _wp.DEFAULT_USD_THB,
                # SG (Nubo Singapore) channel — parallel landed-cost path.
                # Driven by compute_wisdom_retail_sg(); routes through
                # shipping-automation china_to_singapore profile.
                # SG: 0% duty on HS 9503/9506, 9% GST since 2024-01-01.
                "sg_import_duty_rate": _wp.SG_IMPORT_DUTY_RATE,
                "sg_gst_rate":         _wp.SG_GST_RATE,
                "sg_gross_margin":     _wp.SG_GROSS_MARGIN,
                "sg_freight_method":   _wp.SG_FREIGHT_METHOD,
                "default_usd_sgd":     _wp.DEFAULT_USD_SGD,
                "source_pricelist_url": "wisdom-catalog/data/",
                "source_pricelist_label": "Wisdom Excel catalogs (in-repo)",
            },
            # Vortex Aquatics — Canada EXW USD, per-product-line reseller discounts.
            "vortex": _vortex.brand_config(),
            # WePlay (Kiddie's Paradise Inc., Taiwan) — FOB Taiwan, net USD.
            # Taiwan is non-FTA for Thailand → 10% import duty + 7% import VAT.
            # Freight is CBM-driven (carton CBM / pack qty) at sea_lcl_per_cbm_thb;
            # see weplay-catalog/import_pricelist.py. GM 0.50 confirmed 2026-05-29.
            "weplay": {
                "gross_margin": 0.50,
                "import_duty_rate": 0.10,
                "sea_lcl_per_cbm_thb": 5500.0,
                "default_usd_thb": 33.0,
                "source_pricelist_url": "weplay-catalog/import_pricelist.py (AQ1251030077)",
                "source_pricelist_label": "WePlay quotation AQ1251030077 (FOB Taiwan, USD)",
            },
            "4soft": {
                # EU/Czech EXW brand — same shape as Berliner. Added v2.40.0.
                "gross_margin": 0.40,
                "exw_discount": 0.15,
                "trade_terms": "EXW",
                "origin": "EU/Czech",
                "source_pricelist_url": "foursoft-catalog/data/pricelist_2025-03-01.csv",
                "source_pricelist_label": "4soft 2025 EPDM-graphics pricelist (.xls, valid 2025-03-01)",
            },
            # China-origin (Wenzhou Daosen), priced in CNY. Mirrors Wisdom:
            # 0% duty (ASEAN-China FTA Form E), 7% import VAT, 50% GM.
            "archimedes-water-play": {
                "gross_margin": 0.50,
                "import_duty_rate": 0.00,
                "currency": "CNY",
                "origin": "china",
                "default_cny_thb": 4.80,
                "source_pricelist_url": "archimedes-water-play-catalog/data/source/daosen_pricelist_2026-05-29.xls",
                "source_pricelist_label": "Wenzhou Daosen 温州道森游乐戏水 pricelist 2026-05-29 (in-repo XLS)",
            },
        },
        "logistics_tiers": tiers,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "scripts/seed_pricing_config.py",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing doc.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the doc that would be written; touch nothing.")
    args = ap.parse_args()

    doc = build_seed_doc()

    if args.dry_run:
        import json
        print(json.dumps(doc, indent=2))
        return 0

    from google.cloud import firestore  # type: ignore

    db = firestore.Client(project=FS_PROJECT, database=FS_DATABASE)
    ref = db.collection(FS_COLLECTION).document(FS_DOCUMENT)
    snap = ref.get()
    if snap.exists and not args.force:
        print(f"Doc already exists at {FS_COLLECTION}/{FS_DOCUMENT}. "
              f"Use --force to overwrite.", file=sys.stderr)
        return 1
    ref.set(doc)
    print(f"Wrote {FS_COLLECTION}/{FS_DOCUMENT} "
          f"(global={len(doc['global'])} keys, "
          f"brands={list(doc['brands'])}, "
          f"tiers={len(doc['logistics_tiers'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
