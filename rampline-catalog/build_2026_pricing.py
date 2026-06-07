"""Rampline 2026 retail pricing → repo JSON + Firestore (vendors/rampline).

The 2026 Rampline price list (eff. 2025-12-01) was parsed and cost-stacked in
the sibling `vendors` repo at 35% gross margin / 10% import duty, with a fixed
FX snapshot (frankfurter.app 2026-06-05: 1 NOK = 3.5029 THB / 0.10734 USD /
0.09221 EUR). That `pricelist_landed.json` is the authoritative cost-plus
output (landed_thb, retail_thb/usd/eur, all EX-VAT) and supersedes the older
2025 xlsx that `rampline-catalog/import_pricelist.py` reads.

This script:
  1. Reads the two vendors JSONs (pricelist.json + pricelist_landed.json).
  2. ANCHORS retail_thb / retail_usd / retail_eur to the vendors stack so the
     two catalogs agree exactly (ex-VAT, 35% GM, 10% duty).
  3. DERIVES retail_sgd via the house SG-GST logic (shared/pricing_config.py:
     sg_nubo_gst_registered → multiplier; currently False → x1.0) and a FX rate
     coherent with the vendors NOK snapshot: THB per SGD = 3.5029 / 0.13776
     (NOK→SGD, same frankfurter 2026-06-05 date) = 25.4276.
  4. Writes a committed retail-structure JSON to rampline-catalog/parsed/.
  5. (--write-firestore) Upserts vendors/rampline/products/{code} with
     item_code + pricing.retail_{thb,usd,eur,sgd}/gross_margin/import_duty_rate/
     price_date so scripts/sync_brand_prices_to_medusa.py (brand rampline,
     SKU-matched) can push them to Medusa. Also refreshes the audit doc
     vendors/rampline/pricelists/2026-12-01.
  6. (--update-config) Sets pricing_config/canonical brands.rampline.gross_margin
     0.30 → 0.35 for house consistency.

NB: For Rampline we follow the task directive — retail_thb is EX-VAT (no 7% TH
customer VAT embedded), unlike the shared price_row() default which embeds it.
This keeps Rampline consistent with the vendors RRP comparison. Flagged in
BUILD_LOG so it can be revisited if VAT-inclusive parity is wanted later.

Usage:
    python rampline-catalog/build_2026_pricing.py                      # compute + write repo JSON only
    python rampline-catalog/build_2026_pricing.py --write-firestore    # + Firestore upsert
    python rampline-catalog/build_2026_pricing.py --write-firestore --update-config
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("rampline_2026_pricing")

BRAND = "rampline"
PRICE_DATE = "2026-12-01"          # price list effective date (eff. 2025-12-01 list)
PRICELIST_DOC_ID = "2026-12-01"

# --- Costing parameters (user-set 2026-06-07; flat stack, volumetric handled
# separately by the owner). Landed THB is recomputed from net_nok, NOT anchored
# to the vendors stack (which used 18% freight + fixed per-SKU clearance).
#   goods    = net_nok * NOK→THB
#   freight  = goods * 0.30                       (flat 30% of goods)
#   insurance= goods * 0.01
#   CIF      = goods + freight + insurance
#   duty     = CIF * 0.10
#   import_vat = (CIF + duty) * 0.07              (Thai import VAT, kept in landed)
#   clearance= goods * 0.06                       (flat 6% of goods)
#   landed   = CIF + duty + import_vat + clearance
#   retail_thb = landed / (1-GM) * (1 + TH customer VAT)   ← VAT-INCLUSIVE
#   retail_usd/eur/sgd = (landed / (1-GM)) / FX            ← ex customer-VAT
GROSS_MARGIN = 0.35
IMPORT_DUTY_RATE = 0.10
FREIGHT_PCT = 0.30
INSURANCE_PCT = 0.01
CLEARANCE_PCT = 0.06
IMPORT_VAT_RATE = 0.07
TH_CUSTOMER_VAT_RATE = 0.07        # embedded in retail_thb (VAT-inclusive)

# The "Kids Tramp" family (Loop trampolines, PlayPro rings, springs, jumping beds)
# are Eurotramp-manufactured items resold through the Rampline price list under
# IDENTICAL Eurotramp article codes (97010B, E97047, E31120, E21898B, ...). Those
# SKUs already exist as Eurotramp Medusa products (priced by the Eurotramp catalog),
# so pushing Rampline-stack prices (the list gives them 0% distributor discount →
# full RRP-as-cost, inflated) would clobber the correct Eurotramp prices. They are
# computed for reference but EXCLUDED from the Firestore products subcollection that
# feeds the Medusa price sync.
EUROTRAMP_OWNED_FAMILIES = {"Kids Tramp"}
PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
CONFIG_DB = "leka-product-catalogs"

# FX coherent with the vendors NOK snapshot (frankfurter.app 2026-06-05).
FX_SNAPSHOT = {
    "base": "NOK",
    "THB": 3.5029,
    "USD": 0.10734,
    "EUR": 0.09221,
    "SGD": 0.13776,
    "source": "frankfurter.app 2026-06-05",
}
NOK_THB = FX_SNAPSHOT["THB"]                                      # 3.5029
THB_PER_USD = round(FX_SNAPSHOT["THB"] / FX_SNAPSHOT["USD"], 6)   # 32.6337
THB_PER_EUR = round(FX_SNAPSHOT["THB"] / FX_SNAPSHOT["EUR"], 6)   # 37.9883
THB_PER_SGD = round(FX_SNAPSHOT["THB"] / FX_SNAPSHOT["SGD"], 6)   # 25.4276

# Default location of the vendors authoritative JSONs (overridable via --vendors-parsed).
DEFAULT_VENDORS_PARSED = (
    REPO_ROOT.parent / "vendors" / ".claude" / "worktrees"
    / "goofy-merkle-c70082" / "rampline-catalog" / "parsed"
)
OUT_JSON = REPO_ROOT / "rampline-catalog" / "parsed" / "rampline_pricing_2026.json"


def _doc_key(article_code: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", article_code.upper()).strip("_")


def _sg_gst_mult() -> tuple[float, bool]:
    """Replicate price_row()'s SG-GST logic from the house pricing_config."""
    try:
        from shared.pricing_config import get_pricing_config
        cfg = get_pricing_config(BRAND)
        registered = bool(cfg.get("sg_nubo_gst_registered", False))
        rate = float(cfg.get("sg_customer_gst_rate", 0.09))
    except Exception as e:  # offline / no ADC → house default (not registered)
        log.warning("pricing_config unreachable (%s) — SG GST not applied", e)
        registered, rate = False, 0.09
    return ((1.0 + rate) if registered else 1.0), registered


def load_rows(parsed_dir: Path) -> list[dict]:
    """Return normalized source rows (article_code, family, product_name,
    is_spare_part, net_nok, recommended_nok, discount_pct).

    Prefers the vendors parsed JSONs (pricelist.json + pricelist_landed.json);
    falls back to this repo's committed rampline_pricing_2026.json (which
    preserves net_nok for all 82 articles) so the recompute is reproducible
    even when the ephemeral vendors worktree is gone. net_nok is the only real
    input; everything downstream is recomputed here.
    """
    if (parsed_dir / "pricelist_landed.json").exists():
        pl = json.loads((parsed_dir / "pricelist.json").read_text(encoding="utf-8"))
        landed = json.loads((parsed_dir / "pricelist_landed.json").read_text(encoding="utf-8"))
        meta = {r["article_code"]: r for r in pl["rows"]}
        rows = []
        for lr in landed["rows"]:
            m = meta.get(lr["article_code"], {})
            rows.append({
                "article_code": lr["article_code"],
                "family": lr.get("family"),
                "product_name": lr.get("product_name") or m.get("product_name"),
                "is_spare_part": lr.get("is_spare_part", False),
                "net_nok": lr.get("net_nok") or m.get("net_nok"),
                "recommended_nok": m.get("recommended_nok"),
                "discount_pct": lr.get("discount_pct") or m.get("discount_pct"),
            })
        log.info("Loaded %d rows from vendors parsed JSONs (%s)", len(rows), parsed_dir)
        return rows
    if OUT_JSON.exists():
        d = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        rows = [{
            "article_code": r["article_code"],
            "family": r.get("family"),
            "product_name": r.get("product_name"),
            "is_spare_part": r.get("is_spare_part", False),
            "net_nok": r.get("net_nok"),
            "recommended_nok": r.get("recommended_nok"),
            "discount_pct": r.get("discount_pct"),
        } for r in d["rows"]]
        log.warning("vendors parsed dir absent — sourced net_nok from committed %s", OUT_JSON.name)
        return rows
    raise FileNotFoundError(
        f"No source data: neither {parsed_dir}/pricelist_landed.json nor {OUT_JSON} exists"
    )


def _landed_stack(net_nok: float) -> dict:
    """Flat NOK-direct landed cost stack (user params 2026-06-07)."""
    goods = net_nok * NOK_THB
    freight = goods * FREIGHT_PCT
    insurance = goods * INSURANCE_PCT
    cif = goods + freight + insurance
    duty = cif * IMPORT_DUTY_RATE
    import_vat = (cif + duty) * IMPORT_VAT_RATE
    clearance = goods * CLEARANCE_PCT
    landed = cif + duty + import_vat + clearance
    return {
        "goods_thb": round(goods, 2),
        "freight_thb": round(freight, 2),
        "insurance_thb": round(insurance, 2),
        "cif_thb": round(cif, 2),
        "duty_thb": round(duty, 2),
        "import_vat_thb": round(import_vat, 2),
        "clearance_thb": round(clearance, 2),
        "landed_thb": round(landed, 2),
    }


def compute(rows: list[dict]) -> list[dict]:
    sg_mult, sg_registered = _sg_gst_mult()
    th_vat_mult = 1.0 + TH_CUSTOMER_VAT_RATE
    records: list[dict] = []
    for lr in rows:
        code = lr["article_code"]
        meta = lr
        net_nok = lr.get("net_nok")
        stack = _landed_stack(net_nok)
        landed_thb = stack["landed_thb"]
        pretax = landed_thb / (1 - GROSS_MARGIN)            # ex customer-VAT base
        retail_thb = round(pretax * th_vat_mult, 2)         # VAT-INCLUSIVE
        retail_usd = round(pretax / THB_PER_USD, 2)         # ex customer-VAT
        retail_eur = round(pretax / THB_PER_EUR, 2)
        retail_sgd = round((pretax / THB_PER_SGD) * sg_mult, 2)
        excluded = lr.get("family") in EUROTRAMP_OWNED_FAMILIES
        records.append({
            "item_code": code,                              # exact Medusa variant SKU
            "article_code": code,
            "family": lr.get("family"),
            "product_name": lr.get("product_name") or meta.get("product_name"),
            "is_spare_part": lr.get("is_spare_part", False),
            "excluded_from_medusa": excluded,
            "excluded_reason": ("Eurotramp-owned family — priced by the Eurotramp catalog; "
                                "shares Eurotramp SKUs") if excluded else None,
            "net_nok": net_nok,
            "recommended_nok": meta.get("recommended_nok"),
            "discount_pct": lr.get("discount_pct"),
            "landed_thb": landed_thb,
            "cost_stack": stack,
            "pricing": {
                "retail_thb": retail_thb,
                "retail_usd": retail_usd,
                "retail_eur": retail_eur,
                "retail_sgd": retail_sgd,
                "gross_margin": GROSS_MARGIN,
                "import_duty_rate": IMPORT_DUTY_RATE,
                "freight_pct": FREIGHT_PCT,
                "clearance_pct": CLEARANCE_PCT,
                "price_date": PRICE_DATE,
                "landed_thb": landed_thb,
                "currency_basis": "THB VAT-INCLUSIVE (7%); USD/EUR/SGD ex customer-VAT; "
                                  "SG GST only if Nubo registered",
                "th_customer_vat_rate": TH_CUSTOMER_VAT_RATE,
                "sg_gst_applied": sg_registered,
                "fx_snapshot": FX_SNAPSHOT,
            },
        })
    return records


def write_repo_json(records: list[dict]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "brand": BRAND,
        "price_date": PRICE_DATE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gross_margin": GROSS_MARGIN,
        "import_duty_rate": IMPORT_DUTY_RATE,
        "freight_pct": FREIGHT_PCT,
        "insurance_pct": INSURANCE_PCT,
        "clearance_pct": CLEARANCE_PCT,
        "import_vat_rate": IMPORT_VAT_RATE,
        "th_customer_vat_rate": TH_CUSTOMER_VAT_RATE,
        "thb_per_usd": THB_PER_USD,
        "thb_per_eur": THB_PER_EUR,
        "thb_per_sgd": THB_PER_SGD,
        "fx_snapshot": FX_SNAPSHOT,
        "source": "Rampline 2026 NOK pricelist net_nok (eff. 2025-12-01); landed recomputed",
        "row_count": len(records),
        "notes": (
            "Flat landed stack (user params 2026-06-07): goods=net_nok*3.5029; "
            "freight=30%*goods; insurance=1%*goods; CIF=goods+freight+insurance; "
            "duty=10%*CIF; import_vat=7%*(CIF+duty); clearance=6%*goods; "
            "landed=CIF+duty+import_vat+clearance. retail_thb=landed/0.65*1.07 "
            "(35% GM, 7% TH customer VAT INCLUDED). retail_usd/eur/sgd=(landed/0.65)/FX "
            "(ex customer-VAT); SG GST x1.0 (Nubo not registered). Volumetric handled "
            "separately by owner."
        ),
        "rows": records,
    }
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Wrote %s (%d rows)", OUT_JSON, len(records))


def write_firestore(records: list[dict]) -> None:
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document(BRAND).collection("products")
    now = datetime.now(timezone.utc).isoformat()
    batch = db.batch()
    n = 0
    pushable = [r for r in records if not r.get("excluded_from_medusa")]
    skipped = [r["item_code"] for r in records if r.get("excluded_from_medusa")]
    if skipped:
        log.info("Excluding %d Eurotramp-owned articles from products subcollection: %s",
                 len(skipped), skipped)
    for rec in pushable:
        key = _doc_key(rec["item_code"])
        doc = dict(rec)
        doc["brand"] = BRAND
        doc["updated_at"] = now
        doc["price_source"] = "rampline 2026 NOK pricelist (eff. 2025-12-01)"
        batch.set(coll.document(key), doc, merge=True)
        n += 1
        if n % 400 == 0:
            batch.commit(); batch = db.batch()
    batch.commit()
    log.info("Firestore: upserted %d docs to vendors/%s/products", n, BRAND)

    # Refresh the audit doc (established brand-specific schema / provenance).
    audit = {
        "brand": BRAND,
        "pricelist_date": PRICE_DATE,
        "calculated_at": now,
        "source": "vendors pricelist_landed.json (35% GM / 10% duty, ex-VAT)",
        "gross_margin": GROSS_MARGIN,
        "import_duty_rate": IMPORT_DUTY_RATE,
        "fx_snapshot": FX_SNAPSHOT,
        "thb_per_sgd": THB_PER_SGD,
        "row_count": len(records),
        "currency_basis": "ex-VAT THB/USD/EUR; SGD via house SG-GST logic (x1.0)",
        "variants": {
            _doc_key(r["item_code"]): {
                "article_code": r["item_code"],
                "family": r["family"],
                "product_name": r["product_name"],
                "net_nok": r["net_nok"],
                "landed_thb": r["landed_thb"],
                "retail_thb": r["pricing"]["retail_thb"],
                "retail_usd": r["pricing"]["retail_usd"],
                "retail_eur": r["pricing"]["retail_eur"],
                "retail_sgd": r["pricing"]["retail_sgd"],
            }
            for r in records
        },
    }
    db.collection("vendors").document(BRAND).collection("pricelists").document(
        PRICELIST_DOC_ID
    ).set(audit, merge=True)
    log.info("Firestore: wrote audit doc vendors/%s/pricelists/%s", BRAND, PRICELIST_DOC_ID)


def update_config() -> None:
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=CONFIG_DB)
    ref = db.collection("pricing_config").document("canonical")
    snap = ref.get()
    if not snap.exists:
        log.error("pricing_config/canonical missing — skipping config update")
        return
    d = snap.to_dict()
    brands = d.get("brands") or {}
    ramp = dict(brands.get("rampline") or {})
    old = ramp.get("gross_margin")
    ramp["gross_margin"] = GROSS_MARGIN
    brands["rampline"] = ramp
    ref.set({
        "brands": brands,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "rampline 2026 price go-live (GM 0.30->0.35)",
    }, merge=True)
    log.info("pricing_config: brands.rampline.gross_margin %s -> %s", old, GROSS_MARGIN)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendors-parsed", type=Path, default=DEFAULT_VENDORS_PARSED)
    ap.add_argument("--write-firestore", action="store_true")
    ap.add_argument("--update-config", action="store_true")
    args = ap.parse_args()

    rows = load_rows(args.vendors_parsed)
    records = compute(rows)
    log.info("Computed %d Rampline articles (GM=%.0f%%, duty=%.0f%%, freight=%.0f%%, "
             "clearance=%.0f%%, retail_thb VAT-incl)", len(records), GROSS_MARGIN * 100,
             IMPORT_DUTY_RATE * 100, FREIGHT_PCT * 100, CLEARANCE_PCT * 100)
    for r in records[:3]:
        p = r["pricing"]
        log.info("  %-12s THB %.0f  USD %.2f  EUR %.2f  SGD %.2f",
                 r["item_code"], p["retail_thb"], p["retail_usd"], p["retail_eur"], p["retail_sgd"])
    write_repo_json(records)

    if args.write_firestore:
        write_firestore(records)
    if args.update_config:
        update_config()
    if not (args.write_firestore or args.update_config):
        log.info("Repo JSON only. Re-run with --write-firestore --update-config to push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
