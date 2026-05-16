"""Rampline variant migration → Medusa.

Reads rampline-catalog/data/mapping/variant_scaffold_draft.csv and applies
the resulting structure to Medusa:

  1. CREATE new size sub-products  (rampball-35/50/50r/70r, jumpstone-27/50/3/5)
     - inherits parent images + description + category + sales channel
     - status=draft  (storefront-quiet until pricing lands)
     - options + variants set in the create payload
     - audit metadata on each variant (article_code, family, family_discount,
       net_nok, recommended_nok, pricelist_date, source)

  2. UPDATE existing parents that get new options (single_product families,
     all 21 BP parks, rampline-shockdeck):
       a. add the option titles to the product (POST /admin/products/{id}/options)
       b. POST each variant
       c. DELETE the placeholder "Default" variant (numeric WooCommerce SKU)
       d. DELETE the placeholder "Default" option if no longer used

  3. The 17 unpriced legacy parks + 3 unpriced equipment products are skipped.

Idempotent: variants are matched by SKU; products by handle. Re-running the
script does nothing if all intended variants already exist.

Usage:
    python rampline-catalog/build_variants.py --dry-run
    python rampline-catalog/build_variants.py --dry-run --limit-family Rampball
    python rampline-catalog/build_variants.py --apply
    python rampline-catalog/build_variants.py --apply --limit-family Rampball
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = REPO_ROOT / "rampline-catalog" / "data" / "mapping" / "variant_scaffold_draft.csv"
MEDUSA_SNAPSHOT_DIR = REPO_ROOT / "rampline-catalog" / "data" / "mapping"
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
TIMEOUT = 60
PRICELIST_DATE = "2026-05-13"
BRAND = "rampline"

# Families whose size becomes its own Medusa product (per user decision).
SIZE_AS_PRODUCT_FAMILIES = {
    "Tilting and rotating balance balls",
    "Natural rubber jump pads with a rough surface.",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("build_variants")


# ---------------------------------------------------------------------------
# Medusa REST helpers
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

    def patch(self, path: str, body: dict) -> dict:
        r = self.session.post(f"{BACKEND}{path}", json=body, timeout=TIMEOUT)
        # Medusa uses POST for updates per their REST conventions; keep alias
        if not r.ok:
            log.error("PATCH %s failed (%d): %s", path, r.status_code, r.text[:600])
            r.raise_for_status()
        return r.json()

    def delete(self, path: str) -> dict:
        r = self.session.delete(f"{BACKEND}{path}", timeout=TIMEOUT)
        if not r.ok:
            log.error("DELETE %s failed (%d): %s", path, r.status_code, r.text[:600])
            r.raise_for_status()
        return r.json() if r.text else {}


# ---------------------------------------------------------------------------
# Scaffold loader
# ---------------------------------------------------------------------------
def load_scaffold() -> list[dict]:
    rows = list(csv.DictReader(SCAFFOLD.open(encoding="utf-8")))
    # Coerce numerics
    for r in rows:
        if r.get("family_discount"):
            r["family_discount"] = float(r["family_discount"])
        if r.get("recommended_nok"):
            r["recommended_nok"] = float(r["recommended_nok"])
        if r.get("net_nok"):
            r["net_nok"] = float(r["net_nok"])
    return rows


def parse_options_flat(s: str) -> list[tuple[str, str, str]]:
    """`'Surface=loose_fills:Loose fills|Size=35cm:35 cm'` → list of (title, key, label)."""
    if not s:
        return []
    out = []
    for piece in s.split("|"):
        if "=" not in piece:
            continue
        title, rest = piece.split("=", 1)
        key, label = rest.split(":", 1) if ":" in rest else (rest, rest)
        out.append((title.strip(), key.strip(), label.strip()))
    return out


# ---------------------------------------------------------------------------
# Group rows into (sub_product_handle) → {options, variants}
# ---------------------------------------------------------------------------
def group_by_subproduct(rows: list[dict]) -> dict[str, dict]:
    """Return:
        {
          sub_product_handle: {
            "parent_handle": str,        # source parent (for image / description inheritance)
            "sub_product_handle": str,   # final Medusa handle
            "sub_product_title": str,
            "group": str,                # A-equipment | B-park | B-component
            "family": str,
            "family_discount": float,
            "new_product": bool,         # True if we create a brand-new Medusa product
            "options": list[ {title, values: list[(key, label)] } ],
            "variants": list[ {sku, title, option_values: [(option_title, label)], metadata: {...} } ],
            "article_codes": list[str],
          }
        }
    """
    by_sub: dict[str, dict] = {}
    for r in rows:
        sub_handle = r["sub_product_handle"]
        opts_flat = parse_options_flat(r.get("options_flat", ""))
        if sub_handle not in by_sub:
            by_sub[sub_handle] = {
                "parent_handle": r["parent_handle"],
                "sub_product_handle": sub_handle,
                "sub_product_title": r["sub_product_title"],
                "group": r["group"],
                "family": r["family"],
                "family_discount": r["family_discount"],
                "new_product": sub_handle != r["parent_handle"],  # new if differs
                "option_values": defaultdict(set),  # title → set of (key, label) tuples
                "variants": [],
                "article_codes": [],
            }
        entry = by_sub[sub_handle]
        # collect option values
        for (t, k, l) in opts_flat:
            entry["option_values"][t].add((k, l))
        entry["variants"].append({
            "sku": r["variant_sku"],
            "title": r.get("variant_title") or "Default",
            "option_values": [(t, l) for (t, k, l) in opts_flat],
            "metadata": {
                "article_code": r["sku"],
                "family": r["family"],
                "family_discount": r["family_discount"],
                "net_nok": r["net_nok"],
                "recommended_nok": r["recommended_nok"],
                "description": r.get("description"),
                "pricelist_date": PRICELIST_DATE,
                "source": "rampline-pricelist-2025",
            },
        })
        entry["article_codes"].append(r["sku"])
    # Finalize options[] in stable order
    for entry in by_sub.values():
        options = []
        for title, values in entry["option_values"].items():
            options.append({"title": title, "values": sorted({lbl for (_k, lbl) in values})})
        entry["options"] = options
        del entry["option_values"]
    return by_sub


# ---------------------------------------------------------------------------
# Action planner
# ---------------------------------------------------------------------------
def plan_actions(med: Medusa, by_sub: dict[str, dict], limit_family: str | None) -> list[dict]:
    """Returns a flat list of action dicts, in execution order."""
    # Fetch current Medusa state for all parents we touch (cache)
    handles_to_fetch = set()
    for entry in by_sub.values():
        handles_to_fetch.add(entry["parent_handle"])
        handles_to_fetch.add(entry["sub_product_handle"])
    current: dict[str, dict] = {}
    for h in handles_to_fetch:
        prods = med.get(
            "/admin/products",
            handle=h, limit=1,
            fields="id,handle,title,status,description,thumbnail,"
                   "options.id,options.title,options.values.id,options.values.value,"
                   "variants.id,variants.title,variants.sku,"
                   "variants.options.option_id,variants.options.value,"
                   "categories.id,categories.name,"
                   "images.url,images.id",
        ).get("products") or []
        if prods:
            current[h] = prods[0]

    actions = []
    for entry in by_sub.values():
        if limit_family:
            needle = limit_family.lower()
            haystack = " ".join([
                entry["family"], entry["parent_handle"],
                entry["sub_product_handle"], entry["sub_product_title"],
            ]).lower()
            if needle not in haystack:
                continue
        sub_h = entry["sub_product_handle"]
        sub = current.get(sub_h)
        parent = current.get(entry["parent_handle"])
        if entry["new_product"]:
            if sub:
                # Already exists — go straight to variant-creation path
                actions.extend(_plan_variants_for_existing(sub, entry))
            else:
                actions.append({
                    "op": "CREATE_PRODUCT",
                    "handle": sub_h,
                    "title": entry["sub_product_title"],
                    "parent_handle": entry["parent_handle"],
                    "parent_id": parent["id"] if parent else None,
                    "parent_status": parent["status"] if parent else "draft",
                    "parent_description": (parent or {}).get("description") or "",
                    "parent_thumbnail": (parent or {}).get("thumbnail"),
                    "parent_images": [img["url"] for img in (parent or {}).get("images") or []],
                    "parent_category_ids": [
                        c["id"] for c in (parent or {}).get("categories") or []
                    ],
                    "options": entry["options"],
                    "variants": entry["variants"],
                    "family": entry["family"],
                    "article_codes": entry["article_codes"],
                })
        else:
            if not sub:
                actions.append({
                    "op": "ERROR_PARENT_MISSING",
                    "handle": sub_h,
                    "family": entry["family"],
                })
                continue
            actions.extend(_plan_variants_for_existing(sub, entry))
    return actions


def _plan_variants_for_existing(prod: dict, entry: dict) -> list[dict]:
    """Plan ordering: delete placeholder variant → delete Default option →
    add new option(s) → create variants. Required because Medusa v2 makes
    every variant declare a value for every option on the product."""
    actions = []
    existing_options = {o["title"]: o for o in prod.get("options") or []}
    existing_variants_by_sku = {v["sku"]: v for v in prod.get("variants") or []}

    # Build set of SKUs we'll create; if all are already present we can short-circuit.
    skus_to_create = {v["sku"] for v in entry["variants"]}
    all_exist = skus_to_create.issubset(existing_variants_by_sku.keys())

    # Medusa v2 forbids option-less products. For families with zero real axes
    # (e.g. Rampit Storm / climbing pole — 1 SKU, no surface or size axis),
    # synthesize a single-value "Type" option so the variant has something to
    # reference.
    if not entry["options"]:
        entry = dict(entry)  # don't mutate caller
        entry["options"] = [{"title": "Type", "values": ["Standard"]}]
        entry["variants"] = [
            {**v, "option_values": [("Type", "Standard")], "title": "Standard"}
            for v in entry["variants"]
        ]

    # 1. Delete placeholder default variants (numeric SKU) — but ONLY if there
    #    are real variants to replace them, otherwise the product would end up
    #    empty. Skip when all our intended variants already exist.
    if not all_exist:
        for v in prod.get("variants") or []:
            sku = (v.get("sku") or "").strip()
            if sku.isdigit():
                actions.append({
                    "op": "DELETE_PLACEHOLDER_VARIANT",
                    "product_id": prod["id"],
                    "handle": prod["handle"],
                    "variant_id": v["id"],
                    "sku": sku,
                })

    # 2. Delete the placeholder "Default" option whenever we're creating new
    #    variants. Medusa v2 requires every variant to declare a value for
    #    every option on the product, so leaving Default in place forces the
    #    new variants to carry a redundant "Default": "Default" pair (or even
    #    products with no axes — Rampit Storm — fail with 500 because their
    #    new variant has no value for the Default option). It's cleaner to
    #    remove Default and let new variants either carry the real axes or
    #    nothing at all.
    default_option = existing_options.get("Default")
    if default_option and not all_exist:
        actions.append({
            "op": "DELETE_DEFAULT_OPTION",
            "product_id": prod["id"],
            "handle": prod["handle"],
            "option_id": default_option["id"],
        })

    # 3. Add any missing real options.
    for opt in entry["options"]:
        title = opt["title"]
        values = opt["values"]
        if title == "Default":
            continue
        existing = existing_options.get(title)
        if existing:
            existing_values = {v["value"] for v in existing.get("values") or []}
            missing = [v for v in values if v not in existing_values]
            if missing:
                actions.append({
                    "op": "ADD_OPTION_VALUES",
                    "product_id": prod["id"],
                    "handle": prod["handle"],
                    "option_id": existing["id"],
                    "option_title": title,
                    "values": missing,
                })
        else:
            actions.append({
                "op": "ADD_OPTION",
                "product_id": prod["id"],
                "handle": prod["handle"],
                "option_title": title,
                "values": values,
            })

    # 4. Create new variants (skip ones already present).
    for v in entry["variants"]:
        if v["sku"] in existing_variants_by_sku:
            actions.append({
                "op": "VARIANT_EXISTS",
                "product_id": prod["id"],
                "handle": prod["handle"],
                "sku": v["sku"],
            })
            continue
        actions.append({
            "op": "CREATE_VARIANT",
            "product_id": prod["id"],
            "handle": prod["handle"],
            "sku": v["sku"],
            "title": v["title"],
            "option_values": v["option_values"],
            "metadata": v["metadata"],
        })

    return actions


# ---------------------------------------------------------------------------
# Action executor
# ---------------------------------------------------------------------------
def execute_actions(med: Medusa, actions: list[dict], dry_run: bool) -> dict:
    """Run the actions. Returns {op_counts, errors}."""
    counts: dict[str, int] = defaultdict(int)
    errors: list[dict] = []

    for i, action in enumerate(actions, 1):
        op = action["op"]
        counts[op] += 1
        if dry_run:
            continue
        try:
            if op == "CREATE_PRODUCT":
                _run_create_product(med, action)
            elif op == "ADD_OPTION":
                med.post(
                    f"/admin/products/{action['product_id']}/options",
                    {"title": action["option_title"], "values": action["values"]},
                )
                log.info("  added option %r to %s", action["option_title"], action["handle"])
            elif op == "ADD_OPTION_VALUES":
                # Medusa v2: PATCH option to extend values
                med.post(
                    f"/admin/products/{action['product_id']}/options/{action['option_id']}",
                    {"title": action["option_title"], "values": action["values"]},
                )
                log.info("  added %d values to %s.%s", len(action["values"]),
                         action["handle"], action["option_title"])
            elif op == "CREATE_VARIANT":
                med.post(
                    f"/admin/products/{action['product_id']}/variants",
                    {
                        "title": action["title"],
                        "sku": action["sku"],
                        "manage_inventory": False,
                        "options": dict(action["option_values"]),
                        "metadata": action["metadata"],
                        "prices": [],  # Medusa v2 requires field; pricing handled separately
                    },
                )
                log.info("  + variant %s on %s", action["sku"], action["handle"])
            elif op == "DELETE_PLACEHOLDER_VARIANT":
                med.delete(
                    f"/admin/products/{action['product_id']}/variants/{action['variant_id']}"
                )
                log.info("  - placeholder variant %s on %s", action["sku"], action["handle"])
            elif op == "DELETE_DEFAULT_OPTION":
                med.delete(
                    f"/admin/products/{action['product_id']}/options/{action['option_id']}"
                )
                log.info("  - Default option on %s", action["handle"])
            elif op == "VARIANT_EXISTS":
                pass
            elif op == "ERROR_PARENT_MISSING":
                errors.append(action)
        except Exception as e:
            errors.append({**action, "error": str(e)})
            log.error("action %d failed: %s — %s", i, op, e)
            # Stop the run on any unexpected error
            break

    return {"counts": dict(counts), "errors": errors}


def _run_create_product(med: Medusa, a: dict):
    body = {
        "title": a["title"],
        "handle": a["handle"],
        "description": a["parent_description"],
        "status": "draft",
        "thumbnail": a["parent_thumbnail"],
        "images": [{"url": u} for u in a["parent_images"]],
        "categories": [{"id": cid} for cid in a["parent_category_ids"]],
        "sales_channels": [{"id": RAMPLINE_SALES_CHANNEL_ID}],
        "options": a["options"],
        "variants": [
            {
                "title": v["title"],
                "sku": v["sku"],
                "manage_inventory": False,
                "options": dict(v["option_values"]),
                "metadata": v["metadata"],
                "prices": [],  # Medusa v2 requires the field; pricing handled separately
            }
            for v in a["variants"]
        ],
        "metadata": {
            "brand_slug": BRAND,
            "brand_name": "Rampline",
            "parent_handle": a["parent_handle"],
            "source": "rampline-pricelist-2025-variant-migration",
        },
    }
    med.post("/admin/products", body)
    log.info("  CREATED product %s with %d variants", a["handle"], len(a["variants"]))


# ---------------------------------------------------------------------------
# Output run log
# ---------------------------------------------------------------------------
def write_run_log(actions: list[dict], result: dict, dry_run: bool, args) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = f"{'dryrun' if dry_run else 'applied'}_{stamp}"
    out = RUN_LOG_DIR / f"{name}.json"
    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": dry_run,
        "limit_family": args.limit_family,
        "totals": result.get("counts", {}),
        "errors": result.get("errors", []),
        "actions": actions,
    }, indent=2, default=str), encoding="utf-8")
    log.info("Run log: %s", out)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Plan and print only, no Medusa writes")
    ap.add_argument("--apply", action="store_true", help="Execute writes (off by default)")
    ap.add_argument("--limit-family", default=None,
                    help="Substring match on family name to run a single family")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("Specify --dry-run or --apply")

    rows = load_scaffold()
    by_sub = group_by_subproduct(rows)
    log.info("Loaded scaffold: %d rows → %d sub-products", len(rows), len(by_sub))

    med = Medusa()
    actions = plan_actions(med, by_sub, args.limit_family)

    # Plan summary
    summary: dict[str, int] = defaultdict(int)
    for a in actions:
        summary[a["op"]] += 1
    log.info("Planned actions: %s", dict(summary))

    if args.dry_run:
        log.info("DRY RUN — printing first 12 actions then writing run log")
        for a in actions[:12]:
            log.info("  %s  %s", a["op"], json.dumps({k: v for k, v in a.items() if k != "op"})[:240])
        result = {"counts": dict(summary), "errors": []}
        write_run_log(actions, result, dry_run=True, args=args)
        return

    log.info("APPLYING %d actions to Medusa…", len(actions))
    result = execute_actions(med, actions, dry_run=False)
    log.info("Result: %s", result["counts"])
    if result["errors"]:
        log.error("Errors: %d", len(result["errors"]))
        for e in result["errors"][:10]:
            log.error("  %s", e)
    write_run_log(actions, result, dry_run=False, args=args)


if __name__ == "__main__":
    main()
