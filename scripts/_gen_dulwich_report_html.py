"""Render the Dulwich PO 2026060101 FOB→SGD pricing breakdown as HTML + CSV.

Reads data/dulwich-po-2026060101-report.json (built by _build_dulwich_report_data.py)
and writes:
  docs/reports/dulwich-po-2026060101-pricing.html   (Leka Design System)
  docs/reports/dulwich-po-2026060101-pricing.csv
"""
from __future__ import annotations
import csv, html, json
from pathlib import Path

DATA = Path("data/dulwich-po-2026060101-report.json")
HTML_OUT = Path("docs/reports/dulwich-po-2026060101-pricing.html")
CSV_OUT = Path("docs/reports/dulwich-po-2026060101-pricing.csv")


def clean(s) -> str:
    if s is None:
        return ""
    # Drop unencodable replacement chars / control chars
    return "".join(ch for ch in str(s) if ch == "\n" or ch.isprintable()).replace("�", "").strip()


def thb(v):
    return f"฿{v:,.2f}" if v is not None else "—"


def usd(v):
    return f"${v:,.2f}" if v is not None else "—"


def sgd(v):
    return f"S${v:,.2f}" if v is not None else "—"


def main() -> None:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    c = d["constants"]
    m = d["meta"]
    s = d["summary"]
    rows = d["rows"]

    # ---- CSV ----
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([
            "code", "name", "first_time_priced", "qty", "fob_usd", "usd_thb",
            "cif_thb", "duty_thb", "vat_thb_7pct", "landed_thb",
            "retail_thb", "retail_usd", "retail_sgd", "stored_retail_sgd",
            "reconciled", "line_total_sgd",
            "r2_heuristic_sgd_fob_x4.44", "r2_line_total_sgd",
        ])
        for r in rows:
            cm = r["computed"]
            w.writerow([
                r["code"], clean(r["name"]), "YES" if r["first_time_priced"] else "",
                r["qty"], r["fob_usd"], c["usd_thb"],
                cm["cif_thb"], cm["duty_thb"], cm["vat_thb"], cm["landed_thb"],
                cm["retail_thb"], cm["retail_usd"], cm["retail_sgd"],
                r["stored"]["retail_sgd"],
                "OK" if r["recon_chain_ok"] else "MISMATCH",
                r["line_total_sgd"], r["r2_sgd"], r["r2_line_total_sgd"],
            ])

    # ---- worked example: DDGT-BZ ----
    ex = next(r for r in rows if r["code"] == "DDGT-BZ")
    exc = ex["computed"]

    # ---- table rows ----
    trs = []
    for r in rows:
        cm = r["computed"]
        ftp = r["first_time_priced"]
        ok = r["recon_chain_ok"]
        recon_badge = (
            '<span class="badge ok">✓ match</span>' if ok
            else '<span class="badge fail">✗ MISMATCH</span>'
        )
        ftp_badge = '<span class="badge new">NEW</span>' if ftp else ""
        rowcls = "ftp" if ftp else ""
        trs.append(f"""<tr class="{rowcls}">
  <td class="code">{html.escape(r['code'])} {ftp_badge}</td>
  <td class="name">{html.escape(clean(r['name']))}</td>
  <td class="num">{usd(r['fob_usd'])}</td>
  <td class="num thb">{thb(cm['cif_thb'])}</td>
  <td class="num thb">{thb(cm['vat_thb'])}</td>
  <td class="num thb">{thb(cm['landed_thb'])}</td>
  <td class="num thb">{thb(cm['retail_thb'])}</td>
  <td class="num">{usd(cm['retail_usd'])}</td>
  <td class="num sgd">{sgd(cm['retail_sgd'])}</td>
  <td class="num">{int(r['qty'])}</td>
  <td class="num sgd">{sgd(r['line_total_sgd'])}</td>
  <td class="num r2">{sgd(r['r2_sgd'])}</td>
  <td class="recon">{recon_badge}</td>
</tr>""")
    tbody = "\n".join(trs)

    ftp_codes = [r["code"] for r in rows if r["first_time_priced"]]

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dulwich PO 2026060101 — Wisdom FOB→SGD pricing breakdown</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --purple:#8003FF; --navy:#182557; --cream:#FFF9E6; --magenta:#970260;
    --amber:#FFA900; --redorange:#E54822;
    --card-radius:16px; --btn-radius:8px;
    --shadow:0px 2px 8px rgba(24,37,87,0.08);
    --line:#e7e9f2;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    font-family:'Manrope',-apple-system,Segoe UI,Roboto,sans-serif;
    color:var(--navy); background:#f6f5fb; margin:0; padding:32px 20px 80px;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1280px; margin:0 auto; }}
  h1 {{ font-size:28px; font-weight:800; letter-spacing:-0.02em; margin:0 0 6px; }}
  h2 {{ font-size:18px; font-weight:700; margin:0 0 14px; }}
  .sub {{ color:#5b648a; font-weight:500; margin:0 0 24px; font-size:15px; }}
  .card {{
    background:#fff; border-radius:var(--card-radius); box-shadow:var(--shadow);
    padding:24px; margin-bottom:22px; border:1px solid var(--line);
  }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }}
  .stat {{ background:var(--cream); border-radius:var(--btn-radius); padding:14px 16px; }}
  .stat .k {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--magenta); font-weight:700; }}
  .stat .v {{ font-size:22px; font-weight:800; margin-top:4px; }}
  .meta-row {{ display:flex; flex-wrap:wrap; gap:8px 28px; font-size:14px; color:#41496f; margin-top:4px; }}
  .meta-row b {{ color:var(--navy); }}
  table.formula {{ width:100%; border-collapse:collapse; font-size:14px; }}
  table.formula td {{ padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  table.formula td:first-child {{ font-weight:700; width:160px; color:var(--purple); }}
  code, .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; background:#f3effc; padding:1px 6px; border-radius:5px; color:var(--purple); }}
  .worked {{ background:var(--navy); color:#fff; border-radius:var(--card-radius); padding:22px 24px; }}
  .worked h2 {{ color:#fff; }}
  .worked .step {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid rgba(255,255,255,.12); font-size:14px; }}
  .worked .step span:first-child {{ color:#c9ccff; }}
  .worked .step b {{ font-weight:700; }}
  .worked .final {{ color:var(--amber); font-size:17px; }}
  .tablewrap {{ overflow-x:auto; border-radius:var(--card-radius); border:1px solid var(--line); }}
  table.data {{ width:100%; border-collapse:collapse; font-size:13px; background:#fff; min-width:1100px; }}
  table.data thead th {{
    position:sticky; top:0; background:var(--navy); color:#fff; font-weight:700;
    padding:11px 9px; text-align:right; font-size:12px; white-space:nowrap; z-index:2;
  }}
  table.data thead th:first-child, table.data thead th:nth-child(2) {{ text-align:left; }}
  table.data tbody td {{ padding:9px; border-bottom:1px solid var(--line); }}
  table.data tbody tr:hover {{ background:#faf8ff; }}
  td.num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
  td.code {{ font-weight:700; white-space:nowrap; }}
  td.name {{ color:#41496f; max-width:240px; }}
  td.thb {{ color:#5b648a; }}
  td.sgd {{ font-weight:700; color:var(--purple); }}
  td.r2 {{ color:var(--redorange); font-weight:600; }}
  td.recon {{ text-align:center; }}
  tr.ftp {{ background:#fff6fb; }}
  tr.ftp:hover {{ background:#ffeef7; }}
  tr.ftp td.code {{ color:var(--magenta); }}
  .badge {{ display:inline-block; font-size:10px; font-weight:800; padding:2px 7px; border-radius:9999px; letter-spacing:.04em; vertical-align:middle; }}
  .badge.new {{ background:var(--magenta); color:#fff; }}
  .badge.ok {{ background:#e7f7ec; color:#1c8a45; }}
  .badge.fail {{ background:#fdecea; color:var(--redorange); }}
  tfoot td {{ padding:11px 9px; font-weight:800; border-top:2px solid var(--navy); background:var(--cream); }}
  .note {{ font-size:13px; color:#5b648a; line-height:1.6; }}
  .note b {{ color:var(--navy); }}
  .pill {{ display:inline-block; background:var(--purple); color:#fff; font-size:12px; font-weight:700; padding:4px 12px; border-radius:9999px; }}
  .legend {{ display:flex; gap:18px; flex-wrap:wrap; font-size:12.5px; margin-top:12px; color:#5b648a; }}
  .legend .sw {{ display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:middle; }}
  a {{ color:var(--purple); }}
  .footer {{ text-align:center; color:#9aa0bf; font-size:12px; margin-top:30px; }}
</style>
</head>
<body>
<div class="wrap">

  <span class="pill">Leka · Wisdom catalog</span>
  <h1 style="margin-top:12px">Dulwich PO 2026060101 — Wisdom FOB→SGD pricing breakdown</h1>
  <p class="sub">Per-product audit trail from FOB USD to retail SGD · proforma invoice from
  <b>{html.escape(clean(m.get('vendor_name')))}</b>, dated {html.escape(clean(m.get('date')))} ·
  {s['n_items']} line items · flat China path (CIF ≈ FOB) as actually used at ingest.</p>

  <div class="card">
    <h2>Purchase order</h2>
    <div class="meta-row">
      <div><b>PO / Quotation</b> · {html.escape(clean(m.get('po_number')))}</div>
      <div><b>Vendor</b> · {html.escape(clean(m.get('vendor_name')))}</div>
      <div><b>Project</b> · {html.escape(clean(m.get('project')))}</div>
      <div><b>Price term</b> · {html.escape(clean(m.get('price_term')))}</div>
      <div><b>PO total</b> · {usd(m.get('total_usd'))}</div>
      <div><b>Price date</b> · {html.escape(clean(c['price_date']))}</div>
    </div>
    <div class="grid" style="margin-top:18px">
      <div class="stat"><div class="k">Line items</div><div class="v">{s['n_items']}</div></div>
      <div class="stat"><div class="k">First-time priced</div><div class="v">{s['n_first_time_priced']}</div></div>
      <div class="stat"><div class="k">Reconciled OK</div><div class="v">{s['n_items'] - s['n_recon_fail']}/{s['n_items']}</div></div>
      <div class="stat"><div class="k">Σ Retail (catalog)</div><div class="v">{sgd(s['total_retail_sgd'])}</div></div>
      <div class="stat"><div class="k">Σ R2 heuristic</div><div class="v">{sgd(s['total_r2_sgd'])}</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Constants &amp; formula (flat China path, as used at ingest)</h2>
    <div class="meta-row" style="margin-bottom:14px">
      <div><b>USD→THB</b> · {c['usd_thb']:.4f}</div>
      <div><b>SGD→THB</b> · {c['sgd_thb']:.4f}</div>
      <div><b>Import duty</b> · {c['import_duty_rate']*100:.0f}% (ASEAN–China FTA Form E)</div>
      <div><b>Import VAT</b> · {c['thai_vat_rate']*100:.0f}%</div>
      <div><b>Gross margin</b> · {c['gross_margin']*100:.0f}%</div>
      <div><b>TH customer VAT</b> · {c['th_customer_vat_rate']*100:.0f}% (THB retail only)</div>
      <div><b>SG GST</b> · off (Nubo not GST-registered → ×1.0)</div>
    </div>
    <table class="formula">
      <tr><td>1 · CIF THB</td><td><code>FOB USD × USD→THB</code> — China consolidated sea: CIF ≈ FOB (no separate freight)</td></tr>
      <tr><td>2 · Duty</td><td><code>CIF × 0%</code> = 0</td></tr>
      <tr><td>3 · Import VAT</td><td><code>(CIF + duty) × 7%</code></td></tr>
      <tr><td>4 · Landed THB</td><td><code>CIF + duty + VAT</code> = CIF × 1.07</td></tr>
      <tr><td>5 · Retail THB</td><td><code>Landed ÷ (1 − 0.50) × (1 + 0.07)</code> — 50% GM, +7% TH customer VAT</td></tr>
      <tr><td>6 · Retail USD</td><td><code>(Landed ÷ 33.2020) ÷ (1 − 0.50)</code> — no TH VAT</td></tr>
      <tr><td>7 · Retail SGD</td><td><code>(Landed ÷ 26.0071) ÷ (1 − 0.50) × 1.0</code> — no TH VAT, SG GST off</td></tr>
    </table>
    <p class="note" style="margin-top:14px">Source of truth: <code>shared/wisdom_pricing.py</code> ·
    <code>compute_wisdom_retail()</code>. The ingest called it <b>without CBM</b>, so the
    flat China path was used (CIF ≈ FOB) — not the LCL/CBM logistics path.</p>
  </div>

  <div class="worked">
    <h2>Worked example — DDGT-BZ (Holey Block Motor Skills Set)</h2>
    <div class="step"><span>FOB USD</span><b>{usd(ex['fob_usd'])}</b></div>
    <div class="step"><span>× USD→THB {c['usd_thb']:.4f} → CIF THB</span><b>{thb(exc['cif_thb'])}</b></div>
    <div class="step"><span>Duty (0%)</span><b>{thb(exc['duty_thb'])}</b></div>
    <div class="step"><span>Import VAT 7% of CIF</span><b>{thb(exc['vat_thb'])}</b></div>
    <div class="step"><span>Landed THB (CIF × 1.07)</span><b>{thb(exc['landed_thb'])}</b></div>
    <div class="step"><span>Retail THB (÷0.5 × 1.07)</span><b>{thb(exc['retail_thb'])}</b></div>
    <div class="step"><span>Retail USD (Landed÷33.2020 ÷0.5)</span><b>{usd(exc['retail_usd'])}</b></div>
    <div class="step final"><span>Retail SGD (Landed÷26.0071 ÷0.5)</span><b>{sgd(exc['retail_sgd'])}</b></div>
    <p class="note" style="color:#c9ccff; margin-top:12px">Confirmed against stored
    <code style="background:rgba(255,255,255,.12);color:#fff">pricing.retail_sgd</code> = {sgd(ex['stored']['retail_sgd'])} ✓</p>
  </div>

  <div class="card">
    <h2>Per-product pricing — all {s['n_items']} line items</h2>
    <div class="legend">
      <span><span class="sw" style="background:#fff6fb;border:1px solid #f0c9e0"></span>First-time-priced set (7) — previously no FOB, would render TBC</span>
      <span><span class="sw" style="background:var(--purple)"></span>Retail SGD (catalog, served price)</span>
      <span><span class="sw" style="background:var(--redorange)"></span>R2 heuristic SGD = FOB × 4.44</span>
    </div>
    <div class="tablewrap" style="margin-top:14px">
      <table class="data">
        <thead><tr>
          <th>Code</th><th>Name</th><th>FOB USD</th><th>×rate → CIF THB</th>
          <th>VAT 7%</th><th>Landed THB</th><th>Retail THB</th><th>Retail USD</th>
          <th>Retail SGD</th><th>Qty</th><th>Line total SGD</th>
          <th>R2 ≈FOB×4.44</th><th>Recon</th>
        </tr></thead>
        <tbody>
{tbody}
        </tbody>
        <tfoot><tr>
          <td colspan="9" style="text-align:right">PO totals →</td>
          <td class="num">{s['n_items']} items</td>
          <td class="num sgd">{sgd(s['total_retail_sgd'])}</td>
          <td class="num r2">{sgd(s['total_r2_sgd'])}</td>
          <td></td>
        </tr></tfoot>
      </table>
    </div>
    <p class="note" style="margin-top:14px"><b>Reconciliation:</b> every computed Retail SGD (and
    the full VAT / Landed / Retail THB / Retail USD chain) was recomputed locally from
    <code>fob_usd</code> and checked against the stored <code>products_wisdom/&lt;code&gt;.pricing.*</code>.
    <b>{s['n_items'] - s['n_recon_fail']} of {s['n_items']} match exactly</b>
    ({'no mismatches' if s['n_recon_fail']==0 else str(s['n_recon_fail'])+' mismatch(es) flagged above'}).</p>
  </div>

  <div class="card">
    <h2>Catalog retail vs Dulwich R2 proposal heuristic</h2>
    <p class="note">The numbers in the <b>Retail SGD</b> column above are the canonical catalog
    landed-cost retail prices from <code>shared/wisdom_pricing.py</code> (effectively
    <b>FOB × 2.732</b>: 33.2020 × 1.07 ÷ 26.0071 ÷ 0.50). The customer-facing
    <b>Dulwich R2 proposal</b> in <code>leka-projects</code>
    (<code>build_r2_draft_order.py</code>) prices Wisdom-landed draft-order lines with a
    separate quick heuristic — <code>WISDOM_FOB_TO_SGD = 104.09 × 1.05 ÷ 24.6 ≈ 4.44</code>,
    i.e. <b>SGD ≈ FOB × 4.44</b>. Because 4.44 &gt; 2.732, the R2 draft lines run materially
    higher than the catalog retail (PO-wide: {sgd(s['total_r2_sgd'])} vs {sgd(s['total_retail_sgd'])},
    +{(s['total_r2_sgd']/s['total_retail_sgd']-1)*100:.0f}%). Both are shown per line so the
    difference is auditable. The R2 heuristic is a draft-stage estimate only; the catalog
    flat-path retail is the reconciled source of truth stored in Firestore.</p>
  </div>

  <p class="footer">Generated from live Firestore (<code>leka-product-catalogs</code>) ·
  quotation <code>leka_vendor_quotations/wisdom-PO-2026060101</code> +
  <code>products_wisdom/*.pricing</code> · leka-product-catalogs v2.60.0 ·
  first-time-priced: {', '.join(ftp_codes)}</p>
</div>
</body>
</html>"""

    HTML_OUT.write_text(page, encoding="utf-8")
    print(f"Wrote {HTML_OUT} ({len(page):,} bytes)")
    print(f"Wrote {CSV_OUT}")


if __name__ == "__main__":
    main()
