"""
backfill_r2_vendor_urls.py — Phase 3 of the Dulwich Rev2 pipeline.

Preserves the vendor URLs captured from the Notion R2 page onto the matching
Medusa products, so the proposal render (which reads product.metadata.supplier_url)
shows clickable vendor links.

For every R2 item that carries a Notion `vendor_url` (mostly the epdm-graphics.com
links on the Walkway 4soft graphics), resolve each of its codes to a Medusa
product via a full product index (by variant sku + metadata.legacy_sku — the
`?sku=` admin filter is unreliable on this backend), then MERGE
metadata.supplier_url + metadata.source_url onto the product (only when missing
or different). Idempotent.

Dry-run by default; --write to apply.
Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
DEFAULT_SELECTION = (
    r"C:\Users\Eukrit\OneDrive\Claude Code\NUC11\leka-projects\.claude"
    r"\worktrees\goofy-snyder-ab838e\projects\dulwich-singapore\_data"
    r"\dulwich-singapore-r2-selection.json")


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def index_all(c) -> dict[str, tuple[str, str]]:
    idx: dict[str, tuple[str, str]] = {}
    off = 0
    while True:
        r = c._get("/admin/products", {
            "limit": 200, "offset": off,
            "fields": "id,handle,variants.id,variants.sku,variants.metadata"})
        b = r.get("products", [])
        if not b:
            break
        for p in b:
            for v in p.get("variants") or []:
                for key in (v.get("sku"), (v.get("metadata") or {}).get("legacy_sku")):
                    if key:
                        idx.setdefault(norm(key), (p["id"], v["id"]))
        if len(b) < 200:
            break
        off += 200
    return idx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selection", default=DEFAULT_SELECTION)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    sel = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    items = [it for it in sel["items"] if it.get("vendor_url")]
    print(f"== Phase 3: {len(items)} R2 items carry a vendor URL "
          f"({'WRITE' if args.write else 'DRY-RUN'}) ==")

    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    c = MedusaImporter(base_url=BACKEND)

    print("   indexing all Medusa variants…")
    idx = index_all(c)
    print(f"   indexed {len(idx)} keys")

    # code -> vendor_url (one item may share a url across codes)
    code_url: dict[str, str] = {}
    for it in items:
        for code in (it.get("codes") or []):
            code_url.setdefault(code, it["vendor_url"])

    # group target products
    pid_url: dict[str, tuple[str, str]] = {}   # pid -> (url, sample_code)
    unresolved = []
    for code, url in code_url.items():
        hit = idx.get(norm(code))
        if not hit:
            unresolved.append(code)
            continue
        pid_url.setdefault(hit[0], (url, code))

    print(f"   target products={len(pid_url)} unresolved_codes={unresolved}")

    updated = skipped = errors = 0
    for pid, (url, code) in pid_url.items():
        try:
            cur = c._get(f"/admin/products/{pid}", {"fields": "id,metadata"})
            md = (cur.get("product") or {}).get("metadata") or {}
            if md.get("supplier_url") == url and md.get("source_url") == url:
                skipped += 1
                continue
            if not args.write:
                print(f"   [dry] {code:14} pid={pid} <- {url[:60]}")
                updated += 1
                continue
            new_md = dict(md)
            new_md["supplier_url"] = url
            new_md.setdefault("source_url", url)
            c._post(f"/admin/products/{pid}", {"metadata": new_md})
            updated += 1
        except Exception as e:
            errors += 1
            body = getattr(getattr(e, "response", None), "text", "") or str(e)
            print(f"   ! {code} ({pid}): {body[:200]}")

    print(f"\n== done: updated={updated} already_set={skipped} errors={errors} ==")
    if not args.write:
        print("   (dry-run — re-run with --write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
