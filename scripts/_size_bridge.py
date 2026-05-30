"""Size the vendors/wisdom -> Medusa Leka Project bridge yield.

For every Medusa placeholder SKU, look up the matching vendors/wisdom/products
doc and bucket by whether/how confidently it has usable images.

Outputs:
  data/bridge-sizing.json
  data/bridge-candidates.csv  (one row per placeholder SKU with bridge details)
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from pathlib import Path

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests
from google.cloud import firestore

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SC_PK = "pk_b7d7b7412262b05054450cd08213cd3d7d3432616ffff885e4c8a57e1b596e53"

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


def prefix_of(c: str) -> str:
    if not c:
        return "(empty)"
    m = re.match(r"^[A-Z]+", c)
    return m.group(0) if m else "(num)"


def main() -> None:
    print("[1/3] Enumerating placeholder products from Medusa...")
    placeholders = []
    for p in iter_all_products():
        th = p.get("thumbnail") or ""
        imgs = p.get("images") or []
        meta = p.get("metadata") or {}
        tag = meta.get("image_status")
        if tag == "placeholder" or "leka-coming-soon" in th or (not imgs and not th):
            placeholders.append({
                "id": p["id"],
                "handle": p.get("handle"),
                "title": p.get("title") or "",
                "code": code_for(p) or "",
                "thumbnail": th,
            })
    print(f"   {len(placeholders)} placeholders")

    print("[2/3] Reading vendors/wisdom/products (no limit)...")
    vendors_db = firestore.Client(project="ai-agents-go", database="vendors")
    col = vendors_db.collection("vendors").document("wisdom").collection("products")
    by_code: dict[str, dict] = {}
    n = 0
    for d in col.stream():
        n += 1
        data = d.to_dict() or {}
        code = data.get("item_code") or d.id.replace("wisdom-", "")
        if isinstance(code, str):
            by_code[code] = {
                "doc_id": d.id,
                "images": data.get("images") or [],
                "image_verified": data.get("image_verified"),
                "image_match_score": data.get("image_match_score"),
                "image_cleared_reason": data.get("image_cleared_reason"),
                "image_mismatch_reason": data.get("image_mismatch_reason"),
                "category": data.get("category"),
                "subcategory": data.get("subcategory"),
            }
    print(f"   {n} vendors/wisdom/products docs read, {len(by_code)} indexed by item_code")

    print("[3/3] Bucketing placeholders by bridge eligibility...")
    counts = Counter()
    per_prefix_yield = Counter()
    per_prefix_total = Counter()
    source_pdf_yield = Counter()
    rows = []

    for p in placeholders:
        c = p["code"]
        pref = prefix_of(c)
        per_prefix_total[pref] += 1
        vdoc = by_code.get(c)
        if not vdoc:
            counts["no_vendor_doc"] += 1
            rows.append({**p, "decision": "no_vendor_doc", "n_images": 0,
                         "image_verified": "", "image_match_score": "",
                         "primary_url": "", "image_sources": ""})
            continue
        imgs = vdoc["images"] or []
        if not imgs:
            counts["vendor_doc_no_images"] += 1
            rows.append({**p, "decision": "vendor_doc_no_images", "n_images": 0,
                         "image_verified": vdoc.get("image_verified") or "",
                         "image_match_score": vdoc.get("image_match_score") or "",
                         "primary_url": "",
                         "image_sources": vdoc.get("image_mismatch_reason") or ""})
            continue
        # Verified gate
        verified = bool(vdoc.get("image_verified"))
        score = vdoc.get("image_match_score")
        try:
            score_f = float(score) if score not in (None, "") else None
        except (TypeError, ValueError):
            score_f = None
        eligible = verified or (score_f is not None and score_f >= 0.70)
        src_set = sorted({(img.get("source") or "") for img in imgs if isinstance(img, dict)})
        prim = next((img.get("url") for img in imgs if isinstance(img, dict) and img.get("url")), "")
        if eligible:
            counts["bridge_eligible"] += 1
            per_prefix_yield[pref] += 1
            for s in src_set:
                source_pdf_yield[s] += 1
            decision = "bridge_eligible"
        else:
            counts["images_but_not_verified"] += 1
            decision = "images_but_not_verified"
        rows.append({**p, "decision": decision, "n_images": len(imgs),
                     "image_verified": str(vdoc.get("image_verified") or ""),
                     "image_match_score": str(vdoc.get("image_match_score") or ""),
                     "primary_url": prim,
                     "image_sources": ";".join(src_set)})

    summary = {
        "total_placeholders": len(placeholders),
        "buckets": dict(counts),
        "yield_by_prefix_top20": per_prefix_yield.most_common(20),
        "placeholder_count_by_prefix_top20": per_prefix_total.most_common(20),
        "yield_by_source_pdf": source_pdf_yield.most_common(20),
        "vendors_wisdom_total_docs_read": n,
        "vendors_wisdom_indexed_codes": len(by_code),
    }
    (OUT_DIR / "bridge-sizing.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    csv_path = OUT_DIR / "bridge-candidates.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "code", "handle", "title", "decision", "n_images",
            "image_verified", "image_match_score", "image_sources",
            "primary_url", "id", "thumbnail",
        ])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["decision"], x.get("code") or "")):
            w.writerow(r)

    print(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
