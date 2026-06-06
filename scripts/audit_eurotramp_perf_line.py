"""Audit the Eurotramp competition/performance-line products for the three
enrichment axes — hero image, pricing, specifications.

Reads the scope from data/curated/eurotramp_performance_line.json, pulls live
Medusa state (thumbnail, gallery, variant prices, metadata dims) and the
vendors-Firestore pricing presence, and writes a markdown report to
docs/reports/eurotramp-perf-line-audit-<date>.md.

Read-only. Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD.

Usage:
    python scripts/audit_eurotramp_perf_line.py [--date 2026-06-06]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.reclassify_eurotramp_images import classify  # noqa: E402

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SC_EUROTRAMP = "sc_01KNQAA3Y72W17B7CP2VQ93T3M"
SCOPE_FILE = REPO_ROOT / "data" / "curated" / "eurotramp_performance_line.json"
PRICE_CCYS = ("thb", "usd", "eur", "sgd")


def _fname(url: str) -> str:
    return (url or "").split("?")[0].split("/")[-1]


def load_scope() -> dict[str, str]:
    """handle -> group name."""
    data = json.loads(SCOPE_FILE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for group, handles in data["groups"].items():
        for h in handles:
            out[h] = group
    return out


def medusa_token(s: requests.Session) -> str:
    r = s.post(
        BACKEND + "/auth/user/emailpass",
        json={
            "email": os.environ["LEKA_MEDUSA_ADMIN_EMAIL"],
            "password": os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"],
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def fetch_eurotramp(s: requests.Session, headers: dict) -> dict[str, dict]:
    prods: dict[str, dict] = {}
    off = 0
    fields = (
        "id,handle,status,thumbnail,images.url,variants.id,variants.sku,"
        "variants.prices.amount,variants.prices.currency_code,"
        "metadata.length_cm,metadata.width_cm,metadata.height_cm"
    )
    while True:
        r = s.get(
            BACKEND + "/admin/products",
            headers=headers,
            params={"limit": 100, "offset": off,
                    "sales_channel_id[]": SC_EUROTRAMP, "fields": fields},
            timeout=60,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        for p in batch:
            prods[p["handle"]] = p
        off += 100
        if len(batch) < 100:
            break
    return prods


def firestore_pricing() -> dict[str, dict]:
    from google.cloud import firestore
    db = firestore.Client(project="ai-agents-go", database="vendors")
    out: dict[str, dict] = {}
    for d in db.collection("vendors").document("eurotramp").collection("products").stream():
        out[d.id] = d.to_dict() or {}
    return out


def real_prices(variants: list[dict]) -> dict[str, int]:
    """Highest non-zero amount seen per currency across variants (minor units)."""
    best: dict[str, int] = {}
    for v in variants or []:
        for pr in v.get("prices") or []:
            cc = pr.get("currency_code")
            amt = pr.get("amount") or 0
            if amt and amt > best.get(cc, 0):
                best[cc] = amt
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-06-06")
    args = ap.parse_args()

    scope = load_scope()
    s = requests.Session()
    token = medusa_token(s)
    headers = {"Authorization": "Bearer " + token}
    live = fetch_eurotramp(s, headers)
    fs = firestore_pricing()

    rows = []
    summ = {"no_real_price": 0, "zero_dims": 0, "nonphoto_thumb": 0, "missing": 0,
            "fs_no_pricing": 0}
    for handle, group in scope.items():
        p = live.get(handle)
        if not p:
            rows.append((group, handle, "MISSING", "-", "-", "-", "-", "-"))
            summ["missing"] += 1
            continue
        thumb_kind = classify(_fname(p.get("thumbnail")))
        imgs = [_fname(i.get("url")) for i in (p.get("images") or [])]
        photo = sum(1 for f in imgs if classify(f) == "photo")
        junk = len(imgs) - photo
        md = p.get("metadata") or {}
        dims = (md.get("length_cm") or 0, md.get("width_cm") or 0, md.get("height_cm") or 0)
        zero_dims = all(int(x or 0) == 0 for x in dims)
        rp = real_prices(p.get("variants") or [])
        has_real_price = any(rp.get(c) for c in PRICE_CCYS)
        fsdoc = fs.get(handle) or {}
        fsprice = fsdoc.get("pricing") or {}
        fs_retail = any(fsprice.get(f"retail_{c}") for c in PRICE_CCYS)

        if not has_real_price:
            summ["no_real_price"] += 1
        if zero_dims:
            summ["zero_dims"] += 1
        if thumb_kind != "photo":
            summ["nonphoto_thumb"] += 1
        if not fs_retail:
            summ["fs_no_pricing"] += 1

        price_str = ",".join(f"{c}={rp[c]/100:.0f}" for c in PRICE_CCYS if rp.get(c)) or "—(usd=0 stub)"
        rows.append((
            group, handle, p.get("status"),
            f"{thumb_kind}", f"{photo}/{len(imgs)}",
            "0×0×0" if zero_dims else "×".join(str(int(x or 0)) for x in dims),
            price_str,
            "yes" if fs_retail else "no",
        ))

    out = REPO_ROOT / "docs" / "reports" / f"eurotramp-perf-line-audit-{args.date}.md"
    lines = [
        f"# Eurotramp Performance-Line Audit — {args.date}",
        "",
        f"Scope: **{len(scope)}** handles from `data/curated/eurotramp_performance_line.json`.",
        "",
        "## Summary (gaps)",
        f"- Products with **no real price** (only usd=0 stub or none): **{summ['no_real_price']}/{len(scope)}**",
        f"- Products with **zero dimensions** (metadata.length/width/height_cm all 0): **{summ['zero_dims']}/{len(scope)}**",
        f"- Products with a **non-photo thumbnail** (cert/badge/placeholder/…): **{summ['nonphoto_thumb']}/{len(scope)}**",
        f"- Firestore `vendors/eurotramp/products` docs with **no retail pricing**: **{summ['fs_no_pricing']}/{len(scope)}**",
        f"- Scope handles **missing** from Medusa: **{summ['missing']}**",
        "",
        "## Per-product",
        "",
        "| group | handle | status | thumb kind | photos/imgs | dims (cm) | medusa price | fs retail |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows):
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
