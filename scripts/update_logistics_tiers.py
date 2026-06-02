"""Surgically update ONLY `logistics_tiers` on pricing_config/canonical.

Unlike `seed_pricing_config.py --force` (which rewrites the entire doc from
module constants and would clobber any field edited live via the gateway form —
notably 4soft's 0.20 reseller discount written directly by PR #98), this performs
a partial Firestore `update()` touching only `logistics_tiers` plus
`updated_at` / `updated_by`. Every brand block is left exactly as-is.

The new tier values are read from `shared/landed_pricing.py` (the single source),
so run this AFTER editing `LOGISTICS_TIERS` there.

Usage:
    python scripts/update_logistics_tiers.py --dry-run   # print, touch nothing
    python scripts/update_logistics_tiers.py             # write

Auth: ADC or GOOGLE_APPLICATION_CREDENTIALS → ai-agents-go SA key.
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
from shared.pricing_config import (  # noqa: E402
    FS_COLLECTION, FS_DATABASE, FS_DOCUMENT, FS_PROJECT,
)


def build_tiers() -> list[dict]:
    return [
        {
            "fob_eur_max": (None if cap == float("inf") else cap),
            "min_pct": lo,
            "max_pct": hi,
        }
        for (cap, lo, hi) in _lp.LOGISTICS_TIERS
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the tiers that would be written; touch nothing.")
    ap.add_argument("--updated-by", default="tighten logistics tiers v2.67.0")
    args = ap.parse_args()

    tiers = build_tiers()

    if args.dry_run:
        import json
        print(json.dumps(tiers, indent=2))
        return 0

    from google.cloud import firestore  # type: ignore

    db = firestore.Client(project=FS_PROJECT, database=FS_DATABASE)
    ref = db.collection(FS_COLLECTION).document(FS_DOCUMENT)
    if not ref.get().exists:
        print(f"Doc {FS_COLLECTION}/{FS_DOCUMENT} does not exist — run "
              f"seed_pricing_config.py first.", file=sys.stderr)
        return 1

    ref.update({
        "logistics_tiers": tiers,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": args.updated_by,
    })
    print(f"Updated logistics_tiers on {FS_COLLECTION}/{FS_DOCUMENT} "
          f"({len(tiers)} tiers). Brand blocks untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
