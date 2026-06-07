"""Enrich the live Eurotramp Medusa catalog from the local EuroTramp 2023
Info-Package asset folder (KidsTramp-PlayPro + Playground-Outdoor-Trampolines).

What it does
------------
1. Catalogs every local image + PDF, verifies each is hydrated (real bytes,
   not a 0-byte OneDrive placeholder).
2. Maps assets -> Medusa product handle using TWO signals:
     * Tier-1 (HIGH): article number embedded in the filename
       (e.g. ``97000-...``, ``E97047-...``) matched against the product
       article index built from the live snapshot.
     * Tier-2 (MEDIUM): a CURATED visual mapping (the result of a manual
       review of the generic ``Eurotramp-0XX.jpg`` marketing library) that
       attaches type-correct lifestyle photos to specific image-gap products.
3. Writes a dry-run asset map + backfill plan to docs/reports/ for review.
4. On --apply: uploads the mapped photos to
   ``gs://ai-agents-go-vendors/eurotramp/<handle>/<fn>`` via ``gcloud storage``
   (active gcloud SA — the GCS SDK needs ADC reauth here), points Medusa
   images[]/thumbnail at the proxy URLs (real-photo-first, full-replace),
   stashes rollback metadata, and enriches metadata with EN 1176 / TUV-GS /
   facility-type / dimension specs extracted from the catalog PDFs.

CRITICAL: a photo is only ever attached to the product it actually depicts
(article-number or curated type match). Anything uncertain is left ``review``.

Usage:
    python scripts/enrich_eurotramp_from_local_assets.py --dry-run
    python scripts/enrich_eurotramp_from_local_assets.py --apply [--limit N] [--force]
    python scripts/enrich_eurotramp_from_local_assets.py --rollback
"""
from __future__ import annotations

import argparse
import datetime
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
REPORTS_DIR = REPO_ROOT / "docs" / "reports"

from shared.medusa_importer import MedusaImporter  # noqa: E402
from reclassify_eurotramp_images import classify  # noqa: E402
from fix_eurotramp_thumbnails import fn_of, photo_rank, handle_tokens, handle_overlap  # noqa: E402

GCLOUD = shutil.which("gcloud") or "gcloud"
MEDUSA_URL = os.environ.get(
    "MEDUSA_BACKEND_URL",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
GCS_BUCKET = "ai-agents-go-vendors"
GCS_PREFIX = "eurotramp"
PROXY_BASE = "https://catalogs.leka.studio/api/i"

ASSET_ROOT = Path(
    r"C:\Users\eukri\OneDrive\Documents\Documents GO\2023-06-23 EuroTramp 2023 Downloads"
)
KIDS = "Info-Package-KidsTramp-PlayPro_EN"
OUT = "Info-Package-Playground-Outdoor-Trampolines-2023"

# ── Tier-2 curated mapping ────────────────────────────────────────────────
# Result of a manual review of the generic Eurotramp-0XX marketing library.
# Each entry attaches a type-correct photo set to one product. ``set_thumbnail``
# means the first listed asset becomes the new hero. ``confidence`` is logged.
CURATED: list[dict] = [
    {
        "handle": "eurotramp-kids-tramp-kindergarten",
        "is_gap": True,
        "confidence": "medium",
        "scene": "square in-ground trampoline in a daycare/kindergarten garden",
        "evidence": "075-084 are a single product shoot of a square supervised "
                    "garden trampoline = the 'Kindergarten' (supervised) model",
        "set_thumbnail": True,
        "assets": [f"{OUT}/Eurotramp-078.jpg", f"{OUT}/Eurotramp-076.jpg",
                   f"{OUT}/Eurotramp-082.jpg"],
        "upload_as": ["productdetails-kids-tramp-kindergarten-078.jpg",
                      "productdetails-kids-tramp-kindergarten-076.jpg",
                      "productdetails-kids-tramp-kindergarten-082.jpg"],
    },
    {
        "handle": "eurotramp-wehrfritz-fun-xl-kindergarten",
        "is_gap": True,
        "confidence": "medium",
        "scene": "wheelchair user entering an in-ground trampoline via the ramped edge",
        "evidence": "wheelchair accessibility is the Wehrfritz FUN XL Kindergarten "
                    "signature feature (metadata suitable-for-wheelchairs)",
        "set_thumbnail": True,
        "assets": [f"{OUT}/Eurotramp-019.jpg", f"{OUT}/Eurotramp-021.jpg",
                   f"{OUT}/Eurotramp-020.jpg"],
        "upload_as": ["productdetails-wehrfritz-fun-xl-kindergarten-019.jpg",
                      "productdetails-wehrfritz-fun-xl-kindergarten-021.jpg",
                      "productdetails-wehrfritz-fun-xl-kindergarten-020.jpg"],
    },
]

# Named article-number photos (Tier-1). filename article -> the product whose
# article index entry matches. The product handle is resolved from the live
# snapshot at runtime so we never hardcode a wrong handle.
# ``handle`` is an explicit override for article numbers that are NOT embedded
# in the Medusa handle/title (the Kids Tramp models use names, not numbers).
# 97000 = Kids Tramp Playground, 97010 = Kids Tramp Playground Loop
# (per the Q4 KidsTramp 2023 catalog art-no lineup: 97004-97009/97012 = Playground).
NAMED_PHOTOS: list[dict] = [
    {"file": f"{KIDS}/97000-KidsTramp-Playground-EPDM-TSV-Bulach.jpg", "article": "97000",
     "handle": "eurotramp-kids-tramp-playground",
     "upload_as": "97000-kidstramp-playground-epdm.jpg"},
    {"file": f"{KIDS}/97000B-KidsTramp-Playground-PlayPro.jpg", "article": "97000",
     "handle": "eurotramp-kids-tramp-playground",
     "upload_as": "97000b-kidstramp-playground-playpro.jpg"},
    {"file": f"{KIDS}/97010B-KidsTramp-PlaygroundLoop-PlayPro.jpg", "article": "97010",
     "handle": "eurotramp-kids-tramp-playground-loop",
     "upload_as": "97010b-kidstramp-playgroundloop-playpro.jpg"},
    {"file": f"{KIDS}/E97047-PlayPro-rubber-protection-ring-Loop.jpg", "article": "e97047",
     "upload_as": "e97047-playpro-rubber-protection-ring-loop.jpg"},
    {"file": f"{KIDS}/E97048-PlayPro-rubber-protection-lip-square-KidsTramp.jpg", "article": "e97048",
     "upload_as": "e97048-playpro-rubber-protection-lip-square.jpg"},
    {"file": f"{KIDS}/E97548-PlayPro-rubber-protection-lip-square-KidsTrampXL.jpg", "article": "e97548",
     "upload_as": "e97548-playpro-rubber-protection-lip-square-xl.jpg"},
    # Section diagram — supporting gallery image for the lip products (not a thumbnail).
    {"file": f"{KIDS}/PlayProSquare_Section.png", "article": "e97048", "diagram": True,
     "upload_as": "playpro-square-section.png"},
    # No Medusa product for e97047-XL ring (loop XL) — left for review.
    {"file": f"{KIDS}/E97547-PlayPro-rubber-protection-ring-LoopXL.jpg", "article": "e97547",
     "upload_as": "e97547-playpro-rubber-protection-ring-loop-xl.jpg", "no_target_ok": True},
]

# ── Metadata enrichment (additive; only fills MISSING keys) ────────────────
SPEC_COMMON = {"standard_playground": "DIN EN 1176", "tuv_gs_tested": True,
               "made_in": "Germany", "enriched_source": "EuroTramp 2023 Info-Package (local asset pack)"}
PLAYGROUND_SPECS = {
    **SPEC_COMMON,
    "facility_type": "unsupervised public usage areas",
    "supervision": "unsupervised",
    "surface_features": ["flame-retardant coating", "vandal-proof / cut-resistant surface",
                         "UV-light resistant", "heat-resistant", "cold-resistant",
                         "water-resistant", "all-year-round use"],
    "applications": ["playgrounds", "schools", "public spaces"],
}
KINDERGARTEN_SPECS = {
    **SPEC_COMMON,
    "facility_type": "supervised areas",
    "supervision": "supervised",
    "applications": ["daycare", "kindergarten", "schools", "therapy"],
}
# handle -> metadata additions
SPECS: dict[str, dict] = {
    "eurotramp-kids-tramp-playground": PLAYGROUND_SPECS,
    "eurotramp-kids-tramp-playground-xl": {**PLAYGROUND_SPECS, "size_m": "2x2"},
    "eurotramp-kids-tramp-playground-loop": PLAYGROUND_SPECS,
    "eurotramp-kids-tramp-playground-loop-xl": PLAYGROUND_SPECS,
    "eurotramp-kids-tramp-kindergarten": KINDERGARTEN_SPECS,
    "eurotramp-kids-tramp-kindergarten-xl": KINDERGARTEN_SPECS,
    "eurotramp-kids-tramp-kindergarten-loop": {**KINDERGARTEN_SPECS, "size_m": "1.5x1.5"},
    "eurotramp-kids-tramp-kindergarten-loop-xl": KINDERGARTEN_SPECS,
    "eurotramp-wehrfritz-fun-xl-kindergarten": {**KINDERGARTEN_SPECS, "size_m": "2.65x2.65",
                                                "wheelchair_accessible": True},
    "eurotramp-wehrfritz-fun-round-kindergarten-94750": {**KINDERGARTEN_SPECS, "shape": "round"},
    "eurotramp-eurotramp-play": {
        **SPEC_COMMON,
        "features": ["12V light & sound generator powered by jumping (no external power)",
                     "audio feed via USB stick", "LED reaction/teaching games",
                     "switchable effects"],
        "add_on": "can also be installed on existing trampolines",
    },
    "eurotramp-eurotramp-play-light-epl0001": {
        **SPEC_COMMON,
        "features": ["12V light & sound generator powered by jumping", "LED light games"],
    },
    # PlayPro impact protection (natural rubber ring/lip).
    "eurotramp-playpro-rubber-protection-ring-for-kids-tramp-loop-e97047": {
        "material": "natural rubber", "standard_playground": "DIN EN 1176",
        "developed_by": "Rampline in cooperation with Eurotramp",
        "function": "shock-absorbing impact-protection ring; smooth transition to EPDM wet-pour / artificial turf",
        "enriched_source": SPEC_COMMON["enriched_source"]},
    "eurotramp-playpro-rubber-protection-lip-for-kids-tramp-e97048": {
        "material": "natural rubber", "standard_playground": "DIN EN 1176",
        "developed_by": "Rampline in cooperation with Eurotramp",
        "function": "shock-absorbing impact-protection lip (square Kids Tramp); smooth transition to EPDM / turf",
        "enriched_source": SPEC_COMMON["enriched_source"]},
    "eurotramp-playpro-rubber-protection-lip-for-kids-tramp-xl-e97548": {
        "material": "natural rubber", "standard_playground": "DIN EN 1176",
        "developed_by": "Rampline in cooperation with Eurotramp",
        "function": "shock-absorbing impact-protection lip (square Kids Tramp XL); smooth transition to EPDM / turf",
        "enriched_source": SPEC_COMMON["enriched_source"]},
}


def _env_alias() -> None:
    for a, b in (("LEKA_MEDUSA_ADMIN_EMAIL", "MEDUSA_ADMIN_EMAIL"),
                 ("LEKA_MEDUSA_ADMIN_PASSWORD", "MEDUSA_ADMIN_PASSWORD")):
        if not os.environ.get(b) and os.environ.get(a):
            os.environ[b] = os.environ[a]


def is_hydrated(p: Path) -> bool:
    """Real bytes on disk, not a 0-byte OneDrive online-only placeholder."""
    try:
        return p.is_file() and p.stat().st_size > 1024
    except OSError:
        return False


# gcloud storage's multiprocessing worker pool DEADLOCKS on Windows under a
# non-interactive shell (the 2nd+ `cp` invocation hangs forever). Forcing a
# single process + single thread disables that pool and makes uploads reliable.
GCS_ENV = {**os.environ, "CLOUDSDK_STORAGE_PROCESS_COUNT": "1",
           "CLOUDSDK_STORAGE_THREAD_COUNT": "1"}


def gcs_upload(local: Path, gcs_path: str) -> None:
    """Idempotent upload via `gcloud storage cp --no-clobber` (skips existing,
    returns 0). Single-process/thread (see GCS_ENV) + per-call timeout + retries
    so a flaky gcloud invocation can never hang the whole run indefinitely."""
    uri = f"gs://{GCS_BUCKET}/{gcs_path}"
    ctype = mimetypes.guess_type(str(local))[0] or "image/jpeg"
    last = ""
    for attempt in range(3):
        try:
            r = subprocess.run(
                [GCLOUD, "storage", "cp", "--no-clobber",
                 f"--content-type={ctype}", str(local), uri],
                capture_output=True, text=True, timeout=180, env=GCS_ENV,
            )
        except subprocess.TimeoutExpired:
            last = f"timeout after 180s (attempt {attempt + 1})"
            continue
        if r.returncode == 0:
            return
        last = (r.stderr or "")[:300]
    raise RuntimeError(f"gcloud upload failed after retries: {last}")


def fetch_eurotramp(client: MedusaImporter) -> list[dict]:
    fields = "id,handle,title,status,thumbnail,images.url,metadata"
    out, offset, limit = [], 0, 200
    while True:
        r = client._get("/admin/products", {"limit": limit, "offset": offset, "fields": fields})
        batch = r.get("products", [])
        if not batch:
            break
        out += [p for p in batch if (p.get("handle") or "").startswith("eurotramp-")]
        offset += limit
    out.sort(key=lambda p: p["handle"])
    return out


def article_index(products: list[dict]) -> dict[str, str]:
    idx = {}
    for p in products:
        for src in (p["handle"], p.get("title") or ""):
            for m in re.findall(r"\b(e?\d{4,6})\b", src, re.IGNORECASE):
                idx.setdefault(m.lower(), p["handle"])
    return idx


def proxy_url(handle: str, fn: str) -> str:
    return f"{PROXY_BASE}/{GCS_PREFIX}/{handle}/{fn}"


def build_plan(products: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (image_plan, review) entries. image_plan items are applied."""
    by_handle = {p["handle"]: p for p in products}
    art_idx = article_index(products)
    plan, review = [], []

    # Tier-1 named article photos
    for np_ in NAMED_PHOTOS:
        fp = ASSET_ROOT / np_["file"]
        # explicit override wins, but only if that handle really exists
        handle = np_.get("handle") if np_.get("handle") in by_handle else art_idx.get(np_["article"])
        entry = {
            "asset": np_["file"], "article": np_["article"], "tier": "1-article",
            "confidence": "high", "upload_as": np_["upload_as"],
            "hydrated": is_hydrated(fp), "diagram": np_.get("diagram", False),
        }
        if not handle:
            entry.update({"target_handle": None, "action": "review",
                          "reason": "no Medusa product for this article number"})
            review.append(entry)
            continue
        entry.update({"target_handle": handle, "is_gap": handle in GAP_HANDLES,
                      "set_thumbnail": not np_.get("diagram", False),
                      "action": "apply"})
        plan.append(entry)

    # Tier-2 curated visual photos
    for cu in CURATED:
        h = cu["handle"]
        if h not in by_handle:
            review.append({**cu, "action": "review", "reason": "handle not in catalog"})
            continue
        for i, (a, up) in enumerate(zip(cu["assets"], cu["upload_as"])):
            fp = ASSET_ROOT / a
            plan.append({
                "asset": a, "tier": "2-curated", "confidence": cu["confidence"],
                "scene": cu["scene"], "evidence": cu["evidence"],
                "target_handle": h, "is_gap": cu["is_gap"], "upload_as": up,
                "set_thumbnail": cu["set_thumbnail"] and i == 0,
                "hydrated": is_hydrated(fp), "diagram": False, "action": "apply",
            })

    # Everything else in the generic library -> review pool
    mapped = {e["asset"] for e in plan} | {e.get("asset") for e in review}
    for fp in sorted((ASSET_ROOT / OUT).glob("Eurotramp-*.jpg")):
        rel = f"{OUT}/{fp.name}"
        if rel in mapped:
            continue
        review.append({"asset": rel, "tier": "library", "confidence": "unmapped",
                       "target_handle": None, "action": "review",
                       "reason": "generic marketing-library photo; no confident product match",
                       "hydrated": is_hydrated(fp)})
    return plan, review


GAP_HANDLES: set[str] = set()


def load_gap_handles() -> set[str]:
    md = (REPORTS_DIR / "eurotramp-image-gaps-2026-06-05.md").read_text(encoding="utf-8")
    out = set()
    for line in md.splitlines():
        m = re.match(r"\|\s*(?:draft|published)\s*\|\s*([a-z0-9-]+)\s*\|", line)
        if m:
            out.add(m.group(1))
    return out


def apply_images(client, products, plan, now, dry, limit, force):
    by_handle = {p["handle"]: p for p in products}
    # group plan by handle
    by_h: dict[str, list[dict]] = {}
    for e in plan:
        by_h.setdefault(e["target_handle"], []).append(e)
    log, n_prod, n_up, n_fail = [], 0, 0, 0
    handles = list(by_h)
    if limit:
        handles = handles[:limit]
    for h in handles:
        p = by_handle[h]
        entries = by_h[h]
        meta = dict(p.get("metadata") or {})
        if meta.get("local_asset_enriched_at") and not force:
            log.append({"handle": h, "status": "skipped_already_enriched"})
            continue
        htoks = handle_tokens(h)
        proxy_new, thumb_pick = [], None
        for e in entries:
            fp = ASSET_ROOT / e["asset"]
            if not is_hydrated(fp):
                n_fail += 1
                log.append({"handle": h, "asset": e["asset"], "status": "not_hydrated"})
                continue
            fn = e["upload_as"]
            gcs_path = f"{GCS_PREFIX}/{h}/{fn}"
            url = proxy_url(h, fn)
            if not dry:
                try:
                    gcs_upload(fp, gcs_path)
                    n_up += 1
                    print(f"   up {h}/{fn}", flush=True)
                except Exception as ex:
                    n_fail += 1
                    log.append({"handle": h, "asset": e["asset"], "status": "upload_error",
                                "error": str(ex)[:200]})
                    print(f"   x  {h}/{fn}: {str(ex)[:120]}", flush=True)
                    continue
            else:
                n_up += 1
            if not e.get("diagram"):
                proxy_new.append(url)
            else:
                proxy_new.append(url)  # diagram appended but never thumbnail
            if e.get("set_thumbnail") and thumb_pick is None and not e.get("diagram"):
                thumb_pick = url
        if not proxy_new:
            continue
        existing = [im["url"] for im in (p.get("images") or [])]
        # real photos first (ranked by handle-overlap + photo_rank), then existing, dedup
        ranked_new = sorted(proxy_new, key=lambda u: (handle_overlap(fn_of(u), htoks), *photo_rank(u)),
                            reverse=True)
        merged, seen = [], set()
        for u in ranked_new + existing:
            if u not in seen:
                seen.add(u)
                merged.append(u)
        cur_thumb = p.get("thumbnail")
        cur_kind = classify(fn_of(cur_thumb)) if cur_thumb else "none"
        new_thumb = thumb_pick or cur_thumb
        if cur_kind == "photo" and not force:
            new_thumb = cur_thumb  # never override an existing real-photo thumbnail
        meta.setdefault("previous_thumbnail", cur_thumb)
        meta.setdefault("previous_images", existing)
        meta["local_asset_enriched_at"] = now
        rec = {"handle": h, "status": "dry_run" if dry else "updated",
               "n_assets": len(proxy_new), "thumb": fn_of(new_thumb),
               "confidence": entries[0].get("confidence"), "is_gap": h in GAP_HANDLES,
               "images": f"{len(existing)}->{len(merged)}"}
        if dry:
            log.append(rec)
            n_prod += 1
            continue
        payload = {"images": [{"url": u} for u in merged], "thumbnail": new_thumb, "metadata": meta}
        try:
            client._post(f"/admin/products/{p['id']}", payload)
            n_prod += 1
            log.append(rec)
            print(f"   OK medusa {h}  imgs {rec['images']} thumb={rec['thumb']}", flush=True)
        except Exception as ex:
            n_fail += 1
            log.append({"handle": h, "status": "medusa_error", "error": str(ex)[:200]})
            print(f"   x medusa {h}: {str(ex)[:120]}", flush=True)
    return log, n_prod, n_up, n_fail


def apply_specs(client, products, now, dry, force):
    by_handle = {p["handle"]: p for p in products}
    log, n = [], 0
    for h, additions in SPECS.items():
        p = by_handle.get(h)
        if not p:
            log.append({"handle": h, "status": "not_found"})
            continue
        meta = dict(p.get("metadata") or {})
        if meta.get("specs_enriched_at") and not force:
            continue
        added = {}
        for k, v in additions.items():
            if k not in meta or meta.get(k) in (None, "", [], {}):
                meta[k] = v
                added[k] = v
        if not added:
            continue
        meta["specs_enriched_at"] = now
        n += 1
        log.append({"handle": h, "status": "dry_run" if dry else "updated",
                    "added_keys": list(added)})
        if not dry:
            try:
                client._post(f"/admin/products/{p['id']}", {"metadata": meta})
            except Exception as ex:
                log[-1] = {"handle": h, "status": "error", "error": str(ex)[:200]}
    return log, n


def rollback(client, products):
    n = 0
    for p in products:
        meta = dict(p.get("metadata") or {})
        if "previous_thumbnail" not in meta and "previous_images" not in meta:
            continue
        if not meta.get("local_asset_enriched_at"):
            continue
        payload = {"thumbnail": meta.get("previous_thumbnail"),
                   "images": [{"url": u} for u in (meta.get("previous_images") or [])]}
        for k in ("previous_thumbnail", "previous_images", "local_asset_enriched_at"):
            meta.pop(k, None)
        payload["metadata"] = meta
        try:
            client._post(f"/admin/products/{p['id']}", payload)
            n += 1
            print(f"  rolled back {p['handle']}")
        except Exception as ex:
            print(f"  ! rollback failed {p['handle']}: {ex}")
    print(f"rolled back {n} products")


def main() -> int:
    # Windows console/file default is cp1252 — force UTF-8 so progress prints
    # (and any non-ASCII product titles) never raise UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--rollback", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-specs", action="store_true")
    args = ap.parse_args()

    global GAP_HANDLES
    GAP_HANDLES = load_gap_handles()

    _env_alias()
    client = MedusaImporter(base_url=MEDUSA_URL)
    if not client.api_key:
        print("ERROR: no Medusa admin auth.", file=sys.stderr)
        return 2
    # Bound every Medusa admin POST so a slow Cloud Run response can't hang the run.
    _orig_post = client.session.post
    def _post_with_timeout(url, **kw):
        kw.setdefault("timeout", 90)
        return _orig_post(url, **kw)
    client.session.post = _post_with_timeout
    products = fetch_eurotramp(client)
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now(datetime.UTC).isoformat()

    if args.rollback:
        rollback(client, products)
        return 0

    plan, review = build_plan(products)
    dry = args.dry_run

    img_log, n_prod, n_up, n_fail = apply_images(client, products, plan, now, dry,
                                                 args.limit, args.force)
    spec_log, n_spec = ([], 0) if args.no_specs else apply_specs(client, products, now, dry, args.force)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    # asset map (dry-run artefact, always written)
    amap = REPORTS_DIR / f"eurotramp-asset-map-{today}.json"
    amap.write_text(json.dumps({
        "generated_at": now, "mode": "dry-run" if dry else "apply",
        "asset_root": str(ASSET_ROOT),
        "counts": {"plan_assets": len(plan), "review_assets": len(review),
                   "gap_handles_total": len(GAP_HANDLES)},
        "image_plan": plan, "review": review,
        "spec_enrichment_targets": sorted(SPECS),
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    out = REPORTS_DIR / f"eurotramp-local-asset-{'dryrun' if dry else 'apply'}-{today}.json"
    out.write_text(json.dumps({
        "generated_at": now, "mode": "dry-run" if dry else "apply",
        "totals": {"products_images": n_prod, "uploads": n_up, "failed": n_fail,
                   "products_specs": n_spec},
        "image_log": img_log, "spec_log": spec_log,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== {'DRY-RUN' if dry else 'APPLY'} ===")
    print(f"image products: {n_prod}  uploads: {n_up}  failed: {n_fail}")
    print(f"spec products : {n_spec}")
    print(f"plan assets   : {len(plan)}  review assets: {len(review)}")
    gap_hit = sorted({e['target_handle'] for e in plan if e.get('is_gap')})
    print(f"gap handles closed by photos: {len(gap_hit)} -> {gap_hit}")
    print(f"asset map: {amap}")
    print(f"log      : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
