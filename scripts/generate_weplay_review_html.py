"""Generate a static HTML review page for Weplay AI-inferred drafts +
multi-doc SKU groups (variant candidates).

Outputs to docs/weplay-review.html.

Two sections:
  1. AI-inferred drafts (103 from stamp_weplay_ai_inferred.py) —
     review whether the AI-assigned SKU + name + description are correct.
  2. SKU tokens with multiple docs (variant candidates) — review
     whether to merge / promote / keep separate.

No write-back from the HTML — it's a read-only review aid.
"""
from __future__ import annotations

import argparse
import html as html_lib
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from google.cloud import firestore

_FALLBACK_ADC = (
    r"C:\Users\Eukrit\AppData\Roaming\gcloud\legacy_credentials"
    r"\codex-chatgpt@ai-agents-go.iam.gserviceaccount.com\adc.json"
)
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ or not os.path.exists(
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
):
    if os.path.exists(_FALLBACK_ADC):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _FALLBACK_ADC
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("generate_weplay_review_html")

SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")
PROXY_BASE = "https://catalogs.leka.studio/api/i/weplay"
OUT = Path("docs/weplay-review.html")

PAGE_TMPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Weplay Catalog Review</title>
<style>
:root {{
  --purple: #8003FF;
  --navy: #182557;
  --cream: #FFF9E6;
  --red: #C7161E;
  --bg: #f5f5f7;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; background: var(--bg); color: #1a1a1f; }}
h1 {{ font-size: 24px; margin: 0 0 8px; color: var(--navy); }}
.subtitle {{ color: #666; margin-bottom: 24px; font-size: 14px; }}
.tabs {{ display: flex; gap: 8px; margin: 24px 0 16px; border-bottom: 2px solid #e0e0e0; }}
.tab {{ padding: 10px 18px; cursor: pointer; font-weight: 600; color: #666; border-bottom: 2px solid transparent; margin-bottom: -2px; }}
.tab.active {{ color: var(--purple); border-bottom-color: var(--purple); }}
.search {{ margin: 16px 0; }}
.search input {{ padding: 8px 12px; width: 320px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }}
.section {{ display: none; }}
.section.active {{ display: block; }}

/* AI-inferred cards */
.cat-group {{ margin: 24px 0 12px; }}
.cat-header {{ font-size: 14px; font-weight: 700; text-transform: uppercase; color: var(--purple); margin: 16px 0 8px; letter-spacing: 0.5px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
.card {{ background: white; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(24,37,87,0.06); border-left: 4px solid #ddd; }}
.card.ai-inferred {{ border-left-color: var(--purple); }}
.card.variant-group {{ border-left-color: var(--red); }}
.sku {{ font-family: monospace; font-size: 11px; color: #888; }}
.name {{ font-size: 16px; font-weight: 600; margin: 4px 0; }}
.desc {{ font-size: 13px; color: #444; line-height: 1.5; }}
.meta {{ margin-top: 8px; font-size: 11px; color: #888; }}
.notes {{ margin-top: 8px; font-size: 12px; color: #666; font-style: italic; padding: 6px 10px; background: #fafafa; border-radius: 6px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; text-transform: uppercase; }}
.badge-cat {{ background: #f0e8ff; color: var(--purple); }}
.badge-status {{ background: #fff0e8; color: var(--red); }}
.badge-active {{ background: #e8f5e9; color: #2e7d32; }}

/* Variant groups */
.variant-group-card {{ background: white; border-radius: 12px; padding: 18px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(24,37,87,0.06); border-left: 4px solid var(--red); }}
.variant-group-header {{ font-size: 17px; font-weight: 700; color: var(--navy); margin-bottom: 4px; }}
.variant-group-meta {{ font-size: 12px; color: #888; margin-bottom: 12px; }}
.variant-list {{ display: flex; flex-direction: column; gap: 8px; }}
.variant-row {{ display: grid; grid-template-columns: 120px 1fr 1fr 80px; gap: 12px; padding: 8px 10px; background: #fafafa; border-radius: 6px; font-size: 13px; }}
.variant-row.canonical {{ background: #fff8e1; border-left: 3px solid var(--purple); }}
.variant-row .doc {{ font-family: monospace; font-size: 11px; }}
.variant-row .nm {{ font-weight: 500; }}
.variant-row .img {{ text-align: center; font-size: 11px; }}

.summary-bar {{ background: white; padding: 16px; border-radius: 10px; margin-bottom: 16px; display: flex; gap: 24px; flex-wrap: wrap; }}
.summary-item {{ display: flex; flex-direction: column; }}
.summary-num {{ font-size: 28px; font-weight: 700; color: var(--purple); line-height: 1; }}
.summary-label {{ font-size: 12px; color: #666; margin-top: 4px; }}
</style>
</head>
<body>
<h1>Weplay Catalog Review</h1>
<div class="subtitle">Generated {ts} — review aid for AI-inferred drafts (103) and multi-doc SKU groups</div>

<div class="summary-bar">
  <div class="summary-item"><div class="summary-num">{n_ai}</div><div class="summary-label">AI-inferred drafts</div></div>
  <div class="summary-item"><div class="summary-num">{n_var_groups}</div><div class="summary-label">multi-doc SKU tokens</div></div>
  <div class="summary-item"><div class="summary-num">{n_var_docs}</div><div class="summary-label">docs in variant groups</div></div>
  <div class="summary-item"><div class="summary-num">{n_active}</div><div class="summary-label">total active products</div></div>
</div>

<div class="tabs">
  <div class="tab active" onclick="show('ai')">AI-Inferred Drafts ({n_ai})</div>
  <div class="tab" onclick="show('var')">Variant Groups ({n_var_groups})</div>
</div>

<div class="search"><input type="text" id="search" placeholder="Search by SKU or name..." oninput="filter()"></div>

<div id="section-ai" class="section active">
{ai_cards}
</div>

<div id="section-var" class="section">
{variant_groups}
</div>

<script>
function show(which) {{
  document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', (i===0 && which==='ai') || (i===1 && which==='var')));
  document.getElementById('section-ai').classList.toggle('active', which==='ai');
  document.getElementById('section-var').classList.toggle('active', which==='var');
}}
function filter() {{
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.card, .variant-group-card').forEach(el => {{
    el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>
"""


def _esc(s) -> str:
    return html_lib.escape(str(s or ""))


def build(coll: firestore.CollectionReference) -> str:
    ai_inferred: list[dict] = []
    token_groups: dict[str, list[dict]] = defaultdict(list)
    n_active_total = 0

    for snap in coll.stream():
        d = snap.to_dict() or {}
        if d.get("status") == "active":
            n_active_total += 1
        # AI-inferred drafts
        if d.get("source_ai_inferred"):
            ai_inferred.append({
                "doc_id": snap.id,
                "item_code": d.get("item_code") or "",
                "name": d.get("name") or "",
                "description": (d.get("description") or "")[:400],
                "category": d.get("category") or "uncategorized",
                "notes": (d.get("notes") or "")[:300],
                "source_sha": d.get("source_ai_sha") or "",
            })
        # Multi-doc SKU tokens (excluding merged duplicates)
        if d.get("status") != "merged_duplicate":
            sku = (d.get("item_code") or "").upper()
            m = SKU_TOKEN_RE.search(sku)
            if m:
                token_groups[m.group(1)].append({
                    "doc_id": snap.id,
                    "item_code": sku,
                    "status": d.get("status") or "",
                    "name": d.get("name") or "",
                    "description": (d.get("description") or "")[:120],
                    "image": ((d.get("images") or [{}])[0] or {}).get("url", ""),
                    "has_images": bool(d.get("images")),
                })

    variant_groups = {t: docs for t, docs in token_groups.items() if len(docs) > 1}

    # Build AI-inferred section grouped by category
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for d in ai_inferred:
        by_cat[d["category"]].append(d)
    ai_chunks: list[str] = []
    for cat in sorted(by_cat):
        ai_chunks.append(f'<div class="cat-header">{_esc(cat)} ({len(by_cat[cat])})</div>')
        ai_chunks.append('<div class="grid">')
        for d in sorted(by_cat[cat], key=lambda x: x["item_code"]):
            ai_chunks.append(f"""
<div class="card ai-inferred">
  <div class="sku">{_esc(d['item_code'])} <span style="color:#bbb"> · </span> {_esc(d['doc_id'])}</div>
  <div class="name">{_esc(d['name'])}</div>
  <div class="desc">{_esc(d['description'])}</div>
  <div class="meta"><span class="badge badge-cat">{_esc(d['category'])}</span> <span class="badge badge-status">DRAFT</span></div>
  <div class="notes">📝 {_esc(d['notes'])}</div>
</div>""")
        ai_chunks.append('</div>')

    # Build variant-group section
    var_chunks: list[str] = []
    for token in sorted(variant_groups, key=lambda t: -len(variant_groups[t])):
        docs = variant_groups[token]
        canonical_name = max((d["name"] for d in docs), key=len)
        all_same_name = len({(d["name"] or "").strip().lower() for d in docs}) == 1
        var_chunks.append(f"""
<div class="variant-group-card">
  <div class="variant-group-header">{_esc(token)} — {_esc(canonical_name)}</div>
  <div class="variant-group-meta">{len(docs)} docs · {"same name across all docs" if all_same_name else "MIXED names — likely AI mis-inference"}</div>
  <div class="variant-list">""")
        for d in sorted(docs, key=lambda x: x["doc_id"]):
            img = (
                f'<img src="{_esc(d["image"])}" style="width:60px;height:60px;object-fit:cover;border-radius:4px;">'
                if d["has_images"] and d["image"] else "—"
            )
            status_badge = (
                '<span class="badge badge-active">ACTIVE</span>'
                if d["status"] == "active"
                else '<span class="badge badge-status">DRAFT</span>'
            )
            var_chunks.append(f"""
    <div class="variant-row">
      <div class="doc">{_esc(d['doc_id'])}</div>
      <div class="nm">{_esc(d['name'] or '(unnamed)')}<br><span class="sku">{_esc(d['item_code'])}</span></div>
      <div>{status_badge}</div>
      <div class="img">{img}</div>
    </div>""")
        var_chunks.append("  </div>\n</div>")

    html = PAGE_TMPL.format(
        ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
        n_ai=len(ai_inferred),
        n_var_groups=len(variant_groups),
        n_var_docs=sum(len(v) for v in variant_groups.values()),
        n_active=n_active_total,
        ai_cards="\n".join(ai_chunks),
        variant_groups="\n".join(var_chunks),
    )
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=str, default=str(OUT))
    args = ap.parse_args()
    db = firestore.Client(project="ai-agents-go", database="vendors")
    coll = db.collection("vendors").document("weplay").collection("products")
    log.info("reading Firestore...")
    html_str = build(coll)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_str, encoding="utf-8")
    log.info("wrote %s (%d bytes)", out_path, len(html_str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
