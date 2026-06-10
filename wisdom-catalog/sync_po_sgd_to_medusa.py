"""Backfill the SGD retail price onto Leka-Project (Wisdom) Medusa variants.

The Wisdom→Medusa price push (`wisdom-catalog/update_pricing.py :: update_medusa`)
historically pushed only THB (retail) + USD (FOB), so SGD-currency draft orders
and the Dulwich R2 proposal had no Medusa SGD price to read — forcing the R2
builder onto the `fob*4.44` heuristic. This script closes that gap.

For every `products_wisdom/<code>` doc that carries `pricing.retail_sgd`
(currently the 36 Dulwich PO 2026060101 codes), it re-sends the variant's full
price list to Medusa as:
    thb = pricing.retail_thb   (unchanged — catalog retail)
    usd = pricing.fob_usd      (unchanged — existing FOB convention)
    sgd = pricing.retail_sgd   (NEW — the reconciled flat-path retail)

`update_variant_prices` REPLACES the price list, so all three are sent together
to avoid wiping THB/USD. Source of truth = Firestore products_wisdom pricing
(same values reconciled in docs/reports/dulwich-po-2026060101-pricing.html).

Dry-run by default; --write to apply. Auth: LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD
(or pulled from Secret Manager medusa-admin-email/-password when --secrets).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROJECT = "ai-agents-go"
DB = "leka-product-catalogs"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"


def _secret(name: str) -> str:
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         f"--secret={name}", f"--project={PROJECT}"],
        capture_output=True, text=True, shell=True)
    return out.stdout.strip()


def _norm(s) -> str:
    import re
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--secrets", action="store_true",
                    help="Fetch Medusa admin creds from Secret Manager")
    args = ap.parse_args()

    sa = (r"C:\Users\Eukrit\OneDrive\Documents\Claude Code"
          r"\Credentials Claude Code\ai-agents-go-claude-sa.json")
    if Path(sa).exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", sa)
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT)

    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=DB)

    # Collect the priced docs (those with pricing.retail_sgd).
    rows = []
    for d in db.collection("products_wisdom").stream():
        pd = d.to_dict() or {}
        pr = pd.get("pricing") or {}
        if pr.get("retail_sgd"):
            rows.append({
                "code": d.id,
                "fob_usd": pr.get("fob_usd"),
                "retail_thb": pr.get("retail_thb"),
                "retail_sgd": pr.get("retail_sgd"),
            })
    print(f"== Wisdom SGD→Medusa backfill ({'WRITE' if args.write else 'DRY-RUN'}) ==")
    print(f"   {len(rows)} products_wisdom docs carry pricing.retail_sgd")

    os.environ["MEDUSA_BACKEND_URL"] = BACKEND
    if args.secrets or not os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL"):
        os.environ["MEDUSA_ADMIN_EMAIL"] = _secret("leka-medusa-admin-email")
        os.environ["MEDUSA_ADMIN_PASSWORD"] = _secret("leka-medusa-admin-password")
    else:
        os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ["LEKA_MEDUSA_ADMIN_EMAIL"]
        os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")

    from shared.medusa_importer import MedusaImporter
    c = MedusaImporter(base_url=BACKEND)

    # Index variants by sku + legacy_sku, capturing current prices.
    idx: dict[str, dict] = {}
    off = 0
    while True:
        r = c._get("/admin/products", {
            "limit": 100, "offset": off,
            "fields": "id,variants.id,variants.sku,variants.metadata,"
                      "variants.prices.amount,variants.prices.currency_code"})
        b = r.get("products", [])
        if not b:
            break
        for p in b:
            for v in p.get("variants") or []:
                cur = {pr["currency_code"]: pr["amount"] for pr in (v.get("prices") or [])}
                for k in (v.get("sku"), (v.get("metadata") or {}).get("legacy_sku")):
                    if k:
                        idx.setdefault(_norm(k), {"pid": p["id"], "vid": v["id"], "cur": cur})
        if len(b) < 100:
            break
        off += 100
    print(f"   indexed {len(idx)} Medusa variant keys\n")

    updated = skipped = already = 0
    for row in sorted(rows, key=lambda x: x["code"]):
        hit = idx.get(_norm(row["code"]))
        if not hit:
            print(f"   {row['code']:<18} NOT FOUND in Medusa — skip")
            skipped += 1
            continue
        thb_c = int(round(row["retail_thb"] * 100))
        usd_c = int(round(row["fob_usd"] * 100))
        sgd_c = int(round(row["retail_sgd"] * 100))
        cur_sgd = hit["cur"].get("sgd")
        tag = "add SGD" if cur_sgd is None else (
            "ok" if cur_sgd == sgd_c else f"fix SGD {cur_sgd/100:.2f}→{sgd_c/100:.2f}")
        print(f"   {row['code']:<18} SGD S${row['retail_sgd']:>9,.2f}  "
              f"THB ฿{row['retail_thb']:>10,.2f}  USD ${row['fob_usd']:>8,.2f}  [{tag}]")
        if cur_sgd == sgd_c:
            already += 1
            continue
        if args.write:
            c.update_variant_prices(hit["pid"], hit["vid"], [
                {"amount": usd_c, "currency_code": "usd"},
                {"amount": thb_c, "currency_code": "thb"},
                {"amount": sgd_c, "currency_code": "sgd"},
            ])
            updated += 1

    print(f"\n   {'updated' if args.write else 'would update'}: "
          f"{len([r for r in rows if idx.get(_norm(r['code'])) and idx[_norm(r['code'])]['cur'].get('sgd') != int(round(r['retail_sgd']*100))])}"
          f"  already-correct: {already}  not-found: {skipped}")
    if not args.write:
        print("   (dry-run — re-run with --write to push SGD prices)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
