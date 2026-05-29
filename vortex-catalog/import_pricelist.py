"""Parse Vortex's 2026 USD price list (PDF) → vendors/vortex/products docs,
with per-product-LINE reseller discounts and the shared landed-cost pipeline.

Pricing model (Vortex = EXW Pointe-Claire, Quebec, Canada; USD):
  1. line          = collection → top-level product line (vortex_config)
  2. our_cost_usd  = list_usd × (1 - line_discount)        # EXW cost we pay
  3. fob_usd       = our_cost_usd
  4. landed_thb    = flat-uplift CIF (1.35) + 10% non-China duty + 7% import VAT
                     (the 2026 pricelist carries no dimensions, so every SKU
                     uses the flat-uplift path — same as DesignPark/WePlay).
                     Vinci tier floor/cap clamp then applies (USD→EUR-equiv band).
  5. retail_thb    = (landed / (1-gm)) × 1.07  (TH customer VAT, THB only)
     retail_usd/eur/sgd derived independently from the same landed cost.

Also merges the canonical `brands.vortex` block into
`pricing_config/canonical` (deep-merge; leaves other brands intact) — mirrors
the WePlay importer's `brands.weplay seed` pattern.

Idempotent. Merge-writes only. Provenance per doc:
  source_pricelist: "<file>:page<N>:row<N>"
  product_number / item_code (VOR-<zero-padded>) / collection / product_line /
  line_discount / pricing.*

Usage:
    python vortex-catalog/import_pricelist.py --dry-run
    python vortex-catalog/import_pricelist.py --apply
    python vortex-catalog/import_pricelist.py --dry-run --dump-csv=/tmp/vortex.csv
    python vortex-catalog/import_pricelist.py --apply --skip-config   # prices only
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ADC bootstrap (mirrors ingest_designpark_pricelist.py).
_LOCAL_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for cand in _LOCAL_SA_CANDIDATES:
        if os.path.exists(cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402

from shared.landed_pricing import (  # noqa: E402
    DUTY_RATE_NON_CHINA,
    SG_CUSTOMER_GST_RATE,
    SG_NUBO_GST_REGISTERED,
    THAI_VAT_RATE,
    TH_CUSTOMER_VAT_RATE,
    UNMATCHED_LANDED_UPLIFT,
    LOGISTICS_TIERS,
    get_fx_rates,
    logistics_band,
)
from shared.pricing_config import get_pricing_config  # noqa: E402

# Canonical maps (single source of truth shared with seed_pricing_config.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vortex_config as vc  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("import_vortex_pricelist")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
CONFIG_DB = "leka-product-catalogs"
SLUG = "vortex"
CATEGORY = "water_play"
FORMULA_VERSION = "vortex-v1-2026-05-29"

# Cross-machine source path (Eukrit / eukri profiles).
_PDF_CANDIDATES = [
    Path(r"C:\Users\Eukrit\My Drive\Partners Playground\Vortex\2026-04-22 Vortex 2026_USD_Price List_R2 (1).pdf"),
    Path(r"C:\Users\eukri\My Drive\Partners Playground\Vortex\2026-04-22 Vortex 2026_USD_Price List_R2 (1).pdf"),
]


def _resolve_pdf() -> Path:
    env = os.environ.get("VORTEX_PRICELIST_PDF")
    if env and Path(env).exists():
        return Path(env)
    for p in _PDF_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Vortex 2026 pricelist PDF not found. Set VORTEX_PRICELIST_PDF or place "
        f"it at one of: {[str(p) for p in _PDF_CANDIDATES]}")


_SLUG_BAD = re.compile(r"[^a-z0-9]+")
_PRICE_RE = re.compile(r"[^\d.]")
_NUMERIC_CODE = re.compile(r"\d{1,4}")


def slugify(text: str) -> str:
    return _SLUG_BAD.sub("-", (text or "").lower()).strip("-") or "unknown"


def medusa_sku(product_number: str) -> str:
    """Vortex Medusa variant SKUs are VOR-<code>; bare numeric catalog numbers
    are zero-padded to 4 digits (e.g. 623 → VOR-0623, 3501 → VOR-3501)."""
    code = str(product_number).strip()
    if _NUMERIC_CODE.fullmatch(code):
        return "VOR-" + code.zfill(4)
    return "VOR-" + code


def parse_price(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = _PRICE_RE.sub("", str(raw))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def parse_pdf(pdf_path: Path) -> list[dict]:
    """Extract product rows. Columns: Product Number | Product Name | Collection | USD Price."""
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for r in table:
                    if not r or len(r) < 4:
                        continue
                    pn, name, coll, price = [(c or "").strip().replace("\n", " ") for c in r[:4]]
                    if not pn or pn.lower().startswith("product") or coll.lower() == "collection":
                        continue
                    list_usd = parse_price(price)
                    rows.append({
                        "product_number": pn,
                        "name": name or pn,
                        "collection": coll,
                        "list_usd": list_usd,
                        "source_pricelist": f"{pdf_path.name}:page{pi}",
                    })
    log.info("parsed %d product rows from %s", len(rows), pdf_path.name)
    return rows


# --- Pricing ---------------------------------------------------------------
def _vortex_params() -> dict:
    cfg = get_pricing_config(SLUG) or {}
    tiers_raw = cfg.get("logistics_tiers")
    if tiers_raw:
        tiers = [
            (float("inf") if t.get("fob_eur_max") in (None, "inf") else float(t["fob_eur_max"]),
             float(t["min_pct"]), float(t["max_pct"]))
            for t in tiers_raw
        ]
    else:
        tiers = LOGISTICS_TIERS
    return {
        "gross_margin": float(cfg.get("gross_margin", vc.GROSS_MARGIN)),
        "duty_rate_non_china": float(cfg.get("duty_rate_non_china", DUTY_RATE_NON_CHINA)),
        "thai_vat_rate": float(cfg.get("thai_vat_rate", THAI_VAT_RATE)),
        "th_customer_vat_rate": float(cfg.get("th_customer_vat_rate", TH_CUSTOMER_VAT_RATE)),
        "unmatched_landed_uplift": float(cfg.get("unmatched_landed_uplift", UNMATCHED_LANDED_UPLIFT)),
        "sg_customer_gst_rate": float(cfg.get("sg_customer_gst_rate", SG_CUSTOMER_GST_RATE)),
        "sg_nubo_gst_registered": bool(cfg.get("sg_nubo_gst_registered", SG_NUBO_GST_REGISTERED)),
        "line_discounts": cfg.get("line_discounts") or dict(vc.LINE_DISCOUNTS),
        "collection_to_line": cfg.get("collection_to_line") or dict(vc.COLLECTION_TO_LINE),
        "tiers": tiers,
    }


def price_vortex_row(list_usd: float, collection: str, fx: dict, p: dict) -> dict:
    """USD list → per-line reseller discount → EXW cost → landed THB → retail."""
    line = vc.COLLECTION_TO_LINE.get(vc.normalize_collection(collection))
    if line is None:
        line = vc.DEFAULT_LINE
        log.warning("unknown collection %r → defaulting to %s", collection, line)
    line_disc = float(p["line_discounts"].get(line, 0.0))
    our_cost_usd = round(list_usd * (1 - line_disc), 2)

    usd_thb = fx.get("USD", 35.0)
    eur_thb = fx.get("EUR", 38.0)
    sgd_thb = fx.get("SGD", 25.0)
    gm = p["gross_margin"]

    fob_usd = our_cost_usd
    fob_thb = fob_usd * usd_thb
    cif_thb = fob_thb * p["unmatched_landed_uplift"]
    freight_thb = cif_thb - fob_thb
    duty_thb = round(cif_thb * p["duty_rate_non_china"], 2)
    vat_thb = round((cif_thb + duty_thb) * p["thai_vat_rate"], 2)
    landed_raw = round(cif_thb + duty_thb + vat_thb, 2)

    # Vinci tier clamp, evaluated in the EUR-equivalent FOB band (DesignPark approach).
    eur_fob_equiv = fob_usd * usd_thb / eur_thb
    lo_pct, hi_pct = logistics_band(eur_fob_equiv, p["tiers"])
    floor_landed = fob_thb * (1 + lo_pct)
    cap_landed = fob_thb * (1 + hi_pct)
    clamp = ""
    landed_thb = landed_raw
    if landed_thb < floor_landed:
        landed_thb, clamp = floor_landed, "floored"
    elif landed_thb > cap_landed:
        landed_thb, clamp = cap_landed, "capped"
    landed_thb = round(landed_thb, 2)

    th_vat_mult = 1.0 + p["th_customer_vat_rate"]
    retail_thb = round((landed_thb / (1 - gm)) * th_vat_mult, 2)
    retail_usd = round((landed_thb / usd_thb) / (1 - gm), 2)
    retail_eur = round((landed_thb / eur_thb) / (1 - gm), 2)
    sg_mult = (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    retail_sgd = round(((landed_thb / sgd_thb) / (1 - gm)) * sg_mult, 2)

    return {
        "product_line": line,
        "line_discount": line_disc,
        "list_usd": round(list_usd, 2),
        "our_cost_usd": our_cost_usd,
        "fob_usd": fob_usd,
        "fob_thb": round(fob_thb, 2),
        "freight_thb": round(freight_thb, 2),
        "duty_thb": duty_thb,
        "vat_thb": vat_thb,
        "landed_thb": landed_thb,
        "landed_thb_raw": landed_raw,
        "logistics_clamp": clamp,
        "retail_thb": retail_thb,
        "retail_usd": retail_usd,
        "retail_eur": retail_eur,
        "retail_sgd": retail_sgd,
        "gross_margin": gm,
        "th_customer_vat_rate": p["th_customer_vat_rate"],
        "logistics_uplift": round(p["unmatched_landed_uplift"] - 1, 4),
        "method": "flat_uplift_canada_exw",
        "formula_version": FORMULA_VERSION,
    }


def build_doc(row: dict, fx: dict, p: dict) -> dict:
    pn = row["product_number"]
    handle = f"vortex-{slugify(pn)}"
    doc = {
        "handle": handle,
        "slug": SLUG,
        "name": row["name"],
        "product_number": pn,
        "item_code": medusa_sku(pn),           # matches Medusa variant SKU (VOR-…)
        "collection": row["collection"],
        "category": CATEGORY,
        "source_pricelist": row["source_pricelist"],
    }
    if row.get("list_usd") and row["list_usd"] > 0:
        doc["pricing"] = price_vortex_row(row["list_usd"], row["collection"], fx, p)
        doc["product_line"] = doc["pricing"]["product_line"]
        doc["status"] = "active_priced"
    else:
        doc["product_line"] = vc.line_for_collection(row["collection"])
        doc["pricing"] = {"list_usd": 0.0, "method": "no_price_in_pricelist",
                          "formula_version": FORMULA_VERSION}
        doc["status"] = "draft_no_price"
    return doc


# --- Firestore writes ------------------------------------------------------
def write_products(docs: list[dict], dry: bool) -> int:
    if dry:
        log.info("[DRY] would write %d docs to vendors/%s/products", len(docs), SLUG)
        return len(docs)
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document(SLUG).collection("products")
    batch = db.batch()
    pending = n = 0
    for d in docs:
        batch.set(coll.document(d["handle"]), d, merge=True)
        pending += 1
        n += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()
    return n


def merge_brand_config(dry: bool) -> None:
    """Deep-merge brands.vortex into pricing_config/canonical (mirrors WePlay)."""
    body = vc.brand_config()
    if dry:
        log.info("[DRY] would merge pricing_config/canonical.brands.vortex "
                 "(gm=%.2f, lines=%s)", body["gross_margin"], list(body["line_discounts"]))
        return
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT, database=CONFIG_DB)
    db.collection("pricing_config").document("canonical").set({
        "brands": {"vortex": body},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "vortex-catalog/import_pricelist.py (brands.vortex seed)",
    }, merge=True)
    log.info("merged pricing_config/canonical.brands.vortex")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-config", action="store_true",
                    help="Do not write brands.vortex to pricing_config/canonical.")
    ap.add_argument("--dump-csv", type=str, default=None)
    args = ap.parse_args()
    dry = args.dry_run

    pdf_path = _resolve_pdf()
    fx = get_fx_rates()
    log.info("FX snapshot: USD=%.4f THB/USD EUR=%.4f SGD=%.4f", fx.get("USD", 0), fx.get("EUR", 0), fx.get("SGD", 0))

    # Config first so price_row reads the freshly-merged brand block on --apply.
    if not args.skip_config:
        merge_brand_config(dry)
        if not dry:
            from shared.pricing_config import reset_cache
            reset_cache()

    p = _vortex_params()
    log.info("vortex params: gm=%.2f line_discounts=%s", p["gross_margin"], p["line_discounts"])

    rows = parse_pdf(pdf_path)
    if args.limit:
        rows = rows[: args.limit]

    docs = [build_doc(r, fx, p) for r in rows]

    # Coverage report by line.
    from collections import Counter
    by_line = Counter(d["product_line"] for d in docs)
    log.info("line coverage: %s", dict(by_line))
    priced = [d for d in docs if d["status"] == "active_priced"]
    log.info("priced %d / %d (%d no-price)", len(priced), len(docs), len(docs) - len(priced))

    if args.dump_csv:
        out = Path(args.dump_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["handle", "item_code", "product_number", "name", "collection",
                        "product_line", "line_discount", "list_usd", "our_cost_usd",
                        "landed_thb", "retail_thb", "retail_usd", "retail_sgd", "clamp"])
            for d in docs:
                pr = d.get("pricing", {})
                w.writerow([d["handle"], d["item_code"], d["product_number"], d["name"],
                            d["collection"], d.get("product_line"), pr.get("line_discount"),
                            pr.get("list_usd"), pr.get("our_cost_usd"), pr.get("landed_thb"),
                            pr.get("retail_thb"), pr.get("retail_usd"), pr.get("retail_sgd"),
                            pr.get("logistics_clamp")])
        log.info("wrote audit CSV: %s", out)

    if dry:
        log.info("[DRY] sample:")
        for d in priced[:6]:
            pr = d["pricing"]
            log.info("  %s | %s | %s | %s | list=$%s disc=%.0f%% cost=$%s → retail $%s / ฿%s",
                     d["item_code"], d["name"][:28], d["collection"][:16], pr["product_line"],
                     pr["list_usd"], pr["line_discount"] * 100, pr["our_cost_usd"],
                     pr["retail_usd"], pr["retail_thb"])

    n = write_products(docs, dry)
    log.info("%s %d docs → vendors/%s/products", "[DRY]" if dry else "wrote", n, SLUG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
