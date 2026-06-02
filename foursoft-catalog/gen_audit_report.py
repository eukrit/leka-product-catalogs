"""Generate docs/reports/4soft-pricing-audit.html from the audit CSV/JSON.

Read-only: consumes foursoft-catalog/data/4soft_pricing_audit.csv +
_summary.json + _audit_movers.json and renders a Leka-styled HTML report.
"""
from __future__ import annotations
import csv, json, html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "foursoft-catalog" / "data"
OUT = ROOT / "docs" / "reports" / "4soft-pricing-audit.html"

rows = list(csv.DictReader((DATA / "4soft_pricing_audit.csv").open(encoding="utf-8")))
summary = json.loads((DATA / "4soft_pricing_audit_summary.json").read_text(encoding="utf-8"))
movers = json.loads((DATA / "_audit_movers.json").read_text(encoding="utf-8"))


def f(x):
    try:
        return float(x)
    except Exception:
        return None


def money(x, dp=0):
    v = f(x)
    return "—" if v is None else f"{v:,.{dp}f}"


# Representative rows for the worked-table (5 chain examples + 2 TBC bases + top movers)
rep_codes = ["A1-01A-00", "D2-02A-09", "J1-02B-05", "V1-03B-001", "J3-02A-20", "G2-27A-09"]
by_code = {r["item_code"]: r for r in rows}
rep_rows = [by_code[c] for c in rep_codes if c in by_code]

not_med = [r for r in rows if r["in_medusa"] == "False"]

# ---- build HTML ----
st = summary
bt = st["by_type"]


def data_row(r, highlight=""):
    live = f(r["retail_sgd_live_medusa"])
    sea = f(r["retail_sgd_sea_computed"])
    air = f(r["retail_sgd_air_computed"])
    delta = ""
    if sea and air:
        d = (air - sea) / sea * 100
        delta = f"{d:+.1f}%"
    return f"""<tr class="{highlight}">
      <td class="code">{html.escape(r['item_code'])}</td>
      <td class="name">{html.escape(r['name'])}</td>
      <td>{r['type']}</td>
      <td class="num">{money(r['list_eur'])}</td>
      <td class="num">{money(r['eur_fob'])}</td>
      <td>{r['cbm_method'] or '—'}</td>
      <td class="num thb">{money(r['landed_thb_sea'])}</td>
      <td class="num sgd">{money(r['retail_sgd_sea_computed'])}</td>
      <td class="num">{money(r['retail_sgd_air_computed'])}</td>
      <td class="num">{delta}</td>
      <td class="num"><b>{money(r['retail_sgd_live_medusa'])}</b></td>
      <td>{(r['medusa_status'] or 'not in Medusa')}</td>
    </tr>"""


rep_html = "\n".join(data_row(r) for r in rep_rows)
mover_html = "\n".join(
    f"<tr><td class='num r2'>{m[0]:+.1f}%</td><td class='code'>{html.escape(m[1])}</td>"
    f"<td>{m[2]}</td><td class='name'>{html.escape(m[3])}</td>"
    f"<td class='num'>{m[4]:,.0f}</td><td class='num'>{m[5]:,.0f}</td>"
    f"<td class='num'><b>{m[6]}</b></td></tr>"
    for m in movers["movers_top"]
)
notmed_html = "\n".join(
    f"<tr><td class='code'>{html.escape(r['item_code'])}</td><td>{r['type']}</td>"
    f"<td class='name'>{html.escape(r['name'])}</td><td class='num'>{money(r['list_eur'])}</td></tr>"
    for r in not_med
)

HTML = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>4soft pricing audit — EUR-EXW → landed → retail SGD</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{ --purple:#8003FF; --navy:#182557; --cream:#FFF9E6; --magenta:#970260;
    --amber:#FFA900; --redorange:#E54822; --card-radius:16px; --btn-radius:8px;
    --shadow:0px 2px 8px rgba(24,37,87,0.08); --line:#e7e9f2; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Manrope',-apple-system,Segoe UI,Roboto,sans-serif; color:var(--navy);
    background:#f6f5fb; margin:0; padding:32px 20px 80px; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1320px; margin:0 auto; }}
  h1 {{ font-size:28px; font-weight:800; letter-spacing:-0.02em; margin:0 0 6px; }}
  h2 {{ font-size:18px; font-weight:700; margin:0 0 14px; }}
  h3 {{ font-size:15px; font-weight:700; margin:18px 0 8px; color:var(--magenta); }}
  .sub {{ color:#5b648a; font-weight:500; margin:0 0 24px; font-size:15px; }}
  .card {{ background:#fff; border-radius:var(--card-radius); box-shadow:var(--shadow);
    padding:24px; margin-bottom:22px; border:1px solid var(--line); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }}
  .stat {{ background:var(--cream); border-radius:var(--btn-radius); padding:14px 16px; }}
  .stat .k {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--magenta); font-weight:700; }}
  .stat .v {{ font-size:22px; font-weight:800; margin-top:4px; }}
  .stat .s {{ font-size:12px; color:#5b648a; margin-top:2px; }}
  table.formula {{ width:100%; border-collapse:collapse; font-size:14px; }}
  table.formula td {{ padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  table.formula td:first-child {{ font-weight:700; width:180px; color:var(--purple); }}
  code,.mono {{ font-family:ui-monospace,Menlo,monospace; font-size:13px; background:#f3effc; padding:1px 6px; border-radius:5px; color:var(--purple); }}
  .worked {{ background:var(--navy); color:#fff; border-radius:var(--card-radius); padding:22px 24px; }}
  .worked h2 {{ color:#fff; }}
  .worked .step {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid rgba(255,255,255,.12); font-size:14px; }}
  .worked .step span:first-child {{ color:#c9ccff; }}
  .worked .final {{ color:var(--amber); font-size:17px; font-weight:700; }}
  .tablewrap {{ overflow-x:auto; border-radius:var(--card-radius); border:1px solid var(--line); margin-top:8px; }}
  table.data {{ width:100%; border-collapse:collapse; font-size:13px; background:#fff; min-width:1100px; }}
  table.data thead th {{ position:sticky; top:0; background:var(--navy); color:#fff; font-weight:700;
    padding:11px 9px; text-align:right; font-size:12px; white-space:nowrap; z-index:2; }}
  table.data thead th:nth-child(-n+3) {{ text-align:left; }}
  table.data tbody td {{ padding:9px; border-bottom:1px solid var(--line); }}
  table.data tbody tr:hover {{ background:#faf8ff; }}
  td.num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
  td.code {{ font-weight:700; white-space:nowrap; }}
  td.name {{ color:#41496f; max-width:240px; }}
  td.thb {{ color:#5b648a; }} td.sgd {{ font-weight:700; color:var(--purple); }}
  td.r2 {{ color:var(--redorange); font-weight:700; }}
  .pill {{ display:inline-block; border-radius:9999px; padding:3px 12px; font-size:12px; font-weight:700; }}
  .pill.ok {{ background:#e7f8ee; color:#1a7f44; }} .pill.warn {{ background:#fff3da; color:#a06b00; }}
  .pill.bad {{ background:#fde9e3; color:var(--redorange); }}
  .finding {{ border-left:4px solid var(--amber); padding:8px 16px; margin:12px 0; background:#fffaf0; border-radius:0 8px 8px 0; }}
  .finding.crit {{ border-color:var(--redorange); background:#fff5f2; }}
  .finding b {{ color:var(--navy); }}
  ul.rec {{ margin:6px 0; padding-left:20px; }} ul.rec li {{ margin:7px 0; font-size:14px; }}
  .tag {{ font-size:12px; color:#fff; background:var(--purple); padding:2px 9px; border-radius:9999px; font-weight:700; }}
</style></head><body><div class="wrap">

<h1>4soft pricing audit — EUR-EXW → landed → retail SGD</h1>
<p class="sub">Read-only investigation · mirrors the Dulwich-proposal pricing study · 4soft = EPDM surface-graphics / 3D play elements / 2D ground markings (4soft s.r.o., Tanvald CZ) · generated 2026-06-02 · <b>no pricing changed</b></p>

<div class="card">
  <h2>Headline</h2>
  <div class="grid">
    <div class="stat"><div class="k">Pricelist SKUs</div><div class="v">{st['total_pricelist_skus']:,}</div><div class="s">2025 EPDM .xls</div></div>
    <div class="stat"><div class="k">In Medusa</div><div class="v">{st['in_medusa']:,}</div><div class="s">{st['medusa_by_status'].get('published',0)} published · {st['medusa_by_status'].get('draft',0)} draft</div></div>
    <div class="stat"><div class="k">Live SGD price</div><div class="v">{st['live_priced_sgd']:,}</div><div class="s">0 zero / missing</div></div>
    <div class="stat"><div class="k">Live = sea-LCL</div><div class="v">{st['price_state'].get('live=sea-LCL',0):,}</div><div class="s">live = air: 0</div></div>
    <div class="stat"><div class="k">Not in Medusa</div><div class="v">{st['not_in_medusa']}</div><div class="s">packaging/accessory + 2 skips</div></div>
  </div>
  <div class="finding crit" style="margin-top:18px">
    <b>Finding 1 — the air-freight pivot (v2.45.0) is NOT live.</b> All
    <b>{st['price_state'].get('live=sea-LCL',0):,} priced variants</b> carry the
    <b>sea-LCL</b> price; <b>zero</b> carry the air-freight price. The 2026-05-30 pivot
    ran <span class="pill warn">dry-run only</span> — Firestore <code>pricing_config</code> was last written
    2026-05-29 and <code>vendors/4soft</code> pricing still shows <code>fx_snapshot</code> from that run.
    Live retail therefore reflects the <b>old sea-LCL cost basis</b>.
  </div>
</div>

<div class="card">
  <h2>The pricing chain &amp; constants</h2>
  <p class="sub" style="margin-bottom:12px">All 4soft retail derives from one canonical EUR-EXW → landed → margin pipeline
  (<code>foursoft-catalog/import_pricelist.py</code>, mirroring <code>shared/landed_pricing.py</code>). Constants live in Firestore
  <code>pricing_config/canonical</code> (db <code>leka-product-catalogs</code>), brand key <code>brands.4soft</code>.</p>
  <table class="formula">
    <tr><td>1 · Cost basis</td><td><b>EUR list price</b> from the 2025 .xls (col D "Target SALE price EUR"). Trade terms <b>EXW</b>.</td></tr>
    <tr><td>2 · EXW discount</td><td><code>eur_fob = list_eur × (1 − 0.15)</code> — 15% basic reseller discount (2020 "Price conditions" PDF).</td></tr>
    <tr><td>3 · Freight</td><td><span class="tag">SEA-LCL (LIVE)</span> shipping-automation <code>cost_engine</code>, Europe→Thailand LCL, Baltic-rate calibrated per CBM. <span class="tag">AIR (dry-run)</span> chargeable-weight = CBM×167 kg/m³ @ 105 THB/kg (median). Method flag <code>METHOD</code> is <code>"air"</code> in code but was never written live.</td></tr>
    <tr><td>4 · CBM source</td><td><b>251 / 2,410</b> have real dims → <code>dims_scaled</code> CBM. The other <b>2,159</b> have no dims → flat 35% uplift (<code>unmatched_landed_uplift = 1.35</code>).</td></tr>
    <tr><td>5 · Duty + VAT</td><td>EU/Czech origin → <b>10% Thai duty</b> (<code>duty_rate_non_china</code>), <b>7% import VAT</b> on (CIF+duty).</td></tr>
    <tr><td>6 · Logistics clamp</td><td>Tiered floor/cap as % of FOB-in-THB (<code>logistics_tiers</code>, sea-tuned: 0.80–2.50 ≤€500 … 0.35–0.80 &gt;€10k). <b>Binds on ~95% of SKUs</b> — this is why most prices don't move under the air pivot.</td></tr>
    <tr><td>7 · Margin</td><td><code>retail = landed_thb / (1 − 0.40)</code> — <b>40% gross margin</b> (4soft-specific, user 2026-05-29).</td></tr>
    <tr><td>8 · TH customer VAT</td><td><code>retail_thb × 1.07</code> — embedded in THB only. USD/EUR/SGD are pre-TH-VAT.</td></tr>
    <tr><td>9 · Retail SGD</td><td><code>retail_sgd = (landed_thb / SGD_THB) / (1 − 0.40)</code>. SG GST <b>not</b> added — Nubo is not GST-registered (<code>sg_nubo_gst_registered = false</code>) → zero-rated export base.</td></tr>
  </table>
  <h3>Live constants (Firestore, written 2026-05-29)</h3>
  <div class="grid">
    <div class="stat"><div class="k">EXW discount</div><div class="v">15%</div></div>
    <div class="stat"><div class="k">Gross margin</div><div class="v">40%</div></div>
    <div class="stat"><div class="k">Duty (non-China)</div><div class="v">10%</div></div>
    <div class="stat"><div class="k">Import VAT</div><div class="v">7%</div></div>
    <div class="stat"><div class="k">TH cust. VAT</div><div class="v">7%</div><div class="s">THB only</div></div>
    <div class="stat"><div class="k">SG GST</div><div class="v">0%</div><div class="s">not registered</div></div>
  </div>
  <h3>FX snapshot baked into live prices (2026-05-29, exchangerate-api.com +2%)</h3>
  <div class="grid">
    <div class="stat"><div class="k">EUR/THB</div><div class="v">38.71</div></div>
    <div class="stat"><div class="k">USD/THB</div><div class="v">33.25</div></div>
    <div class="stat"><div class="k">SGD/THB</div><div class="v">26.04</div></div>
  </div>
</div>

<div class="worked card">
  <h2>Worked example — J1-02B-05 (3D Monkey, girl target)</h2>
  <div class="step"><span>EUR list</span><b>€2,050.00</b></div>
  <div class="step"><span>× (1 − 0.15) EXW → eur_fob</span><b>€1,742.50</b></div>
  <div class="step"><span>flat_uplift landed (no dims): CIF×1.35 + 10% duty + 7% VAT</span><b>฿107,918.46</b></div>
  <div class="step"><span>÷ (1 − 0.40) margin</span><b>฿179,864</b></div>
  <div class="step"><span>× 1.07 TH customer VAT → retail_thb</span><b>฿192,454.59</b></div>
  <div class="step"><span>SGD: (฿107,918.46 / 26.0437) / 0.60</span><b>S$6,906.24</b></div>
  <div class="step final"><span>LIVE Medusa SGD</span><span>S$6,906.24 ✓ (= sea-LCL; air would be S$6,906 too — floored)</span></div>
</div>

<div class="card">
  <h2>Inventory by type</h2>
  <div class="grid">
    <div class="stat"><div class="k">2D ground markings</div><div class="v">{bt.get('2D',0):,}</div><div class="s">mostly draft</div></div>
    <div class="stat"><div class="k">3D play elements</div><div class="v">{bt.get('3D',0):,}</div><div class="s">dims-based where known</div></div>
    <div class="stat"><div class="k">Accessory</div><div class="v">{bt.get('accessory',0)}</div><div class="s">6 — not in Medusa</div></div>
    <div class="stat"><div class="k">Packaging</div><div class="v">{bt.get('packaging',0)}</div><div class="s">10 — not in Medusa</div></div>
  </div>
  <div class="finding"><b>Finding 3 — coverage is effectively complete for sellable SKUs.</b>
  2,392 / 2,410 are in Medusa and <b>all 2,392 carry a non-zero live SGD price</b> (0 TBC/zero in the catalog itself).
  The 18 not in Medusa are 10 packaging boxes/pallets + 6 fixing accessories (deliberately excluded as non-products) +
  <b>2 UV 2D codes that hit "handle already exists" skips</b> (E3-01C-70UV, G2-09A-65UV) during the v2.44.0 create.</div>
</div>

<div class="card">
  <h2>Sea-LCL vs air-freight — what the pivot would actually change</h2>
  <p class="sub" style="margin-bottom:10px">Median impact by type is <b>0%</b>: the sea-tuned logistics floor/cap binds on ~95% of SKUs, so freight method is irrelevant for them. Only <b>107 dims_scaled SKUs</b> (mid-CBM, high-FOB 3D + larger 2D) move &gt;2% — and they get <b>cheaper</b> under air (up to −30%), because air avoids the ฿18,000 LCL clearance fee. The 2,159 flat_uplift rows are byte-identical.</p>
  <div class="tablewrap"><table class="data">
    <thead><tr><th>Δ% (air vs sea)</th><th>Code</th><th>Type</th><th>Name</th><th>SGD sea</th><th>SGD air</th><th>SGD live</th></tr></thead>
    <tbody>{mover_html}</tbody>
  </table></div>
  <p class="sub" style="margin-top:8px">Top 12 of {movers['movers_count']} movers shown. <b>Note every "SGD live" equals "SGD sea"</b> — direct proof the air pivot is not deployed.</p>
</div>

<div class="card">
  <h2>The 2 R2 "TBC" EPDM codes — root cause</h2>
  <div class="finding crit"><b>Finding 2 — D2-02A-09UV and G2-27A-09UV are non-existent SKUs (malformed codes), not pricing gaps.</b>
  Neither appears in the 2025 pricelist or Medusa. They are the R2 BoQ's standard color "09" with an erroneous "UV" suffix appended:
  <ul class="rec">
    <li><code>D2-02A-09UV</code> → the real catalog has <b>D2-02A-09</b> (Flower-5 rose, std, €154, <b>live S$1,134.90, published</b>). UV variants of this family use a different color scheme (D2-02A-52UV … -59UV, €174) — there is no "-09UV".</li>
    <li><code>G2-27A-09UV</code> → the real catalog has <b>G2-27A-09</b> (Bumpy road sign, €65, <b>live S$479.02, published</b>) — this family has <b>no UV variant at all</b>.</li>
  </ul>
  In <code>build_r2_curated.py</code> the <code>is_epdm()</code> regex matches the malformed codes, but <code>med_sgd</code> has no exact key for them → they fall through to TBC. The fix is a <b>code correction in the R2 BoQ</b> (drop "UV" or pick a real UV color), not a pricing run.</div>
</div>

<div class="card">
  <h2>How 4soft prices reach the Dulwich R2 proposal</h2>
  <table class="formula">
    <tr><td>Source</td><td><code>import_pricelist.py</code> writes retail_{{thb,usd,eur,sgd}} to Firestore <code>vendors/4soft/products[].pricing</code>.</td></tr>
    <tr><td>Sync</td><td><code>sync_brand_prices_to_medusa.py --brand 4soft</code> pushes those onto Medusa variants by SKU (update-only). Last live sync: v2.44.0, 2,394/2,410 matched.</td></tr>
    <tr><td>R2 read</td><td><code>build_r2_curated.py</code> pulls each variant's stored <b>SGD</b> price into <code>med_sgd[norm(code)]</code> and, for EPDM codes (regex <code>^[A-Z]\\d-\\d{{2}}[A-Z]-\\d{{2,3}}</code>), uses it as the proposal unit price via <code>price_of()</code>.</td></tr>
    <tr><td>Coherence</td><td><b>R2 prices = the catalog SGD = sea-LCL.</b> They are internally consistent — but inherit the stale sea-LCL basis. If the air pivot is applied, R2 must be rebuilt to pick up the new prices.</td></tr>
  </table>
</div>

<div class="card">
  <h2>Representative chain rows (live vs computed)</h2>
  <div class="tablewrap"><table class="data">
    <thead><tr><th>Code</th><th>Name</th><th>Type</th><th>list €</th><th>FOB €</th><th>CBM method</th><th>landed ฿ (sea)</th><th>SGD sea</th><th>SGD air</th><th>Δ%</th><th>SGD LIVE</th><th>status</th></tr></thead>
    <tbody>{rep_html}</tbody>
  </table></div>
  <p class="sub" style="margin-top:8px">Full per-SKU table (2,410 rows): <code>foursoft-catalog/data/4soft_pricing_audit.csv</code>.</p>
</div>

<div class="card">
  <h2>Items not in Medusa ({len(not_med)})</h2>
  <div class="tablewrap"><table class="data" style="min-width:600px">
    <thead><tr><th>Code</th><th>Type</th><th>Name</th><th>list €</th></tr></thead>
    <tbody>{notmed_html}</tbody>
  </table></div>
</div>

<div class="card">
  <h2>Findings &amp; recommendations <span class="pill warn">no changes made — review first</span></h2>
  <ul class="rec">
    <li><b>1. Decide the freight basis.</b> Live prices are sea-LCL. The air pivot is validated (dry-run, 26/26 tests) and would <b>lower</b> ~107 mid-CBM 3D/large-2D prices by up to 30% while leaving ~95% unchanged (clamp-bound). To apply: pick a rate (LO 90 / <b>MID 105 recommended</b> / HI 135 THB/kg), run <code>import_pricelist.py --air-rate 105</code> (writes Firestore), then <code>sync_brand_prices_to_medusa.py --brand 4soft --write</code>.</li>
    <li><b>2. Retune the logistics clamp.</b> <code>LOGISTICS_TIERS</code> are still sea-tuned; under air the floor binds on ~2,069 SKUs and the cap on ~134. Until retuned, the air pivot barely moves the catalog — the clamp, not freight, sets most prices. A clamp retune (separate PR with the dry-run evidence) is the higher-leverage change.</li>
    <li><b>3. Fix the 2 R2 TBC codes at the BoQ level.</b> Replace <code>D2-02A-09UV</code> → <code>D2-02A-09</code> (S$1,134.90) and <code>G2-27A-09UV</code> → <code>G2-27A-09</code> (S$479.02), or choose a real UV color for the flower. No catalog change needed — both base codes are already published &amp; priced.</li>
    <li><b>4. Investigate the A6-01A-00 tiny-CBM data bug</b> (0.0002 m³ for a 40 cm mat — missing thickness). It will dominate post-cap landed once clamps are retuned.</li>
    <li><b>5. Recreate the 2 skipped UV 2D codes</b> (E3-01C-70UV, G2-09A-65UV) that hit handle collisions in v2.44.0, if they are wanted as sellable variants.</li>
    <li><b>6. Refresh FX.</b> Live prices bake the 2026-05-29 snapshot (EUR 38.71 / SGD 26.04). Any reprice run will re-pull live FX — confirm that is desired before running.</li>
  </ul>
</div>

<p class="sub">Audit scripts (read-only): <code>foursoft-catalog/audit_pricing.py</code> · <code>foursoft-catalog/gen_audit_report.py</code>. Data: <code>foursoft-catalog/data/4soft_pricing_audit.csv</code> + <code>_summary.json</code>.</p>
</div></body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"Wrote {OUT} ({len(HTML):,} bytes)")
