"""Add an 'Impact Protection' option (PlayPro / Bonded Tiles Grey / Bonded Tiles Red)
and bundle-priced variants to the Kids Tramp base products in Medusa.

Bundle price = base variant price + accessory retail price, per currency (THB/USD/EUR/SGD).
SKU convention: composite '<base_sku>+<accessory_sku>' (e.g. '97000+E97041').

Idempotent & safe:
  - skips adding the option if it already exists on a product
  - backfills existing variants to Impact Protection='None'
  - skips creating a variant whose SKU already exists
  - processes ONE product at a time, verifies, and ABORTS on first error

Usage:
  python scripts/add_kidstramp_impact_protection.py --dry-run
  python scripts/add_kidstramp_impact_protection.py --write [--only <product_id>]
"""
from __future__ import annotations
import argparse, os, sys, json, time
from google.cloud import secretmanager


def post_retry(cl, url, body, tries=6):
    """POST with backoff on transient 502/503/504 / connection errors."""
    import requests
    last = None
    for i in range(tries):
        try:
            r = cl.session.post(url, json=body, timeout=60)
            if r.status_code in (502, 503, 504):
                last = requests.HTTPError(f"{r.status_code}", response=r)
                time.sleep(2 * (i + 1))
                continue
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
CCY = ["thb", "usd", "eur", "sgd"]
OPT = "Impact Protection"

# accessory retail (major units) thb,usd,eur,sgd
ACC = {
 'E97047':(31509.47,891.09,759.21,1133.75), 'E97048':(41465.43,1172.65,999.1,1491.98),
 'E97548':(58171.88,1645.11,1401.64,2093.1), 'E97448':(108870.15,3078.86,2623.2,3917.29),
 'E97648':(147519.81,4171.88,3554.45,5307.96), 'E97848':(186170.48,5264.93,4485.73,6698.66),
 'E97948':(224819.12,6357.92,5416.96,8089.29), 'E97041':(37673.9,1065.42,907.74,1355.56),
 'E97044':(37673.9,1065.42,907.74,1355.56), 'E97051':(24822.39,701.98,598.09,893.14),
 'E97544':(55777.5,1577.4,1343.94,2006.95), 'E97542':(46166.23,1305.59,1112.36,1661.12),
 'E97441':(109048.12,3083.9,2627.49,3923.7), 'E97641':(143391.78,4055.14,3454.99,5159.43),
 'E97841':(180560.41,5106.27,4350.56,6496.81), 'E97941':(217708.59,6156.83,5245.63,7833.45),
}

def ip(label, color, sku):
    return {"label": label + (f" ({color})" if color else ""), "color": color, "acc": sku}

# Each product: pid, the option titles in order, existing variants (sku, {opt:val}),
# and the IP entries to add. base variants we attach to (Track: 'Track only' only).
PRODUCTS = [
 {"pid":"prod_01KNQ3PDJ6PZK8TP07CHQTSY7G","title":'Kids Tramp "Kindergarten Loop XL"',
  "opt_titles":["Default"],
  "attach":[("ET-97112",{"Default":"Default"})],
  "ip":[ip("Bonded Tiles","Grey","E97542")]},
 {"pid":"prod_01KNQ3PD7BPPHB47MHAR59D8ME","title":'Kids Tramp "Kindergarten"',
  "opt_titles":["Default"],
  "attach":[("ET-97100",{"Default":"Default"})],
  "ip":[ip("PlayPro",None,"E97048"),ip("Bonded Tiles","Grey","E97041"),ip("Bonded Tiles","Red","E97044")]},
 {"pid":"prod_01KNQ3PDW8V2GECP14SJ6FFZV4","title":'Kids Tramp "Kindergarten Loop"',
  "opt_titles":["Default"],
  "attach":[("ET-97110",{"Default":"Default"})],
  "ip":[ip("PlayPro",None,"E97047"),ip("Bonded Tiles","Grey","E97051")]},
 {"pid":"prod_01KNQ3PCVPJ2P1M4TJZ89XMENG","title":'Kids Tramp "Kindergarten XL"',
  "opt_titles":["Default"],
  "attach":[("ET-97510",{"Default":"Default"})],
  "ip":[ip("PlayPro",None,"E97548"),ip("Bonded Tiles","Red","E97544")]},
 {"pid":"prod_01KNQ3PAV4JHZQHB0E1401Q39W","title":'Kids Tramp "Playground"',
  "opt_titles":["Default","Coating"],
  "attach":[("97000",{"Default":"Default","Coating":"Standard"}),
            ("97000B",{"Default":"Default","Coating":"Additional Coating"})],
  "ip":[ip("PlayPro",None,"E97048"),ip("Bonded Tiles","Grey","E97041"),ip("Bonded Tiles","Red","E97044")]},
 {"pid":"prod_01KNQ3PBH1XCQ22QG4YQV6HRTD","title":'Kids Tramp "Playground Loop"',
  "opt_titles":["Default","Coating"],
  "attach":[("97010",{"Default":"Default","Coating":"Standard"}),
            ("97010B",{"Default":"Default","Coating":"Additional Coating"})],
  "ip":[ip("PlayPro",None,"E97047"),ip("Bonded Tiles","Grey","E97051")]},
 {"pid":"prod_01KNQ3PAH3VHJWECTJ5CZ53F02","title":'Kids Tramp "Playground XL"',
  "opt_titles":["Default","Coating"],
  "attach":[("97500",{"Default":"Default","Coating":"Standard"}),
            ("97500B",{"Default":"Default","Coating":"Additional Coating"})],
  "ip":[ip("PlayPro",None,"E97548"),ip("Bonded Tiles","Red","E97544")]},
 {"pid":"prod_01KNQ3PB5VREBGG6YJCC4846YA","title":'Kids Tramp "Playground Loop XL"',
  "opt_titles":["Default","Coating"],
  "attach":[("97012",{"Default":"Default","Coating":"Standard"}),
            ("97012B",{"Default":"Default","Coating":"Additional Coating"})],
  "ip":[ip("Bonded Tiles","Grey","E97542")]},
 {"pid":"prod_01KNQ3PBVYXZRJ6ZVVP9NBN87K","title":'Kids Tramp Track "Playground"',
  "opt_titles":["Length","Variant"],
  # Track-only base variants only (skip 'With EPDM').
  "attach":[("97044",{"Length":"4 m","Variant":"Track only"}),
            ("97046",{"Length":"6 m","Variant":"Track only"}),
            ("97048",{"Length":"8 m","Variant":"Track only"}),
            ("97049",{"Length":"10 m","Variant":"Track only"})],
  # length-specific accessory: keyed by Length value
  "ip_by_length":{
    "4 m":[ip("PlayPro",None,"E97448"),ip("Bonded Tiles","Grey","E97441")],
    "6 m":[ip("PlayPro",None,"E97648"),ip("Bonded Tiles","Grey","E97641")],
    "8 m":[ip("PlayPro",None,"E97848"),ip("Bonded Tiles","Grey","E97841")],
    "10 m":[ip("PlayPro",None,"E97948"),ip("Bonded Tiles","Grey","E97941")],
  }},
]


def get_secret(name):
    c = secretmanager.SecretManagerServiceClient()
    return c.access_secret_version(name=f"projects/ai-agents-go/secrets/{name}/versions/latest").payload.data.decode().strip()


def bundle(base_prices, acc_sku):
    a = ACC[acc_sku]
    return {c: int(base_prices[c]) + int(round(a[i]*100)) for i, c in enumerate(CCY)}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--only", default=None, help="process a single product_id")
    args = ap.parse_args()
    write = args.write

    os.environ["MEDUSA_BACKEND_URL"] = BACKEND
    os.environ["MEDUSA_ADMIN_EMAIL"] = get_secret("medusa-admin-email")
    os.environ["MEDUSA_ADMIN_PASSWORD"] = get_secret("medusa-admin-password")
    sys.path.insert(0, ".")
    from shared.medusa_importer import MedusaImporter
    cl = MedusaImporter(base_url=BACKEND)

    total_new = total_skipped = 0
    for prod in PRODUCTS:
        if args.only and prod["pid"] != args.only:
            continue
        pid, title = prod["pid"], prod["title"]
        print(f"\n=== {title}  ({pid}) ===")
        # fresh fetch with current option + variant detail incl prices
        r = cl._get("/admin/products", {"id": pid, "limit": 1,
            "fields": "id,title,options.id,options.title,options.values.value,"
                      "variants.id,variants.sku,variants.options.option_id,variants.options.value,"
                      "variants.prices.amount,variants.prices.currency_code"})
        p = r["products"][0]
        existing_opt_titles = {o["title"] for o in p.get("options", [])}
        optid_to_title = {o["id"]: o["title"] for o in p.get("options", [])}
        var_by_sku = {}
        for v in p.get("variants", []):
            pm = {pr["currency_code"]: pr["amount"] for pr in (v.get("prices") or [])}
            vopts = {optid_to_title.get(o.get("option_id")): o.get("value")
                     for o in (v.get("options") or []) if optid_to_title.get(o.get("option_id"))}
            var_by_sku[v["sku"]] = {"id": v["id"], "prices": pm, "options": vopts}
        existing_skus = set(var_by_sku)

        # collect the IP value labels for this product's option
        if "ip_by_length" in prod:
            labels = sorted({e["label"] for lst in prod["ip_by_length"].values() for e in lst})
        else:
            labels = sorted({e["label"] for e in prod["ip"]})
        option_values = ["None"] + labels

        # build planned new variants
        planned = []
        for base_sku, base_opts in prod["attach"]:
            bp = var_by_sku.get(base_sku, {}).get("prices")
            if not bp:
                print(f"  ! base variant {base_sku} not found / no prices — ABORT")
                return 1
            ent = prod["ip_by_length"][base_opts["Length"]] if "ip_by_length" in prod else prod["ip"]
            for e in ent:
                new_sku = f"{base_sku}+{e['acc']}"
                opts = dict(base_opts); opts[OPT] = e["label"]
                title_v = " – ".join([base_sku] + ([] if not e["color"] else []) + [e["label"]])
                planned.append({"sku": new_sku, "options": opts, "label": e["label"],
                                "acc": e["acc"], "prices": bundle(bp, e["acc"]),
                                "title": f"{base_sku} {e['label']}"})

        print(f"  option '{OPT}' values: {option_values}")
        print(f"  existing variants → backfill '{OPT}=None': {sorted(existing_skus)}")
        for pl in planned:
            tag = "EXISTS(skip)" if pl["sku"] in existing_skus else "NEW"
            print(f"  [{tag}] {pl['sku']:18} {pl['label']:20} "
                  f"THB {pl['prices']['thb']/100:,.2f}  EUR {pl['prices']['eur']/100:,.2f}")

        if not write:
            total_new += sum(1 for pl in planned if pl["sku"] not in existing_skus)
            continue

        # --- WRITE PATH ---
        try:
            # 1) add option if missing
            if OPT not in existing_opt_titles:
                cl._post(f"/admin/products/{pid}/options", {"title": OPT, "values": option_values})
                print(f"  + added option '{OPT}'")
            # 2) backfill existing variants to None (must send FULL option map)
            for sku in existing_skus:
                vinfo = var_by_sku[sku]
                # Only backfill variants that have NO Impact Protection value yet.
                # (Already-'None' originals and our own bundle variants are left alone.)
                if vinfo["options"].get(OPT) is not None:
                    continue
                full_opts = dict(vinfo["options"]); full_opts[OPT] = "None"
                post_retry(cl, f"{BACKEND}/admin/products/{pid}/variants/{vinfo['id']}",
                           {"options": full_opts})
            # 3) create new variants
            for pl in planned:
                if pl["sku"] in existing_skus:
                    total_skipped += 1
                    continue
                prices = [{"amount": pl["prices"][c], "currency_code": c} for c in CCY]
                body = {"title": pl["title"], "sku": pl["sku"], "prices": prices,
                        "options": pl["options"],
                        "metadata": {"base_sku": pl["sku"].split("+")[0],
                                     "accessory_sku": pl["acc"],
                                     "impact_protection": pl["label"]}}
                try:
                    post_retry(cl, f"{BACKEND}/admin/products/{pid}/variants", body)
                    total_new += 1
                    print(f"  + created {pl['sku']}")
                except Exception as ce:
                    import requests
                    body_txt = ce.response.text if isinstance(ce, requests.HTTPError) else str(ce)
                    # A 503-that-actually-succeeded leads to an 'already exists' on retry.
                    if "already exists" in body_txt:
                        total_skipped += 1
                        print(f"  ~ {pl['sku']} already exists (idempotent skip)")
                    else:
                        raise
        except Exception as ex:
            import requests
            msg = ex.response.text[:400] if isinstance(ex, requests.HTTPError) else str(ex)
            print(f"  !! ERROR on {title}: {msg}\n  ABORTING — no further products touched.")
            return 1

        # 4) verify
        rv = cl._get("/admin/products", {"id": pid, "limit": 1,
            "fields": "id,variants.sku,variants.prices.amount,variants.prices.currency_code"})
        got = {v["sku"]: {pr["currency_code"]: pr["amount"] for pr in (v.get("prices") or [])}
               for v in rv["products"][0].get("variants", [])}
        ok = True
        for pl in planned:
            live = got.get(pl["sku"])
            if not live:
                print(f"  VERIFY FAIL: {pl['sku']} missing after write"); ok = False; continue
            for c in CCY:
                if int(live.get(c, -1)) != pl["prices"][c]:
                    print(f"  VERIFY FAIL: {pl['sku']} {c} {live.get(c)} != {pl['prices'][c]}"); ok = False
        print(f"  verify: {'OK' if ok else 'FAILED'} ({len(planned)} planned)")
        if not ok:
            print("  ABORTING after verify failure."); return 1

    print(f"\n=== DONE === new={total_new} skipped(existing)={total_skipped} "
          f"({'WRITE' if write else 'DRY-RUN'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
