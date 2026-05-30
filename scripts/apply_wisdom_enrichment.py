"""Push Wisdom AI enrichment records (Firestore `wisdom_enrichment`) to live Medusa.

For each cached enrichment, POST `/admin/products/{id}`:
  - `description` (when current desc == title, i.e. has not been hand-edited)
  - `metadata.materials` (array, what the PDP reads)
  - `metadata.material` (singular, deprecated — kept for legacy callers)
  - `metadata.specifications` map: age_group, num_users, indoor_outdoor, subcategory
  - `metadata.category_inferred` (e.g. "toys" — used by the Toys category linker)
  - `metadata.enrichment_source = "ai_inferred"`
  - `metadata.enrichment_confidence` (float)

Idempotent: previous applies record `metadata.enrichment_applied_at` (UTC ISO8601);
re-runs skip unless --force or the enrichment doc's `decided_at` is newer than
`enrichment_applied_at`.

Usage
-----
    python scripts/apply_wisdom_enrichment.py --dry-run --limit 20
    python scripts/apply_wisdom_enrichment.py --limit 50
    python scripts/apply_wisdom_enrichment.py                  # full pass
    python scripts/apply_wisdom_enrichment.py --force          # rewrite all
    python scripts/apply_wisdom_enrichment.py --min-confidence 0.7
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests  # noqa: E402
from google.cloud import firestore, secretmanager  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("apply_wisdom_enrichment")

PROJECT = "ai-agents-go"
FIRESTORE_DB = "leka-product-catalogs"
ENRICHMENT_COLLECTION = "wisdom_enrichment"

MEDUSA_BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
TIMEOUT = 60


def _sm_secret(name: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{PROJECT}/secrets/{name}/versions/latest"
    return client.access_secret_version(name=path).payload.data.decode().strip()


def _medusa_admin_token() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL") or _sm_secret("medusa-admin-email")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD") or _sm_secret("medusa-admin-password")
    r = requests.post(
        f"{MEDUSA_BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        log.error("admin auth returned no token: %s", r.text[:200])
        sys.exit(2)
    log.info("Medusa admin auth OK (%s)", email)
    return tok


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _retry(method: str, url: str, tok: str, *, json_body=None, max_attempts: int = 5):
    delays = [2, 5, 15, 45]
    last: Exception | None = None
    for attempt in range(max_attempts):
        try:
            r = requests.request(method, url, headers=_hdr(tok),
                                  json=json_body, timeout=TIMEOUT)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
            return r
        except (requests.RequestException, requests.HTTPError) as e:
            last = e
            if attempt == len(delays):
                break
            time.sleep(delays[attempt] + random.random() * 2)
    raise last if last else RuntimeError("retry exhausted")


def fetch_product_meta(tok: str, product_id: str) -> dict:
    r = _retry("GET", f"{MEDUSA_BACKEND}/admin/products/{product_id}", tok)
    r.raise_for_status()
    return r.json().get("product", {})


def build_payload(rec: dict, current_meta: dict, current_desc: str | None,
                  current_title: str | None) -> dict:
    """Compose the PATCH body, preserving any human-edited fields."""
    age_min = rec.get("age_min_years")
    age_max = rec.get("age_max_years")
    age_group = None
    if age_min is not None and age_max is not None:
        age_group = f"{age_min}-{age_max} yrs"
    num_min = rec.get("num_users_min")
    num_max = rec.get("num_users_max")
    num_users = None
    if num_min is not None and num_max is not None:
        num_users = f"{num_min}-{num_max}" if num_min != num_max else f"{num_min}"

    materials = [str(m).strip().lower() for m in (rec.get("materials") or []) if m]

    # Merge specifications into any existing map; do not clobber human-set keys.
    existing_specs = current_meta.get("specifications") or {}
    if not isinstance(existing_specs, dict):
        existing_specs = {}
    new_specs = dict(existing_specs)
    if age_group and not new_specs.get("age_group"):
        new_specs["age_group"] = age_group
    if num_users and not new_specs.get("num_users"):
        new_specs["num_users"] = num_users
    io = rec.get("indoor_outdoor")
    if io and io != "unknown" and not new_specs.get("indoor_outdoor"):
        new_specs["indoor_outdoor"] = io
    if rec.get("subcategory") and not new_specs.get("subcategory"):
        new_specs["subcategory"] = rec["subcategory"]
    new_specs["source"] = "ai_inferred"

    new_meta = {
        "materials": materials,
        "material": materials[0] if materials else None,
        "specifications": new_specs,
        "category_inferred": rec.get("category"),
        "enrichment_source": "ai_inferred",
        "enrichment_confidence": float(rec.get("confidence") or 0.0),
        "enrichment_applied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Keep existing keys we don't touch:
    for k, v in current_meta.items():
        if k not in new_meta:
            new_meta[k] = v
    # Make sure materials value isn't None
    if new_meta.get("material") is None:
        new_meta.pop("material", None)

    payload: dict = {"metadata": new_meta}

    new_desc = rec.get("description") or ""
    # Only overwrite description if current desc is empty OR equals the title
    # (i.e. nobody has hand-edited it). Spaces/case normalised.
    cur = (current_desc or "").strip().lower()
    title = (current_title or "").strip().lower()
    if new_desc and (cur == "" or cur == title):
        payload["description"] = new_desc

    return payload


def cmd_apply(args) -> None:
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    tok = None if args.dry_run else _medusa_admin_token()

    log.info("Loading enrichment records from Firestore...")
    recs: list[dict] = []
    for d in fs_client.collection(ENRICHMENT_COLLECTION).stream():
        doc = d.to_dict() or {}
        if doc.get("status") != "ok":
            continue
        if (doc.get("confidence") or 0.0) < args.min_confidence:
            continue
        recs.append(doc)
    log.info("  %d enrichment records meet --min-confidence=%.2f",
             len(recs), args.min_confidence)

    if args.limit:
        recs = recs[: args.limit]
        log.info("--limit applied: applying %d", len(recs))

    counts = {"applied": 0, "skipped": 0, "errors": 0, "dry": 0}
    started = time.time()

    for i, rec in enumerate(recs, 1):
        pid = rec.get("product_id")
        if not pid:
            counts["errors"] += 1
            continue
        try:
            current = fetch_product_meta(tok, pid) if tok else {}
        except Exception as e:
            log.error("  fetch %s failed: %s", pid, str(e)[:200])
            counts["errors"] += 1
            continue
        cur_meta = current.get("metadata") or {}
        if not args.force and cur_meta.get("enrichment_applied_at"):
            counts["skipped"] += 1
            continue
        payload = build_payload(rec, cur_meta, current.get("description"),
                                 current.get("title") or rec.get("title"))
        if args.dry_run:
            counts["dry"] += 1
            if i <= 3:
                log.info("  [dry] %s -> %s",
                         rec.get("sku"),
                         json.dumps(payload, default=str)[:300])
            continue
        try:
            r = _retry("POST", f"{MEDUSA_BACKEND}/admin/products/{pid}", tok,
                       json_body=payload)
            r.raise_for_status()
            counts["applied"] += 1
        except Exception as e:
            log.error("  update %s failed: %s", pid, str(e)[:200])
            counts["errors"] += 1
        if i % 50 == 0 or i == len(recs):
            rate = i / max(time.time() - started, 0.001)
            log.info("  %d/%d (%.1f/s) %s", i, len(recs), rate, counts)

    log.info("Apply done in %.1fs: %s", time.time() - started, counts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-apply even when enrichment_applied_at is set")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-confidence", type=float, default=0.5,
                    help="skip enrichments below this confidence")
    args = ap.parse_args()
    cmd_apply(args)


if __name__ == "__main__":
    main()
