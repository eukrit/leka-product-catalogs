"""Backfill multi-currency retail (THB/USD/EUR/SGD) on the Leka brands.

Recomputes the full landed → retail cascade for each in-scope brand straight
from the original-pricelist FOB captured on each Firestore doc, then writes
`pricing.retail_{thb,usd,eur,sgd}` back to `vendors/{slug}/products`. SGD is
added everywhere; THB/USD/EUR are recomputed against one consistent live-FX
snapshot so all currencies stay coherent (per user direction 2026-05-21:
"always refer to original pricelist and use pricing calculation to THB/SGD/USD
as target").

Per-brand source FOB and pricing path:
  vinci      eur_fob + stored dimensions → shared.price_row (dims-scaled / flat)
  berliner   eur_fob (post-EXW cost) + stored dims → shared.price_row
  designpark fob_usd (Korea LCL flat uplift) → ingest_designpark.price_designpark_row
  wisdom     fob_usd (China FOB flat) → shared.wisdom_pricing.compute_wisdom_retail
  rampline   audit doc vendors/rampline/pricelists/<latest>; retail_sgd derived
             from stored retail_thb. Medusa surfacing stays DEFERRED (per-variant
             migration not done) — this only refreshes the audit map.

Default is DRY-RUN (no writes): prints a sample spanning the price range, the
SGD distribution, and how much recompute drifts existing THB/USD vs stored.
Pass --write to persist.

Usage:
    python scripts/backfill_sgd_pricing.py --brand vinci
    python scripts/backfill_sgd_pricing.py --brand all
    python scripts/backfill_sgd_pricing.py --brand wisdom --write
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_TS = datetime.now(timezone.utc).isoformat()
BASIS_TAG = "backfill_sgd_2026-05-22"
BACKUP_DIR = Path(__file__).resolve().parent / "backfill_backups"

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ADC bootstrap — prefer the SA key present on this machine.
_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for c in _SA_CANDIDATES:
        if os.path.exists(c):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = c
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("backfill_sgd")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
BATCH = 400
EU_BRANDS = {"vinci", "berliner"}
USD_FLAT_BRANDS = {"designpark", "wisdom"}
SUPPORTED = ["vinci", "berliner", "designpark", "wisdom", "rampline"]


def _fc():
    from google.cloud import firestore
    return firestore.Client(project=PROJECT, database=VENDORS_DB)


def _dims_of(doc: dict) -> dict | None:
    """Return parsed {length,width,height}_cm or None. Mirrors the original
    importers, which coerce raw dimension strings via parse_dim."""
    from shared.landed_pricing import parse_dim
    d = doc.get("dimensions") or {}
    L = parse_dim(d.get("length_cm"))
    W = parse_dim(d.get("width_cm"))
    H = parse_dim(d.get("height_cm"))
    if L and W and H:
        return {"length_cm": L, "width_cm": W, "height_cm": H}
    return None


def _recompute_eu(slug, docs, fx, baltic):
    """vinci / berliner: recompute via shared.price_row from the original-pricelist
    cost basis + stored dims.

    Trade terms (verified 2026-05-22 against vendors DB + repo):
      vinci    — FOB, no discount. eur_fob is the pricelist FOB; use as-is.
      berliner — EXW. Cost = list_eur × (1 - exw_discount). We re-derive from
                 list_eur with the *current* config discount so the basis tracks
                 config rather than a frozen eur_fob (the two match today).
    """
    from shared.landed_pricing import price_row
    from shared.pricing_config import get_pricing_config
    exw_disc = float(get_pricing_config("berliner").get("exw_discount", 0.15)) if slug == "berliner" else 0.0
    rows = []
    for d in docs:
        p = d.get("pricing") or {}
        if slug == "berliner" and p.get("list_eur"):
            eur = round(float(p["list_eur"]) * (1 - exw_disc), 2)
        else:
            eur = p.get("eur_fob")
        if not eur or eur <= 0:
            continue
        code = d.get("item_code") or d.get("handle") or "?"
        dims = _dims_of(d)
        dim_index = {code: dims} if dims else {}
        pr = price_row(code, float(eur), dim_index, fx, baltic, brand=slug)
        rows.append({
            "doc_id": d["_id"], "code": code, "fob": float(eur), "fob_ccy": "EUR",
            "landed_thb": pr.landed_thb, "cbm_method": pr.cbm_method,
            "retail_thb": pr.retail_thb, "retail_usd": pr.retail_usd,
            "retail_eur": pr.retail_eur, "retail_sgd": pr.retail_sgd,
            "old_thb": p.get("retail_thb"), "old_usd": p.get("retail_usd"),
            "update": {
                "pricing.retail_thb": pr.retail_thb,
                "pricing.retail_usd": pr.retail_usd,
                "pricing.retail_eur": pr.retail_eur,
                "pricing.retail_sgd": pr.retail_sgd,
                "pricing.landed_thb": pr.landed_thb,
                "pricing.cbm_method": pr.cbm_method,
            },
        })
    return rows


def _recompute_designpark(docs, fx):
    from scripts.ingest_designpark_pricelist import price_designpark_row
    rows = []
    for d in docs:
        p = d.get("pricing") or {}
        fob = p.get("fob_usd")
        if not fob or fob <= 0:
            continue
        pr = price_designpark_row(float(fob), fx)
        rows.append({
            "doc_id": d["_id"], "code": d.get("item_code") or d.get("handle") or "?",
            "fob": float(fob), "fob_ccy": "USD",
            "landed_thb": pr["landed_thb"], "cbm_method": pr["method"],
            "retail_thb": pr["retail_thb"], "retail_usd": pr["retail_usd"],
            "retail_eur": pr.get("retail_eur"), "retail_sgd": pr["retail_sgd"],
            "old_thb": p.get("retail_thb"), "old_usd": p.get("retail_usd"),
            "update": {
                "pricing.retail_thb": pr["retail_thb"],
                "pricing.retail_usd": pr["retail_usd"],
                "pricing.retail_eur": pr["retail_eur"],
                "pricing.retail_sgd": pr["retail_sgd"],
                "pricing.landed_thb": pr["landed_thb"],
            },
        })
    return rows


def _recompute_wisdom(docs, fx):
    from shared.wisdom_pricing import compute_wisdom_retail, get_sgd_thb
    usd_thb = fx.get("USD", 35.0)
    sgd_thb = fx.get("SGD") or get_sgd_thb()
    rows = []
    for d in docs:
        p = d.get("pricing") or {}
        fob = p.get("fob_usd")
        if not fob or fob <= 0:
            continue
        r = compute_wisdom_retail(float(fob), usd_thb, sgd_thb)
        if not r:
            continue
        rows.append({
            "doc_id": d["_id"], "code": d.get("item_code") or d.get("handle") or "?",
            "fob": float(fob), "fob_ccy": "USD",
            "landed_thb": r.landed_thb, "cbm_method": "china_flat",
            "retail_thb": r.retail_thb, "retail_usd": r.retail_usd,
            "retail_eur": None, "retail_sgd": r.retail_sgd,
            "old_thb": p.get("retail_thb"), "old_usd": p.get("retail_usd"),
            "update": {
                "pricing.retail_thb": r.retail_thb,
                "pricing.retail_usd": r.retail_usd,
                "pricing.retail_sgd": r.retail_sgd,
                "pricing.landed_thb": r.landed_thb,
                "pricing.duty_thb": r.duty_thb,
                "pricing.vat_thb": r.vat_thb,
                "pricing.usd_thb": r.usd_thb,
                "pricing.sgd_thb": r.sgd_thb,
            },
        })
    return rows


def run_brand(slug: str, write: bool, sample_n: int = 10) -> dict:
    from shared.landed_pricing import calibrate_baltic_rate, get_fx_rates
    fx = get_fx_rates(buffer_pct=2)
    log.info("[%s] FX USD=%.4f EUR=%.4f SGD=%.4f source=%s",
             slug, fx.get("USD", 0), fx.get("EUR", 0), fx.get("SGD", 0), fx.get("_source"))

    if slug == "rampline":
        return _run_rampline(fx, write)

    baltic = calibrate_baltic_rate(fx) if slug in EU_BRANDS else None
    if baltic:
        log.info("[%s] Baltic LCL %.2f THB/CBM", slug, baltic["per_cbm_thb"])

    db = _fc()
    raw = list(db.collection("vendors").document(slug).collection("products").stream())
    docs = []
    for d in raw:
        dd = d.to_dict() or {}
        dd["_id"] = d.id
        docs.append(dd)
    log.info("[%s] %d product docs read", slug, len(docs))

    if slug in EU_BRANDS:
        rows = _recompute_eu(slug, docs, fx, baltic)
    elif slug == "designpark":
        rows = _recompute_designpark(docs, fx)
    elif slug == "wisdom":
        rows = _recompute_wisdom(docs, fx)
    else:
        raise SystemExit(f"unknown brand {slug}")

    _report(slug, rows)

    if write:
        _write_updates(db, slug, rows, fx)
    return {"brand": slug, "priced": len(rows), "written": len(rows) if write else 0}


def _run_rampline(fx, write):
    """Refresh retail_sgd on the latest rampline pricelist audit doc.

    Rampline prices live in vendors/rampline/pricelists/<date>.variants and do
    NOT surface in Medusa (per-variant migration deferred). We add retail_sgd
    derived from each variant's stored landed_thb at current FX — the canonical
    formula every brand uses (shared.landed_pricing / rampline-catalog importer).

    NOTE (fix 2026-06-02): previously this divided the VAT-inclusive retail_thb
    by the SGD rate, which baked Thailand's 7% domestic customer VAT into the
    SG/international price (retail_sgd came out 1.07x too high). SGD must be
    derived from the landed cost (pre-TH-VAT), matching every other brand.
    """
    from shared.pricing_config import get_pricing_config
    cfg = get_pricing_config("rampline")
    gm = float(cfg.get("gross_margin", 0.30))
    sg_gst_mult = (1 + float(cfg.get("sg_customer_gst_rate", 0.09))) \
        if bool(cfg.get("sg_nubo_gst_registered", False)) else 1.0

    db = _fc()
    pl = list(db.collection("vendors").document("rampline").collection("pricelists").stream())
    if not pl:
        log.warning("[rampline] no pricelist audit docs found")
        return {"brand": "rampline", "priced": 0, "written": 0}
    latest = sorted(pl, key=lambda d: d.id)[-1]
    data = latest.to_dict() or {}
    variants = data.get("variants") or {}
    sgd_thb = fx.get("SGD", 25.0)
    rows = []
    new_variants = {}
    skipped_no_landed = 0
    for key, v in variants.items():
        rt = v.get("retail_thb")
        lt = v.get("landed_thb")
        if not rt:
            new_variants[key] = v
            continue
        if not lt:
            # No landed cost stored → cannot derive SGD on the canonical base.
            # Leave the variant untouched rather than fall back to the wrong
            # (VAT-inclusive retail_thb) formula.
            skipped_no_landed += 1
            new_variants[key] = v
            continue
        # Canonical: SGD off landed cost (pre-TH-VAT), Nubo unregistered → no GST.
        sgd = round(((lt / sgd_thb) / (1 - gm)) * sg_gst_mult, 2)
        nv = dict(v)
        nv["retail_sgd"] = sgd
        new_variants[key] = nv
        rows.append({
            "doc_id": latest.id, "code": v.get("article_code") or key, "fob": v.get("eur_fob"),
            "fob_ccy": "EUR", "landed_thb": lt, "cbm_method": v.get("cbm_method"),
            "retail_thb": rt, "retail_usd": v.get("retail_usd"), "retail_eur": v.get("retail_eur"),
            "retail_sgd": sgd, "old_thb": rt, "old_usd": v.get("retail_usd"),
            "old_sgd": v.get("retail_sgd"),
        })
    if skipped_no_landed:
        log.warning("[rampline] %d variants skipped (no landed_thb stored — "
                    "cannot derive canonical SGD)", skipped_no_landed)
    _report("rampline", rows)
    # SGD-specific drift (the generic _report tracks THB, which is unchanged here).
    sgd_drifts = [d for r in rows if (d := _pct_drift(r["retail_sgd"], r.get("old_sgd"))) is not None]
    if sgd_drifts:
        print(f"  retail_sgd drift vs stored: mean Δ={statistics.mean(sgd_drifts):+.2f}%  "
              f"min={min(sgd_drifts):+.2f}%  max={max(sgd_drifts):+.2f}%  (n={len(sgd_drifts)})")
        print("  (≈0% + FX drift when the stored retail_thb is pre-VAT; ≈ -6.5% if a")
        print("   VAT-inclusive retail_thb was previously divided by SGD — 1/1.07-1.)")
    log.info("[rampline] Medusa surfacing DEFERRED — audit doc only (pricelists/%s)", latest.id)
    if write:
        _backup("rampline", rows)
        latest.reference.set({"variants": new_variants}, merge=True)
        log.info("[rampline] wrote retail_sgd on %d variants → pricelists/%s", len(rows), latest.id)
    return {"brand": "rampline", "priced": len(rows), "written": len(rows) if write else 0}


def _pct_drift(new, old):
    if not old or old == 0:
        return None
    return (new - old) / old * 100.0


def _report(slug: str, rows: list[dict]) -> None:
    if not rows:
        log.warning("[%s] nothing priced", slug)
        return
    rows_sorted = sorted(rows, key=lambda r: r["retail_thb"] or 0)
    n = len(rows_sorted)
    # Sample spanning the distribution: min, quartiles, max.
    idxs = sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1]))
    print(f"\n=== {slug.upper()} -- {n} priced (sample across price range) ===")
    print(f"{'code':22} {'FOB':>10} {'landedTHB':>10} {'rTHB':>10} {'rUSD':>9} {'rSGD':>9} {'THBdrift':>9} {'method':>12}")
    for i in idxs:
        r = rows_sorted[i]
        drift = _pct_drift(r["retail_thb"], r.get("old_thb"))
        drift_s = f"{drift:+.1f}%" if drift is not None else "  new"
        print(f"{str(r['code'])[:22]:22} {r['fob']:>10.2f} {(r['landed_thb'] or 0):>10.0f} "
              f"{(r['retail_thb'] or 0):>10.0f} {(r['retail_usd'] or 0):>9.2f} "
              f"{(r['retail_sgd'] or 0):>9.2f} {drift_s:>9} {str(r['cbm_method'])[:12]:>12}")
    sgds = [r["retail_sgd"] for r in rows if r["retail_sgd"]]
    drifts = [d for r in rows if (d := _pct_drift(r["retail_thb"], r.get("old_thb"))) is not None]
    print(f"  retail_sgd  min={min(sgds):,.2f}  median={statistics.median(sgds):,.2f}  max={max(sgds):,.2f}")
    if drifts:
        print(f"  THB recompute drift vs stored: mean |Δ|={statistics.mean([abs(d) for d in drifts]):.2f}%  "
              f"max |Δ|={max(abs(d) for d in drifts):.2f}%  (n={len(drifts)})")
    else:
        print("  (no prior retail_thb stored — all new)")


def _backup(slug, rows):
    """Dump the existing retail per affected doc before overwriting, so the
    recompute is reversible. One CSV per brand per run."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"{slug}_{RUN_TS.replace(':', '-')}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "code", "old_retail_thb", "old_retail_usd",
                    "new_retail_thb", "new_retail_usd", "new_retail_sgd"])
        for r in rows:
            w.writerow([r["doc_id"], r["code"], r.get("old_thb"), r.get("old_usd"),
                        r["retail_thb"], r["retail_usd"], r["retail_sgd"]])
    log.info("[%s] backup written: %s (%d rows)", slug, path.name, len(rows))


def _write_updates(db, slug, rows, fx):
    _backup(slug, rows)
    fx_snapshot = {k: fx.get(k) for k in ("USD", "EUR", "SGD", "THB")}
    prov = {
        "pricing.fx_snapshot": fx_snapshot,
        "pricing.fx_source": fx.get("_source"),
        "pricing.retail_basis": BASIS_TAG,
        "pricing.calculated_at": RUN_TS,
    }
    batch = db.batch()
    coll = db.collection("vendors").document(slug).collection("products")
    cnt = 0
    for r in rows:
        upd = dict(r["update"])
        upd.update(prov)
        batch.update(coll.document(r["doc_id"]), upd)
        cnt += 1
        if cnt % BATCH == 0:
            batch.commit()
            batch = db.batch()
            log.info("[%s] committed %d", slug, cnt)
    if cnt % BATCH:
        batch.commit()
    log.info("[%s] wrote %d docs", slug, cnt)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True, help="one of %s, or 'all'" % ", ".join(SUPPORTED))
    ap.add_argument("--write", action="store_true", help="persist (default: dry-run)")
    args = ap.parse_args()
    brands = SUPPORTED if args.brand == "all" else [args.brand]
    for b in brands:
        if b not in SUPPORTED:
            log.error("unsupported brand: %s", b)
            return 2
    mode = "WRITE" if args.write else "DRY-RUN"
    log.info("=== backfill_sgd_pricing mode=%s brands=%s ===", mode, brands)
    summary = []
    for b in brands:
        summary.append(run_brand(b, args.write))
    print("\n=== summary ===")
    for s in summary:
        print(f"  {s['brand']:12} priced={s['priced']:5}  written={s['written']:5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
