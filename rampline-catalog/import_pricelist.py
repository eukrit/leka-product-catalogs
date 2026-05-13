"""Rampline pricelist → landed cost → retail (THB/USD/EUR) → Firestore.

Reads the Rampline NOK pricelist (Drive xlsx), converts NOK→EUR via
open.er-api.com (live ECB rates), runs the shared landed-cost + 40% retail
pipeline (shared/landed_pricing.py — same formula as Vinci Play), and writes
the full priced map to vendors/rampline/pricelists/<PRICELIST_DATE>.

Medusa variant migration is intentionally deferred (decision 2026-05-13):
Rampline's 54 Medusa products each have a single "Default" variant keyed on
the WooCommerce numeric ID, while the pricelist exposes 127 article-level
SKUs (e.g. RB35, BP 34 LF) that don't yet exist as Medusa variants. Creating
those variants is a separate, larger migration; for now we only audit the
landed/retail map in Firestore.

Usage:
    python rampline-catalog/import_pricelist.py --dry-run --limit 10
    python rampline-catalog/import_pricelist.py
    python rampline-catalog/import_pricelist.py \\
        --pricelist rampline-catalog/data/source/rampline_pricelist_2025_fetched-2026-05-13.xlsx

Sheet layout (Rampline 2025 pricelist):
  Section header rows: col B = family name, col D = wholesale discount fraction.
  Column header rows: col A = 'Article'.
  Product rows: col A = SKU, col B = description, col C = recommended NOK,
                col D = discount NOK, col E = net (wholesale) NOK ← EXW.

Currency: NOK throughout. Pre-converted to EUR using frankfurter.app daily ECB
rate (cached for the run), then fed into the shared formula.

Dimensions: scraped from rampline.com via scripts/scrape-rampline.ts. Maps
depth_cm → length_cm to match the shared formula's (L, W, H) interface.
SKUs without scraped dims fall back to the 35% flat landed uplift.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAMPLINE_DIR = REPO_ROOT / "rampline-catalog"
OUTPUT_DIR = RAMPLINE_DIR / "data"
DIM_SOURCE = REPO_ROOT / "data" / "scraped" / "rampline" / "products.json"
DEFAULT_PRICELIST = (
    RAMPLINE_DIR / "data" / "source" / "rampline_pricelist_2025_fetched-2026-05-13.xlsx"
)
PRICELIST_DATE = "2026-05-13"
BRAND = "rampline"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from shared.landed_pricing import (  # noqa: E402
    GROSS_MARGIN,
    LOGISTICS_TIERS,
    PricedRow,
    calibrate_baltic_rate,
    get_fx_rates,
    parse_dim,
    price_row,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("rampline_pricelist")


# --- NOK → EUR conversion ---------------------------------------------------
# shipping-automation's get_fx_rates() does not include NOK, so we hit
# frankfurter.app (ECB-backed, no key) once per run and cache.
def fetch_nok_eur_rate() -> tuple[float, str]:
    """Return (EUR per NOK, source string) from a live FX API, with fallback.

    Tries open.er-api.com first (works without key), falls back to
    frankfurter.app, then to a hardcoded approximation. Cached per run by the
    caller; we never hit the network more than once.
    """
    sources = [
        ("open.er-api.com",
         "https://open.er-api.com/v6/latest/NOK",
         lambda d: (d["rates"]["EUR"], d.get("time_last_update_utc", "?"))),
        ("frankfurter.app",
         "https://api.frankfurter.app/latest?from=NOK&to=EUR",
         lambda d: (d["rates"]["EUR"], d.get("date", "?"))),
    ]
    for name, url, extract in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "leka-product-catalogs/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            rate, asof = extract(data)
            return float(rate), f"{name} {asof}"
        except Exception as e:
            log.warning("NOK→EUR via %s failed (%s); trying next", name, e)
    log.warning("All NOK→EUR live sources failed; using fallback 0.087")
    return 0.087, "fallback 0.087 (approx Apr 2026)"


# --- SKU normalization ------------------------------------------------------
# Pricelist SKUs: "RB35", "RB35 AG", "BP 34 LF". Scraped SKUs may use the
# same form or slugified form. Normalize to a canonical comparison key.
def normalize_sku(s: str) -> str:
    return re.sub(r"[\s\-_]+", "", str(s)).upper()


# --- Pricelist parser -------------------------------------------------------
def read_pricelist(path: Path) -> list[dict]:
    """Walk the xlsx, emit product rows tagged with their family + discount."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    out: list[dict] = []
    current_family = None
    current_discount = None
    for row_idx, r in enumerate(ws.iter_rows(values_only=True), start=1):
        if r is None:
            continue
        cells = list(r) + [None] * 5
        a, b, c, d, e = cells[0], cells[1], cells[2], cells[3], cells[4]
        # Family header
        if a is None and isinstance(b, str) and isinstance(d, (int, float)) and 0 < d < 1:
            current_family = b.replace("�", "®").strip()
            current_discount = float(d)
            continue
        # Column header
        if isinstance(a, str) and a.strip().lower() == "article":
            continue
        # Product row
        if (
            isinstance(a, str)
            and a.strip()
            and isinstance(e, (int, float))
            and e > 0
        ):
            sku = a.strip()
            out.append(
                {
                    "row": row_idx,
                    "sku": sku,
                    "description": (str(b).replace("�", "®").replace("\xa0", " ").strip() if b else ""),
                    "family": current_family,
                    "family_discount": current_discount,
                    "recommended_nok": float(c) if isinstance(c, (int, float)) else None,
                    "discount_nok": float(d) if isinstance(d, (int, float)) else None,
                    "net_nok": float(e),
                }
            )
    return out


# --- Dimension index --------------------------------------------------------
# Scraped output: dimensions.{height_cm, width_cm, depth_cm}. The shared
# formula expects {length_cm, width_cm, height_cm} — map depth_cm → length_cm.
def load_dim_index() -> dict[str, dict]:
    if not DIM_SOURCE.exists():
        log.warning(
            "Scraped dims not found at %s — all rows will use flat-uplift pricing. "
            "Run: npx tsx scripts/scrape-rampline.ts",
            DIM_SOURCE,
        )
        return {}
    products = json.loads(DIM_SOURCE.read_text(encoding="utf-8"))
    index: dict[str, dict] = {}
    for p in products:
        sku = str(p.get("sku") or "").strip()
        if not sku:
            continue
        dims = p.get("dimensions") or {}
        depth = parse_dim(dims.get("depth_cm"))
        width = parse_dim(dims.get("width_cm"))
        height = parse_dim(dims.get("height_cm"))
        # Key by both raw and normalized form so fuzzy_lookup can hit either.
        entry = {"length_cm": depth, "width_cm": width, "height_cm": height}
        index[sku] = entry
        norm = normalize_sku(sku)
        if norm != sku:
            index[norm] = entry
    return index


# --- CSV output -------------------------------------------------------------
def write_csv(priced: list[PricedRow], parsed: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    by_sku = {p.item_code: p for p in priced}
    fieldnames = (
        list(asdict(priced[0]).keys())
        + ["family", "family_discount", "recommended_nok", "net_nok", "description"]
    )
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in parsed:
            sku = row["sku"]
            pr = by_sku.get(sku)
            if not pr:
                continue
            out = asdict(pr)
            out.update(
                {
                    "family": row["family"],
                    "family_discount": row["family_discount"],
                    "recommended_nok": row["recommended_nok"],
                    "net_nok": row["net_nok"],
                    "description": row["description"],
                }
            )
            w.writerow(out)


# --- Firestore write --------------------------------------------------------
# We do NOT create per-article Firestore docs because Rampline's Medusa setup
# has 54 family-level products with single "Default" variants — the 127 article
# codes here are pricelist-only. Per design decision 2026-05-13: write one
# audit doc per pricelist date under `vendors/rampline/pricelists/<date>` with
# the full landed/retail map. Medusa variant migration is deferred.
def _fs_value(v):
    """Encode a Python scalar to the Firestore REST value union."""
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: _fs_value(x) for k, x in v.items()}}}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_fs_value(x) for x in v]}}
    return {"stringValue": str(v)}


def _sa_access_token() -> str:
    """Mint a short-lived access token for Firestore REST.

    Prefers LEKA_FIRESTORE_ACCESS_TOKEN (set by caller via gcloud), falls back
    to ADC via google-auth. We avoid shelling out to gcloud here because on
    Windows `gcloud.CMD` invoked through Python subprocess can lose its
    profile-bound credential state — bash-invoked tokens are more reliable.
    """
    tok = os.environ.get("LEKA_FIRESTORE_ACCESS_TOKEN")
    if tok:
        return tok
    try:
        import google.auth
        import google.auth.transport.requests
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/datastore"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    except Exception as e:
        raise RuntimeError(
            "No Firestore access token available. Export "
            "LEKA_FIRESTORE_ACCESS_TOKEN=$(gcloud auth print-access-token "
            "--account codex-chatgpt@ai-agents-go.iam.gserviceaccount.com) or "
            "set up ADC for this project."
        ) from e


def write_firestore(
    priced: list[PricedRow],
    parsed_by_sku: dict[str, dict],
    fx: dict,
    nok_eur: tuple[float, str],
    baltic: dict,
):
    import urllib.error
    import urllib.request

    now = datetime.now(timezone.utc).isoformat()
    nok_eur_rate, nok_eur_source = nok_eur

    variants_map: dict[str, dict] = {}
    for r in priced:
        sku = r.item_code
        parsed = parsed_by_sku.get(sku, {})
        # Firestore field keys can't contain "/" — sanitize SKU for the map key
        # while keeping the original in a field.
        key = re.sub(r"[^A-Z0-9]+", "_", sku.upper()).strip("_")
        variants_map[key] = {
            "article_code": sku,
            "description": parsed.get("description"),
            "family": parsed.get("family"),
            "family_discount": parsed.get("family_discount"),
            "recommended_nok": parsed.get("recommended_nok"),
            "net_nok": parsed.get("net_nok"),
            "eur_fob": r.eur_fob,
            "landed_thb": r.landed_thb,
            "landed_thb_raw": r.landed_thb_raw,
            "logistics_pct": r.logistics_pct,
            "logistics_clamp": r.logistics_clamp,
            "retail_thb": r.retail_thb,
            "retail_usd": r.retail_usd,
            "retail_eur": r.retail_eur,
            "cbm_used": r.cbm,
            "cbm_method": r.cbm_method,
            "freight_thb": r.freight_thb,
            "duty_thb": r.duty_thb,
            "vat_thb": r.vat_thb,
            "match_strategy": r.match_strategy,
        }

    payload = {
        "fields": {
            k: _fs_value(v)
            for k, v in {
                "brand": BRAND,
                "pricelist_date": PRICELIST_DATE,
                "calculated_at": now,
                "source_file": str(DEFAULT_PRICELIST.name),
                "sheet_name": "Price list 2025",
                "row_count": len(priced),
                "gross_margin": GROSS_MARGIN,
                "nok_eur_rate": nok_eur_rate,
                "nok_eur_source": nok_eur_source,
                "fx_snapshot": {k: fx.get(k) for k in ("USD", "EUR", "THB")},
                "fx_source": fx.get("_source"),
                "baltic_rate_snapshot": baltic,
                "logistics_tiers": [
                    {"fob_eur_max": t[0] if t[0] != float("inf") else None,
                     "min_pct": t[1], "max_pct": t[2]}
                    for t in LOGISTICS_TIERS
                ],
                "variants": variants_map,
                "medusa_status": "deferred - per-variant migration not yet done",
            }.items()
        }
    }

    # Use REST so we don't need ADC bootstrapped on this machine.
    token = _sa_access_token()
    doc_id = PRICELIST_DATE
    url = (
        f"https://firestore.googleapis.com/v1/projects/ai-agents-go/"
        f"databases/vendors/documents/vendors/{BRAND}/pricelists/{doc_id}"
    )
    req = urllib.request.Request(
        url,
        method="PATCH",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        log.error("Firestore PATCH failed: %s\n%s", e, e.read().decode("utf-8", "replace"))
        raise
    log.info(
        "Firestore: wrote %d variants to vendors/%s/pricelists/%s",
        len(variants_map), BRAND, doc_id,
    )


# --- Main -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pricelist", type=Path, default=DEFAULT_PRICELIST)
    ap.add_argument("--dry-run", action="store_true",
                    help="Write CSV only; do not touch Firestore.")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--packing-factor", type=float, default=0.15)
    args = ap.parse_args()

    log.info("Pricelist: %s", args.pricelist)
    parsed = read_pricelist(args.pricelist)
    if args.limit:
        parsed = parsed[: args.limit]
    log.info("Loaded %d pricelist rows", len(parsed))

    nok_eur_rate, nok_eur_source = fetch_nok_eur_rate()
    log.info("NOK→EUR: %.6f (%s)", nok_eur_rate, nok_eur_source)

    dim_index = load_dim_index()
    log.info("Loaded %d scraped Rampline dim entries", len(dim_index))

    fx = get_fx_rates(buffer_pct=2)
    log.info("FX (USD=%.4f EUR=%.4f) source=%s",
             fx.get("USD", 0), fx.get("EUR", 0), fx.get("_source"))

    baltic = calibrate_baltic_rate(fx)
    log.info("Baltic LCL rate: %.2f THB/CBM (sources=%d)",
             baltic["per_cbm_thb"], len(baltic["sources"]))

    priced: list[PricedRow] = []
    for row in parsed:
        sku = row["sku"]
        eur = row["net_nok"] * nok_eur_rate
        # Allow fuzzy_lookup inside price_row to also hit the normalized form.
        dim_index_for_call = dict(dim_index)
        norm = normalize_sku(sku)
        if norm in dim_index_for_call and sku not in dim_index_for_call:
            dim_index_for_call[sku] = dim_index_for_call[norm]
        priced.append(
            price_row(sku, eur, dim_index_for_call, fx, baltic, args.packing_factor)
        )

    by_strategy: dict[str, int] = {}
    for r in priced:
        by_strategy[r.match_strategy] = by_strategy.get(r.match_strategy, 0) + 1
    log.info("Match strategy counts: %s", by_strategy)

    out_csv = OUTPUT_DIR / f"pricelist_{PRICELIST_DATE}_landed.csv"
    write_csv(priced, parsed, out_csv)
    log.info("Wrote CSV: %s (%d rows)", out_csv, len(priced))

    if args.dry_run:
        log.info("DRY RUN — Firestore not touched.")
        for r in priced[:5]:
            log.info(
                "  %s  NOK_net=%.0f → EUR %.2f  CBM %.3f  landed %.0f THB  "
                "retail %.0f THB / $%.2f",
                r.item_code,
                next((p["net_nok"] for p in parsed if p["sku"] == r.item_code), 0),
                r.eur_fob, r.cbm, r.landed_thb, r.retail_thb, r.retail_usd,
            )
        return

    parsed_by_sku = {p["sku"]: p for p in parsed}
    write_firestore(priced, parsed_by_sku, fx, (nok_eur_rate, nok_eur_source), baltic)
    log.info(
        "Done. Audit doc: vendors/rampline/pricelists/%s. Medusa variant push "
        "intentionally deferred until per-article variants are created.",
        PRICELIST_DATE,
    )


if __name__ == "__main__":
    main()
