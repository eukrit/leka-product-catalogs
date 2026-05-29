"""WePlay (Kiddie's Paradise Inc., Taiwan) pricelist → landed cost → retail
(THB / USD / SGD) → Firestore `vendors/weplay/products`.

Source quotation (verified 2026-05-29):
  C:\\Users\\Eukrit\\My Drive\\Partners Playground\\Weplay\\
    2025-11-05 Quotation - AQ1251030077 - Go Corporation (Standard Item).pdf

Trade terms (read straight off the quotation header — these ARE GO Corp's
negotiated reseller prices, there is NO list-price/discount split):
  * Vendor    : Kiddie's Paradise Inc. / WePlay, Taipei, Taiwan
  * Incoterm  : FOB TAIWAN
  * Currency  : U.S. DOLLARS (net unit price per item)
  * Origin    : TAIWAN  → 10% Thai import duty (non-FTA) + 7% import VAT
  * Payment   : T/T in advance ; Lead time 30-45 days
  * MOQ       : full master carton per item ; MOV USD 10,000 / shipment
  * Columns   : ITEM NO | DESCRIPTION | UNIT PRICE USD / UNIT |
                master-carton PACK qty | carton CBM | carton G.W. (kg)

Cost cascade (per SKU) — Taiwan/USD path, route-correct sibling of the
EU `shared/landed_pricing.price_row()` and the China-USD `shared/wisdom_pricing`:

    per_unit_cbm = carton_cbm / pack_qty            (carton CBM is per master carton)
    fob_thb      = fob_usd * USD_THB
    freight_thb  = per_unit_cbm * SEA_LCL_PER_CBM_THB        (CBM path)
                 = fob_thb * (UNMATCHED_LANDED_UPLIFT - 1)   (flat-uplift fallback, no CBM)
    cif_thb      = fob_thb + freight_thb
    duty_thb     = cif_thb * IMPORT_DUTY_RATE                (0.10, Taiwan non-FTA)
    import_vat   = (cif_thb + duty_thb) * THAI_VAT_RATE      (0.07, embedded in landed)
    landed_thb   = cif_thb + duty_thb + import_vat
    retail_thb   = landed_thb / (1 - GROSS_MARGIN)           (TH retail is VAT-inclusive
                                                              per the 2026-05-17 convention)
    retail_usd   = retail_thb / USD_THB
    retail_sgd   = retail_thb * sg_gst_mult / SGD_THB        (GST gated on Nubo registration)

Config source of truth: Firestore `pricing_config/canonical`, brands.weplay
(+ global), editable via the gateway-served form. Module constants below are
only the offline fallback and MUST stay in sync with scripts/seed_pricing_config.py.

Idempotent, merge-only. Matches the existing `vendors/weplay/products` docs by
SKU token (same boundary-less `[A-Z]{2}\\d{4,}` token used by every other
WePlay ingest pass) and writes the `pricing.retail_thb/usd/sgd` + audit fields
that scripts/sync_vendors_to_medusa.py then pushes to the WePlay sales channel.

Usage:
    python weplay-catalog/import_pricelist.py --dry-run
    python weplay-catalog/import_pricelist.py --dry-run --dump-csv weplay-catalog/data/pricelist_landed.csv
    python weplay-catalog/import_pricelist.py --apply
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# --- ADC bootstrap (cross-machine) -----------------------------------------
_ADC_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\Eukrit\AppData\Roaming\gcloud\legacy_credentials\codex-chatgpt@ai-agents-go.iam.gserviceaccount.com\adc.json",
    r"C:\Users\eukri\AppData\Roaming\gcloud\legacy_credentials\codex-chatgpt@ai-agents-go.iam.gserviceaccount.com\adc.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ or not os.path.exists(
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
):
    for _cand in _ADC_CANDIDATES:
        if os.path.exists(_cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

from shared.landed_pricing import (  # noqa: E402
    DUTY_RATE_NON_CHINA,
    THAI_VAT_RATE,
    UNMATCHED_LANDED_UPLIFT,
    get_fx_rates,
)
from shared.pricing_config import get_pricing_config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("weplay_pricelist")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "weplay"
QUOTATION_REF = "AQ1251030077"
QUOTATION_DATE = "2025-10-30"
FORMULA_VERSION = "weplay-v1-2026-05-29"

# --- Module-level fallbacks (Firestore brands.weplay is source of truth) ----
GROSS_MARGIN = 0.50                 # confirmed by user 2026-05-29
IMPORT_DUTY_RATE = DUTY_RATE_NON_CHINA   # 0.10 — Taiwan is non-FTA for Thailand
TH_CUSTOMER_VAT_RATE = 0.07         # embedded in retail_thb only (TH domestic)
INSURANCE_RATE = 0.01               # marine insurance on FOB, per the master cascade
# Ocean LCL Kaohsiung → Laem Chabang, THB per CBM. Conservative static rate;
# refine via pricing_config brands.weplay.sea_lcl_per_cbm_thb. WePlay cartons
# are small (mostly < 0.2 CBM each, high pack qty) so per-unit freight is minor.
SEA_LCL_PER_CBM_THB = 5500.0
DEFAULT_USD_THB = 33.0
DEFAULT_SGD_THB = 26.0

# Cross-machine source PDF (Eukrit / eukri profiles).
_PDF_CANDIDATES = [
    Path(r"C:\Users\Eukrit\My Drive\Partners Playground\Weplay"
         r"\2025-11-05 Quotation - AQ1251030077 - Go Corporation (Standard Item).pdf"),
    Path(r"C:\Users\eukri\My Drive\Partners Playground\Weplay"
         r"\2025-11-05 Quotation - AQ1251030077 - Go Corporation (Standard Item).pdf"),
]
DEFAULT_PDF = next((p for p in _PDF_CANDIDATES if p.exists()), _PDF_CANDIDATES[0])

OUTPUT_DIR = REPO_ROOT / "weplay-catalog" / "data"

# Boundary-less SKU token — must match KM1003 inside 6800KM1003 (cross-doc
# lookup), identical to scripts/ingest_weplay_quotation_aq1251030077.py.
SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")

# Quotation line: SKU  DESCRIPTION  PRICE / UNIT  PACK  CBM  G.W. [REMARK]
LINE_RE = re.compile(
    r"^(?P<sku>[A-Z]{2}\d{3,}(?:[.\-][A-Z0-9]+)*)"
    r"\s+(?P<desc>.+?)"
    r"\s+(?P<price>[\d,]+\.\d{2})"
    r"\s*/\s*(?P<unit>[A-Z]+)"
    r"\s+(?P<pack>[\d.]+)"
    r"\s+(?P<cbm>[\d.]+)"
    r"\s+(?P<gw>[\d.]+)"
    r"(?:\s+.*)?$"
)


# --- Resolved params -------------------------------------------------------
def _weplay_params() -> dict:
    cfg = get_pricing_config(SLUG)
    return {
        "gross_margin": float(cfg.get("gross_margin", GROSS_MARGIN)),
        "import_duty_rate": float(cfg.get("import_duty_rate", IMPORT_DUTY_RATE)),
        "thai_vat_rate": float(cfg.get("thai_vat_rate", THAI_VAT_RATE)),
        # TH customer VAT (7%) is embedded in retail_thb only — it is a Thai
        # domestic tax, so USD/SGD international prices exclude it (v2.31.0 rule).
        "th_customer_vat_rate": float(cfg.get("th_customer_vat_rate", TH_CUSTOMER_VAT_RATE)),
        "sea_lcl_per_cbm_thb": float(cfg.get("sea_lcl_per_cbm_thb", SEA_LCL_PER_CBM_THB)),
        "unmatched_landed_uplift": float(cfg.get("unmatched_landed_uplift", UNMATCHED_LANDED_UPLIFT)),
        "sg_customer_gst_rate": float(cfg.get("sg_customer_gst_rate", 0.09)),
        "sg_nubo_gst_registered": bool(cfg.get("sg_nubo_gst_registered", False)),
    }


# --- PDF parser ------------------------------------------------------------
@dataclass
class QuoteRow:
    sku: str
    sku_token: str
    name: str
    fob_usd: float
    unit: str
    pack_qty: float
    carton_cbm: float
    gross_weight_kg: float
    page: int


def parse_pdf(path: Path) -> list[QuoteRow]:
    import pdfplumber

    rows: list[QuoteRow] = []
    with pdfplumber.open(path) as pdf:
        for pn, page in enumerate(pdf.pages, start=1):
            for raw in (page.extract_text() or "").split("\n"):
                line = raw.strip()
                m = LINE_RE.match(line)
                if not m:
                    continue
                sku = m.group("sku").upper()
                tok = SKU_TOKEN_RE.search(sku)
                if not tok:
                    continue
                desc = m.group("desc").strip()
                if len(desc) < 3:
                    continue
                try:
                    price = float(m.group("price").replace(",", ""))
                    pack = float(m.group("pack"))
                    cbm = float(m.group("cbm"))
                    gw = float(m.group("gw"))
                except ValueError:
                    continue
                rows.append(QuoteRow(
                    sku=sku, sku_token=tok.group(1), name=desc,
                    fob_usd=price, unit=m.group("unit"),
                    pack_qty=pack, carton_cbm=cbm, gross_weight_kg=gw, page=pn,
                ))
    log.info("parsed %d quotation rows from %s", len(rows), path.name)
    return rows


def aggregate(rows: list[QuoteRow]) -> dict[str, QuoteRow]:
    """One QuoteRow per SKU token. When several rows share a token (e.g.
    KC0004 / KC0004-032 / KC0004-065) keep the row whose SKU matches the token
    most exactly (shortest SKU)."""
    by_token: dict[str, QuoteRow] = {}
    for r in rows:
        cur = by_token.get(r.sku_token)
        if cur is None or len(r.sku) < len(cur.sku):
            by_token[r.sku_token] = r
    return by_token


# --- Pricing cascade -------------------------------------------------------
@dataclass
class PricedRow:
    sku: str
    sku_token: str
    fob_usd: float
    unit: str
    pack_qty: float
    carton_cbm: float
    per_unit_cbm: float
    usd_thb: float
    sgd_thb: float
    fob_thb: float
    freight_thb: float
    insurance_thb: float
    cif_thb: float
    duty_thb: float
    import_vat_thb: float
    landed_thb: float
    retail_thb: float
    retail_usd: float
    retail_sgd: float
    method: str


def price_row(q: QuoteRow, fx: dict, p: dict) -> PricedRow:
    usd_thb = float(fx.get("USD") or DEFAULT_USD_THB)
    sgd_thb = float(fx.get("SGD") or DEFAULT_SGD_THB)

    per_unit_cbm = (q.carton_cbm / q.pack_qty) if (q.pack_qty and q.carton_cbm) else 0.0
    fob_thb = q.fob_usd * usd_thb

    if per_unit_cbm > 0:
        freight_thb = per_unit_cbm * p["sea_lcl_per_cbm_thb"]
        method = "cbm_lcl"
    else:
        freight_thb = fob_thb * (p["unmatched_landed_uplift"] - 1.0)
        method = "flat_uplift"

    insurance_thb = fob_thb * INSURANCE_RATE
    cif_thb = fob_thb + freight_thb + insurance_thb
    duty_thb = cif_thb * p["import_duty_rate"]
    import_vat_thb = (cif_thb + duty_thb) * p["thai_vat_rate"]
    landed_thb = cif_thb + duty_thb + import_vat_thb

    # Retail — independent per-currency derivation (matches shared/wisdom_pricing,
    # the canonical v2.31.0 convention). The 7% TH customer VAT is a Thai domestic
    # tax embedded in retail_thb ONLY; USD/SGD are international prices without it.
    gm = p["gross_margin"]
    th_vat_mult = 1.0 + p["th_customer_vat_rate"]
    retail_thb = (landed_thb / (1 - gm)) * th_vat_mult
    retail_usd = (landed_thb / usd_thb) / (1 - gm)
    sg_mult = (1 + p["sg_customer_gst_rate"]) if p["sg_nubo_gst_registered"] else 1.0
    retail_sgd = ((landed_thb / sgd_thb) / (1 - gm)) * sg_mult

    return PricedRow(
        sku=q.sku, sku_token=q.sku_token, fob_usd=round(q.fob_usd, 2), unit=q.unit,
        pack_qty=q.pack_qty, carton_cbm=q.carton_cbm,
        per_unit_cbm=round(per_unit_cbm, 6),
        usd_thb=round(usd_thb, 4), sgd_thb=round(sgd_thb, 4),
        fob_thb=round(fob_thb, 2), freight_thb=round(freight_thb, 2),
        insurance_thb=round(insurance_thb, 2),
        cif_thb=round(cif_thb, 2), duty_thb=round(duty_thb, 2),
        import_vat_thb=round(import_vat_thb, 2), landed_thb=round(landed_thb, 2),
        retail_thb=round(retail_thb, 2), retail_usd=round(retail_usd, 2),
        retail_sgd=round(retail_sgd, 2), method=method,
    )


def pricing_map(pr: PricedRow, p: dict) -> dict:
    """The Firestore `pricing.*` sub-map written per matched product doc.
    Merges over the existing pricing map (quote_2025_usd etc. preserved)."""
    return {
        "fob_usd": pr.fob_usd,
        "currency": "USD",
        "incoterm": "FOB TAIWAN",
        "origin_country": "TW",
        "pack_qty": pr.pack_qty,
        "carton_cbm": pr.carton_cbm,
        "per_unit_cbm": pr.per_unit_cbm,
        "usd_thb": pr.usd_thb,
        "sgd_thb": pr.sgd_thb,
        "fob_thb": pr.fob_thb,
        "freight_thb": pr.freight_thb,
        "insurance_thb": pr.insurance_thb,
        "cif_thb": pr.cif_thb,
        "duty_thb": pr.duty_thb,
        "import_duty_rate": p["import_duty_rate"],
        "import_vat_thb": pr.import_vat_thb,
        "thai_vat_rate": p["thai_vat_rate"],
        "th_customer_vat_rate": p["th_customer_vat_rate"],
        "landed_thb": pr.landed_thb,
        "gross_margin": p["gross_margin"],
        "retail_thb": pr.retail_thb,
        "retail_usd": pr.retail_usd,
        "retail_sgd": pr.retail_sgd,
        "freight_method": pr.method,
        "sea_lcl_per_cbm_thb": p["sea_lcl_per_cbm_thb"],
        "price_date": QUOTATION_DATE,
        "quote_ref": QUOTATION_REF,
        "formula_version": FORMULA_VERSION,
    }


# --- CSV audit dump --------------------------------------------------------
def write_csv(priced: dict[str, PricedRow], names: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "sku_token", "name", "fob_usd", "unit", "pack_qty",
                    "carton_cbm", "per_unit_cbm", "freight_thb", "duty_thb",
                    "import_vat_thb", "landed_thb", "retail_thb", "retail_usd",
                    "retail_sgd", "method"])
        for tok, pr in sorted(priced.items()):
            w.writerow([pr.sku, tok, names.get(tok, ""), pr.fob_usd, pr.unit,
                        pr.pack_qty, pr.carton_cbm, pr.per_unit_cbm, pr.freight_thb,
                        pr.duty_thb, pr.import_vat_thb, pr.landed_thb, pr.retail_thb,
                        pr.retail_usd, pr.retail_sgd, pr.method])
    log.info("wrote audit CSV: %s (%d rows)", path, len(priced))


# --- Firestore writeback ---------------------------------------------------
def writeback(priced: dict[str, PricedRow], p: dict, dry_run: bool) -> dict:
    from google.cloud import firestore

    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    coll = db.collection("vendors").document(SLUG).collection("products")

    # Index existing docs by SKU token (search item_code).
    token_to_docs: dict[str, list] = {}
    total = 0
    for snap in coll.stream():
        total += 1
        d = snap.to_dict() or {}
        m = SKU_TOKEN_RE.search((d.get("item_code") or "").upper())
        if m:
            token_to_docs.setdefault(m.group(1), []).append(snap)
    log.info("scanned %d weplay docs; %d unique SKU tokens indexed", total, len(token_to_docs))

    counters = {"priced_tokens": len(priced), "matched_tokens": 0,
                "no_doc_match": 0, "doc_writes": 0}
    no_match = []
    batch = db.batch()
    batch_n = 0
    for tok, pr in priced.items():
        targets = token_to_docs.get(tok, [])
        if not targets:
            counters["no_doc_match"] += 1
            if len(no_match) < 15:
                no_match.append(f"{pr.sku} ${pr.fob_usd}")
            continue
        counters["matched_tokens"] += 1
        pmap = pricing_map(pr, p)
        for snap in targets:
            existing = (snap.to_dict() or {}).get("pricing") or {}
            merged = dict(existing)
            merged.update(pmap)
            payload = {
                "pricing": merged,
                "quotation_refs": firestore.ArrayUnion([QUOTATION_REF]),
            }
            counters["doc_writes"] += 1
            if not dry_run:
                batch.set(snap.reference, payload, merge=True)
                batch_n += 1
                if batch_n >= 200:
                    batch.commit()
                    batch = db.batch()
                    batch_n = 0
    if not dry_run and batch_n:
        batch.commit()

    log.info("=== writeback summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    if no_match:
        log.info("sample tokens with no matching doc: %s", ", ".join(no_match))
    return counters


# --- Main ------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dump-csv", type=Path, default=None)
    args = ap.parse_args()

    log.info("=== weplay import_pricelist mode=%s ===", "WRITE" if args.apply else "DRY-RUN")
    if not args.pdf.exists():
        log.error("quotation PDF not found: %s", args.pdf)
        return 2

    rows = parse_pdf(args.pdf)
    by_token = aggregate(rows)
    log.info("aggregated %d unique SKU tokens from %d rows", len(by_token), len(rows))

    fx = get_fx_rates()
    log.info("FX: USD=%.4f SGD=%.4f source=%s", fx.get("USD", 0), fx.get("SGD", 0), fx.get("_source"))
    p = _weplay_params()
    log.info("params: GM=%.2f duty=%.2f import_vat=%.2f sea_lcl=%.0f THB/CBM sg_gst_registered=%s",
             p["gross_margin"], p["import_duty_rate"], p["thai_vat_rate"],
             p["sea_lcl_per_cbm_thb"], p["sg_nubo_gst_registered"])

    tokens = list(by_token.items())
    if args.limit:
        tokens = tokens[: args.limit]
    priced: dict[str, PricedRow] = {tok: price_row(q, fx, p) for tok, q in tokens}
    names = {tok: q.name for tok, q in by_token.items()}

    by_method: dict[str, int] = {}
    for pr in priced.values():
        by_method[pr.method] = by_method.get(pr.method, 0) + 1
    log.info("freight method counts: %s", by_method)
    for pr in list(priced.values())[:6]:
        log.info("  %-14s $%-9.2f /%s pack=%g cbm=%g  landed %.0f THB  retail %.0f THB / $%.2f / S$%.2f",
                 pr.sku, pr.fob_usd, pr.unit, pr.pack_qty, pr.carton_cbm,
                 pr.landed_thb, pr.retail_thb, pr.retail_usd, pr.retail_sgd)

    if args.dump_csv:
        write_csv(priced, names, args.dump_csv)

    writeback(priced, p, dry_run=not args.apply)
    log.info("done (%s).", "WROTE" if args.apply else "dry-run, no Firestore writes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
