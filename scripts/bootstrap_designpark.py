"""Phase A: bootstrap DesignPark as the 9th brand in the vendors→Medusa pipeline.

What this does (idempotent):
  1. Creates (or fetches) the Medusa Sales Channel "Design Park" via
     `MedusaImporter.get_or_create_sales_channel`. Prints the resulting
     `sc_…` id so it can be pasted into
     `scripts/sync_vendors_to_medusa.py::BRAND_SALES_CHANNELS["designpark"]`.
  2. Writes / merges the `vendors/designpark` root doc in Firestore DB
     `vendors` (project ai-agents-go) with the canonical brand fields the
     other 8 brands carry (`slug`, `name`, `legal_name`, `country`,
     `website`, `currency_native`, `origin_route`, `status`).
  3. Optionally writes the sales-channel id back onto the root doc as
     `sales_channel_id` for the sync script's env-fallback.

Auth:
  - Medusa: env `LEKA_MEDUSA_ADMIN_EMAIL` + `LEKA_MEDUSA_ADMIN_PASSWORD`
    (mirrors sync_vendors_to_medusa.py). Override backend with
    `MEDUSA_BACKEND_URL`.
  - Firestore: GOOGLE_APPLICATION_CREDENTIALS env, or the project's
    SA key under Credentials Claude Code, or `gcloud auth
    application-default login` ADC.

Usage:
    py scripts/bootstrap_designpark.py --dry-run
    py scripts/bootstrap_designpark.py --apply
    py scripts/bootstrap_designpark.py --apply --skip-sc       # only root doc
    py scripts/bootstrap_designpark.py --apply --skip-root     # only SC
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Pre-import: configure ADC the same way sync_vendors_to_medusa.py does so this
# script runs cleanly on both NUC9 (Users/eukri) and NCORE100 (Users/Eukrit).
_LOCAL_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for cand in _LOCAL_SA_CANDIDATES:
        if os.path.exists(cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

# Add repo root to path so `shared.*` imports resolve regardless of cwd.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.cloud import firestore  # noqa: E402
from shared.medusa_importer import MedusaImporter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("bootstrap_designpark")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "designpark"

ROOT_DOC: dict = {
    "slug": SLUG,
    "name": "Design Park",
    "legal_name": "DESIGN PARK Co., Ltd.",
    "country": "South Korea",
    "country_code": "KR",
    "website": "",  # Phase D skipped per plan §7; fill later if scrape happens.
    "currency_native": "USD",          # Pricelist is USD FOB Busan.
    "origin_route": "japan_korea",     # cost_engine ROUTE_PROFILES key.
    "fob_port": "Busan, South Korea",
    "duty_rate_thai": 0.10,            # non-China, mirrors landed_pricing.py
    "status": "active",
    "categories": [
        "Slides & Tubes",
        "Outdoor Fitness",
        "Speed Racers",
        "Modern Igloo",
        "Dry Playground",
        "Water Play",
        "Themes (Dry & Waterplay)",
    ],
    "data_sources": {
        "drive_partners": r"My Drive\Partners Playground\DesignPark",
        "drive_catalogs": r"My Drive\Catalogs GO\DesignPark",
        "onedrive_suppliers": r"OneDrive\Documents\Suppliers GO\DesignPark",
        "slack_channel": "#vendor-design-park",
        "website_scrape": "skipped_v1",
    },
}


def bootstrap_sales_channel(dry_run: bool) -> str | None:
    """Create-or-fetch Medusa Sales Channel; return sc_… id."""
    backend = os.environ.get(
        "MEDUSA_BACKEND_URL",
        "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
    )
    if dry_run:
        log.info("[DRY] would get_or_create_sales_channel name='Design Park' on %s", backend)
        return None

    mi = MedusaImporter(base_url=backend)
    if not mi.api_key:
        log.error(
            "no Medusa auth: set LEKA_MEDUSA_ADMIN_EMAIL + LEKA_MEDUSA_ADMIN_PASSWORD "
            "(or MEDUSA_ADMIN_API_KEY) and retry"
        )
        return None
    sc_id = mi.get_or_create_sales_channel(
        name="Design Park",
        description="DesignPark — Korean playground, water play, outdoor fitness, themed installations.",
    )
    log.info("Medusa Sales Channel id: %s", sc_id)
    return sc_id


def bootstrap_root_doc(dry_run: bool, sc_id: str | None) -> None:
    """Merge-write vendors/designpark root doc in Firestore DB `vendors`."""
    doc = dict(ROOT_DOC)
    if sc_id:
        doc["sales_channel_id"] = sc_id

    if dry_run:
        log.info("[DRY] would merge-write vendors/%s in db=%s with keys=%s",
                 SLUG, VENDORS_DB, sorted(doc.keys()))
        for k, v in doc.items():
            log.info("    %s = %r", k, v)
        return

    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    db.collection("vendors").document(SLUG).set(doc, merge=True)
    log.info("wrote vendors/%s (merge=True) in db=%s", SLUG, VENDORS_DB)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--skip-sc", action="store_true", help="skip Medusa Sales Channel step")
    ap.add_argument("--skip-root", action="store_true", help="skip Firestore root doc step")
    args = ap.parse_args()

    dry = args.dry_run
    sc_id: str | None = None
    if not args.skip_sc:
        sc_id = bootstrap_sales_channel(dry)
    if not args.skip_root:
        bootstrap_root_doc(dry, sc_id)

    if sc_id and not dry:
        print(f"\n>>> Add this line to scripts/sync_vendors_to_medusa.py BRAND_SALES_CHANNELS:")
        print(f'    "designpark": "{sc_id}",')
    return 0


if __name__ == "__main__":
    sys.exit(main())
