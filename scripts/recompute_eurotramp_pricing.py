"""Recompute Eurotramp landed + retail pricing under the HOUSE costing model.

Replaces the earlier FLAT model (computed in the sibling `vendors` repo by
`eurotramp-catalog/scripts/calc_landed_cost.py`) which used:
  - freight = 18% of goods, fixed clearance 512.5 THB/SKU,
  - retail = landed x 1.30 (effective GM ~23.1%),
  - retail_thb carried NO Thai customer VAT.

New model (owner directive 2026-06-07):
  - freight    = 30% of goods (FOB-in-THB)        [user directive]
  - clearance  =  6% of goods                      [user directive]
  - insurance  =  1% of goods (CIF insurance, retained from prior model — FLAGGED)
  - duty       = 10% of CIF (non-China origin)
  - import VAT =  7% of (CIF + duty)               [Thai import VAT]
  - GM         = 35% (brands.eurotramp.gross_margin) — retail = landed / (1 - GM)
  - retail_thb embeds 7% TH CUSTOMER VAT (domestic); USD/EUR/SGD stay ex-VAT.
  - SG GST stacks on retail_sgd only when Nubo is GST-registered (currently no -> x1.0).

Volumetric (CBM) freight and air-vs-LCL routing are NOT applied here: no
Eurotramp SKU carries packing dimensions or shipping weights (the 63 docs with
a `dimensions` field hold installation/frame dims, e.g. frame_length_cm=1036 for
a 10 m track, not a packing envelope; 0 docs carry weight_kg). The owner will
run the volumetric calculation separately. This is FLAGGED in the run report.

FX is pinned to the existing Eurotramp snapshot (EUR=38.7877, USD=33.0472,
SGD=25.974) so the old-vs-new reconciliation isolates the COST-MODEL + MARGIN +
VAT change rather than mixing in FX drift, and so the recompute stays coherent
with the prices already live on the storefront. An FX refresh is a separate
follow-up.

Source of EXW: the authoritative per-article EXW EUR already parsed into
Firestore `vendors/eurotramp/products/{handle}.pricing.exw_eur` (so we do not
re-fetch the raw "Price list 2025 (1E).xlsx" from Gmail). Docs without an EXW
(configurator/pricelist gaps) are left untouched.

Outputs:
  - docs/reports/eurotramp-recompute-<date>.{json,csv} — full old-vs-new reconciliation
  - docs/reports/eurotramp-snapshot-<date>-pre-house-costing.json — pre-write Firestore snapshot
On --write: updates Firestore product pricing + pricing_config/canonical brands.eurotramp.

Usage:
    python scripts/recompute_eurotramp_pricing.py --dry-run
    python scripts/recompute_eurotramp_pricing.py --write
    python scripts/recompute_eurotramp_pricing.py --dry-run --limit 10
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("recompute_eurotramp")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
LEKA_DB = "leka-product-catalogs"
BRAND = "eurotramp"
RUN_DATE = date(2026, 6, 7).isoformat()
REPORTS = REPO_ROOT / "docs" / "reports"

# --- Pinned FX (existing Eurotramp snapshot) --------------------------------
FX_EUR_THB = 38.7877
FX_USD_THB = 33.0472
FX_SGD_THB = 25.974

# --- House costing model knobs (owner directive 2026-06-07) -----------------
FREIGHT_PCT_OF_GOODS = 0.30     # user directive
CLEARANCE_PCT_OF_GOODS = 0.06   # user directive
INSURANCE_PCT_OF_GOODS = 0.01   # retained CIF insurance (flagged)
DUTY_RATE = 0.10                # non-China origin
IMPORT_VAT_RATE = 0.07          # Thai import VAT on (CIF + duty)
GROSS_MARGIN = 0.35             # brands.eurotramp.gross_margin
TH_CUSTOMER_VAT_RATE = 0.07     # embedded in retail_thb only
SG_NUBO_GST_REGISTERED = False  # -> SG GST multiplier = 1.0
SG_CUSTOMER_GST_RATE = 0.09

PRICING_MODEL = "house_lcl_freight30_clearance6_duty10_importvat7_vatincl_gm35"


def compute(exw_eur: float) -> dict:
    """Recompute landed + retail for one article from its EXW EUR."""
    goods_thb = exw_eur * FX_EUR_THB
    insurance_thb = goods_thb * INSURANCE_PCT_OF_GOODS
    freight_thb = goods_thb * FREIGHT_PCT_OF_GOODS
    cif_thb = goods_thb + insurance_thb + freight_thb
    duty_thb = cif_thb * DUTY_RATE
    vat_thb = (cif_thb + duty_thb) * IMPORT_VAT_RATE
    clearance_thb = goods_thb * CLEARANCE_PCT_OF_GOODS
    landed_thb = (
        goods_thb + insurance_thb + freight_thb + duty_thb + vat_thb + clearance_thb
    )

    gm = GROSS_MARGIN
    th_vat_mult = 1.0 + TH_CUSTOMER_VAT_RATE
    sg_gst_mult = (1.0 + SG_CUSTOMER_GST_RATE) if SG_NUBO_GST_REGISTERED else 1.0

    retail_thb = (landed_thb / (1 - gm)) * th_vat_mult            # TH customer VAT embedded
    retail_usd = (landed_thb / FX_USD_THB) / (1 - gm)             # ex-VAT
    retail_eur = (landed_thb / FX_EUR_THB) / (1 - gm)             # ex-VAT
    retail_sgd = ((landed_thb / FX_SGD_THB) / (1 - gm)) * sg_gst_mult  # ex-VAT (+SG GST if registered)

    return {
        "currency_exw": "EUR",
        "exw_eur": round(exw_eur, 2),
        "goods_thb": round(goods_thb, 2),
        "insurance_thb": round(insurance_thb, 2),
        "freight_thb": round(freight_thb, 2),
        "cif_thb": round(cif_thb, 2),
        "duty_thb": round(duty_thb, 2),
        "vat_thb": round(vat_thb, 2),
        "clearance_thb": round(clearance_thb, 2),
        "landed_thb": round(landed_thb, 2),
        "gross_margin": gm,
        "duty_rate": DUTY_RATE,
        "vat_rate": IMPORT_VAT_RATE,
        "th_customer_vat_rate": TH_CUSTOMER_VAT_RATE,
        "freight_pct_of_goods": FREIGHT_PCT_OF_GOODS,
        "clearance_pct_of_goods": CLEARANCE_PCT_OF_GOODS,
        "insurance_pct_of_goods": INSURANCE_PCT_OF_GOODS,
        "retail_thb": round(retail_thb, 2),
        "retail_usd": round(retail_usd, 2),
        "retail_eur": round(retail_eur, 2),
        "retail_sgd": round(retail_sgd, 2),
        "fob_usd": round(retail_usd, 2),         # Medusa-compat alias kept
        "fx_eur_thb": FX_EUR_THB,
        "fx_usd_thb": FX_USD_THB,
        "fx_sgd_thb": FX_SGD_THB,
        "pricing_model": PRICING_MODEL,
        "price_date": RUN_DATE,
        "import_duty_rate": DUTY_RATE,
        "volumetric_applied": False,
        "volumetric_note": "No packing dims/weights; volumetric CBM computed separately by owner.",
    }


def _firestore(db_name: str):
    from google.cloud import firestore
    return firestore.Client(project=PROJECT, database=db_name)


def update_pricing_config(write: bool) -> None:
    """Add brands.eurotramp to pricing_config/canonical (leka-product-catalogs db)."""
    db = _firestore(LEKA_DB)
    ref = db.collection("pricing_config").document("canonical")
    snap = ref.get()
    cur = snap.to_dict() if snap.exists else {}
    brands = dict(cur.get("brands") or {})
    euro = dict(brands.get(BRAND) or {})
    euro.update({
        "gross_margin": GROSS_MARGIN,
        "import_duty_rate": DUTY_RATE,
        "freight_pct_of_goods": FREIGHT_PCT_OF_GOODS,
        "clearance_pct_of_goods": CLEARANCE_PCT_OF_GOODS,
        "insurance_pct_of_goods": INSURANCE_PCT_OF_GOODS,
        "costing_model": PRICING_MODEL,
    })
    log.info("pricing_config brands.eurotramp -> %s", json.dumps(euro))
    if write:
        ref.set({"brands": {BRAND: euro}}, merge=True)
        log.info("WROTE pricing_config/canonical brands.eurotramp")
    else:
        log.info("DRY-RUN — pricing_config not written")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    write = bool(args.write)

    REPORTS.mkdir(parents=True, exist_ok=True)
    db = _firestore(VENDORS_DB)
    col = db.collection("vendors").document(BRAND).collection("products")
    docs = list(col.stream())
    log.info("Loaded %d eurotramp docs", len(docs))

    snapshot: dict[str, dict] = {}
    recon: list[dict] = []
    repriced = skipped = 0

    for d in docs:
        dd = d.to_dict() or {}
        old = dd.get("pricing") or {}
        exw = old.get("exw_eur")
        snapshot[d.id] = old  # full pre-write pricing snapshot (for rollback/audit)
        if not exw:
            skipped += 1
            continue
        try:
            exw = float(exw)
        except (TypeError, ValueError):
            skipped += 1
            continue

        new = compute(exw)
        # Carry forward identity/source fields not recomputed.
        for k in ("msrp_eur", "gtin", "article_number", "source_file", "pricelist"):
            if k in old and k not in new:
                new[k] = old[k]

        # --- No-decrease floor (owner directive 2026-06-07) ---
        # The new 6%-of-goods clearance removes the old fixed 512.5 THB/SKU
        # clearance floor, so a handful of micro-spares (EXW <= ~7 EUR) would
        # drop 50-85%. Guard: no SKU's retail may fall below its current live
        # price. When the computed retail_thb is lower, hold the ENTIRE old
        # retail set (thb/usd/eur/sgd) — those are the prices already live, so
        # nothing on the storefront decreases — while keeping the new cost
        # breakdown for audit.
        old_rt = old.get("retail_thb")
        floored = False
        if old_rt and new["retail_thb"] < old_rt:
            floored = True
            new["price_floor"] = "no_decrease_held_old"
            new["retail_thb_computed"] = new["retail_thb"]
            new["retail_thb"] = round(float(old_rt), 2)
            for ck in ("retail_usd", "retail_eur", "retail_sgd"):
                if old.get(ck) is not None:
                    new[ck] = round(float(old[ck]), 2)
            new["fob_usd"] = new["retail_usd"]
        new["floored"] = floored

        repriced += 1
        recon.append({
            "handle": d.id,
            "item_code": dd.get("item_code"),
            "article_number": old.get("article_number"),
            "floored": floored,
            "exw_eur": exw,
            "old_landed_thb": old.get("landed_thb"),
            "new_landed_thb": new["landed_thb"],
            "old_retail_thb": old.get("retail_thb"),
            "new_retail_thb": new["retail_thb"],
            "old_retail_usd": old.get("retail_usd"),
            "new_retail_usd": new["retail_usd"],
            "old_retail_eur": old.get("retail_eur"),
            "new_retail_eur": new["retail_eur"],
            "old_retail_sgd": old.get("retail_sgd"),
            "new_retail_sgd": new["retail_sgd"],
            "thb_delta_pct": round(
                (new["retail_thb"] / old["retail_thb"] - 1) * 100, 1
            ) if old.get("retail_thb") else None,
            "_new_pricing": new,
        })

    if args.limit:
        recon = recon[: args.limit]
    floored_n = sum(1 for r in recon if r.get("floored"))
    log.info("repriced=%d skipped(no EXW)=%d floored(no-decrease)=%d",
             repriced, skipped, floored_n)
    if floored_n:
        log.info("  floored SKUs (held at old price): %s",
                 [r["handle"] for r in recon if r.get("floored")])

    # --- Reconciliation totals ---
    def _sum(key):
        return sum(r[key] for r in recon if r.get(key))
    tot_old_thb = _sum("old_retail_thb")
    tot_new_thb = _sum("new_retail_thb")
    blended = round((tot_new_thb / tot_old_thb - 1) * 100, 1) if tot_old_thb else None
    log.info("Sum retail THB: old=%.0f new=%.0f (blended %+.1f%%)",
             tot_old_thb, tot_new_thb, blended or 0)

    # --- Write reports (always) ---
    snap_path = REPORTS / f"eurotramp-snapshot-{RUN_DATE}-pre-house-costing.json"
    snap_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote pre-write snapshot: %s (%d docs)", snap_path.name, len(snapshot))

    recon_json = REPORTS / f"eurotramp-recompute-{RUN_DATE}.json"
    recon_json.write_text(json.dumps({
        "brand": BRAND, "run_date": RUN_DATE, "pricing_model": PRICING_MODEL,
        "fx": {"EUR": FX_EUR_THB, "USD": FX_USD_THB, "SGD": FX_SGD_THB},
        "knobs": {
            "freight_pct_of_goods": FREIGHT_PCT_OF_GOODS,
            "clearance_pct_of_goods": CLEARANCE_PCT_OF_GOODS,
            "insurance_pct_of_goods": INSURANCE_PCT_OF_GOODS,
            "duty_rate": DUTY_RATE, "import_vat_rate": IMPORT_VAT_RATE,
            "gross_margin": GROSS_MARGIN, "th_customer_vat_rate": TH_CUSTOMER_VAT_RATE,
        },
        "repriced": repriced, "skipped_no_exw": skipped,
        "floored_no_decrease": floored_n,
        "floored_handles": [r["handle"] for r in recon if r.get("floored")],
        "totals": {"old_retail_thb": round(tot_old_thb, 2),
                   "new_retail_thb": round(tot_new_thb, 2),
                   "blended_delta_pct": blended},
        "rows": [{k: v for k, v in r.items() if k != "_new_pricing"} for r in recon],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote reconciliation: %s", recon_json.name)

    recon_csv = REPORTS / f"eurotramp-recompute-{RUN_DATE}.csv"
    cols = ["handle", "item_code", "article_number", "floored", "exw_eur",
            "old_landed_thb", "new_landed_thb", "old_retail_thb", "new_retail_thb",
            "thb_delta_pct", "old_retail_usd", "new_retail_usd",
            "old_retail_eur", "new_retail_eur", "old_retail_sgd", "new_retail_sgd"]
    with recon_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in recon:
            w.writerow(r)
    log.info("Wrote reconciliation CSV: %s", recon_csv.name)

    # --- Sample print ---
    for r in recon[:6]:
        log.info("  %s art=%s EXW€%.2f  landed %.0f->%.0f  THB %.0f->%.0f (%+.1f%%)",
                 r["handle"][:40], r["article_number"], r["exw_eur"],
                 r["old_landed_thb"] or 0, r["new_landed_thb"],
                 r["old_retail_thb"] or 0, r["new_retail_thb"], r["thb_delta_pct"] or 0)

    # --- Firestore writes ---
    if write:
        n = 0
        for r in recon:
            col.document(r["handle"]).update({"pricing": r["_new_pricing"]})
            n += 1
            if n % 50 == 0:
                log.info("  …updated %d/%d", n, len(recon))
        log.info("WROTE pricing to %d Firestore docs", n)
        update_pricing_config(write=True)
    else:
        log.info("DRY-RUN — Firestore product pricing not written")
        update_pricing_config(write=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
