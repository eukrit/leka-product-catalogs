"""Compare old (TH-derived) vs new (SG-landed) Wisdom retail_sgd.

Dry-run only. Does NOT write Firestore, does NOT touch Medusa. Loads a
representative sample from products_wisdom, computes both pricings, and
writes a markdown report to scripts/reports/sg_pricing_compare_<DATE>.md.

Old SG retail = today's value computed by compute_wisdom_retail() —
landed_thb (Thai freight + 7% TH VAT) / sgd_thb / 0.50.

New SG retail = compute_wisdom_retail_sg() — real Xiamen→Singapore landed
cost (china_to_singapore route, 9% SG GST) / 0.50.

Usage:
    python scripts/compare_sg_pricing.py
    python scripts/compare_sg_pricing.py --limit 25 --strategy spread
    python scripts/compare_sg_pricing.py --strategy by-category
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ADC bootstrap — mirror the pattern in backfill_sgd_pricing.py.
_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-claude-sa.json",
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\GCP Credentials\ai-agents-go-claude.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\GCP Credentials\ai-agents-go-claude.json",
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

from shared.wisdom_pricing import (  # noqa: E402
    compute_wisdom_retail,
    compute_wisdom_retail_sg,
    get_usd_thb,
    get_sgd_thb,
    get_usd_sgd,
)

GCP_PROJECT = "ai-agents-go"
CATALOG_DB = "leka-product-catalogs"
COLLECTION = "products_wisdom"
REPORT_DIR = REPO_ROOT / "scripts" / "reports"


def _fs_client():
    from google.cloud import firestore
    return firestore.Client(project=GCP_PROJECT, database=CATALOG_DB)


def _extract_cbm(d: dict) -> float:
    dims = d.get("dimensions") or {}
    try:
        l_cm = float(dims.get("length_cm") or 0)
        w_cm = float(dims.get("width_cm") or 0)
        h_cm = float(dims.get("height_cm") or 0)
        if l_cm > 0 and w_cm > 0 and h_cm > 0:
            return round(l_cm * w_cm * h_cm / 1_000_000.0 * 0.15, 4)
    except (TypeError, ValueError):
        pass
    return 0.0


def _sample_spread(rows: list[dict], n: int) -> list[dict]:
    """Stratified sample across the FOB price range.

    Splits priced rows into ~equal-size FOB-USD bands and pulls the median
    item from each. Falls back to a head-slice if there are fewer rows
    than requested.
    """
    if len(rows) <= n:
        return rows
    rows_sorted = sorted(rows, key=lambda r: r["fob_usd"])
    out: list[dict] = []
    band_size = len(rows_sorted) / n
    for i in range(n):
        idx = int(i * band_size + band_size / 2)
        out.append(rows_sorted[min(idx, len(rows_sorted) - 1)])
    return out


def _sample_by_category(rows: list[dict], n: int) -> list[dict]:
    """One SKU per top-level category, then fill the remainder by spread."""
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        cat = (r.get("category") or "uncategorized").split(">")[0].strip()
        by_cat.setdefault(cat, []).append(r)
    out: list[dict] = []
    for cat, cat_rows in sorted(by_cat.items()):
        cat_rows.sort(key=lambda r: r["fob_usd"])
        out.append(cat_rows[len(cat_rows) // 2])
        if len(out) >= n:
            break
    if len(out) < n:
        # Top up with spread across all remaining rows.
        seen = {r["item_code"] for r in out}
        remaining = [r for r in rows if r["item_code"] not in seen]
        out.extend(_sample_spread(remaining, n - len(out)))
    return out[:n]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=10,
                    help="Sample size (default 10)")
    ap.add_argument("--strategy", choices=["spread", "by-category", "head"],
                    default="spread",
                    help="Sampling strategy (default spread)")
    ap.add_argument("--report-dir", default=str(REPORT_DIR),
                    help="Output directory for the markdown report")
    args = ap.parse_args()

    usd_thb = get_usd_thb()
    sgd_thb = get_sgd_thb()
    usd_sgd = get_usd_sgd()
    print(f"FX: USD/THB={usd_thb:.4f}  SGD/THB={sgd_thb:.4f}  USD/SGD={usd_sgd:.4f}")

    db = _fs_client()
    print(f"Loading {COLLECTION} from Firestore (db={CATALOG_DB})...")
    docs = list(db.collection(COLLECTION).stream())
    print(f"  {len(docs)} documents total")

    rows: list[dict] = []
    for doc in docs:
        d = doc.to_dict() or {}
        item_code = d.get("item_code") or doc.id
        pricing = d.get("pricing") or {}
        fob = pricing.get("fob_usd") or pricing.get("fob_usd_us")
        if not fob:
            continue
        rows.append({
            "item_code": item_code,
            "fob_usd": float(fob),
            "cbm": _extract_cbm(d),
            "kg": float(d.get("weight_kg") or 0.0),
            "category": d.get("category") or "",
            "name": (d.get("name") or "")[:60],
        })
    print(f"  {len(rows)} rows with fob_usd")

    if not rows:
        print("Nothing to compare.", file=sys.stderr)
        return 1

    if args.strategy == "head":
        sample = rows[: args.limit]
    elif args.strategy == "by-category":
        sample = _sample_by_category(rows, args.limit)
    else:
        sample = _sample_spread(rows, args.limit)
    print(f"  Sampled {len(sample)} SKUs via strategy={args.strategy}\n")

    # Compute both pricings per sample row.
    results: list[dict] = []
    for r in sample:
        th = compute_wisdom_retail(
            r["fob_usd"], usd_thb=usd_thb, sgd_thb=sgd_thb,
            cbm=r["cbm"], kg=r["kg"],
        )
        sg = compute_wisdom_retail_sg(
            r["fob_usd"], cbm=r["cbm"], kg=r["kg"],
            usd_sgd=usd_sgd, sgd_thb=sgd_thb,
        )
        if not th or not sg:
            continue
        old_sgd = th.retail_sgd
        new_sgd = sg.retail_sgd
        delta_pct = (new_sgd - old_sgd) / old_sgd * 100 if old_sgd else 0.0
        results.append({
            **r,
            "old_sgd": old_sgd,
            "new_sgd": new_sgd,
            "delta_pct": delta_pct,
            "freight_sgd": sg.freight_sgd,
            "gst_sgd": sg.gst_sgd,
            "landed_sgd": sg.landed_sgd,
            "cbm_method_sg": sg.cbm_method,
            "clamp_sg": sg.logistics_clamp,
            "clamp_th": th.logistics_clamp,
        })

    # Markdown report.
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    report_path = report_dir / f"sg_pricing_compare_{today}.md"

    deltas = [r["delta_pct"] for r in results]
    higher = sum(1 for d in deltas if d > 0)
    lower = sum(1 for d in deltas if d < 0)
    flag = [r for r in results if abs(r["delta_pct"]) > 25]

    lines: list[str] = []
    lines.append(f"# Wisdom SG retail — old (TH-derived) vs new (SG-landed)")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).isoformat()} by "
                 f"scripts/compare_sg_pricing.py — dry-run, no writes._")
    lines.append("")
    lines.append("## FX snapshot")
    lines.append(f"- USD/THB: `{usd_thb:.4f}`")
    lines.append(f"- SGD/THB: `{sgd_thb:.4f}`")
    lines.append(f"- USD/SGD: `{usd_sgd:.4f}`")
    lines.append("")
    lines.append(f"## Sample ({len(results)} SKUs, strategy={args.strategy})")
    lines.append("")
    lines.append(
        "| item_code | fob_usd | cbm | old retail_sgd (TH-derived) "
        "| new retail_sgd (SG-landed) | Δ% | freight_sgd | gst_sgd "
        "| landed_sgd | cbm_method | clamp |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"
    )
    for r in results:
        clamp = (
            f"sg:{r['clamp_sg']}" if r["clamp_sg"] else ""
        ) + (
            f" th:{r['clamp_th']}" if r["clamp_th"] else ""
        )
        lines.append(
            f"| `{r['item_code']}` "
            f"| {r['fob_usd']:.2f} "
            f"| {r['cbm']:.3f} "
            f"| {r['old_sgd']:.2f} "
            f"| {r['new_sgd']:.2f} "
            f"| {r['delta_pct']:+.1f}% "
            f"| {r['freight_sgd']:.2f} "
            f"| {r['gst_sgd']:.2f} "
            f"| {r['landed_sgd']:.2f} "
            f"| {r['cbm_method_sg']} "
            f"| {clamp.strip() or '—'} |"
        )
    lines.append("")
    lines.append("## Aggregate")
    if deltas:
        lines.append(f"- mean Δ%:   `{statistics.mean(deltas):+.2f}%`")
        lines.append(f"- median Δ%: `{statistics.median(deltas):+.2f}%`")
        lines.append(f"- min Δ%:    `{min(deltas):+.2f}%`")
        lines.append(f"- max Δ%:    `{max(deltas):+.2f}%`")
        lines.append(f"- count new > old: {higher} / {len(deltas)}")
        lines.append(f"- count new < old: {lower} / {len(deltas)}")
    lines.append("")
    if flag:
        lines.append("## Sanity-check flags (|Δ| > 25%)")
        lines.append("")
        for r in flag:
            lines.append(
                f"- `{r['item_code']}`: {r['delta_pct']:+.1f}% "
                f"(old {r['old_sgd']:.2f} → new {r['new_sgd']:.2f}; "
                f"cbm={r['cbm']:.3f}, freight={r['freight_sgd']:.2f}, "
                f"clamp sg={r['clamp_sg'] or '—'} th={r['clamp_th'] or '—'})"
            )
    else:
        lines.append("## Sanity-check flags (|Δ| > 25%)")
        lines.append("")
        lines.append("_None — all deltas within ±25%._")
    lines.append("")
    lines.append("## Method notes")
    lines.append("")
    lines.append(
        "- **old**: `compute_wisdom_retail(...)`.`retail_sgd` — derives SGD "
        "from `landed_thb / sgd_thb / 0.50`. `landed_thb` already includes "
        "Thai freight (Xiamen→Laem Chabang), Thai 7% import VAT, Thai "
        "clearance + last-mile."
    )
    lines.append(
        "- **new**: `compute_wisdom_retail_sg(...)`.`retail_sgd` — routes "
        "through `cost_engine.ROUTE_PROFILES['china_to_singapore']` (LCL) "
        "with `duty_rate=0`, `vat_rate=0.09`, then `landed_sgd / 0.50`. "
        "SG customer GST stack stays off until "
        "`sg_nubo_gst_registered=True`."
    )
    lines.append(
        "- Both paths apply the same Vinci-style logistics tier clamp on "
        "landed cost for symmetry."
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {report_path}")
    print()
    if deltas:
        print(f"mean Δ% = {statistics.mean(deltas):+.2f}%   "
              f"median Δ% = {statistics.median(deltas):+.2f}%   "
              f"range [{min(deltas):+.2f}%, {max(deltas):+.2f}%]")
        print(f"new > old: {higher}   new < old: {lower}")
        if flag:
            print(f"⚠ {len(flag)} SKUs exceed ±25% delta — see report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
