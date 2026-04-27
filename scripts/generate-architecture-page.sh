#!/usr/bin/env bash
# generate-architecture-page.sh — Emit docs/architecture.html from PROJECT_INDEX.md.
#
# Per Rule 4 (refresh): every project has three first-class artifacts —
#   1. Build Log         (BUILD_LOG.md / CHANGELOG.md, markdown, append-only)
#   2. Build Summary     (docs/build-summary.html, latest build status with badge)
#   3. Architecture Summary (docs/architecture.html, this file's output)
#
# Source-of-truth is PROJECT_INDEX.md. We pull six sections and lay them out:
#   - Status        → header card
#   - Directory Map → table
#   - Databases & Data Stores → table
#   - Connectors    → grouped list
#   - Relationships → cross-links
#   - Security Surface → table
#
# Hand-curated escape hatch: if docs/architecture.html starts with the literal
# comment "<!-- HAND-CURATED -->" the generator leaves it alone and exits 0.
#
# Usage:  ./generate-architecture-page.sh [PROJECT_PATH]   (defaults to $PWD)

set -euo pipefail

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

PROJECT_PATH="${1:-$PWD}"
cd "$PROJECT_PATH"
PROJECT_NAME=$(basename "$PROJECT_PATH")
TODAY=$(date +%Y-%m-%d)
OUT="docs/architecture.html"

[ -d docs ] || mkdir -p docs

if [ -f "$OUT" ] && head -1 "$OUT" | grep -q "HAND-CURATED"; then
  echo "[architecture] $OUT is hand-curated — skipping."
  exit 0
fi

if [ ! -f PROJECT_INDEX.md ]; then
  echo "[architecture] no PROJECT_INDEX.md — emitting placeholder."
  cat > "$OUT" <<HTML
<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>${PROJECT_NAME} — Architecture Summary</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}</style>
</head><body>
<h1>${PROJECT_NAME} — Architecture Summary</h1>
<p>No <code>PROJECT_INDEX.md</code> present. Create one from <code>Credentials Claude Code/Instructions/PROJECT_INDEX.template.md</code> and re-run <code>scripts/generate-architecture-page.sh</code>.</p>
</body></html>
HTML
  exit 0
fi

python - "$PROJECT_NAME" "$TODAY" "$OUT" <<'PY'
import sys, re, html, pathlib, json
project, today, out = sys.argv[1], sys.argv[2], sys.argv[3]
txt = pathlib.Path("PROJECT_INDEX.md").read_text(encoding="utf-8", errors="ignore")

def section(name):
    m = re.search(rf'^##\s+{re.escape(name)}\b(.*?)(?=^##\s+|\Z)', txt, re.S | re.M)
    return m.group(1).strip() if m else ""

def md_table_to_rows(md):
    rows = []
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|"): continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Skip header separator like |---|---|
        if all(re.fullmatch(r":?-+:?", c or "") for c in cells): continue
        rows.append(cells)
    return rows

def md_list(md):
    items = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("- "): items.append(s[2:])
    return items

def linkify(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
    s = re.sub(r'(?<![\">])(https?://[^\s<)]+)', r'<a href="\1">\1</a>', s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    return s

# --- pull sections -----------------------------------------------------
status_md       = section("Status")
dirmap_md       = section("Directory Map")
db_md           = section("Databases & Data Stores")
conn_md         = section("Connectors (external services — API-first per Rule 7)") or section("Connectors")
rel_md          = section("Relationships")
sec_md          = section("Security Surface")
ci_md           = section("Cloud Build & CI/CD")
sched_md        = section("Scheduled / Cron / Cloud Scheduler")

# --- header card ----
status_html = "".join(f"<li>{linkify(i)}</li>" for i in md_list(status_md)) or "<li>(no Status section)</li>"

# --- generic table renderer ----
def table_html(md, default=""):
    rows = md_table_to_rows(md)
    if not rows:
        return f"<p class='meta'>{default}</p>" if default else ""
    head, *body = rows
    th = "".join(f"<th>{linkify(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{linkify(c)}</td>" for c in r) + "</tr>" for r in body if r and any(r))
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"

# --- connectors: keep markdown structure (subheaders + bullets) ----
def connectors_html(md):
    if not md: return ""
    out = []
    for line in md.splitlines():
        s = line.rstrip()
        if s.startswith("### "):
            out.append(f"<h3>{html.escape(s[4:])}</h3><ul>")
        elif s.startswith("- "):
            out.append(f"<li>{linkify(s[2:])}</li>")
        elif s == "":
            if out and out[-1].endswith("</li>"): out.append("</ul>")
        else:
            pass
    if out and not out[-1].endswith("</ul>"): out.append("</ul>")
    return "".join(out)

# --- relationships: bullets ----
def relationships_html(md):
    items = md_list(md)
    if not items: return "<p class='meta'>No declared relationships.</p>"
    return "<ul>" + "".join(f"<li>{linkify(i)}</li>" for i in items) + "</ul>"

# --- emit ----
HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>{html.escape(project)} — Architecture Summary</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 1040px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ margin-bottom: 0.25rem; }}
  h2 {{ margin-top: 2rem; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
  h3 {{ margin-top: 1.5rem; color: #374151; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.25rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
  th {{ background: #fafafa; font-weight: 600; }}
  code {{ background: #f4f4f5; padding: 1px 6px; border-radius: 4px; font-size: 0.9em; }}
  a {{ color: #2563eb; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  ul {{ margin-top: 0.4rem; }}
</style>
</head><body>
<h1>{html.escape(project)} <span style="font-weight:400;color:#666">— Architecture Summary</span></h1>
<div class="meta">Generated {today} from <a href="../PROJECT_INDEX.md">PROJECT_INDEX.md</a> · Rule 4 (refresh)</div>

<div class="card">
  <h2 style="margin-top:0;border:0">Status</h2>
  <ul>{status_html}</ul>
</div>

<h2>Directory Map</h2>
{table_html(dirmap_md, "No directory map declared.")}

<h2>Databases &amp; Data Stores</h2>
{table_html(db_md) or '<ul>' + ''.join(f'<li>{linkify(i)}</li>' for i in md_list(db_md)) + '</ul>' if md_list(db_md) else "<p class='meta'>None declared.</p>"}

<h2>Cloud Build &amp; CI/CD</h2>
<ul>{''.join(f'<li>{linkify(i)}</li>' for i in md_list(ci_md)) or "<li class='meta'>No CI/CD declared.</li>"}</ul>

<h2>Scheduled / Cron</h2>
{table_html(sched_md, "No scheduled jobs.")}

<h2>Connectors</h2>
{connectors_html(conn_md) or "<p class='meta'>No connectors declared.</p>"}

<h2>Security Surface</h2>
{table_html(sec_md, "No security surface declared.") }

<h2>Relationships</h2>
{relationships_html(rel_md)}

<p class="meta">Regenerated by <code>scripts/generate-architecture-page.sh</code>. To opt-out of regeneration, replace this file with one whose first line is <code>&lt;!-- HAND-CURATED --&gt;</code>.</p>
</body></html>
"""

pathlib.Path(out).write_text(HTML, encoding="utf-8")
print(f"[architecture] wrote {out}")
PY
