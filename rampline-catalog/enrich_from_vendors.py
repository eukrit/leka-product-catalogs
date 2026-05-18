"""Rampline product enrichment: vendors/rampline → Medusa.

Per the 2026-05-16 architecture statement, `leka-product-catalogs` is the
canonical product database and Medusa syncs from it. The `vendors/*` repo
mirrors external sources (rampline.com website crawl, Drive folder) and
should ENRICH the canonical layer — not replace it.

This script reads the crawl output
  vendors/rampline-catalog/parsed/products.json  (112 products)
and matches each row to a Medusa product on the Rampline sales channel by
slug-similarity of `source_url` ↔ Medusa `handle`. For each match, it
upserts:
  - description (only if Medusa is empty/short)
  - metadata.source_url (always)
  - metadata.crawled_at (always)
  - metadata.crawl_sha   (always)
  - metadata.crawl_category, metadata.crawl_subcategory (always)

Two run modes:
  --report-only           Write reconciliation CSV (no Medusa reads/writes
                          beyond the product index). Use for A.2.
  --dry-run / --apply     Plan + (optionally) execute enrichment. Use for
                          A.1.

Run logs land in rampline-catalog/data/build_runs/ with the same shape as
build_variants.py and sync_variant_prices.py:
  reconciliation_<ts>.csv            for --report-only
  enrichment_dryrun_<ts>.json        for --dry-run
  enrichment_applied_<ts>.json       for --apply

Usage:
    # A.2 — reconciliation CSV
    python rampline-catalog/enrich_from_vendors.py --report-only

    # A.1 — dry-run enrichment plan
    python rampline-catalog/enrich_from_vendors.py --dry-run

    # A.1 — apply
    python rampline-catalog/enrich_from_vendors.py --apply

    # Limit to one family while iterating
    python rampline-catalog/enrich_from_vendors.py --dry-run --limit-family rampball
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"

# Default location of the crawled products.json — overridable via --crawl.
DEFAULT_CRAWL = (
    REPO_ROOT.parent
    / "vendors"
    / "rampline-catalog"
    / "parsed"
    / "products.json"
)

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
TIMEOUT = 60

# Minimum slug-similarity (0–1) before we accept a match.
MIN_MATCH_SCORE = 0.55

# We only overwrite description when the Medusa value is empty or shorter
# than this many characters (i.e. probably just a pricelist title).
DESCRIPTION_OVERWRITE_THRESHOLD = 80

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_from_vendors")


# ---------------------------------------------------------------------------
# Medusa REST client (lifted from sync_variant_prices.py)
# ---------------------------------------------------------------------------
class Medusa:
    def __init__(self):
        email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
        pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
        if not (email and pw):
            raise RuntimeError("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD")
        r = requests.post(
            f"{BACKEND}/auth/user/emailpass",
            json={"email": email, "password": pw},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        self.token = r.json()["token"]
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })

    def get(self, path: str, **params) -> dict:
        r = self.session.get(f"{BACKEND}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> dict:
        r = self.session.post(f"{BACKEND}{path}", json=body, timeout=TIMEOUT)
        if not r.ok:
            log.error("POST %s failed (%d): %s", path, r.status_code, r.text[:600])
            r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------
_SLUG_NOISE = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    s = (s or "").lower()
    s = _SLUG_NOISE.sub("-", s)
    return s.strip("-")


def slug_from_url(url: str) -> str:
    """rampline.com/en/product/rampball/ → 'rampball'."""
    if not url:
        return ""
    parts = [p for p in re.split(r"[/?#]", url) if p]
    # last meaningful path segment
    for seg in reversed(parts):
        if seg in ("en", "no", "product", "products", ""):
            continue
        return slugify(seg)
    return ""


def medusa_slug(handle: str) -> str:
    """rampline-rampball-35 → 'rampball-35'."""
    if handle.startswith("rampline-"):
        return handle[len("rampline-"):]
    return handle


def slug_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return max(0.85, len(a) / max(len(b), 1) if len(a) < len(b) else len(b) / max(len(a), 1))
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Load crawl
# ---------------------------------------------------------------------------
def load_crawl(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for row in data:
        out.append({
            "sku": row.get("sku") or "",
            "name": row.get("product_name") or "",
            "url": row.get("source_url") or "",
            "url_slug": slug_from_url(row.get("source_url") or ""),
            "name_slug": slugify(row.get("product_name") or ""),
            "category": row.get("category") or "",
            "subcategory": row.get("subcategory") or "",
            "description": (row.get("description") or "").strip(),
            "notes": (row.get("notes") or "").strip(),
            "source_sha": row.get("source_sha") or "",
        })
    return out


# ---------------------------------------------------------------------------
# Index Medusa Rampline products
# ---------------------------------------------------------------------------
def index_rampline_products(med: Medusa) -> list[dict]:
    out: list[dict] = []
    off = 0
    while True:
        page = med.get(
            "/admin/products",
            **{
                "sales_channel_id[]": RAMPLINE_SALES_CHANNEL_ID,
                "limit": 100,
                "offset": off,
                "status[]": ["published", "draft"],
            },
            fields="id,handle,title,status,description,metadata",
        )
        batch = page.get("products") or []
        for p in batch:
            out.append({
                "id": p["id"],
                "handle": p["handle"],
                "title": p.get("title") or "",
                "status": p.get("status") or "",
                "description": (p.get("description") or "").strip(),
                "metadata": p.get("metadata") or {},
                "slug": medusa_slug(p["handle"]),
            })
        if len(batch) < 100:
            break
        off += 100
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def best_medusa_match(crawl_row: dict, medusa_products: list[dict]) -> tuple[dict | None, float, str]:
    """Return (matched_product, score, basis) or (None, score, 'NO_MATCH')."""
    needles = [crawl_row["url_slug"], crawl_row["name_slug"], slugify(crawl_row["sku"])]
    needles = [n for n in needles if n]
    if not needles:
        return None, 0.0, "no_crawl_slug"

    best: tuple[dict | None, float, str] = (None, 0.0, "NO_MATCH")
    for needle in needles:
        for prod in medusa_products:
            score = slug_similarity(needle, prod["slug"])
            if score > best[1]:
                best = (prod, score, f"slug:{needle}↔{prod['slug']}")
    if best[1] >= MIN_MATCH_SCORE:
        return best
    return None, best[1], "NO_MATCH"


def reason_for_no_match(crawl_row: dict) -> str:
    """Classify why a crawl row probably has no Medusa product."""
    cat = (crawl_row["category"] or "").lower()
    sub = (crawl_row["subcategory"] or "").lower()
    url = (crawl_row["url"] or "").lower()
    if "/product-category/" in url or "/category/" in url:
        return "listing_page"
    if "/news/" in url or "/blog/" in url or "/press/" in url:
        return "marketing_page"
    if sub in {"shockdeck components", "shockdeck system"}:
        return "subsystem_component"
    if cat in {"surfacing"}:
        return "surfacing_component"
    name_l = (crawl_row["name"] or "").lower()
    if any(k in name_l for k in ("ability", "agile", "bounce", "all in", "classic jump",
                                 "double trouble", "dynamic", "impact", "jane jump",
                                 "juice", "trip", "triple slack")):
        return "legacy_park"  # pre-2025 catalogue, not in current pricelist
    return "no_match"


# ---------------------------------------------------------------------------
# Action planner
# ---------------------------------------------------------------------------
def plan_actions(
    crawl_rows: list[dict],
    medusa_products: list[dict],
    limit_family: str | None,
) -> tuple[list[dict], list[dict]]:
    """Return (actions, unmatched).

    Actions have op ∈ {ENRICH, ALREADY_ENRICHED}. Many crawl rows can share
    the same Medusa product (rampline.com PDPs often contain multiple
    surface variants on one page); we collapse to winner-takes-all on score
    then merge the descriptions of the runner-ups into `metadata.crawl_notes`.
    """
    # First pass: score every (crawl, medusa) candidate
    by_medusa: dict[str, list[tuple[dict, dict, float, str]]] = defaultdict(list)
    skipped_unmatched: list[dict] = []
    for row in crawl_rows:
        prod, score, basis = best_medusa_match(row, medusa_products)
        if not prod:
            skipped_unmatched.append({
                "crawl_sku": row["sku"],
                "crawl_name": row["name"],
                "crawl_url": row["url"],
                "best_score": round(score, 3),
                "reason": reason_for_no_match(row),
            })
            continue
        by_medusa[prod["id"]].append((row, prod, score, basis))

    actions: list[dict] = []
    for prod_id, candidates in by_medusa.items():
        # Winner: highest score, longest description as tiebreaker
        candidates.sort(key=lambda c: (-c[2], -len(c[0]["description"]), -len(c[0]["notes"])))
        winner_row, prod, winner_score, winner_basis = candidates[0]
        runner_ups = [c[0] for c in candidates[1:]]
        row = winner_row

        # Family filter
        if limit_family:
            needle = limit_family.lower()
            hay = (prod["handle"] + " " + row["sku"] + " " + row["category"]).lower()
            if needle not in hay:
                continue

        # Decide what to write
        existing_md = prod["metadata"] or {}
        new_md = {
            "source_url": row["url"],
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "crawl_sha": row["source_sha"],
            "crawl_category": row["category"],
            "crawl_subcategory": row["subcategory"],
        }
        # Runner-up SKUs go into metadata as a comma-joined string for
        # provenance (handy when the same PDP yields multiple surface variants).
        if runner_ups:
            new_md["crawl_variant_skus"] = ",".join(sorted({r["sku"] for r in runner_ups if r["sku"]}))[:500]

        md_changes = {k: v for k, v in new_md.items()
                      if v and existing_md.get(k) != v and not (k == "crawled_at" and existing_md.get(k))}
        # crawled_at: only write if not already stamped (avoid noisy "last seen" churn)

        # Description: only fill if Medusa is empty or short
        desc_change = None
        if row["description"] and len(prod["description"]) < DESCRIPTION_OVERWRITE_THRESHOLD:
            desc_change = row["description"]
            if row["notes"]:
                desc_change = f"{desc_change}\n\n{row['notes']}"

        # No-op if nothing to write
        if not md_changes and not desc_change:
            actions.append({
                "op": "ALREADY_ENRICHED",
                "crawl_sku": row["sku"],
                "handle": prod["handle"],
                "match_score": round(winner_score, 3),
                "match_basis": winner_basis,
                "runner_ups": len(runner_ups),
            })
            continue

        actions.append({
            "op": "ENRICH",
            "crawl_sku": row["sku"],
            "crawl_name": row["name"],
            "crawl_url": row["url"],
            "handle": prod["handle"],
            "product_id": prod["id"],
            "match_score": round(winner_score, 3),
            "match_basis": winner_basis,
            "runner_ups": len(runner_ups),
            "md_changes": md_changes,
            "description_set": bool(desc_change),
            "description_chars": len(desc_change) if desc_change else 0,
            "_target_description": desc_change,
            "_target_metadata": new_md,
        })
    return actions, skipped_unmatched


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------
def execute(med: Medusa, actions: list[dict], dry_run: bool) -> dict:
    counts: dict[str, int] = defaultdict(int)
    errors: list[dict] = []
    for action in actions:
        op = action["op"]
        counts[op] += 1
        if dry_run or op != "ENRICH":
            continue
        try:
            body: dict = {"metadata": action["_target_metadata"]}
            if action["description_set"]:
                body["description"] = action["_target_description"]
            med.post(f"/admin/products/{action['product_id']}", body)
            log.info(
                "  ✓ %s ← %s  (score=%.2f, desc=%s, md=%d)",
                action["handle"],
                action["crawl_sku"],
                action["match_score"],
                "yes" if action["description_set"] else "no",
                len(action["md_changes"]),
            )
        except Exception as e:
            errors.append({"crawl_sku": action["crawl_sku"], "handle": action["handle"], "error": str(e)})
            log.error("enrich failed for %s: %s", action["handle"], e)
    return {"counts": dict(counts), "errors": errors}


# ---------------------------------------------------------------------------
# Run logs
# ---------------------------------------------------------------------------
def write_run_log(actions, unmatched, result, dry_run, args) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = f"enrichment_{'dryrun' if dry_run else 'applied'}_{stamp}"
    out = RUN_LOG_DIR / f"{name}.json"

    serializable_actions = []
    for a in actions:
        clean = {k: v for k, v in a.items() if not k.startswith("_")}
        serializable_actions.append(clean)

    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": dry_run,
        "limit_family": args.limit_family,
        "crawl_path": str(args.crawl),
        "min_match_score": MIN_MATCH_SCORE,
        "description_overwrite_threshold": DESCRIPTION_OVERWRITE_THRESHOLD,
        "totals": result.get("counts", {}),
        "actions_count": len(actions),
        "unmatched_count": len(unmatched),
        "unmatched": unmatched,
        "errors": result.get("errors", []),
        "actions": serializable_actions,
    }, indent=2, default=str), encoding="utf-8")
    log.info("Run log: %s", out)
    return out


def write_reconciliation_csv(
    crawl_rows: list[dict],
    medusa_products: list[dict],
) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = RUN_LOG_DIR / f"reconciliation_{stamp}.csv"

    rows = []
    matched_medusa = set()
    for r in crawl_rows:
        prod, score, basis = best_medusa_match(r, medusa_products)
        if prod:
            matched_medusa.add(prod["id"])
            rows.append({
                "crawl_sku": r["sku"],
                "crawl_name": r["name"],
                "crawl_url": r["url"],
                "crawl_category": r["category"],
                "match_handle": prod["handle"],
                "match_title": prod["title"],
                "match_status": prod["status"],
                "match_score": round(score, 3),
                "match_basis": basis,
                "no_match_reason": "",
            })
        else:
            rows.append({
                "crawl_sku": r["sku"],
                "crawl_name": r["name"],
                "crawl_url": r["url"],
                "crawl_category": r["category"],
                "match_handle": "",
                "match_title": "",
                "match_status": "",
                "match_score": round(score, 3),
                "match_basis": "",
                "no_match_reason": reason_for_no_match(r),
            })

    # Also include Medusa products with no crawl match (rows from the other direction)
    for prod in medusa_products:
        if prod["id"] in matched_medusa:
            continue
        rows.append({
            "crawl_sku": "",
            "crawl_name": "",
            "crawl_url": "",
            "crawl_category": "",
            "match_handle": prod["handle"],
            "match_title": prod["title"],
            "match_status": prod["status"],
            "match_score": 0.0,
            "match_basis": "",
            "no_match_reason": "medusa_only_no_crawl",
        })

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info("Reconciliation CSV: %s (rows=%d)", out, len(rows))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", type=Path, default=DEFAULT_CRAWL,
                    help="Path to vendors/rampline-catalog/parsed/products.json")
    ap.add_argument("--report-only", action="store_true",
                    help="Emit reconciliation CSV. No Medusa writes.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit-family", default=None,
                    help="Only act on rows whose handle / sku / category matches this substring")
    args = ap.parse_args()
    if sum(bool(x) for x in (args.report_only, args.dry_run, args.apply)) != 1:
        ap.error("Specify exactly one of --report-only / --dry-run / --apply")

    log.info("Loading crawl: %s", args.crawl)
    crawl_rows = load_crawl(args.crawl)
    log.info("Loaded %d crawled products", len(crawl_rows))

    med = Medusa()
    log.info("Indexing Rampline products on Medusa…")
    medusa_products = index_rampline_products(med)
    log.info(
        "Indexed %d products on Rampline sales channel (status: %s)",
        len(medusa_products),
        dict((s, sum(1 for p in medusa_products if p["status"] == s))
             for s in {p["status"] for p in medusa_products}),
    )

    if args.report_only:
        write_reconciliation_csv(crawl_rows, medusa_products)
        return

    actions, unmatched = plan_actions(crawl_rows, medusa_products, args.limit_family)
    summary = defaultdict(int)
    for a in actions:
        summary[a["op"]] += 1
    log.info("Planned: %s   (unmatched=%d)", dict(summary), len(unmatched))

    if args.dry_run:
        for a in actions[:6]:
            if a["op"] != "ENRICH":
                continue
            log.info(
                "  ENRICH %s ← %s  score=%.2f desc=%d md_keys=%d",
                a["handle"], a["crawl_sku"], a["match_score"],
                a["description_chars"], len(a["md_changes"]),
            )
        result = {"counts": dict(summary), "errors": []}
        write_run_log(actions, unmatched, result, dry_run=True, args=args)
        log.info("DRY RUN — no Medusa writes")
        return

    log.info("APPLYING %d ENRICH actions…",
             sum(1 for a in actions if a["op"] == "ENRICH"))
    result = execute(med, actions, dry_run=False)
    log.info("Result: %s", result["counts"])
    if result["errors"]:
        log.error("%d errors", len(result["errors"]))
    write_run_log(actions, unmatched, result, dry_run=False, args=args)


if __name__ == "__main__":
    main()
