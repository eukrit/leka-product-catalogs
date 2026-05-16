"""One-shot helper: flip Medusa product `status` to `published` for any
`vendors/designpark/products/<h>` doc that has `status="active"` in Firestore
but is still `draft` on the Medusa side.

The main `sync_vendors_to_medusa.py` intentionally omits `status` from the
update payload to preserve manual Medusa Admin curation across other brands.
This helper lets DesignPark (and only DesignPark) reconcile its drafts in a
single pass — re-runnable any time the asset matcher promotes more products.

Idempotent: products already `published` are skipped; products that are
`draft` in Firestore are skipped.

Auth: same as sync_vendors_to_medusa.py (LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD).

Usage:
    py scripts/promote_designpark_published.py --dry-run
    py scripts/promote_designpark_published.py --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_LOCAL_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for cand in _LOCAL_SA_CANDIDATES:
        if os.path.exists(cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests  # noqa: E402
from google.cloud import firestore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("promote_designpark_published")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "designpark"
SC_ID = "sc_01KRRK0N4ET8QZHX6QB3KZ84YD"
BACKEND = os.environ.get(
    "MEDUSA_BACKEND_URL",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)


def login() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL") or os.environ.get("MEDUSA_ADMIN_EMAIL")
    password = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD") or os.environ.get("MEDUSA_ADMIN_PASSWORD")
    if not email or not password:
        raise SystemExit("missing LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD")
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        raise SystemExit(f"login returned no token: {r.json()}")
    return tok


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run

    fs = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = fs.collection("vendors").document(SLUG).collection("products")
    active = {snap.id for snap in coll.stream()
              if (snap.to_dict() or {}).get("status") == "active"}
    log.info("active in Firestore: %d", len(active))

    token = login()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Fetch all designpark Medusa products.
    offset, all_prods = 0, []
    while True:
        r = requests.get(
            f"{BACKEND}/admin/products",
            params={"sales_channel_id[]": SC_ID, "limit": 100, "offset": offset,
                    "fields": "id,handle,status"},
            headers=headers, timeout=30,
        )
        r.raise_for_status()
        j = r.json()
        all_prods.extend(j.get("products") or [])
        if offset + 100 >= j.get("count", 0):
            break
        offset += 100
    log.info("medusa products: %d", len(all_prods))

    promoted = skipped = errors = 0
    for p in all_prods:
        if p["handle"] not in active:
            continue
        if p["status"] == "published":
            skipped += 1
            continue
        if dry:
            log.info("[DRY] would promote %s", p["handle"])
            promoted += 1
            continue
        r = requests.post(f"{BACKEND}/admin/products/{p['id']}",
                          json={"status": "published"}, headers=headers, timeout=30)
        if r.status_code >= 400:
            log.warning("fail %s: %s %s", p["handle"], r.status_code, r.text[:150])
            errors += 1
        else:
            promoted += 1
        time.sleep(0.05)
        if promoted % 25 == 0 and promoted:
            log.info("progress: promoted %d", promoted)
    log.info("done: promoted=%d already_published=%d errors=%d", promoted, skipped, errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
