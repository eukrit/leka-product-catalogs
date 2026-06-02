"""
build_r2_curated.py — Phase 5b: author the CURATED Dulwich Rev2 BoQ.

Replaces the raw Notion-derived selection with the user's exact per-zone
equipment lists, quantities, removals and explicit surfacing lines. Produces:
  - a Medusa Draft Order (Singapore/SGD) of the PUBLISHED products, one line per
    item with zone (B / BS / C / D) + qty + SGD unit price + dimensions metadata;
  - a manual_yaml BoQ source for the explicit surfacing lines + the products that
    aren't published in Medusa (created here as draft "Proposal"-bucket items, TBC).

Zones (titles already include "Zone X -" so the renderer prints them verbatim):
  B  = Zone B - Toddler and Nursery
  BS = Zone B - Sandpit & Zone C - Sandpit
  C  = Zone C - Truck Path excluding Bike Track
  D  = Zone D - Balcony 17 Classrooms

Pricing: Rev1 BoQ retail_sgd if known, else Wisdom landed (fob*4.44), else TBC.
Surfacing rates: Grass Green EPDM 119.90, Hexagon Grid Green 182.85,
Sand Pit 300mm w/ drainage 420.00 (per user), EPDM Mound lump 25,400 (per user).

Dry-run by default; --write to apply. Auth: LEKA_MEDUSA_ADMIN_*; ADC for Firestore/GCS.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
REGION_SGD = "reg_01KSEBH1EAK9RWAYEW87QY8NWS"
SC_LEKA = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
SC_PROPOSAL = "sc_01KST3PRZ3JSFX79P30TE8TSF2"
WISDOM_FOB_TO_SGD = 104.09 * 1.05 / 24.6  # ≈ 4.44
REV = "dulwich-r2"
CATALOG_DB = "leka-product-catalogs"

# leka-projects worktree that holds the Dulwich R2 data files + receives the
# regenerated manual.yaml. Override with $LEKA_PROJECTS_WORKTREE (the default
# goofy-snyder worktree path is not stable across machines / OneDrive prunes).
LP = os.environ.get("LEKA_PROJECTS_WORKTREE") or (
    r"C:\Users\Eukrit\OneDrive\Claude Code\NUC11\leka-projects\.claude"
    r"\worktrees\goofy-snyder-ab838e")
SELECTION = LP + r"\projects\dulwich-singapore\_data\dulwich-singapore-r2-selection.json"
REV1_BOQ = LP + r"\docs\reports\_data\dulwich-singapore-boq.json"
MANUAL_OUT = LP + r"\projects\dulwich-singapore\_data\dulwich-singapore-r2-manual.yaml"

# Zoning (v3): the old "Zone C (Walkway)" is now Zone A; old "Zone B (Toddler)"
# is now Zone C; sandpit spans A & C; Balcony stays Zone D. Surfacing is pulled
# into a single "Surfacing Summary" section (token ZSURF, sorts last).
ZONE_TITLE = {
    "A":  "Zone A - Truck Path excluding Bike Track",
    "C":  "Zone C - Toddler and Nursery",
    "CS": "Zone A & C - Sandpit",
    "D":  "Zone D - Balcony 17 Classrooms",
    "ZSURF": "Surfacing Summary",
}

# Static product spec: (zone, subzone, code, qty, name)
PRODUCTS = [
    # Zone A — Truck Path (4soft graphics added dynamically below)
    ("A", "Play Equipment", "HW1-S747", 4, "Outdoor Storage House A"),
    ("A", "Holey Blocks", "DDJM-JQ01-V01", 1, "Outdoor Holey Stacking Block Set"),
    ("A", "Holey Blocks", "DDGT-BZ", 1, "Holey Block Motor Skills Set"),
    ("A", "Holey Blocks", "DDHD-BZ", 1, "Holey Block Motor Skills Set"),
    ("A", "Ride-on Toys", "GP2-TC015-V02-06", 5, "Power Tricycle"),
    ("A", "Ride-on Toys", "GP2-TC013-V02-06", 5, "Power Trike"),
    ("A", "Ride-on Toys", "GP2-TC007-V02-06", 5, "Two-wheeled Power Scooter"),
    ("A", "Ride-on Toys", "GP2-TC014-V01-06", 5, "Power Slide Car"),
    ("A", "Ride-on Toys", "GP2-TC018-05", 5, "Scooter & Slide Bike Stand"),
    # Zone C — Toddler and Nursery
    ("C", "Play Equipment", "HW1-S292", 1, "Motor Skills-Forest Set C"),
    ("C", "Play Equipment", "HW1-S023-V06", 1, "Nature's Elements Outdoor Teepee"),
    ("C", "Play Equipment", "HW1-S020-V03", 1, "Nature's Elements Outdoor Play House"),
    ("C", "Play Equipment", "HW1-S256-V01", 1, "Little Farm-Square Set"),
    ("C", "Play Equipment", "HW1-S029", 1, "Nature's Elements Outdoor Chalkboard"),
    ("C", "Play Equipment", "HW1-S031", 1, "Nature's Elements Outdoor Translucent Panel"),
    ("C", "Play Equipment", "HW1-S367-V01", 1, "Vision Wallboard Set-Lines"),
    ("C", "Play Equipment", "HW1-S270-V02", 1, "Music Wallboard Set-Lines"),
    ("C", "Play Equipment", "HW5-SD001-V01", 8, "Nature's Elements Outdoor Stool"),
    # Zone A & C — Sandpit (equipment)
    ("CS", "Sand & Water Play", "HW1-S281-V02", 1, "Sand Delivery Play"),
    ("CS", "Sand & Water Play", "HW1-S484", 1, "Wallboard-Sand Play HW1-S484"),
    ("CS", "Sand & Water Play", "HW1-S062", 1, "Wallboard-Halfpipe Sand Channel HW1-S062"),
    ("CS", "Sand & Water Play", "HW1-S070", 1, "Wallboard-Hosepipe HW1-S070"),
    ("CS", "Sand & Water Play", "HW1-S064", 1, "Wallboard-Sand Channel HW1-S064"),
    ("CS", "Sand & Water Play", "HW1-S071", 1, "Water Channel-Knob HW1-S071"),
    ("CS", "Sand & Water Play", "HW1-S066", 1, "Wallboard-Sand Play HW1-S066"),
    # Zone D — Balcony 17 Classrooms
    ("D", "Water Play Set (per classroom)", "CSS-QB-BZ", 17, "Water Play Set - Wallboard Standard Package"),
    ("D", "Water Play Set (per classroom)", "CSS-DMGD-BZ-V01", 17, "Water Play Set - Ground Tubes & Connector Standard Package"),
    ("D", "Water Play Set (per classroom)", "CSS-CBZJ-BZ", 17, "Water Play Set - Castle Support Standard Package"),
    ("D", "Water Play Set (per classroom)", "CSS-QBWJ-BZ", 17, "Water Play Set - Wallboard Toys Standard Package"),
    ("D", "Classroom Set (per classroom)", "HW1-S035", 17, "Messy Tables & Water Cascade Table"),
    ("D", "Classroom Set (per classroom)", "HW4-SZ006-V02", 17, "Nature's Elements Outdoor Workbench"),
    ("D", "Classroom Set (per classroom)", "HW1-S016-V03", 17, "Nature's Elements Outdoor Kitchen Set"),
    ("D", "Classroom Set (per classroom)", "HW1-S202", 17, "Castle Storage (L)"),
    ("D", "Classroom Set (per classroom)", "HW1-S203", 17, "Castle Storage (R)"),
    ("D", "Classroom Set (per classroom)", "HW1-S201", 17, "Castle Storage B"),
    ("D", "Classroom Set (per classroom)", "HW1-S200", 17, "Castle Storage A"),
]

# Explicit surfacing lines: (zone, subzone, name, qty, unit, rate_or_lump, is_lump)
# EPDM Mound stays an item in Zone C; the 3 surfacing areas are consolidated
# into the ZSURF "Surfacing Summary" section (areas from the Option-1 master plan).
SURFACING = [
    ("C", "Mound", "EPDM Mound height 1.00 m. + Tunnel + Double Slide", 1, "set", 25400.0, True),
    ("ZSURF", "Surfacing", "Zone A — Grass Green EPDM Surfacing with Surface Renovation", 840, "sq.m.", 119.90, False),
    ("ZSURF", "Surfacing", "Zone A & C — Sand Pit 300mm Depth with Drainage System", 92, "sq.m.", 420.0, False),
    ("ZSURF", "Surfacing", "Zone C — Hexagon Grid 45 mm Green Color", 235, "sq.m.", 182.85, False),
]

REMOVED = {"G2-26A-57UV", "E1-02A-20", "E3-04A-20", "G2-09A-02", "E3-02A-20",
           "D2-03A-70UV", "D4-02A-01", "G2-07A-57UV", "C5-05A-52UV",
           "HW1-S138-V02", "HW1-S010-V01", "HW1-S011-V01", "HW1-S009-V01"}


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def is_epdm(code) -> bool:
    return bool(re.match(r"^[A-Z]\d-\d{2}[A-Z]-\d{2,3}", (code or "").upper()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()
    WRITE = args.write

    from shared.medusa_importer import MedusaImporter
    os.environ.setdefault("MEDUSA_BACKEND_URL", BACKEND)
    os.environ["MEDUSA_ADMIN_EMAIL"] = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL", "")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD", "")
    c = MedusaImporter(base_url=BACKEND)

    sel = json.loads(Path(SELECTION).read_text(encoding="utf-8"))
    sel_by_code = {}
    for it in sel["items"]:
        if it.get("product_code"):
            sel_by_code.setdefault(norm(it["product_code"]), it)

    # Dynamic 4soft for Zone C (kept = all 4soft minus REMOVED), dedupe, keep qty.
    removed_n = {norm(x) for x in REMOVED}
    four = []
    seen = set()
    for it in sel["items"]:
        cd = it.get("product_code")
        if cd and is_epdm(cd) and norm(cd) not in removed_n and norm(cd) not in seen:
            seen.add(norm(cd))
            q = (it.get("quantity") or {}).get("qty") or 1
            four.append(("A", "EPDM Surface Graphics", cd, int(q), it["name_clean"] or it["name"]))
    products = list(PRODUCTS) + four

    # Medusa index (status + variant id + SGD unit price).
    # The SGD price is captured so 4soft EPDM-graphic codes — which carry no
    # Rev1 BoQ retail_sgd and no Wisdom FOB — resolve to their catalog price in
    # price_of() (synced onto the 4soft variants from vendors/4soft.retail_sgd)
    # instead of falling through to TBC.
    idx = {}
    med_sgd = {}   # norm(code) -> SGD unit price (dollars)
    off = 0
    while True:
        r = c._get("/admin/products", {"limit": 200, "offset": off,
            "fields": "id,status,variants.id,variants.sku,variants.metadata.legacy_sku,"
                      "variants.prices.amount,variants.prices.currency_code"})
        b = r.get("products", [])
        if not b:
            break
        for p in b:
            for v in p.get("variants") or []:
                sgd_cents = next((pp.get("amount") for pp in (v.get("prices") or [])
                                  if pp.get("currency_code") == "sgd"), None)
                for k in (v.get("sku"), (v.get("metadata") or {}).get("legacy_sku")):
                    if k:
                        idx.setdefault(norm(k), (p["id"], v["id"], p.get("status")))
                        if sgd_cents is not None:
                            med_sgd.setdefault(norm(k), round(sgd_cents / 100.0, 2))
        if len(b) < 200:
            break
        off += 200

    # prices
    rev1 = {}
    try:
        d = json.loads(Path(REV1_BOQ).read_text(encoding="utf-8"))
        for it in d.get("items", []):
            cc, rs = it.get("product_code"), (it.get("pricing") or {}).get("retail_sgd")
            if cc and rs:
                rev1[norm(cc)] = rs
    except Exception:
        pass
    fob = {}
    if WRITE or True:
        from google.cloud import firestore
        db = firestore.Client(project="ai-agents-go", database=CATALOG_DB)
        for dd in db.collection("products_wisdom").stream():
            x = dd.to_dict() or {}
            cd = x.get("item_code")
            pr = x.get("pricing") or {}
            if cd:
                fob[norm(cd)] = pr.get("fob_usd") or pr.get("fob_usd_us")

    def price_of(code):
        n = norm(code)
        # Prefer the authoritative Medusa SGD catalog price. Both 4soft
        # (= vendors/4soft.retail_sgd) and Wisdom / "Leka Project" variants now
        # carry a pipeline-computed retail_sgd, so this is the source of truth —
        # it replaces the old Wisdom fob×FX estimate and prices the items that
        # had neither a Rev1 nor a FOB figure (DD holey blocks, CSS water-play).
        if med_sgd.get(n):
            return med_sgd[n], "priced"
        if n in rev1:
            return round(rev1[n], 2), "priced"
        if fob.get(n):
            return round(fob[n] * WISDOM_FOB_TO_SGD, 2), "priced"
        return None, "tbc"

    def dims_of(code):
        it = sel_by_code.get(norm(code))
        return (it or {}).get("dimensions")

    lines = []          # draft-order lines (published)
    manual = []         # manual BoQ items (missing/draft + surfacing)
    missing = []        # codes to create as draft
    seq = {}

    for zone, subzone, code, qty, name in products:
        hit = idx.get(norm(code))
        price, status = price_of(code)
        seq[(zone, subzone)] = seq.get((zone, subzone), 0) + 1
        common_md = {
            "zone": zone, "zone_title": ZONE_TITLE[zone],
            "subzone": subzone, "subzone_no": 1,
            "subzone_status": "in_scope", "category": subzone,
            "selection_status": "selected", "seq": seq[(zone, subzone)],
            "name_clean": name, "product_code": code,
            "dimensions": dims_of(code), "retail_status": status,
            # Medusa's /admin/draft-orders create drops per-line `quantity`,
            # so carry it in metadata (which persists) for the adapter to read.
            "qty": int(qty),
        }
        if hit and hit[2] == "published":
            lines.append({"variant_id": hit[1], "quantity": int(qty),
                          "unit_price": int(round((price or 0) * 100)),
                          "metadata": common_md})
        else:
            missing.append((zone, subzone, code, qty, name))
            manual.append({
                "zone": zone, "zone_title": ZONE_TITLE[zone], "subzone": subzone,
                "subzone_no": common_md["subzone_no"], "subzone_status": "in_scope",
                "category": subzone, "seq": seq[(zone, subzone)],
                "name": name, "name_clean": name, "product_code": code,
                "option_no": None, "selection_status": "selected",
                "supplier": None, "supplier_url": None, "age_range": None,
                "dimensions": dims_of(code) or {"raw": None, "L": None, "W": None, "H": None, "unit": "cm"},
                "quantity": {"qty": int(qty), "unit": "set", "detail": None},
                "images": (sel_by_code.get(norm(code)) or {}).get("images") or [],
                # Draft/unpublished items carry a catalog SGD price only if their
                # Medusa variant has one (some 4soft drafts do); the rest have no
                # confirmed price yet → stay TBC.
                "pricing": ({"retail_status": status, "retail_sgd": price}
                            if med_sgd.get(norm(code)) else {"retail_status": "tbc", "retail_sgd": None}),
            })

    # surfacing manual items
    for zone, subzone, name, qty, unit, rate, is_lump in SURFACING:
        seq[(zone, subzone)] = seq.get((zone, subzone), 0) + 1
        manual.append({
            "zone": zone, "zone_title": ZONE_TITLE[zone], "subzone": subzone,
            "subzone_no": 2, "subzone_status": "in_scope", "category": subzone,
            "seq": seq[(zone, subzone)], "name": name, "name_clean": name,
            "product_code": None, "option_no": None, "selection_status": "selected",
            "supplier": None, "supplier_url": None, "age_range": None,
            "dimensions": {"raw": f"{qty} {unit}", "L": None, "W": None, "H": None, "unit": unit},
            "quantity": {"qty": int(qty), "unit": unit, "detail": None},
            "images": [],
            "pricing": {"retail_status": "priced", "retail_sgd": round(rate, 2)},
        })

    print(f"== curated Rev2 BoQ ({'WRITE' if WRITE else 'DRY-RUN'}) ==")
    print(f"   products: {len(products)} (4soft Zone C: {len(four)})")
    print(f"   draft-order lines (published): {len(lines)}")
    print(f"   manual items (missing+surfacing): {len(manual)}  missing_to_create: {len(missing)}")
    for z in ("A", "C", "CS", "D", "ZSURF"):
        nz = sum(1 for L in lines if L['metadata']['zone'] == z) + sum(1 for m in manual if m['zone'] == z)
        print(f"     zone {z}: {nz} items")
    if missing:
        print("   missing -> create draft + manual TBC:", [m[2] for m in missing])

    if not WRITE:
        Path(MANUAL_OUT).write_text(json.dumps({"items": manual}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"   wrote preview manual -> {MANUAL_OUT}")
        print("   (dry-run — re-run with --write to create draft order + drafts)")
        return 0

    # create missing products as draft Proposal items
    if missing:
        from google.cloud import firestore
        db = firestore.Client(project="ai-agents-go", database=CATALOG_DB)
        for zone, subzone, code, qty, name in missing:
            handle = f"proposal-{code.lower()}"
            try:
                if not c.find_product_by_handle(handle):
                    c.create_product(title=name, handle=handle, description=name,
                                     status="draft",
                                     metadata={"dulwich_r2": True, "legacy_sku": code, "vendor": "proposal-draft"},
                                     variant={"title": "Default", "sku": code, "manage_inventory": False, "prices": []},
                                     sales_channel_ids=[SC_PROPOSAL])
            except Exception as e:
                print(f"   ! create {code}: {str(e)[:140]}")
            db.collection("products_proposal_draft").document(code).set({
                "item_code": code, "brand": "proposal-draft", "description": name,
                "status": "draft", "catalog_source": "dulwich-r2-curated",
                "updated_at": datetime.now(timezone.utc).isoformat()}, merge=True)

    Path(MANUAL_OUT).write_text(json.dumps({"items": manual}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   wrote {len(manual)} manual items -> {MANUAL_OUT}")

    # delete prior rev draft orders, create fresh
    ex = c._get("/admin/draft-orders", {"limit": 100, "fields": "id,metadata"})
    for o in ex.get("draft_orders", ex.get("orders", [])):
        if (o.get("metadata") or {}).get("rev") == REV:
            try:
                c.session.delete(f"{c.base_url}/admin/draft-orders/{o['id']}")
                print(f"   deleted prior draft order {o['id']}")
            except Exception as e:
                print(f"   ! delete {o['id']}: {str(e)[:100]}")

    body = {"email": "proposals@nubo.asia", "region_id": REGION_SGD,
            "sales_channel_id": SC_LEKA, "items": lines,
            "metadata": {"project_id": "dulwich-singapore", "rev": REV, "curated": True}}
    try:
        res = c._post("/admin/draft-orders", body)
    except Exception as e:
        bdy = getattr(getattr(e, "response", None), "text", "") or str(e)
        print(f"   ! draft-order create failed: {bdy[:400]}")
        return 1
    do = res.get("draft_order") or res.get("order") or res
    print(f"\n== created draft order {do.get('id')} ({len(lines)} lines) ==")
    print(f"   DRAFT_ORDER_ID={do.get('id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
