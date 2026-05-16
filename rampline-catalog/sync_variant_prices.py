"""Rampline variant prices → Medusa.

Reads the Firestore audit doc `vendors/rampline/pricelists/<DATE>` (which
already holds the computed retail_thb / retail_usd / retail_eur per article
code) and writes those prices to the matching Medusa variants on the
Rampline sales channel.

Match strategy: pricelist `article_code` (in Firestore) ↔ Medusa variant
`metadata.article_code` (set when we created the variants in v2.22.0).
Falls back to Medusa `variants.sku` if metadata is missing.

Caveats baked into the audit doc:
  * Computed at v2.19.0 formula constants (GROSS_MARGIN=0.40, no separate
    Thai VAT layer). Re-run rampline-catalog/import_pricelist.py against
    the post-v2.20.1 pricing-config to refresh once that cfg is locked.
  * Currencies pushed: THB, USD, EUR. NOK (wholesale net) stays in the
    variant `metadata` only — pushing it as a customer-facing price would
    confuse storefront UX.

Usage:
    python rampline-catalog/sync_variant_prices.py --dry-run
    python rampline-catalog/sync_variant_prices.py --apply
    python rampline-catalog/sync_variant_prices.py --apply --limit-family rampball
    python rampline-catalog/sync_variant_prices.py --apply --pricelist-date 2026-05-13
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
TIMEOUT = 60

# Currencies we push as customer-facing prices. NOK is supplier-currency
# wholesale, kept in metadata only.
PRICE_CURRENCIES = ("thb", "usd", "eur")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("sync_variant_prices")


# ---------------------------------------------------------------------------
# Firestore REST reader (no ADC required; uses LEKA_FIRESTORE_ACCESS_TOKEN
# from env or falls back to google-auth ADC)
# ---------------------------------------------------------------------------
def _firestore_token() -> str:
    tok = os.environ.get("LEKA_FIRESTORE_ACCESS_TOKEN")
    if tok:
        return tok
    import google.auth
    import google.auth.transport.requests as gtr
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    creds.refresh(gtr.Request())
    return creds.token


def _fs_value(v: dict):
    """Decode a Firestore REST value union to a Python scalar."""
    if v is None:
        return None
    if "nullValue" in v:
        return None
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "booleanValue" in v:
        return bool(v["booleanValue"])
    if "mapValue" in v:
        return {k: _fs_value(x) for k, x in (v["mapValue"].get("fields") or {}).items()}
    if "arrayValue" in v:
        return [_fs_value(x) for x in (v["arrayValue"].get("values") or [])]
    return None


def read_audit_doc(pricelist_date: str) -> dict:
    """Returns {variants: {ARTICLE_KEY: {article_code, net_nok, retail_thb, ...}}, audit: {...}}."""
    token = _firestore_token()
    url = (
        f"https://firestore.googleapis.com/v1/projects/ai-agents-go/"
        f"databases/vendors/documents/vendors/rampline/pricelists/{pricelist_date}"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    fields = raw.get("fields", {})
    decoded = {k: _fs_value(v) for k, v in fields.items()}
    variants_map = decoded.pop("variants", {}) or {}
    return {"audit": decoded, "variants_by_key": variants_map}


# ---------------------------------------------------------------------------
# Medusa REST client
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
# Variant index — match by metadata.article_code (preferred) or sku
# ---------------------------------------------------------------------------
def index_rampline_variants(med: Medusa) -> dict[str, dict]:
    """Return {article_code: {product_id, variant_id, sku, current_prices, handle}}."""
    by_code: dict[str, dict] = {}
    off = 0
    while True:
        page = med.get(
            "/admin/products",
            **{"sales_channel_id[]": RAMPLINE_SALES_CHANNEL_ID, "limit": 100, "offset": off},
            fields=(
                "id,handle,variants.id,variants.sku,variants.metadata,"
                "variants.prices.id,variants.prices.currency_code,variants.prices.amount"
            ),
        )
        batch = page.get("products") or []
        for p in batch:
            for v in (p.get("variants") or []):
                md = v.get("metadata") or {}
                code = md.get("article_code") or v.get("sku")
                if not code:
                    continue
                by_code[code] = {
                    "product_id": p["id"],
                    "handle": p["handle"],
                    "variant_id": v["id"],
                    "sku": v.get("sku"),
                    "prices": v.get("prices") or [],
                }
        if len(batch) < 100:
            break
        off += 100
    return by_code


# ---------------------------------------------------------------------------
# Action planner
# ---------------------------------------------------------------------------
def plan_actions(audit_variants: dict, medusa_index: dict, limit_family: str | None) -> list[dict]:
    actions = []
    unmatched_in_audit = []
    for key, row in audit_variants.items():
        article = row.get("article_code")
        if not article:
            continue
        # Match in Medusa
        mv = medusa_index.get(article) or medusa_index.get((row.get("description") or "").strip())
        if not mv:
            unmatched_in_audit.append(article)
            continue
        if limit_family:
            needle = limit_family.lower()
            haystack = (mv["handle"] + " " + (row.get("family") or "") + " " + article).lower()
            if needle not in haystack:
                continue
        # Build target price set
        target_prices = []
        for ccy in PRICE_CURRENCIES:
            field = f"retail_{ccy}"
            val = row.get(field)
            if val is None or val <= 0:
                continue
            target_prices.append({"currency_code": ccy, "amount": int(round(val * 100))})
        # Determine deltas vs current
        existing_by_ccy = {p["currency_code"]: p for p in mv.get("prices") or []}
        changes = []
        for tp in target_prices:
            existing = existing_by_ccy.get(tp["currency_code"])
            if existing is None:
                changes.append(("create", tp))
            elif int(existing.get("amount") or 0) != tp["amount"]:
                changes.append(("update", tp, int(existing.get("amount") or 0)))
        if not changes:
            actions.append({"op": "PRICES_UPTODATE", "article_code": article, "handle": mv["handle"]})
            continue
        actions.append({
            "op": "SET_VARIANT_PRICES",
            "article_code": article,
            "handle": mv["handle"],
            "product_id": mv["product_id"],
            "variant_id": mv["variant_id"],
            "sku": mv["sku"],
            "target_prices": target_prices,
            "changes": changes,
        })
    return actions, unmatched_in_audit


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------
def execute(med: Medusa, actions: list[dict], audit_meta: dict, dry_run: bool) -> dict:
    counts: dict[str, int] = defaultdict(int)
    errors: list[dict] = []
    for action in actions:
        op = action["op"]
        counts[op] += 1
        if dry_run or op == "PRICES_UPTODATE":
            continue
        try:
            body = {
                "prices": action["target_prices"],
                "metadata": {
                    # Stamp provenance on every priced variant for traceability.
                    "prices_synced_at": datetime.now(timezone.utc).isoformat(),
                    "prices_synced_from": (
                        f"vendors/rampline/pricelists/{audit_meta.get('pricelist_date')}"
                    ),
                    "prices_formula_version": (
                        f"gross_margin={audit_meta.get('gross_margin')}"
                        f" calculated_at={audit_meta.get('calculated_at')}"
                    ),
                },
            }
            med.post(
                f"/admin/products/{action['product_id']}/variants/{action['variant_id']}",
                body,
            )
            log.info(
                "  %s %s  → %s",
                "✓".encode("ascii", "replace").decode(),
                action["article_code"],
                ", ".join(f"{p['currency_code']}={p['amount']/100:,.2f}" for p in action["target_prices"]),
            )
        except Exception as e:
            errors.append({**action, "error": str(e)})
            log.error("price sync failed for %s: %s", action["article_code"], e)
    return {"counts": dict(counts), "errors": errors}


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------
def write_run_log(actions, unmatched, audit_meta, result, dry_run, args) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = f"prices_{'dryrun' if dry_run else 'applied'}_{stamp}"
    out = RUN_LOG_DIR / f"{name}.json"
    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": dry_run,
        "limit_family": args.limit_family,
        "audit_meta": audit_meta,
        "totals": result.get("counts", {}),
        "unmatched_in_audit": unmatched,
        "errors": result.get("errors", []),
        "actions_count": len(actions),
        "actions": actions if dry_run else [
            {k: v for k, v in a.items() if k != "target_prices"} for a in actions
        ],
    }, indent=2, default=str), encoding="utf-8")
    log.info("Run log: %s", out)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pricelist-date", default="2026-05-13",
                    help="Doc id under vendors/rampline/pricelists/")
    ap.add_argument("--limit-family", default=None)
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("Specify --dry-run or --apply")

    log.info("Reading audit doc vendors/rampline/pricelists/%s ...", args.pricelist_date)
    audit = read_audit_doc(args.pricelist_date)
    audit_meta = audit["audit"]
    audit_variants = audit["variants_by_key"]
    log.info(
        "Audit doc: %d variants, gross_margin=%s, calculated_at=%s, fx_source=%s",
        len(audit_variants),
        audit_meta.get("gross_margin"),
        audit_meta.get("calculated_at"),
        audit_meta.get("fx_source"),
    )

    med = Medusa()
    log.info("Indexing Rampline variants on Medusa…")
    medusa_index = index_rampline_variants(med)
    log.info("Indexed %d variants on Rampline sales channel", len(medusa_index))

    actions, unmatched = plan_actions(audit_variants, medusa_index, args.limit_family)
    summary = defaultdict(int)
    for a in actions:
        summary[a["op"]] += 1
    log.info("Planned: %s", dict(summary))
    if unmatched:
        log.warning("Audit codes with no Medusa variant: %d (first 5: %s)",
                    len(unmatched), unmatched[:5])

    if args.dry_run:
        for a in actions[:8]:
            if a["op"] == "PRICES_UPTODATE":
                continue
            log.info(
                "  %s %s → %s",
                a["op"], a["article_code"],
                ", ".join(f"{p['currency_code']}={p['amount']/100:,.2f}" for p in a.get("target_prices") or []),
            )
        result = {"counts": dict(summary), "errors": []}
        write_run_log(actions, unmatched, audit_meta, result, dry_run=True, args=args)
        log.info("DRY RUN — no Medusa writes")
        return

    log.info("APPLYING %d actions…", sum(1 for a in actions if a["op"] != "PRICES_UPTODATE"))
    result = execute(med, actions, audit_meta, dry_run=False)
    log.info("Result: %s", result["counts"])
    if result["errors"]:
        log.error("%d errors", len(result["errors"]))
    write_run_log(actions, unmatched, audit_meta, result, dry_run=False, args=args)


if __name__ == "__main__":
    main()
