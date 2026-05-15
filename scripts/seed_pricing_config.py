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
        },
        "brands": {
            "vinci":    {"gross_margin": _lp.GROSS_MARGIN},
            "berliner": {
                "gross_margin": berliner.get("gross_margin", 0.25),
                "exw_discount": berliner.get("exw_discount", 0.15),
            },
            "rampline": {"gross_margin": rampline.get("gross_margin", 0.30)},
            "wisdom": {
                "gross_margin": _wp.GROSS_MARGIN,
                "import_duty_rate": _wp.IMPORT_DUTY_RATE,
                "default_usd_thb": _wp.DEFAULT_USD_THB,
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
