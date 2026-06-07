"""Rampline hero-product spec enrichment → Medusa (storefront-perfect specs).

Targeted, hand-curated enrichment for the four Rampline products featured on the
Leka Studio "Active Challenge Balancing Area" education page
(next.leka.studio/education-solutions/active-challenge-balancing):

  - rampline-rampball              (Rampball balance balls — 4 sizes)
  - rampline-jumpstone-en          (Jumpstone jump pads — 2 sizes)
  - rampline-rampline-slackline    (Rampline Slackline — Single/Double/Triple)
  - rampline-trampoline-loop-en    (Playground Loop in-ground trampoline)

Why this exists (and why not enrich_specifications.py): the catalog PDP
(leka-website `catalogs/src/app/[brand]/[handle]/product-detail.tsx`) renders
specs from `metadata.specifications.*` + flat `*_cm` + a NEW `metadata.spec_table`
table. The previous crawl-based enrich_specifications.py wrote to
`metadata.installed_dimensions` (which the PDP never reads) and the crawl carried
no numeric dimensions for these four, so every structured spec field stayed 0 and
the Specifications panel rendered nearly empty. This script writes the exact,
vendor-sourced (rampline.com) values to the keys the PDP actually consumes:

  - metadata.specifications  : { subcategory, indoor_outdoor, free_fall_height_cm }
  - metadata.fall_height_cm  : flat fall height (single-size products only)
  - metadata.spec_table      : { title, note?, columns[], rows[][] } per-model table

EN standards are intentionally NOT duplicated into metadata.specifications.en_standard
— they already render from metadata.certifications in the PDP Certifications block.

Medusa v2 `POST /admin/products/{id}` shallow-merges the top-level metadata keys
supplied here into the existing object; untouched keys (materials, downloads,
certifications, brand_country, vendor_data, …) are preserved. Idempotent: writes
only when a target key differs from the live value.

Usage:
    # creds from Secret Manager (project ai-agents-go):
    export LEKA_MEDUSA_ADMIN_EMAIL=$(gcloud secrets versions access latest --secret=medusa-admin-email --project ai-agents-go)
    export LEKA_MEDUSA_ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=medusa-admin-password --project ai-agents-go)
    python rampline-catalog/enrich_hero_specs.py --dry-run
    python rampline-catalog/enrich_hero_specs.py --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
TIMEOUT = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_hero_specs")


# ---------------------------------------------------------------------------
# Target metadata — exact values from rampline.com (verified 2026-06-06).
# Keys map 1:1 onto what product-detail.tsx reads.
# ---------------------------------------------------------------------------
TARGETS: dict[str, dict] = {
    "rampline-rampball": {
        "specifications": {
            "subcategory": "Balance ball",
            "indoor_outdoor": "Outdoor",
        },
        "spec_table": {
            "title": "Models & dimensions",
            "note": "Safety area: 150 cm radius around the equipment (may overlap with adjacent equipment per EN 1176-1). Spring protected by a rubber flange against pinching.",
            "columns": ["Model", "Diameter", "Height", "Weight", "Movement", "Fall height"],
            "rows": [
                ["Rampball 35", "Ø35 cm", "36 cm", "27 kg", "Tilts 5 cm all directions", "36 cm"],
                ["Rampball 50", "Ø50 cm", "51 cm", "66 kg", "Tilts 10 cm all directions", "51 cm"],
                ["Rampball 50R", "Ø50 cm", "51 cm", "75 kg", "Tilts 10 cm + rotates", "51 cm"],
                ["Rampball 70R", "Ø70 cm", "70 cm", "201 kg", "Tilts 15 cm + rotates", "70 cm"],
            ],
        },
    },
    "rampline-jumpstone-en": {
        "specifications": {
            "subcategory": "Jump pad",
            "indoor_outdoor": "Outdoor",
            "free_fall_height_cm": 18,
        },
        "fall_height_cm": 18,
        "spec_table": {
            "title": "Models & dimensions",
            "note": "Safety area: 150 cm radius (may overlap with adjacent equipment per EN 1176-1).",
            "columns": ["Model", "Diameter", "Height", "Weight"],
            "rows": [
                ["Jumpstone 27", "Ø27 cm", "18 cm", "8 kg"],
                ["Jumpstone 50", "Ø50 cm", "18 cm", "20 kg"],
            ],
        },
    },
    "rampline-rampline-slackline": {
        "specifications": {
            "subcategory": "Slackline",
            "indoor_outdoor": "Outdoor",
            "free_fall_height_cm": 100,
        },
        "fall_height_cm": 100,
        "spec_table": {
            "title": "Dimensions",
            "note": "Available as Single, Double Trouble and Triple Slack Fun layouts. Safety area 150 cm radius; shock-absorbing surfacing required for the 100 cm fall height.",
            "columns": ["Spec", "Value"],
            "rows": [
                ["Installed height", "45 cm"],
                ["Total length (Single)", "530 cm"],
                ["Slackline length", "410 cm"],
                ["Webbing width", "40 mm (SlackShield™)"],
                ["Fall height", "100 cm"],
            ],
        },
    },
    "rampline-trampoline-loop-en": {
        "specifications": {
            "subcategory": "In-ground trampoline",
            "indoor_outdoor": "Outdoor",
            "free_fall_height_cm": 100,
        },
        "fall_height_cm": 100,
        "spec_table": {
            "title": "Dimensions",
            "note": "Recommended safety area 200 cm from the jump area, with shock-absorbing surfacing within 150 cm. Optional integrated LED (24 V, 40 W, IP67). Delivered with PlayPro™ rim protection.",
            "columns": ["Spec", "Value"],
            "rows": [
                ["Jump area diameter", "Ø98 cm"],
                ["Steel frame", "150 × 150 × 30 cm"],
                ["Weight", "160 kg"],
                ["Fall height", "100 cm"],
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# Medusa REST client (pattern from enrich_specifications.py)
# ---------------------------------------------------------------------------
class Medusa:
    def __init__(self):
        email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
        pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
        if not (email and pw):
            raise RuntimeError("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD")
        r = requests.post(f"{BACKEND}/auth/user/emailpass",
                          json={"email": email, "password": pw}, timeout=TIMEOUT)
        r.raise_for_status()
        self.token = r.json()["token"]
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.token}",
                                "Content-Type": "application/json"})

    def get(self, path, **params):
        r = self.s.get(f"{BACKEND}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status(); return r.json()

    def post(self, path, body):
        r = self.s.post(f"{BACKEND}{path}", json=body, timeout=TIMEOUT)
        if not r.ok:
            log.error("POST %s failed (%d): %s", path, r.status_code, r.text[:600])
            r.raise_for_status()
        return r.json()


def index_rampline(med: Medusa) -> dict[str, dict]:
    """handle -> {id, metadata} for every product in the Rampline sales channel."""
    out: dict[str, dict] = {}
    off = 0
    while True:
        page = med.get(
            "/admin/products",
            **{"sales_channel_id[]": RAMPLINE_SALES_CHANNEL_ID, "limit": 100, "offset": off,
               "status[]": ["published", "draft"]},
            fields="id,handle,metadata",
        )
        batch = page.get("products") or []
        for p in batch:
            out[p["handle"]] = {"id": p["id"], "metadata": p.get("metadata") or {}}
        if len(batch) < 100:
            break
        off += 100
    return out


def merged_metadata(existing: dict, target: dict) -> tuple[dict, list[str]]:
    """Return (payload, changed_keys). payload = only the top-level keys we set."""
    payload: dict = {}
    changed: list[str] = []
    for k, v in target.items():
        if k == "specifications":
            cur = existing.get("specifications") or {}
            if not isinstance(cur, dict):
                cur = {}
            merged = {**cur, **v}
            if merged != cur:
                changed.append("specifications")
            payload["specifications"] = merged
        else:
            if existing.get(k) != v:
                changed.append(k)
            payload[k] = v
    return payload, changed


def plan(med: Medusa) -> list[dict]:
    idx = index_rampline(med)
    actions: list[dict] = []
    for handle, target in TARGETS.items():
        if handle not in idx:
            actions.append({"op": "MISSING", "handle": handle})
            log.error("  product not found in Rampline SC: %s", handle)
            continue
        existing = idx[handle]["metadata"]
        payload, changed = merged_metadata(existing, target)
        if not changed:
            actions.append({"op": "UPTODATE", "handle": handle})
        else:
            actions.append({
                "op": "ENRICH",
                "handle": handle,
                "product_id": idx[handle]["id"],
                "changed_keys": changed,
                "_payload": payload,
            })
    return actions


def execute(med: Medusa, actions: list[dict], dry_run: bool) -> dict:
    counts: dict[str, int] = {}
    errors: list[dict] = []
    for a in actions:
        counts[a["op"]] = counts.get(a["op"], 0) + 1
        if a["op"] != "ENRICH" or dry_run:
            continue
        try:
            med.post(f"/admin/products/{a['product_id']}", {"metadata": a["_payload"]})
            log.info("  OK %s  set=%s", a["handle"], ",".join(a["changed_keys"]))
        except Exception as e:  # noqa: BLE001
            errors.append({"handle": a["handle"], "error": str(e)})
            log.error("  FAIL %s: %s", a["handle"], e)
    return {"counts": counts, "errors": errors}


def write_run_log(actions, result, dry_run) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = RUN_LOG_DIR / f"hero_specs_{'dryrun' if dry_run else 'applied'}_{stamp}.json"
    serial = [{k: v for k, v in a.items() if not k.startswith("_")} for a in actions]
    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": dry_run,
        "totals": result.get("counts", {}),
        "errors": result.get("errors", []),
        "actions": serial,
    }, indent=2), encoding="utf-8")
    log.info("Run log: %s", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("Specify --dry-run or --apply")

    med = Medusa()
    log.info("Authenticated. Planning %d hero products ...", len(TARGETS))
    actions = plan(med)
    summary: dict[str, int] = {}
    for a in actions:
        summary[a["op"]] = summary.get(a["op"], 0) + 1
    log.info("Planned: %s", summary)
    for a in actions:
        if a["op"] == "ENRICH":
            log.info("  ENRICH %s  keys=%s", a["handle"], a["changed_keys"])

    if args.dry_run:
        write_run_log(actions, {"counts": summary, "errors": []}, dry_run=True)
        log.info("DRY RUN - no Medusa writes")
        return

    result = execute(med, actions, dry_run=False)
    log.info("Result: %s", result["counts"])
    write_run_log(actions, result, dry_run=False)


if __name__ == "__main__":
    main()
