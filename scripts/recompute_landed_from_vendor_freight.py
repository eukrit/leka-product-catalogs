"""Recompute landed cost + retail (THB/USD/EUR/SGD) for SKUs that now carry a
real, vendor-sourced per-SKU freight cost — then write the new retail back to
`vendors/<brand>/products` so scripts/sync_brand_prices_to_medusa.py can push it.

This is the LAST step of the cross-repo per-SKU freight pipeline:

    shipping-automation  →  refresh Europe DDP LCL rates + add a ddp_air method
    vendors (sync_freight.py --write)  →  writes pricing.freight_thb +
        pricing.packing_source (vendor_email/_attachment/_pricelist) on the SKUs
        that have CONFIRMED vendor packing data
    THIS script  →  for exactly those SKUs, re-run shared.landed_pricing.price_row
        with the real freight (instead of the CBM estimate / 1.35x flat uplift),
        write back pricing.{landed_thb,landed_thb_raw,retail_thb/usd/eur/sgd,…}
    sync_brand_prices_to_medusa.py  →  pushes the new retail to Medusa

GATED BY DESIGN. Only docs whose `pricing.packing_source` is a real vendor source
(shared.landed_pricing.VENDOR_PACKING_SOURCES) AND that carry a positive
`pricing.freight_thb` are touched. Every other SKU is left on its existing
estimate — so running this before the upstream vendors sync is a safe no-op.

Usage:
    python scripts/recompute_landed_from_vendor_freight.py --brand all --dry-run
    python scripts/recompute_landed_from_vendor_freight.py --brand rampline --write
    python scripts/recompute_landed_from_vendor_freight.py --brand vinci --write --limit 5

Auth: ADC for the ai-agents-go project (Firestore DB `vendors`).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("recompute_landed")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
BRANDS = ("vinci", "vortex", "rampline")

from shared.landed_pricing import (  # noqa: E402
    VENDOR_PACKING_SOURCES,
    calibrate_baltic_rate,
    get_fx_rates,
    price_row,
)

# Cache live NOK→EUR (only fetched if a Rampline doc lacks a stored EUR FOB).
_nok_eur_cache: tuple[float, str] | None = None


def _firestore():
    from google.cloud import firestore
    return firestore.Client(project=PROJECT, database=VENDORS_DB)


def _nok_eur() -> float:
    global _nok_eur_cache
    if _nok_eur_cache is None:
        try:
            from rampline_catalog_import import fetch_nok_eur_rate  # type: ignore
        except Exception:
            # Reuse the proven fetcher from the Rampline pricelist builder.
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_rampline_imp", REPO_ROOT / "rampline-catalog" / "import_pricelist.py")
            mod = importlib.util.module_from_spec(spec)  # type: ignore
            spec.loader.exec_module(mod)  # type: ignore
            _nok_eur_cache = mod.fetch_nok_eur_rate()
        else:
            _nok_eur_cache = fetch_nok_eur_rate()
    return _nok_eur_cache[0]


def _resolve_eur_fob(brand: str, pricing: dict, fx: dict) -> tuple[float | None, str]:
    """Return (eur_equivalent_fob, source) so price_row's fob_thb = eur*EUR_THB is
    correct regardless of the brand's native FOB currency.

    - vinci    : pricing.eur_fob (already EUR)
    - rampline : pricing.eur_fob if present, else from_net_nok * NOK→EUR
    - vortex   : pricing.eur_fob if present, else fob_usd→EUR-equivalent at FX
                 (Canada/USD origin — DDP-EUR premise is unconfirmed; logged)
    """
    eur = pricing.get("eur_fob") or pricing.get("eur_fob_2026")
    if eur:
        return float(eur), "eur_fob"
    if brand == "rampline":
        nok = pricing.get("from_net_nok") or pricing.get("net_nok")
        if nok:
            return round(float(nok) * _nok_eur(), 2), "from_net_nok*nok_eur"
    if brand == "vortex":
        usd = pricing.get("fob_usd") or pricing.get("our_cost_usd")
        if usd:
            usd_thb = fx.get("USD", 35.0)
            eur_thb = fx.get("EUR", 38.0)
            # EUR-equivalent that reproduces the correct THB FOB: fob_thb = usd*USD_THB.
            return round(float(usd) * usd_thb / eur_thb, 2), "fob_usd→eur_equiv"
    return None, "unresolved"


def run_brand(db, brand: str, fx: dict, baltic: dict, write: bool, limit: int | None) -> dict:
    coll = db.collection("vendors").document(brand).collection("products")
    now = datetime.now(timezone.utc).isoformat()
    fx_snap = {k: fx.get(k) for k in ("USD", "EUR", "SGD")}

    scanned = eligible = updated = skipped_fob = 0
    for snap in coll.stream():
        scanned += 1
        d = snap.to_dict() or {}
        pr = d.get("pricing") or {}
        freight = pr.get("freight_thb")
        source = pr.get("packing_source")
        if not (freight and float(freight) > 0 and source in VENDOR_PACKING_SOURCES):
            continue  # not vendor-sourced → leave on existing estimate
        eligible += 1
        if limit and eligible > limit:
            eligible -= 1
            break

        code = d.get("item_code") or d.get("sku") or snap.id
        eur, eur_src = _resolve_eur_fob(brand, pr, fx)
        if not eur:
            skipped_fob += 1
            log.warning("[%s] %s eligible but no resolvable EUR FOB (pricing keys=%s) — skipped",
                        brand, code, sorted(pr.keys()))
            continue

        row = price_row(
            str(code), float(eur), {}, fx, baltic, brand=brand,
            vendor_freight_thb=float(freight),
            vendor_freight_method=pr.get("freight_method"),
            vendor_packing_source=source,
        )
        log.info("[%s] %s  EUR=%.2f(%s) freight=%.0f → landed_raw=%.0f landed=%.0f%s "
                 "retail THB=%.0f USD=%.2f EUR=%.2f SGD=%.2f",
                 brand, code, eur, eur_src, row.freight_thb, row.landed_thb_raw,
                 row.landed_thb, f" [{row.logistics_clamp}]" if row.logistics_clamp else "",
                 row.retail_thb, row.retail_usd, row.retail_eur, row.retail_sgd)

        if not write:
            continue
        snap.reference.update({
            "pricing.landed_thb": row.landed_thb,
            "pricing.landed_thb_raw": row.landed_thb_raw,
            "pricing.logistics_pct": row.logistics_pct,
            "pricing.logistics_clamp": row.logistics_clamp,
            "pricing.retail_thb": row.retail_thb,
            "pricing.retail_usd": row.retail_usd,
            "pricing.retail_eur": row.retail_eur,
            "pricing.retail_sgd": row.retail_sgd,
            "pricing.retail_basis": f"vendor_freight_recompute:{now[:10]}",
            "pricing.recompute_fx_snapshot": fx_snap,
            "pricing.recomputed_at": now,
        })
        updated += 1

    log.info("[%s] scanned=%d eligible=%d updated=%d skipped_no_fob=%d (%s)",
             brand, scanned, eligible, updated, skipped_fob,
             "WROTE" if write else "dry-run")
    return {"brand": brand, "scanned": scanned, "eligible": eligible,
            "updated": updated, "skipped_no_fob": skipped_fob}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True, help="one of %s, or 'all'" % ", ".join(BRANDS))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="(default intent) no Firestore writes")
    g.add_argument("--write", action="store_true", help="write recomputed retail back to Firestore")
    ap.add_argument("--limit", type=int, default=None, help="cap eligible docs per brand")
    args = ap.parse_args()

    brands = list(BRANDS) if args.brand == "all" else [args.brand]
    for b in brands:
        if b not in BRANDS:
            log.error("unknown brand %s (choices: %s, all)", b, ", ".join(BRANDS))
            return 2

    fx = get_fx_rates(buffer_pct=2)
    log.info("FX USD=%.4f EUR=%.4f SGD=%.4f source=%s",
             fx.get("USD", 0), fx.get("EUR", 0), fx.get("SGD", 0), fx.get("_source"))
    baltic = calibrate_baltic_rate(fx)  # unused by the vendor-freight branch; required arg

    db = _firestore()
    summary = [run_brand(db, b, fx, baltic, args.write, args.limit) for b in brands]

    print("\n=== summary ===")
    total_elig = total_upd = 0
    for s in summary:
        total_elig += s["eligible"]; total_upd += s["updated"]
        print(f"  {s['brand']:9} scanned={s['scanned']:5} eligible={s['eligible']:4} "
              f"updated={s['updated']:4} skipped_no_fob={s['skipped_no_fob']:3}")
    if total_elig == 0:
        print("\n  0 vendor-sourced freight SKUs found — nothing to recompute. This is the")
        print("  expected state until vendors/scripts/sync_freight.py --write populates")
        print("  pricing.freight_thb + pricing.packing_source for confirmed vendor packing data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
