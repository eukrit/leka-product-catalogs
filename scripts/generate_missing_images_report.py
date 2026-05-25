"""Generate `docs/reports/leka-project-missing-images.html`.

Walks the live Medusa Store API for the leka-project SC, collects every product
currently tagged `metadata.image_status = "placeholder"` (i.e. on the Leka
"Image coming soon" card from v2.34.0), groups them by Medusa collection +
category, and renders an on-brand HTML report with search/filter and a deep
link to each PDP on `catalogs.leka.studio/leka-project/<handle>`.

Re-run safely any time. The page is served via the gateway at
  https://gateway.goco.bz/leka-product-catalogs/reports/leka-project-missing-images.html
once the file is committed.

Usage:
    python scripts/generate_missing_images_report.py
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import logging
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("missing_images_report")

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
STORE_PK = "pk_b7d7b7412262b05054450cd08213cd3d7d3432616ffff885e4c8a57e1b596e53"
PDP_BASE = "https://catalogs.leka.studio/leka-project"
COLL_BASE = "https://catalogs.leka.studio/leka-project/series"
OUT_PATH = Path("docs/reports/leka-project-missing-images.html")

# Display order + friendly labels for the 5 themed Medusa collections.
COLLECTION_LABELS = [
    ("leka-project-active-play", "Active Play",
     "Playgrounds, balance, climbing, sports."),
    ("leka-project-furniture-collection", "Furniture",
     "Cabinets, tables, chairs, storage."),
    ("leka-project-outdoor-and-nature-play", "Outdoor & Nature Play",
     "Outdoor, nature play, water play."),
    ("leka-project-creative-and-loose-parts", "Creative & Loose Parts",
     "Art, crafts, loose-parts play."),
    ("leka-project-early-years-collection", "Early Years",
     "Infant & toddler products."),
    ("(none)", "Uncategorized",
     "Products not yet assigned to a themed collection."),
]


def fetch_placeholder_products():
    """Yield every leka-project SC product currently on the placeholder image."""
    offset = 0
    while True:
        r = requests.get(
            f"{BACKEND}/store/products",
            headers={"x-publishable-api-key": STORE_PK},
            params={
                "limit": 100,
                "offset": offset,
                "fields": (
                    "id,handle,title,collection.handle,collection.title,"
                    "categories.handle,categories.name,"
                    "metadata,variants.metadata"
                ),
            },
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            if (p.get("metadata") or {}).get("image_status") != "placeholder":
                continue
            yield p
        offset += 100


def group_by_collection(prods):
    groups: dict[str, list[dict]] = {}
    for p in prods:
        col = (p.get("collection") or {}).get("handle") or "(none)"
        groups.setdefault(col, []).append(p)
    for v in groups.values():
        v.sort(key=lambda x: (x.get("title") or "").lower())
    return groups


def render_html(groups: dict[str, list[dict]], total_sc: int, total_backfilled: int) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_ph = sum(len(v) for v in groups.values())

    # Build a flat client-side dataset for the search + filter.
    flat = []
    for col, items in groups.items():
        label = next((lb for h, lb, _ in COLLECTION_LABELS if h == col), col)
        for p in items:
            vs = p.get("variants") or []
            sku = (vs[0].get("metadata") or {}).get("legacy_sku") if vs else None
            if not sku:
                lh = (p.get("metadata") or {}).get("legacy_handle", "")
                sku = lh.replace("wisdom-", "") if lh else ""
            flat.append({
                "id": p["id"],
                "handle": p["handle"],
                "title": p.get("title") or p["handle"],
                "sku": sku or "",
                "col_handle": col,
                "col_label": label,
                "categories": [c.get("handle") for c in (p.get("categories") or [])][:6],
            })
    flat_json = json.dumps(flat, separators=(",", ":"))

    # Order collection sections per COLLECTION_LABELS, dropping empty ones.
    sections_meta = []
    for ch, lb, blurb in COLLECTION_LABELS:
        n = len(groups.get(ch, []))
        if n:
            sections_meta.append((ch, lb, blurb, n))

    # ------------- HTML / CSS / JS -------------
    css = """
:root{
  --cream:#FFF9E6; --navy:#182557; --purple:#8003FF; --magenta:#970260;
  --amber:#FFA900; --redorange:#E54822; --card:#FFFFFF; --border:rgba(24,37,87,0.12);
  --muted:rgba(24,37,87,0.62);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--cream);color:var(--navy);
  font-family:'Manrope',ui-sans-serif,system-ui,Segoe UI,Arial,sans-serif;
  font-feature-settings:"ss01";-webkit-font-smoothing:antialiased}
a{color:var(--purple);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:48px 24px 96px}
.eyebrow{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:var(--purple)}
h1{font-size:40px;line-height:1.15;margin:.4rem 0 .25rem;font-weight:800}
.lede{font-size:17px;line-height:1.55;color:rgba(24,37,87,.78);margin:0;max-width:780px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0 8px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px;
  box-shadow:0 2px 8px rgba(24,37,87,.06)}
.stat .n{font-size:30px;font-weight:800;color:var(--navy);line-height:1}
.stat .l{font-size:13px;color:var(--muted);margin-top:6px}
.bar{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:14px;
  display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:24px 0 18px;
  position:sticky;top:0;z-index:5;box-shadow:0 2px 8px rgba(24,37,87,.06)}
.bar input{flex:1 1 280px;border:none;outline:none;background:transparent;font:inherit;color:var(--navy);
  padding:10px 12px;border-bottom:2px solid transparent}
.bar input:focus{border-bottom-color:var(--purple)}
.chip{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:9999px;
  border:1px solid var(--border);background:var(--cream);font-size:13px;font-weight:600;
  color:var(--navy);cursor:pointer;user-select:none;transition:all .15s}
.chip:hover{border-color:var(--purple)}
.chip.on{background:var(--purple);color:#fff;border-color:var(--purple)}
.chip .count{font-weight:700;font-size:11px;background:rgba(255,255,255,.18);padding:2px 7px;border-radius:9999px}
.chip:not(.on) .count{background:rgba(24,37,87,.08);color:var(--navy)}
section.coll{margin:34px 0 0}
section.coll header{display:flex;align-items:baseline;justify-content:space-between;gap:14px;margin-bottom:6px}
section.coll h2{font-size:24px;margin:0;font-weight:800}
section.coll .blurb{color:var(--muted);font-size:14px;margin:0 0 14px}
.coll-count{font-size:13px;color:var(--muted);font-weight:600}
.list{background:var(--card);border:1px solid var(--border);border-radius:16px;overflow:hidden;
  box-shadow:0 2px 8px rgba(24,37,87,.06)}
.row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;
  gap:14px;padding:14px 18px;border-top:1px solid var(--border)}
.row:first-child{border-top:none}
.row .meta{min-width:0}
.row .title{font-weight:600;color:var(--navy);font-size:15.5px;line-height:1.4}
.row .title a{color:var(--navy)}
.row .title a:hover{color:var(--purple)}
.row .sub{font-size:12px;color:var(--muted);margin-top:4px;display:flex;flex-wrap:wrap;gap:6px}
.tag{display:inline-block;padding:1px 8px;border-radius:9999px;background:rgba(128,3,255,.08);
  color:var(--purple);font-weight:600;font-size:11px}
.tag.amber{background:rgba(255,169,0,.14);color:#7A4D00}
.tag.gray{background:rgba(24,37,87,.06);color:var(--navy)}
.go{font-size:13px;font-weight:700;color:var(--purple);white-space:nowrap}
.go::after{content:" \\2192"}
.empty{padding:24px;text-align:center;color:var(--muted)}
.footer{margin-top:48px;padding-top:24px;border-top:1px solid var(--border);color:var(--muted);font-size:13px;line-height:1.6}
.footer code{background:rgba(24,37,87,.06);padding:2px 6px;border-radius:6px;font-size:12px}
@media (max-width:720px){.stats{grid-template-columns:repeat(2,1fr)}h1{font-size:32px}}
"""

    sections_html = []
    for ch, lb, blurb, n in sections_meta:
        sections_html.append(
            f'<section class="coll" data-collection="{html.escape(ch)}">'
            f'  <header><h2>{html.escape(lb)}</h2>'
            f'  <span class="coll-count" data-coll-count="{html.escape(ch)}">{n} products</span></header>'
            f'  <p class="blurb">{html.escape(blurb)}</p>'
            f'  <div class="list" data-list="{html.escape(ch)}"></div>'
            f'  <div class="empty" data-empty="{html.escape(ch)}" hidden>'
            f'    No products match the current filter.</div>'
            f'</section>'
        )

    chips_html = ['<div class="chip on" data-filter="__all__">All<span class="count">'
                  f'{total_ph}</span></div>']
    for ch, lb, _, n in sections_meta:
        chips_html.append(
            f'<div class="chip" data-filter="{html.escape(ch)}">{html.escape(lb)}'
            f'<span class="count">{n}</span></div>'
        )

    js = """
const DATA = __DATA__;
const PDP_BASE = "__PDP_BASE__";
const $ = (sel, el=document) => el.querySelector(sel);
const $$ = (sel, el=document) => Array.from(el.querySelectorAll(sel));

function rowHTML(p){
  const tags = (p.categories||[]).map(c=>`<span class="tag gray">${c}</span>`).join("");
  const sku = p.sku ? `<span class="tag">${p.sku}</span>` : "";
  return `
    <a class="row" href="${PDP_BASE}/${encodeURIComponent(p.handle)}" target="_blank" rel="noopener">
      <div class="meta">
        <div class="title">${p.title.replace(/</g,"&lt;")}</div>
        <div class="sub">${sku}${tags}</div>
      </div>
      <div class="go">View PDP</div>
    </a>`;
}

function render(){
  const q = ($("#q").value||"").trim().toLowerCase();
  const active = $(".chip.on")?.dataset.filter || "__all__";
  const byColl = {};
  for(const p of DATA){
    if(active!=="__all__" && p.col_handle!==active) continue;
    if(q){
      const blob = (p.title+" "+p.sku+" "+(p.categories||[]).join(" ")).toLowerCase();
      if(!blob.includes(q)) continue;
    }
    (byColl[p.col_handle]=byColl[p.col_handle]||[]).push(p);
  }
  $$("[data-list]").forEach(el=>{
    const ch = el.dataset.list;
    const items = byColl[ch] || [];
    el.innerHTML = items.map(rowHTML).join("");
    const empty = $(`[data-empty='${ch}']`);
    if(empty) empty.hidden = items.length > 0;
    const cnt = $(`[data-coll-count='${ch}']`);
    if(cnt) cnt.textContent = `${items.length} products`;
    const section = el.closest("section.coll");
    section.hidden = active!=="__all__" && active!==ch ? true : items.length===0 && q;
    if(active===ch) section.hidden = false;
  });
}

document.addEventListener("DOMContentLoaded", ()=>{
  render();
  $("#q").addEventListener("input", render);
  $$(".chip").forEach(c=>c.addEventListener("click", ()=>{
    $$(".chip").forEach(x=>x.classList.remove("on"));
    c.classList.add("on");
    render();
  }));
});
"""
    js = js.replace("__DATA__", flat_json).replace("__PDP_BASE__", PDP_BASE)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Leka Project — Products missing real photos</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">Leka Project · Image audit</div>
  <h1>Products still missing real photos</h1>
  <p class="lede">
    The 2026-05-25 backfill (v2.34.0) restored verified real photos for {total_backfilled} of the
    {total_backfilled + total_ph} previously blank products. The remaining {total_ph} are on the
    Leka-branded <em>"Image coming soon"</em> placeholder until real vendor photos arrive. Click any
    title to open its PDP on catalogs.leka.studio.
  </p>
  <div class="stats">
    <div class="stat"><div class="n">{total_sc:,}</div><div class="l">Total products in SC</div></div>
    <div class="stat"><div class="n">{total_backfilled:,}</div><div class="l">Real photos restored</div></div>
    <div class="stat"><div class="n">{total_ph:,}</div><div class="l">Still on placeholder</div></div>
    <div class="stat"><div class="n">{len(sections_meta)}</div><div class="l">Collections affected</div></div>
  </div>
  <div class="bar">
    <input id="q" type="search" placeholder="Search title, SKU, category…" autocomplete="off" spellcheck="false">
    {''.join(chips_html)}
  </div>
  {''.join(sections_html)}
  <div class="footer">
    <p>Generated {now}. Data source: Medusa Store API
       (<code>sc_01KNKTHC0B7KFEDSZ3NNM49JQW</code>) — every product where
       <code>metadata.image_status == "placeholder"</code>.</p>
    <p>To swap a placeholder for a real photo: drop the new image into
       <code>gs://ai-agents-go-vendors/leka-project/&lt;...&gt;/&lt;item_code&gt;_*</code> then run
       <code>python scripts/backfill_leka_project_images.py --verify --force</code> followed by
       <code>--attach</code>. See <code>CHANGELOG.md</code> v2.34.0 for the full pipeline.</p>
  </div>
</div>
<script>{js}</script>
</body>
</html>
"""


def main():
    log.info("Fetching placeholder products from Store API ...")
    prods = list(fetch_placeholder_products())
    log.info("  %d placeholder products", len(prods))

    # Also fetch total SC product count + backfilled count for the header stats
    log.info("Counting SC totals ...")
    total_sc = 0
    backfilled = 0
    offset = 0
    while True:
        r = requests.get(
            f"{BACKEND}/store/products",
            headers={"x-publishable-api-key": STORE_PK},
            params={"limit": 100, "offset": offset, "fields": "id,metadata.image_status"},
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            break
        total_sc += len(batch)
        for p in batch:
            if (p.get("metadata") or {}).get("image_status") == "backfilled":
                backfilled += 1
        offset += 100
    log.info("  total=%d backfilled=%d placeholder=%d", total_sc, backfilled, len(prods))

    groups = group_by_collection(prods)
    html_out = render_html(groups, total_sc=total_sc, total_backfilled=backfilled)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_out, encoding="utf-8")
    log.info("Wrote %s (%d bytes)", OUT_PATH, len(html_out))


if __name__ == "__main__":
    main()
