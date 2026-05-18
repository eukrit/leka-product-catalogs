"""Rampline specifications enrichment: crawled specs/downloads → Medusa.

Reads `vendors/rampline-catalog/parsed/products.json` and patches each
matching Medusa product with:

  - metadata.installed_dimensions  (raw / length / width / height / unit)
  - metadata.installed_area_raw    (if dimensions.raw says "Area: NN m²")
  - metadata.certifications        (joined string, e.g. "EN 1176, EN 16630")
  - metadata.downloads_json        (JSON-encoded list of {type,url,filename})
  - metadata.notes                 (free-text "notes" field from the crawl)

These are STOREFRONT-USEFUL specs only. They're NOT shipping/packing
dimensions — Rampline's website only publishes the installed footprint
(diameter, height-as-installed, area). Real CBM for landed cost still
requires supplier-supplied packing lists.

Matching uses the `metadata.source_url` already stamped by
enrich_from_vendors.py (v2.23.0). Products without `source_url` are
skipped — they have no rampline.com counterpart.

Winner-takes-all per Medusa product (multiple crawl rows can share one
product page; the one with the richest specs wins, tiebreak on
description length).

Idempotent: writes only when the merged metadata differs from current.

Usage:
    python rampline-catalog/enrich_specifications.py --dry-run
    python rampline-catalog/enrich_specifications.py --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"
DEFAULT_CRAWL = (
    REPO_ROOT.parent / "vendors" / "rampline-catalog" / "parsed" / "products.json"
)

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
TIMEOUT = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_specifications")


# ---------------------------------------------------------------------------
# Medusa REST client
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


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
def specs_richness(row: dict) -> int:
    """Used for winner-takes-all when multiple crawl rows match one product."""
    s = row.get("specifications") or {}
    d = s.get("dimensions") or {}
    score = 0
    if d.get("raw"): score += 4
    if d.get("length"): score += 1
    if d.get("width"):  score += 1
    if d.get("height"): score += 1
    if s.get("certifications"): score += 2
    if row.get("downloads"):    score += 3
    if row.get("notes"):        score += 1
    if row.get("description"):  score += len(row["description"]) // 200
    return score


def index_products(med: Medusa) -> list[dict]:
    out: list[dict] = []
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
            md = p.get("metadata") or {}
            src = md.get("source_url") or ""
            if not src:
                continue
            out.append({"id": p["id"], "handle": p["handle"], "metadata": md, "source_url": src})
        if len(batch) < 100:
            break
        off += 100
    return out


def build_specs_payload(row: dict) -> dict:
    """Reduce a crawled row into the storefront-useful metadata fields."""
    specs = row.get("specifications") or {}
    dims = specs.get("dimensions") or {}
    out: dict = {}

    # installed dimensions (NOT packing CBM)
    raw_dim = (dims.get("raw") or "").strip()
    if raw_dim or any(dims.get(k) for k in ("length", "width", "height")):
        out["installed_dimensions"] = {
            "raw": raw_dim,
            "length": dims.get("length") or 0,
            "width":  dims.get("width") or 0,
            "height": dims.get("height") or 0,
            "unit":   dims.get("unit") or "",
        }
        # Detect "Area: NN m²" lines and store as area_raw for convenience.
        if "area" in raw_dim.lower() and "m" in raw_dim.lower():
            out["installed_area_raw"] = raw_dim

    certs = specs.get("certifications") or []
    if certs:
        out["certifications"] = ", ".join(str(c) for c in certs if c)

    dls = row.get("downloads") or []
    cleaned_dls = []
    for d in dls:
        if not isinstance(d, dict):
            continue
        item = {
            "type":     str(d.get("type") or ""),
            "url":      str(d.get("url") or ""),
            "filename": str(d.get("filename") or ""),
        }
        if item["url"]:
            cleaned_dls.append(item)
    if cleaned_dls:
        # Store as JSON string — Medusa metadata is shallow object map and
        # nested lists/objects are easier to round-trip as strings.
        out["downloads_json"] = json.dumps(cleaned_dls, ensure_ascii=False)
        out["downloads_count"] = len(cleaned_dls)

    notes = (row.get("notes") or "").strip()
    if notes:
        out["crawl_notes"] = notes[:1000]

    return out


def plan_actions(crawl_rows: list[dict], products: list[dict], limit_family: str | None):
    # Index crawl rows by source_url
    by_url: dict[str, list[dict]] = defaultdict(list)
    for r in crawl_rows:
        u = (r.get("source_url") or "").rstrip("/")
        if u:
            by_url[u].append(r)

    actions: list[dict] = []
    skipped: list[dict] = []
    for p in products:
        src = (p["source_url"] or "").rstrip("/")
        candidates = by_url.get(src) or by_url.get(src + "/") or []
        if not candidates:
            skipped.append({"handle": p["handle"], "reason": "no_crawl_row", "source_url": src})
            continue
        # Winner: richest specs, longest description tiebreak
        candidates.sort(key=lambda r: (-specs_richness(r), -len(r.get("description") or "")))
        winner = candidates[0]

        if limit_family:
            needle = limit_family.lower()
            hay = (p["handle"] + " " + (winner.get("sku") or "")).lower()
            if needle not in hay:
                continue

        target = build_specs_payload(winner)
        if not target:
            actions.append({"op": "NO_SPECS", "handle": p["handle"]})
            continue

        # Compute diff vs existing metadata
        existing = p["metadata"] or {}
        diff_keys = []
        for k, v in target.items():
            if existing.get(k) != v:
                diff_keys.append(k)
        if not diff_keys:
            actions.append({"op": "SPECS_UPTODATE", "handle": p["handle"]})
            continue

        actions.append({
            "op": "ENRICH_SPECS",
            "handle": p["handle"],
            "product_id": p["id"],
            "crawl_sku": winner.get("sku"),
            "diff_keys": diff_keys,
            "_target": target,
            "_sample": {k: target[k] for k in diff_keys[:3]},
        })
    return actions, skipped


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------
def execute(med: Medusa, actions: list[dict], dry_run: bool) -> dict:
    counts: dict[str, int] = defaultdict(int)
    errors: list[dict] = []
    for a in actions:
        op = a["op"]
        counts[op] += 1
        if dry_run or op != "ENRICH_SPECS":
            continue
        try:
            med.post(f"/admin/products/{a['product_id']}", {"metadata": a["_target"]})
            log.info("  ✓ %s  +%d keys (%s)", a["handle"], len(a["diff_keys"]),
                     ",".join(a["diff_keys"]))
        except Exception as e:
            errors.append({"handle": a["handle"], "error": str(e)})
            log.error("enrich-specs failed for %s: %s", a["handle"], e)
    return {"counts": dict(counts), "errors": errors}


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------
def write_run_log(actions, skipped, result, dry_run, args) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = f"specs_{'dryrun' if dry_run else 'applied'}_{stamp}"
    out = RUN_LOG_DIR / f"{name}.json"
    serial = []
    for a in actions:
        serial.append({k: v for k, v in a.items() if not k.startswith("_")})
    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": dry_run,
        "totals": result.get("counts", {}),
        "actions_count": len(actions),
        "skipped_count": len(skipped),
        "errors": result.get("errors", []),
        "skipped": skipped,
        "actions": serial,
    }, indent=2, default=str), encoding="utf-8")
    log.info("Run log: %s", out)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", type=Path, default=DEFAULT_CRAWL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit-family", default=None)
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("Specify --dry-run or --apply")

    log.info("Loading crawl: %s", args.crawl)
    crawl_rows = json.loads(args.crawl.read_text(encoding="utf-8"))
    log.info("Loaded %d crawled rows", len(crawl_rows))

    med = Medusa()
    log.info("Indexing Rampline products with source_url …")
    products = index_products(med)
    log.info("Indexed %d products", len(products))

    actions, skipped = plan_actions(crawl_rows, products, args.limit_family)
    summary = defaultdict(int)
    for a in actions:
        summary[a["op"]] += 1
    log.info("Planned: %s   (skipped=%d)", dict(summary), len(skipped))

    if args.dry_run:
        for a in [x for x in actions if x["op"] == "ENRICH_SPECS"][:6]:
            log.info("  ENRICH_SPECS %s  keys=%s", a["handle"], a["diff_keys"])
        result = {"counts": dict(summary), "errors": []}
        write_run_log(actions, skipped, result, dry_run=True, args=args)
        log.info("DRY RUN — no Medusa writes")
        return

    log.info("APPLYING %d ENRICH_SPECS actions …",
             sum(1 for a in actions if a["op"] == "ENRICH_SPECS"))
    result = execute(med, actions, dry_run=False)
    log.info("Result: %s", result["counts"])
    write_run_log(actions, skipped, result, dry_run=False, args=args)


if __name__ == "__main__":
    main()
