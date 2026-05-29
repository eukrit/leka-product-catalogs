"""Peek at vendors/wisdom/products + vendors/wisdom/* to find what has already
been parsed from the 2025-08-11 Furniture Catalog and 2025-06-13 USA Catalogue.

Outputs:
  data/vendors-wisdom-snapshot.json  — totals, source breakdown, prefix counts
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

from google.cloud import firestore

PROJECT = "ai-agents-go"
DST_DB = "vendors"

OUT = Path("data") / "vendors-wisdom-snapshot.json"
OUT.parent.mkdir(exist_ok=True)


def main() -> None:
    db = firestore.Client(project=PROJECT, database=DST_DB)

    # Identify what subcollections exist under vendors/wisdom/
    try:
        wisdom_ref = db.collection("vendors").document("wisdom")
        subs = list(wisdom_ref.collections())
        print(f"vendors/wisdom subcollections: {[s.id for s in subs]}")
    except Exception as e:
        print(f"Could not list subcollections: {e}")
        subs = []

    summary = {"subcollections": [s.id for s in subs]}

    # Snapshot products
    prod_col = db.collection("vendors").document("wisdom").collection("products")
    docs = list(prod_col.limit(5000).stream())
    print(f"vendors/wisdom/products: {len(docs)} docs read (capped 5000)")

    src_counter = Counter()
    prefix_counter = Counter()
    has_images = 0
    img_src_pdf = Counter()
    sample_fields = set()
    sample_docs = []

    import re
    for d in docs:
        data = d.to_dict() or {}
        sample_fields.update(data.keys())
        code = data.get("item_code") or data.get("sku") or d.id
        if not isinstance(code, str):
            code = str(code)
        m = re.match(r"^[A-Z]+", code)
        if m:
            prefix_counter[m.group(0)] += 1
        # detect what's there
        imgs = data.get("images") or []
        if imgs:
            has_images += 1
            for img in (imgs if isinstance(imgs, list) else [imgs]):
                if isinstance(img, dict):
                    src = img.get("source") or img.get("source_pdf") or ""
                    if src:
                        img_src_pdf[src] += 1
        # source-PDF flag we may have set
        src = data.get("source") or data.get("source_pdf") or data.get("source_catalog")
        if src:
            src_counter[str(src)] += 1
        if len(sample_docs) < 3:
            sample_docs.append({"id": d.id, "data_keys": sorted(data.keys()),
                                "code": code,
                                "n_images": len(imgs) if isinstance(imgs, list) else 0,
                                "image_sample": (imgs[0] if isinstance(imgs, list) and imgs else None)})

    summary.update({
        "total_products_read": len(docs),
        "products_with_images": has_images,
        "prefix_distribution_top20": prefix_counter.most_common(20),
        "image_source_pdf_counts": img_src_pdf.most_common(20),
        "doc_field_universe": sorted(sample_fields),
        "source_field_distribution": src_counter.most_common(20),
        "sample_docs": sample_docs,
    })
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str)[:4000])
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
