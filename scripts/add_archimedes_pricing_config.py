"""Merge a `brands.archimedes-water-play` block into pricing_config/canonical.

Idempotent, merge-only. Does NOT touch other brands (vortex/4soft/weplay/...)
already present in the live doc — unlike `seed_pricing_config.py --force`,
which rebuilds the whole document from module constants and would drop the
brands added by later PRs.

Archimedes Water Play is a China-origin (Wenzhou Daosen) brand priced in CNY.
It reuses the Wisdom (China FOB) pricing pattern:
  - 0% Thai import duty (ASEAN-China FTA, Form E)
  - 7% Thai import VAT on (CIF + duty)
  - 7% TH customer VAT embedded in retail_thb
  - 50% gross margin (default for China-origin brands, matches Wisdom)

Usage:
    python scripts/add_archimedes_pricing_config.py            # merge if absent
    python scripts/add_archimedes_pricing_config.py --force    # overwrite block
    python scripts/add_archimedes_pricing_config.py --dry-run

Auth: ADC (`gcloud auth application-default login`) or
GOOGLE_APPLICATION_CREDENTIALS pointed at the ai-agents-go SA key.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.pricing_config import (  # noqa: E402
    FS_COLLECTION, FS_DATABASE, FS_DOCUMENT, FS_PROJECT,
)

BRAND_KEY = "archimedes-water-play"
ARCHIMEDES_BLOCK = {
    "gross_margin": 0.50,                # China-origin default (matches Wisdom)
    "import_duty_rate": 0.00,            # ASEAN-China FTA Form E
    "currency": "CNY",                   # source pricelist currency
    "origin": "china",
    "default_cny_thb": 4.80,             # offline FX fallback (THB per CNY)
    "source_pricelist_url": "archimedes-water-play-catalog/data/source/daosen_pricelist_2026-05-29.xls",
    "source_pricelist_label": "Wenzhou Daosen 温州道森游乐戏水 pricelist 2026-05-29 (in-repo XLS)",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="Overwrite the brand block if it already exists.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be written; touch nothing.")
    args = ap.parse_args()

    if args.dry_run:
        print(json.dumps({BRAND_KEY: ARCHIMEDES_BLOCK}, indent=2, ensure_ascii=False))
        return 0

    from google.cloud import firestore  # type: ignore

    db = firestore.Client(project=FS_PROJECT, database=FS_DATABASE)
    ref = db.collection(FS_COLLECTION).document(FS_DOCUMENT)
    snap = ref.get()
    if not snap.exists:
        print(f"{FS_COLLECTION}/{FS_DOCUMENT} does not exist — run "
              f"scripts/seed_pricing_config.py first.", file=sys.stderr)
        return 1

    doc = snap.to_dict() or {}
    brands = doc.get("brands") or {}
    if BRAND_KEY in brands and not args.force:
        print(f"brands.{BRAND_KEY} already present. Use --force to overwrite.",
              file=sys.stderr)
        print(json.dumps(brands[BRAND_KEY], indent=2, ensure_ascii=False))
        return 0

    # Merge-only update: nested-field path keeps every other brand intact.
    ref.update({
        f"brands.{BRAND_KEY}": ARCHIMEDES_BLOCK,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "scripts/add_archimedes_pricing_config.py",
    })
    print(f"Merged brands.{BRAND_KEY} into {FS_COLLECTION}/{FS_DOCUMENT}")
    print(json.dumps(ARCHIMEDES_BLOCK, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
