"""Build the recrop worklist for outdoor-play Gemini rejections.

Phase 1 of the recrop pipeline (sibling to import_outdoor_play_to_medusa.py).

Pulls rejection records from Firestore `wisdom_outdoor_play_verify`,
groups them by SKU, cross-references the merged JSON for source PDF +
exact pages, resolves each SKU to a Medusa product_id via the Leka
Project sales-channel legacy_sku index, and filters to the subset of
products whose current Medusa thumbnail is still the leka-coming-soon
placeholder.

Output: wisdom-catalog/recrop_worklist.json — one row per (pdf, page)
work-unit, with the list of candidate SKUs that should appear on that
page and the Medusa product_id each maps to.

Usage:
    python wisdom-catalog/build_recrop_worklist.py \
        [--input <merged.json>] \
        [--vendors-repo <path>] \
        [--output wisdom-catalog/recrop_worklist.json]

Credentials: ADC (`gcloud auth application-default login`) for Firestore;
MEDUSA_ADMIN_EMAIL / MEDUSA_ADMIN_PASSWORD env (or matching Secret
Manager versions auto-loaded by the importer helpers).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from shared.medusa_importer import MedusaImporter  # noqa: E402

# Reuse helpers from the existing importer (single-source config).
from import_outdoor_play_to_medusa import (  # noqa: E402
    load_merged_json,
    open_firestore,
    build_legacy_lookup_combined,
    find_existing,
    is_image_placeholder,
    LEKA_PROJECT_SC_ID,
    GEMINI_VERIFY_COLLECTION,
    GCP_PROJECT,
    MEDUSA_DEFAULT_URL,
    DEFAULT_VENDORS_REPO,
    PLACEHOLDER_URL,
)

COLLECTION_ID = "pcol_01KSTM5ZC4H197S057QC2TNATR"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("recrop_worklist")

OUTPUT_DEFAULT = os.path.join(THIS_DIR, "recrop_worklist.json")

# Pull SKU out of a verify-cache URL. Patterns observed in the reject set:
#   …/catalog/<SKU>_imgN.jpeg
#   …/spatial_v2/<SKU>_wisdom_2025_p<N>_<hash>.jpeg
#   …/verified/<SKU>_wisdom_2025_p<N>_<hash>.jpeg
_SKU_RE = re.compile(r"/(?:catalog|spatial_v2|verified)/([A-Z0-9][A-Z0-9\-]+?)(?:_img\d+|_wisdom_|_usa_)", re.I)


def sku_from_url(url: str) -> Optional[str]:
    m = _SKU_RE.search(url or "")
    if m:
        return m.group(1).upper()
    return None


def query_rejections(fs_client) -> list[dict]:
    """Return every reject decision from the verify cache."""
    log.info("Querying Firestore %s for decision==reject …", GEMINI_VERIFY_COLLECTION)
    out = []
    col = fs_client.collection(GEMINI_VERIFY_COLLECTION)
    # No composite index needed — single field filter.
    for snap in col.where("decision", "==", "reject").stream():
        d = snap.to_dict() or {}
        d["_doc_id"] = snap.id
        out.append(d)
    log.info("  %d rejection records.", len(out))
    return out


def fetch_product_states(client: MedusaImporter, product_ids: set[str], workers: int = 8) -> dict:
    """Return {product_id: {'thumbnail': str|None, 'image_status': str|None, 'handle': str}}."""
    log.info("Fetching Medusa state for %d unique products …", len(product_ids))
    out: dict = {}

    def _one(pid: str):
        try:
            resp = client.session.get(
                f"{client.base_url}/admin/products/{pid}",
                params={"fields": "id,handle,title,thumbnail,metadata,*variants"},
            )
            resp.raise_for_status()
            p = (resp.json() or {}).get("product") or {}
            variant_skus = []
            legacy_skus = []
            for v in (p.get("variants") or []):
                if v.get("sku"):
                    variant_skus.append(v["sku"])
                vmd = v.get("metadata") or {}
                if vmd.get("legacy_sku"):
                    legacy_skus.append(vmd["legacy_sku"])
            return pid, {
                "thumbnail": p.get("thumbnail"),
                "image_status": (p.get("metadata") or {}).get("image_status"),
                "handle": p.get("handle"),
                "title": p.get("title"),
                "variant_skus": variant_skus,
                "legacy_skus": legacy_skus,
            }
        except Exception as e:
            return pid, {"error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, pid): pid for pid in product_ids}
        for fut in as_completed(futs):
            pid, state = fut.result()
            out[pid] = state
    return out


def enumerate_collection_products(client: MedusaImporter, collection_id: str) -> list[dict]:
    """Page through every product in the collection. Returns list of products
    with id/handle/title/thumbnail/metadata/variants (sku + metadata.legacy_sku)."""
    log.info("Enumerating Medusa collection %s …", collection_id)
    products: list[dict] = []
    offset = 0
    limit = 100
    while True:
        resp = client.session.get(
            f"{client.base_url}/admin/products",
            params={
                "collection_id": collection_id,
                "limit": limit,
                "offset": offset,
                "fields": "id,handle,title,thumbnail,metadata,*variants",
            },
        )
        resp.raise_for_status()
        body = resp.json() or {}
        batch = body.get("products") or []
        products.extend(batch)
        total = body.get("count") or len(products)
        log.info("  fetched %d/%d", len(products), total)
        if not batch or len(products) >= total:
            break
        offset += limit
    return products


def find_silent_placeholders(client: MedusaImporter,
                             collection_id: str,
                             already_in_scope_pids: set[str],
                             sku_meta: dict[str, dict]) -> list[dict]:
    """Enumerate collection, find products on placeholder thumb that are NOT
    already covered by the reject-cache scan. Map each back to an outdoor-play
    SKU via variant.metadata.legacy_sku → merged JSON. Skip wisdom-* products
    (the 17 firestore-null new wisdom SKUs — out of scope per task brief)."""
    products = enumerate_collection_products(client, collection_id)
    log.info("  total in collection: %d", len(products))

    silent: list[dict] = []
    skipped_new_wisdom = 0
    skipped_no_sku_match = 0
    skipped_no_page = 0
    for p in products:
        thumb = p.get("thumbnail")
        md = p.get("metadata") or {}
        if not is_image_placeholder(thumb, md.get("image_status")):
            continue
        if p["id"] in already_in_scope_pids:
            continue
        handle = p.get("handle") or ""
        # 17 new wisdom-* products: out of scope per task brief.
        if handle.startswith("wisdom-"):
            skipped_new_wisdom += 1
            continue
        # Map back to a SKU in sku_meta via variant.metadata.legacy_sku / sku.
        candidates = []
        for v in (p.get("variants") or []):
            vmd = v.get("metadata") or {}
            for s in (vmd.get("legacy_sku"), v.get("sku")):
                if s and s.upper() in sku_meta:
                    candidates.append(s.upper())
        # De-dupe preserving order
        seen = set()
        candidates = [c for c in candidates if not (c in seen or seen.add(c))]
        if not candidates:
            skipped_no_sku_match += 1
            continue
        # Use the first SKU's page set as the source of truth.
        primary_sku = candidates[0]
        meta = sku_meta[primary_sku]
        if not meta.get("pdf") or not meta.get("pages"):
            skipped_no_page += 1
            continue
        silent.append({
            "product_id": p["id"],
            "handle": handle,
            "title": p.get("title"),
            "thumbnail": thumb,
            "all_candidate_skus": candidates,
            "primary_sku": primary_sku,
            "pdf": meta["pdf"],
            "pages": meta["pages"],
            "matched_id": meta.get("matched_id"),
            "sub_area": meta.get("sub_area"),
        })
    log.info("  silent placeholder products: %d (skipped %d new-wisdom, "
             "%d no-sku-match, %d no-page)",
             len(silent), skipped_new_wisdom, skipped_no_sku_match, skipped_no_page)
    return silent


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input")
    parser.add_argument("--vendors-repo", default=DEFAULT_VENDORS_REPO)
    parser.add_argument("--output", default=OUTPUT_DEFAULT)
    parser.add_argument("--medusa-url", default=os.environ.get("MEDUSA_BACKEND_URL", MEDUSA_DEFAULT_URL))
    parser.add_argument("--include-non-placeholders", action="store_true",
                        help="Also include SKUs whose product already has a real thumbnail "
                             "(useful for full audit; default scope is placeholder-only).")
    args = parser.parse_args()

    # ── 1. Load merged JSON → sku→{pdf, pages, title, matched_id}
    log.info("[1] Loading merged JSON …")
    rows = load_merged_json(args.input, args.vendors_repo)
    log.info("    %d rows in merged JSON.", len(rows))

    PDF_SEARCH_DIRS = [
        r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\2026 Wisdom Product Catalogs Claude\Wisdom Slack Downloads",
        r"C:\Users\Eukrit\My Drive\Catalogs GO\Wisdom Playground",
    ]
    MAIN_PDF_NAME = "2025 Wisdom catalog.pdf"  # prefer this when a SKU appears in multiple sources

    def _find_pdf(name: str) -> Optional[str]:
        for d in PDF_SEARCH_DIRS:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
        return None

    def _parse_range(rng: str) -> tuple[int, int] | None:
        if not rng or "-" not in rng:
            return None
        try:
            a, b = rng.split("-", 1)
            return int(a), int(b)
        except Exception:
            return None

    def _classify_pages(pages: list[int], sources: list[dict]) -> list[tuple[str, int]]:
        """For each page, find the source PDF whose page_range covers it.
        Returns list of (pdf, page). Prefers the main catalog when multiple
        sources cover the same page. Drops pages from PDFs that don't exist
        on local disk (with a logged warning per missing PDF)."""
        ranges_by_pdf: list[tuple[str, int, int]] = []
        for s in sources:
            pdf = s.get("pdf")
            r = _parse_range(s.get("page_range", ""))
            if pdf and r:
                ranges_by_pdf.append((pdf, r[0], r[1]))
        out: list[tuple[str, int]] = []
        for p in pages:
            matches = [pdf for pdf, a, b in ranges_by_pdf if a <= p <= b]
            if not matches:
                continue
            # Prefer the main catalog when it covers the page; else the first
            # available PDF that exists on disk.
            chosen = None
            if MAIN_PDF_NAME in matches and _find_pdf(MAIN_PDF_NAME):
                chosen = MAIN_PDF_NAME
            else:
                for m in matches:
                    if _find_pdf(m):
                        chosen = m
                        break
            if chosen is None:
                continue
            out.append((chosen, p))
        # Dedupe pages within same PDF
        seen = set()
        deduped = []
        for pdf, p in out:
            key = (pdf, p)
            if key in seen:
                continue
            seen.add(key)
            deduped.append((pdf, p))
        return deduped

    sku_meta: dict[str, dict] = {}
    for r in rows:
        sku = (r.get("sku") or "").upper()
        if not sku:
            continue
        fs = r.get("firestore") or {}
        sources = r.get("sources") or []
        pages = r.get("pages") or []
        page_assignments = _classify_pages(pages, sources)
        sku_meta[sku] = {
            "title": fs.get("description") or r.get("name") or sku,
            "matched_id": fs.get("matched_id"),
            # Keep page_assignments as the authoritative (pdf, page) list.
            "page_assignments": page_assignments,
            # Legacy fields for downstream code that still reads `pdf` + `pages`.
            "pdf": page_assignments[0][0] if page_assignments else None,
            "pages": [p for _pdf, p in page_assignments],
            "sub_area": r.get("sub_area"),
        }

    # ── 2. Pull rejection records
    log.info("[2] Pulling rejection records from verify cache …")
    fs_client = open_firestore()
    rejects = query_rejections(fs_client)

    # ── 3. Group by SKU
    log.info("[3] Grouping rejections by SKU …")
    by_sku: dict[str, list[dict]] = defaultdict(list)
    unparsed = 0
    for rec in rejects:
        url = rec.get("url") or ""
        sku = sku_from_url(url)
        if not sku:
            unparsed += 1
            continue
        by_sku[sku].append({
            "url": url,
            "confidence": rec.get("confidence"),
            "depicted": rec.get("depicted") or "",
            "title_at_verify": rec.get("title") or "",
        })
    log.info("    %d SKUs with rejections (%d URLs couldn't be parsed).",
             len(by_sku), unparsed)

    # Restrict to SKUs present in the outdoor-play merged JSON.
    outdoor_play_skus = set(sku_meta.keys())
    in_scope = {sku: v for sku, v in by_sku.items() if sku in outdoor_play_skus}
    out_of_scope = {sku: v for sku, v in by_sku.items() if sku not in outdoor_play_skus}
    log.info("    %d SKUs in outdoor-play scope; %d rejections from other collections (skipped).",
             len(in_scope), len(out_of_scope))

    # ── 4. Resolve each SKU → Medusa product_id
    log.info("[4] Building Medusa legacy_sku index (Leka Project SC) …")
    client = MedusaImporter(base_url=args.medusa_url)
    if not client.api_key:
        raise SystemExit(
            "Medusa client has no token. Set MEDUSA_ADMIN_EMAIL + "
            "MEDUSA_ADMIN_PASSWORD env vars, then re-run."
        )
    idx = build_legacy_lookup_combined(client)

    sku_to_pid: dict[str, str] = {}
    unresolved: list[str] = []
    for sku in in_scope:
        meta = sku_meta[sku]
        pid, _vid, _method = find_existing(idx, sku, meta.get("matched_id"))
        if pid:
            sku_to_pid[sku] = pid
        else:
            unresolved.append(sku)
    log.info("    Resolved %d SKUs → product_id; %d unresolved.",
             len(sku_to_pid), len(unresolved))

    # ── 5. Inspect current product state
    unique_pids = set(sku_to_pid.values())
    states = fetch_product_states(client, unique_pids)
    placeholder_pids = {
        pid for pid, s in states.items()
        if is_image_placeholder(s.get("thumbnail"), s.get("image_status"))
    }
    log.info("    %d / %d products currently sit on placeholder.",
             len(placeholder_pids), len(unique_pids))

    # Bucket A — products whose current thumbnail is itself a Gemini-rejected URL.
    rejected_url_set = {r["url"] for sku, recs in in_scope.items() for r in recs}
    bucket_rejected_thumb_pids: set[str] = set()
    for sku, pid in sku_to_pid.items():
        thumb = states.get(pid, {}).get("thumbnail")
        if thumb and thumb in rejected_url_set:
            bucket_rejected_thumb_pids.add(pid)
    log.info("    Bucket A (rejected-URL thumb): %d products.",
             len(bucket_rejected_thumb_pids))

    # Bucket B — products in the rejection scan that ALSO landed on placeholder.
    bucket_placeholder_with_rejections_pids = placeholder_pids
    log.info("    Bucket B (rejection-scan placeholder): %d products.",
             len(bucket_placeholder_with_rejections_pids))

    # ── 5b. Bucket C — silent-placeholder products NOT in the rejection scan
    log.info("[5b] Scanning wisdom-outdoor-play collection for silent placeholders …")
    already_pids = bucket_rejected_thumb_pids | bucket_placeholder_with_rejections_pids
    silent = find_silent_placeholders(client, COLLECTION_ID, already_pids, sku_meta)
    log.info("    Bucket C (silent placeholder): %d products.", len(silent))

    if args.include_non_placeholders:
        bucket_rejected_thumb_pids = unique_pids
        log.info("    --include-non-placeholders set; bucket A expanded to all %d "
                 "rejection-scan products.", len(unique_pids))

    # ── 6. Group SKUs by (pdf, page) — the unit of work for Phase 2
    log.info("[6] Grouping targets by (pdf, page) …")
    pages: dict[tuple[str, int], list[dict]] = defaultdict(list)
    skipped_no_page = []
    targets_by_sku: list[dict] = []

    # Buckets A + B (the rejection-scan SKUs)
    target_pids_ab = bucket_rejected_thumb_pids | bucket_placeholder_with_rejections_pids
    for sku, pid in sku_to_pid.items():
        if pid not in target_pids_ab:
            continue
        meta = sku_meta[sku]
        page_assignments = meta.get("page_assignments") or []
        if not page_assignments:
            skipped_no_page.append(sku)
            continue
        bucket = "A_rejected_thumb" if pid in bucket_rejected_thumb_pids else "B_placeholder_with_rejections"
        target = {
            "sku": sku,
            "product_id": pid,
            "title": meta["title"],
            "current_thumbnail": states.get(pid, {}).get("thumbnail"),
            "current_image_status": states.get(pid, {}).get("image_status"),
            "handle": states.get(pid, {}).get("handle"),
            "matched_id": meta.get("matched_id"),
            "sub_area": meta.get("sub_area"),
            "page_assignments": page_assignments,
            "rejections": in_scope[sku],
            "bucket": bucket,
        }
        targets_by_sku.append(target)
        for pdf, p in page_assignments:
            pages[(pdf, int(p))].append({
                "sku": sku,
                "product_id": pid,
                "title": meta["title"],
                "bucket": bucket,
            })

    # Bucket C (silent placeholders not in rejection-scan)
    silent_seen_skus: set[str] = set()
    for entry in silent:
        sku = entry["primary_sku"]
        if sku in silent_seen_skus:
            continue
        silent_seen_skus.add(sku)
        meta = sku_meta.get(sku, {})
        page_assignments = meta.get("page_assignments") or []
        if not page_assignments:
            skipped_no_page.append(sku)
            continue
        target = {
            "sku": sku,
            "product_id": entry["product_id"],
            "title": entry["title"] or meta.get("title"),
            "current_thumbnail": entry["thumbnail"],
            "current_image_status": "placeholder",
            "handle": entry["handle"],
            "matched_id": entry["matched_id"],
            "sub_area": entry["sub_area"],
            "page_assignments": page_assignments,
            "rejections": [],
            "bucket": "C_silent_placeholder",
            "all_candidate_skus": entry["all_candidate_skus"],
        }
        targets_by_sku.append(target)
        for pdf, p in page_assignments:
            pages[(pdf, int(p))].append({
                "sku": sku,
                "product_id": entry["product_id"],
                "title": target["title"],
                "bucket": "C_silent_placeholder",
            })

    # ── 7. Emit
    work_units = [
        {"pdf": pdf, "page": page, "candidates": sorted(cands, key=lambda c: c["sku"])}
        for (pdf, page), cands in sorted(pages.items(),
                                         key=lambda kv: (kv[0][0], kv[0][1]))
    ]

    bucket_counts = defaultdict(int)
    for t in targets_by_sku:
        bucket_counts[t["bucket"]] += 1

    output = {
        "_meta": {
            "generated_by": "wisdom-catalog/build_recrop_worklist.py",
            "medusa_url": args.medusa_url,
            "verify_collection": GEMINI_VERIFY_COLLECTION,
            "collection_id": COLLECTION_ID,
            "placeholder_url": PLACEHOLDER_URL,
        },
        "summary": {
            "rejection_records": len(rejects),
            "skus_with_rejections": len(by_sku),
            "skus_in_outdoor_play": len(in_scope),
            "skus_resolved_to_medusa": len(sku_to_pid),
            "skus_unresolved": len(unresolved),
            "unique_products_with_rejections": len(unique_pids),
            "bucket_A_rejected_thumb": bucket_counts["A_rejected_thumb"],
            "bucket_B_placeholder_with_rejections": bucket_counts["B_placeholder_with_rejections"],
            "bucket_C_silent_placeholder": bucket_counts["C_silent_placeholder"],
            "targets": len(targets_by_sku),
            "unique_pages": len(work_units),
            "skipped_no_page": len(skipped_no_page),
        },
        "targets_by_sku": sorted(targets_by_sku, key=lambda t: t["sku"]),
        "work_units": work_units,
        "unresolved_skus": sorted(unresolved),
        "skipped_no_page": sorted(skipped_no_page),
    }

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    log.info("[7] Wrote %s", args.output)

    # ── 8. Pretty summary to stdout
    print()
    print("=" * 70)
    print("RECROP WORKLIST SUMMARY")
    print("=" * 70)
    for k, v in output["summary"].items():
        print(f"  {k:34s} {v:>5}")
    print()
    print(f"Unique pages to render: {len(work_units)}")
    print(f"Unique target products: {len({t['product_id'] for t in targets_by_sku})}")
    print(f"Target SKUs:            {len(targets_by_sku)}")
    print()
    if work_units:
        print("First 5 work units (pdf, page -> candidate SKUs):")
        for wu in work_units[:5]:
            skus = ", ".join(c["sku"] for c in wu["candidates"])
            print(f"  p{wu['page']:>3}  {wu['pdf'][:40]:40s}  [{skus}]")
    print()
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
