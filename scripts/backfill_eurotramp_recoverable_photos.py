"""Backfill real product photos to Eurotramp Medusa products that still have a
non-photo thumbnail but DO have recoverable photos in the local scrape
(data/scraped/eurotramp/products.json).

Self-contained — does not depend on the audit/diff/manifest chain, and it
NORMALISES the scrape handle (`112--125` -> `112-125`) so matches the diff
script misses are caught. Photos are size-upgraded, rehosted to
`gs://ai-agents-go-vendors/eurotramp/<handle>/<fn>` (via `gcloud storage`,
which uses the active gcloud SA — the GCS SDK needs ADC reauth here), then the
proxy URLs are pushed to Medusa images[] (real-photo-first) and the thumbnail
re-pointed to the best new photo. Rollback metadata is stashed.

Usage:
    python scripts/backfill_eurotramp_recoverable_photos.py --dry-run
    python scripts/backfill_eurotramp_recoverable_photos.py --apply [--limit N]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

# On Windows, gcloud is a .CMD; bare "gcloud" isn't resolved by subprocess
# (no PATHEXT lookup without a shell). Resolve the full path once.
GCLOUD = shutil.which("gcloud") or "gcloud"

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
SCRAPE_JSON = REPO_ROOT / "data" / "scraped" / "eurotramp" / "products.json"
TMP_DIR = REPO_ROOT / "data" / "scraped" / "eurotramp" / "_rehost_tmp"

from shared.medusa_importer import MedusaImporter  # noqa: E402
from reclassify_eurotramp_images import classify  # noqa: E402
from rehost_missing_eurotramp_photos import upgrade_url_to_largest  # noqa: E402
from fix_eurotramp_thumbnails import fn_of, photo_rank, handle_tokens, handle_overlap  # noqa: E402

MEDUSA_URL = os.environ.get(
    "MEDUSA_BACKEND_URL",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
GCS_BUCKET = "ai-agents-go-vendors"
GCS_PREFIX = "eurotramp"
PROXY_BASE = "https://catalogs.leka.studio/api/i"
UA = "AredaCatalogBot/1.0 (Eurotramp photo backfill; +https://catalogs.leka.studio)"


def _env_alias() -> None:
    for a, b in (("LEKA_MEDUSA_ADMIN_EMAIL", "MEDUSA_ADMIN_EMAIL"),
                 ("LEKA_MEDUSA_ADMIN_PASSWORD", "MEDUSA_ADMIN_PASSWORD")):
        if not os.environ.get(b) and os.environ.get(a):
            os.environ[b] = os.environ[a]


def norm(h: str) -> str:
    return h.replace("--", "-")


def gcs_exists(gcs_path: str) -> bool:
    uri = f"gs://{GCS_BUCKET}/{gcs_path}"
    r = subprocess.run([GCLOUD, "storage", "ls", uri], capture_output=True, text=True)
    return r.returncode == 0 and uri in r.stdout


def gcs_upload(local: Path, gcs_path: str) -> None:
    uri = f"gs://{GCS_BUCKET}/{gcs_path}"
    r = subprocess.run(
        [GCLOUD, "storage", "cp", "--no-clobber", "--content-type=image/jpeg", str(local), uri],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gcloud upload failed: {r.stderr[:300]}")


def fetch_eurotramp(client: MedusaImporter) -> list[dict]:
    fields = "id,handle,thumbnail,images.url,metadata"
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


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    _env_alias()
    client = MedusaImporter(base_url=MEDUSA_URL)
    if not client.api_key:
        print("ERROR: no Medusa admin auth.", file=sys.stderr)
        return 2

    scrape = json.loads(SCRAPE_JSON.read_text(encoding="utf-8"))
    sc = {norm(p["handle"]): p for p in scrape}
    products = fetch_eurotramp(client)

    # Build the recoverable worklist.
    work = []
    for p in products:
        h = p["handle"]
        # Add recoverable photos regardless of current thumbnail state; the
        # thumbnail is only re-pointed below if it isn't already a real photo.
        thumb = p.get("thumbnail")
        sp = sc.get(norm(h)) or sc.get(h)
        if not sp:
            continue
        med_urls = [im["url"] for im in (p.get("images") or [])]
        med_fns = {fn_of(u).lower() for u in med_urls}
        if thumb:
            med_fns.add(fn_of(thumb).lower())
        scrape_photos = [u for u in (sp.get("image_urls") or []) if classify(fn_of(u)) == "photo"]
        # new = scrape photo whose filename not already in medusa, dedup by fn
        new_by_fn = {}
        for u in scrape_photos:
            f = fn_of(u)
            if f.lower() in med_fns:
                continue
            if f not in new_by_fn or len(u) > len(new_by_fn[f]):
                new_by_fn[f] = u
        if new_by_fn:
            work.append((p, list(new_by_fn.values())))

    if args.limit:
        work = work[: args.limit]
    print(f"Recoverable products: {len(work)} "
          f"(total new photos: {sum(len(v) for _, v in work)})")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    log, n_prod, n_photos, n_fail = [], 0, 0, 0

    for i, (p, new_urls) in enumerate(work, 1):
        h = p["handle"]
        htoks = handle_tokens(h)
        print(f"\n[{i}/{len(work)}] {h}  (+{len(new_urls)} photos)")
        proxy_urls = []
        for original in new_urls:
            url = original if args.dry_run else upgrade_url_to_largest(original, session)
            fn = fn_of(url)
            gcs_path = f"{GCS_PREFIX}/{h}/{fn}"
            proxy = f"{PROXY_BASE}/{GCS_PREFIX}/{h}/{fn}"
            if args.dry_run:
                print(f"   [dry] {fn}")
                proxy_urls.append(proxy)
                continue
            local = TMP_DIR / fn
            try:
                if not local.exists():
                    time.sleep(0.2)
                    r = session.get(url, timeout=30)
                    if r.status_code != 200 or len(r.content) < 200:
                        print(f"   x download {r.status_code}: {fn}")
                        n_fail += 1
                        continue
                    local.write_bytes(r.content)
                if not gcs_exists(gcs_path):
                    gcs_upload(local, gcs_path)
                proxy_urls.append(proxy)
                n_photos += 1
            except Exception as e:
                print(f"   x {fn}: {e}")
                n_fail += 1

        if not proxy_urls:
            continue

        # Compose new images[]: new real photos (ranked) first, then existing, dedup.
        existing = [im["url"] for im in (p.get("images") or [])]
        ranked_new = sorted(proxy_urls, key=lambda u: (handle_overlap(fn_of(u), htoks), *photo_rank(u)), reverse=True)
        merged, seen = [], set()
        for u in ranked_new + existing:
            if u not in seen:
                seen.add(u)
                merged.append(u)

        thumb = p.get("thumbnail")
        thumb_kind = classify(fn_of(thumb)) if thumb else "none"
        best_new = ranked_new[0]
        # New photos come from THIS product's matched vendor page, so relevance
        # is guaranteed — re-point the thumbnail whenever it isn't already a
        # real photo (no handle-overlap gate needed here).
        new_thumb = best_new if thumb_kind != "photo" else thumb

        if args.dry_run:
            print(f"   [dry] images {len(existing)} -> {len(merged)}; thumb -> {fn_of(new_thumb)}")
            log.append({"handle": h, "status": "dry_run", "new_photos": len(proxy_urls)})
            n_prod += 1
            continue

        meta = dict(p.get("metadata") or {})
        meta.setdefault("previous_thumbnail", thumb)
        meta.setdefault("previous_images", existing)
        meta["photo_backfilled_at"] = now
        payload = {"images": [{"url": u} for u in merged], "thumbnail": new_thumb, "metadata": meta}
        try:
            client._post(f"/admin/products/{p['id']}", payload)
            n_prod += 1
            log.append({"handle": h, "status": "updated", "new_photos": len(proxy_urls),
                        "thumb": fn_of(new_thumb)})
            print(f"   updated: images {len(existing)} -> {len(merged)}; thumb {fn_of(new_thumb)}")
        except Exception as e:
            n_fail += 1
            log.append({"handle": h, "status": "error", "error": str(e)})
            print(f"   x medusa update: {e}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"eurotramp-recoverable-backfill-{today}.json"
    out.write_text(json.dumps({
        "generated_at": now, "mode": "dry-run" if args.dry_run else "apply",
        "totals": {"products": n_prod, "photos_uploaded": n_photos, "failed": n_fail},
        "log": log,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n=== {'DRY-RUN' if args.dry_run else 'APPLY'} ===")
    print(f"products: {n_prod}, photos uploaded: {n_photos}, failed: {n_fail}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
