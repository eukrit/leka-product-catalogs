"""
build_r2_draft_order.py — Phase 5 of the Dulwich Rev2 pipeline.

Assembles a Medusa v2 Draft Order (Singapore / SGD) from the R2 selection, one
line per PUBLISHED R2 product, with the per-line zone/subzone/category/selection
metadata the leka-projects proposal adapter reads.

Items that can't be draft-order lines (the 8 draft "Proposal"-bucket items, the
2 code-less items, or anything unresolved) are written to a manual_yaml BoQ
source so the proposal render still shows them as TBC. The render then merges:
    boq.sources: [{medusa, draft_order_ids:[…]}, {manual_yaml, path: …r2-manual.yaml}]

Pricing (SGD = order currency). Precedence (v2.61.0 — synced to Medusa):
  - Medusa variant SGD price (AUTHORITATIVE; backfilled by
    wisdom-catalog/sync_po_sgd_to_medusa.py from the reconciled catalog
    flat-path retail), else
  - Rev1 BoQ retail_sgd, else
  - the fob*4.44 LAST-RESORT heuristic (only when a code has neither a Medusa
    SGD price nor a Rev1 price — logged with a warning), else
  - TBC (unit_price 0, retail_status="tbc").
  The fob*4.44 heuristic is no longer the primary path for Wisdom lines; the
  Medusa SGD price is. Per-line `metadata.price_source` records which path won.

Idempotent on metadata.rev == "dulwich-r2" unless --force. Variant lookup uses a
full product index (sku + metadata.legacy_sku); the `?sku=` filter is unreliable.
Dry-run by default; --write to create. Auth: LEKA_MEDUSA_ADMIN_EMAIL/PASSWORD.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
REGION_SGD = "reg_01KSEBH1EAK9RWAYEW87QY8NWS"
SC_LEKA = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
WISDOM_FOB_TO_SGD = 104.09 * 1.05 / 24.6  # ≈ 4.44 — LAST-RESORT only (v2.61.0); Medusa SGD price is now authoritative
REV = "dulwich-r2"

LP = (r"C:\Users\Eukrit\OneDrive\Claude Code\NUC11\leka-projects\.claude"
      r"\worktrees\goofy-snyder-ab838e")
DEFAULT_SELECTION = LP + r"\projects\dulwich-singapore\_data\dulwich-singapore-r2-selection.json"
REV1_BOQ = LP + r"\docs\reports\_data\dulwich-singapore-boq.json"
MAPPING = LP + r"\docs\reports\_data\dulwich-singapore-r2-mapping.json"
MANUAL_YAML = LP + r"\projects\dulwich-singapore\_data\dulwich-singapore-r2-manual.yaml"


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def index_all(c) -> dict[str, dict]:
    """norm(code) -> {pid, vid, status, sgd} where sgd is the variant's SGD price
    in major units (float) or None when the variant has no SGD price."""
    idx: dict[str, dict] = {}
    off = 0
    while True:
        r = c._get("/admin/products", {
            "limit": 200, "offset": off,
            "fields": "id,status,variants.id,variants.sku,variants.metadata,"
                      "variants.prices.amount,variants.prices.currency_code"})
        b = r.get("products", [])
        if not b:
            break
        for p in b:
            st = p.get("status")
            for v in p.get("variants") or []:
                sgd_minor = next(
                    (pr["amount"] for pr in (v.get("prices") or [])
                     if pr.get("currency_code") == "sgd"), None)
                sgd = round(sgd_minor / 100, 2) if sgd_minor is not None else None
                for k in (v.get("sku"), (v.get("metadata") or {}).get("legacy_sku")):
                    if k:
                        idx.setdefault(norm(k), {
                            "pid": p["id"], "vid": v["id"], "status": st, "sgd": sgd})
        if len(b) < 200:
            break
        off += 200
    return idx


def load_prices():
    rev1, fob = {}, {}
    try:
        d = json.loads(Path(REV1_BOQ).read_text(encoding="utf-8"))
        for it in d.get("items", []):
            cc, rs = it.get("product_code"), (it.get("pricing") or {}).get("retail_sgd")
            if cc and rs:
                rev1[norm(cc)] = rs
    except Exception:
        pass
    try:
        m = json.loads(Path(MAPPING).read_text(encoding="utf-8"))
        for it in m.get("items", []):
            for mt in it.get("matches", []):
                if mt.get("status") == "found" and mt.get("fob_usd"):
                    fob[norm(mt["code"])] = mt["fob_usd"]
    except Exception:
        pass
    return rev1, fob


def price_for(code, idx, rev1, fob):
    """Resolve the SGD unit price. Returns (price, status, source).

    Precedence: Medusa variant SGD price (authoritative) -> Rev1 BoQ retail_sgd
    -> fob*4.44 last-resort heuristic -> TBC.
    """
    n = norm(code)
    hit = idx.get(n)
    if hit and hit.get("sgd") is not None:
        return round(hit["sgd"], 2), "priced", "medusa"
    if n in rev1:
        return round(rev1[n], 2), "priced", "rev1"
    if n in fob:
        return round(fob[n] * WISDOM_FOB_TO_SGD, 2), "priced", "heuristic"
    return None, "tbc", "tbc"


def boq_item_from_selection(it, price, status, source="tbc"):
    """Convert an R2 selection item to a renderer BoQ item (for manual_yaml)."""
    return {
        "zone": it["zone"], "zone_title": it["zone_title"],
        "subzone": it["subzone"], "subzone_no": it.get("subzone_no") or 0,
        "subzone_status": it.get("subzone_status") or "in_scope",
        "category": it.get("category") or it["subzone"],
        "seq": it.get("seq") or 0,
        "name": it["name"], "name_clean": it.get("name_clean") or it["name"],
        "product_code": it.get("product_code"),
        "option_no": it.get("option_no"),
        "selection_status": it.get("selection_status") or "selected",
        "supplier": it.get("supplier"), "supplier_url": it.get("vendor_url"),
        "age_range": it.get("age_range"),
        "dimensions": it.get("dimensions") or {"raw": None, "L": None, "W": None,
                                               "H": None, "unit": "cm"},
        # Renderer's get_qty() expects a {qty, unit, detail} dict.
        "quantity": it.get("quantity") or {"qty": 1, "unit": "pc", "detail": None},
        "images": it.get("images") or [],
        "pricing": {"retail_status": status,
                    "price_source": source,
                    "retail_sgd": price if status == "priced" else None},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selection", default=DEFAULT_SELECTION)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    sel = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    items = sel["items"][:args.limit] if args.limit else sel["items"]

    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    c = MedusaImporter(base_url=BACKEND)

    print(f"== Phase 5: build Dulwich R2 draft order "
          f"({'WRITE' if args.write else 'DRY-RUN'}) ==")
    print("   indexing Medusa variants…")
    idx = index_all(c)
    rev1, fob = load_prices()
    print(f"   indexed {len(idx)} keys; rev1_prices={len(rev1)} fobs={len(fob)}")

    lines, manual = [], []
    priced = tbc = 0
    src_counts = {"medusa": 0, "rev1": 0, "heuristic": 0, "tbc": 0}
    heuristic_codes = []
    for it in items:
        code = it.get("product_code")
        price, status, source = price_for(code, idx, rev1, fob) if code \
            else (None, "tbc", "tbc")
        src_counts[source] = src_counts.get(source, 0) + 1
        if source == "heuristic":
            heuristic_codes.append(code)
        if status == "priced":
            priced += 1
        else:
            tbc += 1
        hit = idx.get(norm(code)) if code else None
        # Only PUBLISHED products can be draft-order lines.
        if hit and hit["status"] == "published":
            qty = (it.get("quantity") or {}).get("qty") or 1
            lines.append({
                "variant_id": hit["vid"], "quantity": int(qty),
                "unit_price": int(round((price or 0) * 100)),
                "metadata": {
                    "zone": it["zone"], "zone_title": it["zone_title"],
                    "subzone": it["subzone"], "subzone_no": it.get("subzone_no") or 0,
                    "subzone_status": it.get("subzone_status") or "in_scope",
                    "category": it.get("category") or it["subzone"],
                    "selection_status": it.get("selection_status") or "selected",
                    "seq": it.get("seq") or 0, "option_no": it.get("option_no"),
                    "name_clean": it.get("name_clean"),
                    "retail_status": status, "price_source": source,
                    "product_code": code,
                    "dimensions": it.get("dimensions"),
                    "vendor_url": it.get("vendor_url"),
                },
            })
        else:
            manual.append(boq_item_from_selection(it, price, status, source))

    print(f"   draft-order lines={len(lines)} (published)  "
          f"manual/TBC items={len(manual)}  priced={priced} tbc={tbc}")
    print(f"   price sources: medusa={src_counts['medusa']} rev1={src_counts['rev1']} "
          f"heuristic={src_counts['heuristic']} tbc={src_counts['tbc']}")
    if heuristic_codes:
        print(f"   WARNING: {len(heuristic_codes)} line(s) fell back to the fob*4.44 "
              f"last-resort heuristic (no Medusa SGD nor Rev1 price): "
              f"{', '.join(str(x) for x in heuristic_codes)}")

    # write manual_yaml (draft Proposal items + code-less + unresolved).
    # JSON is valid YAML and boq_sources loads it with yaml.safe_load, so we
    # emit JSON to avoid a pyyaml dependency in this venv.
    if args.write:
        Path(MANUAL_YAML).parent.mkdir(parents=True, exist_ok=True)
        Path(MANUAL_YAML).write_text(
            json.dumps({"items": manual}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"   wrote {len(manual)} manual items -> {MANUAL_YAML}")

    if not args.write:
        print("   (dry-run — re-run with --write to create the draft order + manual yaml)")
        return 0

    if not args.force:
        ex = c._get("/admin/draft-orders", {"limit": 100, "fields": "id,metadata"})
        for o in ex.get("draft_orders", ex.get("orders", [])):
            if (o.get("metadata") or {}).get("rev") == REV:
                print(f"   existing draft order rev={REV}: {o['id']} (use --force for new)")
                print(f"   DRAFT_ORDER_ID={o['id']}")
                return 0

    body = {"email": "proposals@nubo.asia", "region_id": REGION_SGD,
            "sales_channel_id": SC_LEKA, "items": lines,
            "metadata": {"project_id": "dulwich-singapore", "rev": REV,
                         "source": "notion:R2:36f82cea8bb08003b63af7179e9378bc"}}
    try:
        res = c._post("/admin/draft-orders", body)
    except Exception as e:
        bdy = getattr(getattr(e, "response", None), "text", "") or str(e)
        print(f"   ! draft-order create failed: {bdy[:500]}")
        return 1
    do = res.get("draft_order") or res.get("order") or res
    doid = do.get("id")
    print(f"\n== created draft order {doid} (status={do.get('status')}, {len(lines)} lines) ==")

    for attempt in range(5):
        time.sleep(1.5)
        try:
            exp = c._get(f"/admin/draft-orders/{doid}/proposal-export")
            n = len(exp.get("cart", {}).get("items", []))
            print(f"   proposal-export OK: {n} items, "
                  f"currency={exp.get('cart',{}).get('currency_code')}")
            break
        except Exception as e:
            if attempt == 4:
                bdy = getattr(getattr(e, "response", None), "text", "") or str(e)
                print(f"   ! proposal-export still failing: {bdy[:200]}")
    print(f"\n   DRAFT_ORDER_ID={doid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
