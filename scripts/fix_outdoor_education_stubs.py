"""Fix two mis-titled Wisdom outdoor-education import stubs in Medusa.

Both products were created by the 2026-05-29 wisdom-outdoor-play import as
"missing from firestore" placeholders: their titles were scraped from spec
lines, so they evade store-API title search and leave dead hotspots on the
leka-website /catalogue/outdoor-education page.

  HW1-S610  leka-project-6f9c3w5n  "Pre-treated Pinewood" -> "Outdoor Classroom - Blackboard"
  HW1-S638  leka-project-ikx4fp5b  "Age Group: 3Y+"       -> "Outdoor Teepee (Pinewood)"

This renames + redescribes them and assigns sensible categories. It does NOT
touch images (no real asset exists for either SKU — vendor raw media was
requested; the leka-coming-soon placeholder is kept, matching 43 sibling
stubs) and does NOT invent prices (no authoritative price source exists).

Auth: HTTP Basic with a Medusa secret API key in env MEDUSA_KEY.
  export MEDUSA_BACKEND_URL=https://leka-medusa-backend-538978391890.asia-southeast1.run.app
  export MEDUSA_KEY=$(gcloud secrets versions access latest \
      --secret=medusa-admin-api-key-proposal-engine --project=ai-agents-go)
  python scripts/fix_outdoor_education_stubs.py [--apply]

Idempotent: safe to re-run. Without --apply it only prints the planned diff.
"""
import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("MEDUSA_BACKEND_URL", "https://leka-medusa-backend-538978391890.asia-southeast1.run.app").rstrip("/")
KEY = os.environ.get("MEDUSA_KEY", "")
AUTH = "Basic " + base64.b64encode((KEY + ":").encode()).decode()

# category ids resolved live from sibling products (Teacher Table / teepee)
CAT_KIDS_FURNITURE = "pcat_01KSSGSNA28N297YFX9TW14B8B"
CAT_OUTDOOR = "pcat_01KNKVH7Y2HGWGJFXNGQ1V0GKA"
CAT_PLAYGROUND = "pcat_01KNQ3PW44X2NS3P2VC06K0Z9B"

TARGETS = [
    {
        "handle": "leka-project-6f9c3w5n",
        "expect_sku": "HW1-S610",
        "title": "Outdoor Classroom - Blackboard",
        "description": (
            "Outdoor Classroom - Blackboard — a large freestanding outdoor blackboard "
            "for open-air teaching and group activities. Part of the Wisdom outdoor "
            "classroom range."
        ),
        "category_ids": [CAT_KIDS_FURNITURE, CAT_OUTDOOR],
    },
    {
        "handle": "leka-project-ikx4fp5b",
        "expect_sku": "HW1-S638",
        "title": "Outdoor Teepee (Pinewood)",
        "description": (
            "Outdoor Teepee (Pinewood) — a natural pinewood teepee giving children a "
            "calm, sheltered corner for quiet play and retreat. Part of the Wisdom "
            "outdoor role-play range."
        ),
        "category_ids": [CAT_OUTDOOR, CAT_PLAYGROUND],
    },
]

FIELDS = "id,handle,title,status,thumbnail,variants.id,variants.sku,*categories,*sales_channels"


def req(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json", "Authorization": AUTH})
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


def get_by_handle(handle):
    s, d = req("GET", f"/admin/products?{urllib.parse.urlencode({'handle': handle, 'limit': 1, 'fields': FIELDS})}")
    if isinstance(d, dict) and d.get("products"):
        return d["products"][0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="perform the writes (default: dry-run)")
    args = ap.parse_args()
    if not KEY:
        raise SystemExit("MEDUSA_KEY env not set")

    print(f"Backend: {BASE}\nMode: {'APPLY' if args.apply else 'DRY-RUN'}\n")
    for t in TARGETS:
        p = get_by_handle(t["handle"])
        if not p:
            print(f"!! {t['handle']}: NOT FOUND — skipping")
            continue
        skus = [v.get("sku") for v in (p.get("variants") or [])]
        if t["expect_sku"] not in skus:
            print(f"!! {t['handle']}: expected sku {t['expect_sku']} not in {skus} — SKIPPING (safety)")
            continue
        cur_cats = sorted(c.get("id") for c in (p.get("categories") or []))
        want_cats = sorted(t["category_ids"])
        print(f"== {t['handle']}  (sku {t['expect_sku']})")
        print(f"   title    : {p.get('title')!r}  ->  {t['title']!r}")
        print(f"   status   : {p.get('status')}")
        print(f"   categories: {cur_cats}  ->  {want_cats}")
        print(f"   thumbnail: {p.get('thumbnail')}  (unchanged)")
        if not args.apply:
            print("   (dry-run: no write)\n")
            continue
        body = {
            "title": t["title"],
            "description": t["description"],
            "status": "published",
            "categories": [{"id": c} for c in t["category_ids"]],
        }
        s, d = req("POST", f"/admin/products/{p['id']}", body)
        if s == 200:
            after = get_by_handle(t["handle"])
            print(f"   -> OK. now title={after.get('title')!r}, "
                  f"cats={sorted(c.get('id') for c in (after.get('categories') or []))}\n")
        else:
            print(f"   -> FAILED {s}: {d}\n")


if __name__ == "__main__":
    main()
