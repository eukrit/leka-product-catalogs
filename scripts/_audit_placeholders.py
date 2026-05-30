"""Snapshot placeholder/imageless products from the live Medusa store + intersect
with codes already hosted under gs://ai-agents-go-vendors/leka-project/catalog/.

Outputs:
  data/wisdom-placeholder-skus.csv      one row per placeholder product
  data/wisdom-placeholder-summary.json  totals + intersection stats
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests
from google.cloud import storage

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SC_PK = "pk_b7d7b7412262b05054450cd08213cd3d7d3432616ffff885e4c8a57e1b596e53"

BUCKET = "ai-agents-go-vendors"
PREFIX = "leka-project/catalog/"
PROXY_BASE = "https://catalogs.leka.studio/api/i/leka-project/_placeholder/leka-coming-soon.png"

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)


def iter_all_products():
    offset = 0
    while True:
        r = requests.get(
            f"{BACKEND}/store/products",
            headers={"x-publishable-api-key": SC_PK},
            params={
                "limit": 100,
                "offset": offset,
                "fields": "id,handle,title,thumbnail,images.url,variants.metadata,metadata",
            },
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            yield p
        offset += 100


def code_for(p: dict) -> str | None:
    vs = p.get("variants") or []
    code = (vs[0].get("metadata") or {}).get("legacy_sku") if vs else None
    if not code:
        lh = (p.get("metadata") or {}).get("legacy_handle", "")
        code = lh.replace("wisdom-", "") if lh else None
    return code


def main() -> None:
    print("[1/2] Enumerating Medusa store products...")
    rows = []
    counts = Counter()
    for p in iter_all_products():
        counts["total"] += 1
        th = p.get("thumbnail") or ""
        imgs = p.get("images") or []
        meta = p.get("metadata") or {}
        tag = meta.get("image_status")
        is_placeholder = (
            tag == "placeholder"
            or "leka-coming-soon" in th
            or (not imgs and not th)
        )
        if not is_placeholder:
            counts["non_placeholder"] += 1
            continue
        counts["placeholder"] += 1
        code = code_for(p) or ""
        rows.append({
            "code": code,
            "handle": p.get("handle"),
            "title": p.get("title"),
            "image_status": tag or "",
        })

    print(f"   total={counts['total']}  placeholder={counts['placeholder']}  non={counts['non_placeholder']}")

    print("[2/2] Indexing catalog/ codes in GCS...")
    sc = storage.Client(project="ai-agents-go")
    catalog_codes: set[str] = set()
    for blob in sc.list_blobs(BUCKET, prefix=PREFIX):
        fn = blob.name[len(PREFIX):]
        if "/" in fn or "_" not in fn:
            continue
        catalog_codes.add(fn.split("_", 1)[0])
    print(f"   {len(catalog_codes)} distinct codes already in catalog/")

    have = sum(1 for r in rows if r["code"] in catalog_codes)
    missing = sum(1 for r in rows if r["code"] and r["code"] not in catalog_codes)
    no_code = sum(1 for r in rows if not r["code"])

    # Prefix bucket
    def prefix_of(c: str) -> str:
        import re
        m = re.match(r"^[A-Z]+", c)
        return m.group(0) if m else "(other)"

    pref_missing = Counter(prefix_of(r["code"]) for r in rows
                            if r["code"] and r["code"] not in catalog_codes)
    pref_have = Counter(prefix_of(r["code"]) for r in rows
                         if r["code"] in catalog_codes)

    csv_path = OUT_DIR / "wisdom-placeholder-skus.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "code", "handle", "title", "image_status", "has_catalog_object",
        ])
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["code"] or ""):
            w.writerow({**r, "has_catalog_object": r["code"] in catalog_codes})

    summary = {
        "total_products": counts["total"],
        "placeholder_products": counts["placeholder"],
        "placeholder_with_existing_catalog_object": have,
        "placeholder_with_no_catalog_object": missing,
        "placeholder_no_legacy_code": no_code,
        "distinct_catalog_codes_in_bucket": len(catalog_codes),
        "prefix_missing_top20": pref_missing.most_common(20),
        "prefix_have_existing_top20": pref_have.most_common(20),
    }
    (OUT_DIR / "wisdom-placeholder-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
