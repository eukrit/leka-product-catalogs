"""Collapse duplicate Weplay product docs that share a SKU token, keeping
one canonical doc and tagging the others as merged.

Background
----------
The Weplay catalog accumulated docs from multiple scrape passes (live
weplay.com.tw, e-weplay.com.tw, AI-vision-inferred, PDF OCR). Several
SKUs ended up with multiple Firestore docs that point to the same
product — e.g. KM2802 has 11 docs all named "Soft Gym (7 pcs)"
(km2802_007, km2802_009, ..., km2802a, km2802b, ...), KC0002 has 4
docs all named "Brick Me" (6800kc0002_1_090, kc0002, kc0002_1,
we_kc0002).

Each duplicate became a separate published product in Medusa, so
catalogs.leka.studio/weplay shows the same card 4 or 11 times.

Strategy
--------
Group docs by (sku_token, normalized_name). Within each group, pick a
canonical doc using this priority:
  1. status == "active" and has images
  2. status == "active"
  3. has images
  4. shortest doc_id (least suffix noise)

For each non-canonical doc:
  - Set `merged_into = <canonical_doc_id>`
  - Set `status = "merged_duplicate"`
  - Keep all other fields (preserves history/audit trail)

Then DELETE the corresponding Medusa products under the Weplay SC.

Idempotent. Doesn't touch docs that are the only one in their (token, name)
group, and doesn't touch tokens where docs have DIFFERENT names (those
are likely real variants or AI-misinferred SKUs that need human review).

Usage:
    py scripts/merge_weplay_duplicates.py --dry-run
    py scripts/merge_weplay_duplicates.py --apply
    py scripts/merge_weplay_duplicates.py --apply --no-medusa     # Firestore only
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import defaultdict

import requests
from google.cloud import firestore

_FALLBACK_ADC = (
    r"C:\Users\Eukrit\AppData\Roaming\gcloud\legacy_credentials"
    r"\codex-chatgpt@ai-agents-go.iam.gserviceaccount.com\adc.json"
)
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ or not os.path.exists(
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
):
    if os.path.exists(_FALLBACK_ADC):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _FALLBACK_ADC
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("merge_weplay_duplicates")

PROJECT = "ai-agents-go"
DB = "vendors"
SLUG = "weplay"
SC_ID = "sc_01KR6Z0VBSXWYZDVGF30EAP0EQ"
BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SKU_TOKEN_RE = re.compile(r"([A-Z]{2}[0-9]{4,})")


def _normalize_name(name: str | None) -> str:
    """Collapse whitespace and casing for grouping. Strip Weplay prefix."""
    s = (name or "").strip()
    s = re.sub(r"^[Ww]eplay\s+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _pick_canonical(docs: list[dict]) -> dict:
    """Priority: active+images > active > has_images > shortest doc_id."""
    def key(d):
        return (
            0 if (d["status"] == "active" and d["has_images"]) else 1,
            0 if d["status"] == "active" else 1,
            0 if d["has_images"] else 1,
            len(d["doc_id"]),
            d["doc_id"],  # stable tiebreak
        )
    return sorted(docs, key=key)[0]


def _medusa_token() -> str:
    pw = os.popen(
        "gcloud secrets versions access latest --secret=medusa-admin-password --project=ai-agents-go"
    ).read().strip()
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": "admin@leka.studio", "password": pw}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _medusa_handle_to_id(token: str) -> dict[str, str]:
    """Return {handle: product_id} for all products in the Weplay SC."""
    out: dict[str, str] = {}
    offset = 0
    while True:
        r = requests.get(
            f"{BACKEND}/admin/products",
            params={"sales_channel_id[]": SC_ID, "limit": 100, "offset": offset,
                    "fields": "id,handle"},
            headers={"Authorization": f"Bearer {token}"}, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        for p in data.get("products", []):
            out[p["handle"]] = p["id"]
        if len(data.get("products", [])) < 100:
            break
        offset += 100
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-medusa", action="store_true",
                    help="Skip Medusa product deletes (Firestore-only).")
    args = ap.parse_args()
    write = bool(args.apply)
    log.info("=== merge_weplay_duplicates mode=%s no-medusa=%s ===",
             "WRITE" if write else "DRY-RUN", args.no_medusa)

    db = firestore.Client(project=PROJECT, database=DB)
    coll = db.collection("vendors").document(SLUG).collection("products")

    # Build (token, normalized_name) -> [doc records]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for snap in coll.stream():
        d = snap.to_dict() or {}
        if d.get("status") == "merged_duplicate":
            continue  # already merged
        sku = (d.get("item_code") or "").upper()
        m = SKU_TOKEN_RE.search(sku)
        if not m:
            continue
        token = m.group(1)
        name = _normalize_name(d.get("name"))
        if not name:
            continue
        groups[(token, name)].append({
            "doc_id": snap.id,
            "ref": snap.reference,
            "item_code": sku,
            "status": d.get("status"),
            "handle": d.get("handle") or "",
            "name": d.get("name"),
            "has_images": bool(d.get("images")),
        })

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    log.info("found %d (token,name) groups with >1 doc (total %d duplicate docs)",
             len(dup_groups), sum(len(v) for v in dup_groups.values()))

    counters = {
        "groups": len(dup_groups),
        "merged_docs": 0,
        "canonical_kept": 0,
        "medusa_deletes_attempted": 0,
        "medusa_deletes_ok": 0,
        "medusa_deletes_failed": 0,
        "medusa_not_found": 0,
    }
    sample_merges: list[str] = []

    # Medusa context — only fetch if we'll delete
    medusa_token = None
    medusa_handle_map: dict[str, str] = {}
    if write and not args.no_medusa:
        try:
            medusa_token = _medusa_token()
            medusa_handle_map = _medusa_handle_to_id(medusa_token)
            log.info("loaded %d Medusa products under Weplay SC", len(medusa_handle_map))
        except Exception as e:
            log.warning("Medusa auth/load failed (will skip deletes): %s", e)

    batch = db.batch()
    batch_n = 0

    for (token, name), docs in sorted(dup_groups.items()):
        canonical = _pick_canonical(docs)
        counters["canonical_kept"] += 1
        for d in docs:
            if d["doc_id"] == canonical["doc_id"]:
                continue
            counters["merged_docs"] += 1
            if len(sample_merges) < 12:
                sample_merges.append(
                    f"  [{token}/{name[:30]}] merge {d['doc_id']}({d['item_code']}) -> {canonical['doc_id']}({canonical['item_code']})"
                )

            payload = {
                "status": "merged_duplicate",
                "merged_into": canonical["doc_id"],
                "merged_canonical_sku": canonical["item_code"],
                "merged_at": firestore.SERVER_TIMESTAMP,
            }
            if write:
                batch.set(d["ref"], payload, merge=True)
                batch_n += 1
                if batch_n >= 200:
                    batch.commit()
                    log.info("committed Firestore batch (%d)", batch_n)
                    batch = db.batch()
                    batch_n = 0

                # Medusa delete
                if medusa_token and not args.no_medusa:
                    medusa_id = medusa_handle_map.get(d["handle"])
                    if medusa_id:
                        counters["medusa_deletes_attempted"] += 1
                        rr = requests.delete(
                            f"{BACKEND}/admin/products/{medusa_id}",
                            headers={"Authorization": f"Bearer {medusa_token}"},
                            timeout=30,
                        )
                        if rr.status_code < 400:
                            counters["medusa_deletes_ok"] += 1
                        else:
                            counters["medusa_deletes_failed"] += 1
                            log.warning("Medusa delete failed %s (handle=%s, status=%s): %s",
                                        medusa_id, d["handle"], rr.status_code, rr.text[:200])
                    else:
                        counters["medusa_not_found"] += 1

    if write and batch_n:
        batch.commit()
        log.info("committed final Firestore batch (%d)", batch_n)

    log.info("=== summary ===")
    for k, v in counters.items():
        log.info("  %s: %d", k, v)
    if sample_merges:
        log.info("\nsample merges:")
        for s in sample_merges:
            log.info(s)
    log.info("\nnet result: %d canonical actives kept, %d duplicates marked merged",
             counters["canonical_kept"], counters["merged_docs"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
