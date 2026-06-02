"""Build the complete report dataset for Dulwich PO 2026060101.

Combines the quotation line items with stored products_wisdom pricing, recomputes
the flat-path chain locally to reconcile, flags first-time-priced sets (product
created_at on the PO price_date), and writes data/dulwich-po-2026060101-report.json.
"""
from __future__ import annotations
import json, os
from pathlib import Path

SA = (r"C:\Users\Eukrit\OneDrive\Documents\Claude Code"
      r"\Credentials Claude Code\ai-agents-go-claude-sa.json")
if Path(SA).exists():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SA
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")
from google.cloud import firestore

PROJECT, DB = "ai-agents-go", "leka-product-catalogs"
PRICE_DATE = "2026-06-01"

# Constants as actually used at ingest (flat China path)
USD_THB = 33.2020
SGD_THB = 26.0071
IMPORT_DUTY_RATE = 0.00
THAI_VAT_RATE = 0.07
TH_CUSTOMER_VAT_RATE = 0.07
GROSS_MARGIN = 0.50
SG_GST_MULT = 1.0  # Nubo not GST-registered

# Exact 7 codes priced for the first time by this PO (per ingest CHANGELOG v2.58.0):
# previously had no FOB → would render TBC in the Dulwich R2 proposal.
FIRST_TIME_PRICED = {
    "DDJM-JQ01-V01", "DDGT-BZ", "DDHD-BZ",
    "CSS-QB-BZ", "CSS-DMGD-BZ-V01", "CSS-CBZJ-BZ", "CSS-QBWJ-BZ",
}
# R2 draft-order quick heuristic (leka-projects build_r2_draft_order.py):
# WISDOM_FOB_TO_SGD = 104.09 * 1.05 / 24.6  (≈ FOB × 4.44)
R2_FOB_TO_SGD = 104.09 * 1.05 / 24.6


def compute_flat(fob_usd: float) -> dict:
    """Reproduce shared.wisdom_pricing flat path exactly (rounding at each step)."""
    cif_thb = fob_usd * USD_THB
    duty_thb = round(cif_thb * IMPORT_DUTY_RATE, 2)
    vat_thb = round((cif_thb + duty_thb) * THAI_VAT_RATE, 2)
    landed_thb = round(cif_thb + duty_thb + vat_thb, 2)
    retail_thb = round((landed_thb / (1 - GROSS_MARGIN)) * (1 + TH_CUSTOMER_VAT_RATE), 2)
    retail_usd = round((landed_thb / USD_THB) / (1 - GROSS_MARGIN), 2)
    retail_sgd = round(((landed_thb / SGD_THB) / (1 - GROSS_MARGIN)) * SG_GST_MULT, 2)
    return {
        "cif_thb": round(cif_thb, 2),
        "duty_thb": duty_thb,
        "vat_thb": vat_thb,
        "landed_thb": landed_thb,
        "retail_thb": retail_thb,
        "retail_usd": retail_usd,
        "retail_sgd": retail_sgd,
    }


def short_name(pd: dict) -> str:
    for k in ("title", "name", "product_name"):
        v = pd.get(k)
        if v:
            return str(v)
    desc = pd.get("description") or pd.get("gemini_description") or ""
    desc = " ".join(str(desc).split())
    if desc:
        return desc[:70] + ("…" if len(desc) > 70 else "")
    cat = pd.get("subcategory") or pd.get("category") or ""
    return str(cat) or "(unnamed)"


def main() -> None:
    db = firestore.Client(project=PROJECT, database=DB)
    quote = db.collection("leka_vendor_quotations").document("wisdom-PO-2026060101").get().to_dict()
    items = quote.get("items") or []

    rows = []
    for it in items:
        code = it.get("item_code")
        fob = float(it.get("fob_usd"))
        qty = float(it.get("qty"))
        cbm = it.get("volume_cbm")
        snap = db.collection("products_wisdom").document(code).get()
        pd = snap.to_dict() or {}
        pr = pd.get("pricing") or {}
        created = pd.get("created_at")
        updated = pd.get("updated_at")
        created_s = str(created)[:10] if created else None
        comp = compute_flat(fob)
        stored_sgd = pr.get("retail_sgd")
        recon_ok = stored_sgd is not None and abs(comp["retail_sgd"] - float(stored_sgd)) < 0.01
        # full-chain reconciliation
        chain_ok = all(
            pr.get(k) is not None and abs(comp[k] - float(pr.get(k))) < 0.02
            for k in ("vat_thb", "landed_thb", "retail_thb", "retail_usd", "retail_sgd")
        )
        rows.append({
            "code": code,
            "name": short_name(pd),
            "category": pd.get("category"),
            "subcategory": pd.get("subcategory"),
            "qty": qty,
            "volume_cbm": cbm,
            "amount_usd": it.get("amount_usd"),
            "fob_usd": fob,
            "created_at": created_s,
            "updated_at": str(updated)[:10] if updated else None,
            "first_time_priced": code in FIRST_TIME_PRICED,
            "computed": comp,
            "stored": {
                "vat_thb": pr.get("vat_thb"),
                "landed_thb": pr.get("landed_thb"),
                "retail_thb": pr.get("retail_thb"),
                "retail_usd": pr.get("retail_usd"),
                "retail_sgd": pr.get("retail_sgd"),
                "usd_thb": pr.get("usd_thb"),
                "sgd_thb": pr.get("sgd_thb"),
                "cost_source": pr.get("cost_source"),
                "fob_usd_prior": pr.get("fob_usd_prior"),
            },
            "recon_sgd_ok": recon_ok,
            "recon_chain_ok": chain_ok,
            "line_total_sgd": round(comp["retail_sgd"] * qty, 2),
            # R2 heuristic (leka-projects draft-order quick estimate)
            "r2_sgd": round(fob * R2_FOB_TO_SGD, 2),
            "r2_line_total_sgd": round(fob * R2_FOB_TO_SGD * qty, 2),
        })

    n_first = sum(1 for r in rows if r["first_time_priced"])
    n_recon_fail = sum(1 for r in rows if not r["recon_sgd_ok"])
    out = {
        "quote_id": "wisdom-PO-2026060101",
        "meta": {k: v for k, v in quote.items() if k not in ("items", "line_items")},
        "constants": {
            "usd_thb": USD_THB, "sgd_thb": SGD_THB,
            "import_duty_rate": IMPORT_DUTY_RATE, "thai_vat_rate": THAI_VAT_RATE,
            "th_customer_vat_rate": TH_CUSTOMER_VAT_RATE, "gross_margin": GROSS_MARGIN,
            "sg_gst_mult": SG_GST_MULT, "price_date": PRICE_DATE,
        },
        "summary": {
            "n_items": len(rows),
            "n_first_time_priced": n_first,
            "n_recon_fail": n_recon_fail,
            "total_fob_usd": round(sum(r["fob_usd"] * r["qty"] for r in rows), 2),
            "total_retail_sgd": round(sum(r["line_total_sgd"] for r in rows), 2),
            "total_r2_sgd": round(sum(r["r2_line_total_sgd"] for r in rows), 2),
        },
        "rows": rows,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/dulwich-po-2026060101-report.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"items={len(rows)} first_time_priced={n_first} recon_fail={n_recon_fail}")
    print("first-time-priced codes:", [r["code"] for r in rows if r["first_time_priced"]])
    print("recon failures:", [r["code"] for r in rows if not r["recon_sgd_ok"]])
    print("total_retail_sgd=", out["summary"]["total_retail_sgd"],
          "total_r2_sgd=", out["summary"]["total_r2_sgd"])


if __name__ == "__main__":
    main()
