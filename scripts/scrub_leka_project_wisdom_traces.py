"""Scrub avoidable internal 'Wisdom' / vendor traces from the Leka Project brand.

The Wisdom catalog was rebranded to the customer-facing "Leka Project" brand
(Brand id=01KT1GW9C6EPW9AXESA7FGJBW6, SC sc_01KNKTHC0B7KFEDSZ3NNM49JQW). Titles,
subtitles, descriptions, product handles and variant SKUs were already cleaned,
but several internal traces still name the original vendor. Some of these reach
an *unauthenticated* storefront caller. This script verifies the public exposure
and scrubs the avoidable leaks.

Three modes (pick one; --dry-run is the default if none given):

  --verify    Read-only. Scan the brand via the Admin API for every trace,
              count them, then probe the *store* API (with the browser-exposed
              publishable key) to determine which traces a real customer can see.
              Writes docs/reports/leka-project-wisdom-exposure.json.

  --dry-run   Compute the scrub plan (metadata strip + exw sanitize + image
              re-host) and print counts + samples. No writes. DEFAULT.

  --write     Apply the scrub. Idempotent and resumable.

What gets scrubbed (avoidable leaks):
  * product.metadata.source_brand_internal            -> removed
  * product.metadata.legacy_handle                    -> removed
  * product.metadata.outdoor_play.wisdom_item_code    -> removed (keeps the rest
                                                         of the outdoor_play blob)
  * product.metadata.wisdom_item_code (top-level)     -> removed
  * product.metadata.source == "wisdom-outdoor-play-merged"
                                                      -> "outdoor-play-merged"
  * variant.metadata.exw_source "(Wisdom/TUMACO ...)" -> vendor name stripped,
                                                         PI ref + "EXW Shanghai"
                                                         kept
  * images/thumbnail .../<sub>/<code>_wisdom_2025_pNN_<hash>.jpeg
                                                      -> re-hosted to a neutral
                                                         object name (no "wisdom"
                                                         token) under
                                                         leka-project/catalog2025/
                                                         and the product repointed

What is intentionally KEPT (do NOT change):
  * variant.metadata.legacy_sku  — used by pricing/image tooling
  * brand handle "wisdom"        — wired into storefront ?filters[brand][handle]
  * geography tokens (_usa_2025_, _intl_2025_, _china_2025_, catalog_source)
    — these do not name the vendor

Old GCS objects are NOT deleted in this run (a later cleanup can sweep them);
we just stop referencing them.

Auth:
  Admin  — env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD
           (load from Secret Manager: medusa-admin-email / medusa-admin-password)
  Store  — env LEKA_PROJECT_PUBLISHABLE_KEY (browser-exposed publishable key;
           --verify only)
  GCS    — ADC or GOOGLE_APPLICATION_CREDENTIALS / --sa-key (--write images only)

Usage:
  python scripts/scrub_leka_project_wisdom_traces.py --verify
  python scripts/scrub_leka_project_wisdom_traces.py --dry-run
  python scripts/scrub_leka_project_wisdom_traces.py --write
  python scripts/scrub_leka_project_wisdom_traces.py --write --metadata-only
  python scripts/scrub_leka_project_wisdom_traces.py --write --images-only --max-images 1500
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import string
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("scrub_leka_project")

BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"  # the "Leka Project" sales channel
TIMEOUT = 90

# Image proxy / GCS
PROXY_ROOT = "https://catalogs.leka.studio/api/i/leka-project/"
GCS_BUCKET = "ai-agents-go-vendors"
GCS_BRAND_PREFIX = "leka-project/"
NEUTRAL_SUBDIR = "catalog2025/"  # neutral landing folder for re-hosted images
WISDOM_IMG_TOKEN = "_wisdom_2025_"
NEUTRAL_IMG_TOKEN = "_2025_"

REPORT_PATH = Path("docs/reports/leka-project-wisdom-exposure.json")

# Handle rebrand (the 17 outdoor-play products never rebranded from wisdom-*)
HANDLE_PREFIX = "leka-project"
REDIRECT_MAP_PATH = Path("migration/wisdom-handle-redirects.json")
_ID_ALPHABET = string.ascii_lowercase + string.digits


def _new_handle(seen: set[str]) -> str:
    for _ in range(40):
        h = f"{HANDLE_PREFIX}-{''.join(random.choices(_ID_ALPHABET, k=8))}"
        if h not in seen:
            seen.add(h)
            return h
    raise RuntimeError("Could not allocate a fresh handle in 40 tries.")

# Metadata keys to strip outright from product.metadata
STRIP_PRODUCT_MD_KEYS = ("source_brand_internal", "legacy_handle", "wisdom_item_code")
# value-level sanitisations on product.metadata
MD_SOURCE_OLD = "wisdom-outdoor-play-merged"
MD_SOURCE_NEW = "outdoor-play-merged"

# exw_source vendor tokens to remove (keeps PI ref + "EXW Shanghai ...")
EXW_VENDOR_RE = re.compile(r"\s*Wisdom\s*/\s*TUMACO\s*|\bWisdom\b|\bTUMACO\b", re.I)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _admin_token() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        log.error("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD "
                  "(Secret Manager: medusa-admin-email / medusa-admin-password).")
        sys.exit(2)
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        log.error("Auth response missing token: %s", r.json())
        sys.exit(2)
    return tok


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _retry(method: str, url: str, tok: str, **kw) -> requests.Response:
    delays = [2, 5, 15, 45]
    last_err: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            r = requests.request(method, url, headers=_hdr(tok), timeout=TIMEOUT, **kw)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
            return r
        except (requests.RequestException, requests.HTTPError) as e:
            last_err = e
            if attempt == len(delays):
                break
            time.sleep(delays[attempt] + random.random() * 2)
    raise last_err if last_err else RuntimeError("retry loop fell through")


def _iter_products(tok: str, fields: str, limit_per_page: int = 100):
    offset = 0
    while True:
        r = _retry("GET", f"{BACKEND}/admin/products", tok,
                   params={"sales_channel_id[]": SC_ID, "limit": limit_per_page,
                           "offset": offset, "fields": fields})
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            yield p
        if len(batch) < limit_per_page:
            return
        offset += limit_per_page


# ---------------------------------------------------------------------------
# Pure scrub transforms (no I/O) — easy to reason about + test
# ---------------------------------------------------------------------------
def scrub_product_metadata(md: dict) -> tuple[dict, list[str]]:
    """Return (delta, changes) where `delta` is a Medusa-merge payload.

    Medusa v2's `POST /admin/products/:id` metadata update is a SHALLOW MERGE,
    not a replace: omitting a key keeps it, and `null` is ignored. The only way
    to delete a key over the HTTP admin API is to send it with value "" (empty
    string acts as the delete sentinel). So we emit a minimal delta:
      * keys to delete -> ""
      * `source` value rewrite -> new value
      * `outdoor_play` -> the full nested object minus wisdom_item_code (sending
        the object replaces that top-level key under the shallow merge)
    Idempotent: returns an empty delta once a product is already clean.
    """
    md = md or {}
    delta: dict = {}
    changes: list[str] = []
    for k in STRIP_PRODUCT_MD_KEYS:
        if md.get(k) not in (None, ""):
            delta[k] = ""  # empty-string sentinel deletes the key (Medusa v2 merge)
            changes.append(f"-{k}")
    if md.get("source") == MD_SOURCE_OLD:
        delta["source"] = MD_SOURCE_NEW
        changes.append("source~")
    op = md.get("outdoor_play")
    if isinstance(op, dict) and "wisdom_item_code" in op:
        delta["outdoor_play"] = {k: v for k, v in op.items() if k != "wisdom_item_code"}
        changes.append("-outdoor_play.wisdom_item_code")
    return delta, changes


def scrub_exw(vmd: dict) -> tuple[dict, bool]:
    """Strip the vendor name from variant.metadata.exw_source. Keeps legacy_sku."""
    exw = (vmd or {}).get("exw_source")
    if not isinstance(exw, str) or not EXW_VENDOR_RE.search(exw):
        return vmd, False
    cleaned = EXW_VENDOR_RE.sub("", exw)
    # tidy: "PI 2026031801 ( EXW Shanghai, ...)" -> "PI 2026031801 (EXW Shanghai, ...)"
    cleaned = re.sub(r"\(\s+", "(", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    new = dict(vmd)
    new["exw_source"] = cleaned
    return new, True


def neutral_image(url: str) -> tuple[str, str, str] | None:
    """For a `_wisdom_2025_` proxy URL, return (src_key, dst_key, new_url).

    src_key / dst_key are object keys inside the GCS bucket. Returns None if the
    URL does not carry the wisdom token or is not a leka-project proxy URL.
    """
    if not url or WISDOM_IMG_TOKEN not in url or PROXY_ROOT not in url:
        return None
    path = url.split(PROXY_ROOT, 1)[1]          # e.g. spatial_v2/63-..._wisdom_2025_p58_x.jpeg
    src_key = GCS_BRAND_PREFIX + path           # leka-project/spatial_v2/...
    flat = path.replace("/", "_").replace(WISDOM_IMG_TOKEN, NEUTRAL_IMG_TOKEN)
    dst_rel = NEUTRAL_SUBDIR + flat             # catalog2025/spatial_v2_63-..._2025_p58_x.jpeg
    dst_key = GCS_BRAND_PREFIX + dst_rel
    new_url = PROXY_ROOT + dst_rel
    return src_key, dst_key, new_url


# ---------------------------------------------------------------------------
# VERIFY
# ---------------------------------------------------------------------------
def run_verify(tok: str) -> dict:
    log.info("VERIFY: scanning brand via Admin API ...")
    counts = {k: 0 for k in (
        "total", "source_brand_internal", "legacy_handle",
        "outdoor_play.wisdom_item_code", "md_source_wisdom", "md_wisdom_item_code",
        "exw_source_vendor", "wisdom_image_products", "wisdom_image_objects",
        "wisdom_handle_products",
    )}
    objs: set[str] = set()
    samples = {"source_brand_internal": None, "legacy_handle": None,
               "outdoor_play.wisdom_item_code": None, "exw_source": None,
               "wisdom_image": None, "wisdom_handle": None}
    for p in _iter_products(tok, "id,handle,status,thumbnail,metadata,images.url,variants.metadata"):
        counts["total"] += 1
        h = p.get("handle", "")
        md = p.get("metadata") or {}
        if h.startswith("wisdom-"):
            counts["wisdom_handle_products"] += 1
            samples["wisdom_handle"] = samples["wisdom_handle"] or {"handle": h, "status": p.get("status")}
        if md.get("source_brand_internal"):
            counts["source_brand_internal"] += 1
            samples["source_brand_internal"] = samples["source_brand_internal"] or h
        if md.get("legacy_handle"):
            counts["legacy_handle"] += 1
            samples["legacy_handle"] = samples["legacy_handle"] or {"handle": h, "legacy_handle": md["legacy_handle"]}
        if md.get("wisdom_item_code"):
            counts["md_wisdom_item_code"] += 1
        if md.get("source") == MD_SOURCE_OLD:
            counts["md_source_wisdom"] += 1
        op = md.get("outdoor_play")
        if isinstance(op, dict) and op.get("wisdom_item_code"):
            counts["outdoor_play.wisdom_item_code"] += 1
            samples["outdoor_play.wisdom_item_code"] = samples["outdoor_play.wisdom_item_code"] or {"handle": h, "code": op["wisdom_item_code"]}
        for v in (p.get("variants") or []):
            exw = (v.get("metadata") or {}).get("exw_source")
            if isinstance(exw, str) and EXW_VENDOR_RE.search(exw):
                counts["exw_source_vendor"] += 1
                samples["exw_source"] = samples["exw_source"] or {"handle": h, "exw_source": exw}
                break
        urls = [i.get("url") for i in (p.get("images") or [])] + [p.get("thumbnail")]
        w = [u for u in urls if u and WISDOM_IMG_TOKEN in u]
        if w:
            counts["wisdom_image_products"] += 1
            for u in w:
                objs.add(u)
            samples["wisdom_image"] = samples["wisdom_image"] or {"handle": h, "url": w[0]}
        if counts["total"] % 1000 == 0:
            log.info("  ...%d scanned", counts["total"])
    counts["wisdom_image_objects"] = len(objs)

    # Store-API probe — what does an unauthenticated customer actually see?
    pk = os.environ.get("LEKA_PROJECT_PUBLISHABLE_KEY")
    exposure = {}
    if not pk:
        log.warning("LEKA_PROJECT_PUBLISHABLE_KEY not set — skipping store-API probe.")
        exposure = {"_skipped": "LEKA_PROJECT_PUBLISHABLE_KEY not set"}
    else:
        sh = {"x-publishable-api-key": pk}

        def store(handle, fields=None):
            params = {"handle": handle, "limit": 1}
            if fields:
                params["fields"] = fields
            r = requests.get(f"{BACKEND}/store/products", headers=sh, params=params, timeout=TIMEOUT)
            ps = r.json().get("products", []) if r.status_code == 200 else []
            return r.status_code, (ps[0] if ps else None)

        # exw_source — default fields
        if samples["exw_source"]:
            sc, pr = store(samples["exw_source"]["handle"])
            vmd = ((pr.get("variants") or [{}])[0].get("metadata") if pr else None) or {}
            exposure["variant.metadata.exw_source"] = {
                "default_query": bool(vmd.get("exw_source") and EXW_VENDOR_RE.search(str(vmd.get("exw_source")))),
                "value_seen": vmd.get("exw_source"),
                "note": "variant metadata is returned by the store API with NO special fields param",
            }
        # image url — default fields
        if samples["wisdom_image"]:
            sc, pr = store(samples["wisdom_image"]["handle"])
            urls = ([pr.get("thumbnail")] + [i.get("url") for i in (pr.get("images") or [])]) if pr else []
            exposure["image_urls"] = {
                "default_query": any(u and WISDOM_IMG_TOKEN in u for u in urls),
                "value_seen": next((u for u in urls if u and WISDOM_IMG_TOKEN in u), None),
                "note": "image URLs (incl. the _wisdom_2025_ filename) appear in <img src> with NO special fields",
            }
        # product.metadata — default vs +metadata
        if samples["source_brand_internal"]:
            sc0, pr0 = store(samples["source_brand_internal"])
            sc1, pr1 = store(samples["source_brand_internal"], "+metadata")
            exposure["product.metadata"] = {
                "default_query": bool(pr0 and pr0.get("metadata")),
                "with_fields_plus_metadata": bool(pr1 and pr1.get("metadata") and pr1["metadata"].get("source_brand_internal")),
                "note": "hidden by default, but the publishable key is browser-exposed so "
                        "anyone can append ?fields=+metadata and read source_brand_internal / "
                        "legacy_handle / outdoor_play.wisdom_item_code",
            }
        # wisdom- handle — is the product published on the store?
        if samples["wisdom_handle"]:
            sc, pr = store(samples["wisdom_handle"]["handle"], "+metadata")
            exposure["product_handle"] = {
                "default_query": bool(pr),
                "value_seen": samples["wisdom_handle"]["handle"],
                "note": "the literal 'wisdom-...' handle is the product URL slug — fully public",
            }

    report = {"backend": BACKEND, "sales_channel": SC_ID, "counts": counts,
              "samples": samples, "store_exposure": exposure}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("VERIFY report -> %s", REPORT_PATH)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


# ---------------------------------------------------------------------------
# SCRUB (dry-run / write)
# ---------------------------------------------------------------------------
def run_scrub(tok: str, write: bool, do_meta: bool, do_images: bool,
              rebrand_handles: bool, limit: int | None, max_images: int) -> dict:
    mode = "WRITE" if write else "DRY-RUN"
    log.info("SCRUB (%s): metadata=%s images=%s rebrand_handles=%s max_images=%s",
             mode, do_meta, do_images, rebrand_handles, max_images or "all")

    gcs_bucket = None
    if do_images and write:
        from google.cloud import storage
        gcs_bucket = storage.Client(project="ai-agents-go").bucket(GCS_BUCKET)

    # Load (and later extend) the handle redirect map so storefront redirects survive.
    redirect_map: dict[str, str] = {}
    seen_handles: set[str] = set()
    if REDIRECT_MAP_PATH.exists():
        try:
            redirect_map = json.loads(REDIRECT_MAP_PATH.read_text(encoding="utf-8"))
            seen_handles.update(redirect_map.values())
        except Exception as e:
            log.warning("Could not parse %s: %s", REDIRECT_MAP_PATH, e)

    c = {"products": 0, "md_updated": 0, "exw_updated": 0, "handles_rebranded": 0,
         "img_products_updated": 0, "objects_copied": 0, "objects_existing": 0,
         "objects_missing": 0, "img_products_deferred": 0, "errors": 0}
    copied: set[str] = set()
    samples: list[dict] = []
    img_budget_hit = False

    fields = "id,handle,metadata,thumbnail,images.url,variants.id,variants.metadata"
    for p in _iter_products(tok, fields):
        c["products"] += 1
        pid = p["id"]
        h = p.get("handle", "")
        md = p.get("metadata") or {}

        # ---- metadata (+ optional handle rebrand for leftover wisdom-* slugs) ----
        if do_meta:
            md_delta, changes = scrub_product_metadata(md)
            payload: dict = {}
            new_handle = None
            if rebrand_handles and h.startswith("wisdom-"):
                new_handle = redirect_map.get(h) or _new_handle(seen_handles)
                payload["handle"] = new_handle
                redirect_map[h] = new_handle
                changes = changes + [f"handle:{h}->{new_handle}"]
            if changes:
                if md_delta:
                    payload["metadata"] = md_delta
                if len(samples) < 8:
                    samples.append({"handle": h, "md_changes": changes})
                if write and payload:
                    try:
                        _retry("POST", f"{BACKEND}/admin/products/{pid}", tok,
                               json=payload).raise_for_status()
                        c["md_updated"] += 1
                        if new_handle:
                            c["handles_rebranded"] += 1
                    except Exception as e:
                        c["errors"] += 1
                        redirect_map.pop(h, None)
                        log.error("  md %s: %s", h, str(e)[:160])
                else:
                    c["md_updated"] += 1
                    if new_handle:
                        c["handles_rebranded"] += 1

            # ---- exw_source on variants ----
            for v in (p.get("variants") or []):
                vmd = v.get("metadata") or {}
                new_vmd, ch = scrub_exw(vmd)
                if ch:
                    if write:
                        try:
                            _retry("POST", f"{BACKEND}/admin/products/{pid}/variants/{v['id']}",
                                   tok, json={"metadata": new_vmd}).raise_for_status()
                            c["exw_updated"] += 1
                        except Exception as e:
                            c["errors"] += 1
                            log.error("  exw %s: %s", h, str(e)[:160])
                    else:
                        c["exw_updated"] += 1

        # ---- images ----
        if do_images:
            urls = [i.get("url") for i in (p.get("images") or [])]
            thumb = p.get("thumbnail")
            needs = [u for u in (urls + [thumb]) if u and WISDOM_IMG_TOKEN in u]
            if needs:
                if max_images and (c["objects_copied"] + c["objects_existing"]) >= max_images:
                    c["img_products_deferred"] += 1
                    img_budget_hit = True
                    continue

                url_map: dict[str, str] = {}
                for u in set(needs):
                    nm = neutral_image(u)
                    if not nm:
                        continue
                    src_key, dst_key, new_url = nm
                    url_map[u] = new_url
                    if write:
                        if dst_key in copied:
                            continue
                        try:
                            dst_blob = gcs_bucket.blob(dst_key)
                            if dst_blob.exists():
                                c["objects_existing"] += 1
                                copied.add(dst_key)
                                continue
                            src_blob = gcs_bucket.blob(src_key)
                            if not src_blob.exists():
                                c["objects_missing"] += 1
                                url_map.pop(u, None)  # keep original; cannot repoint
                                continue
                            gcs_bucket.copy_blob(src_blob, gcs_bucket, dst_key)
                            c["objects_copied"] += 1
                            copied.add(dst_key)
                        except Exception as e:
                            c["errors"] += 1
                            url_map.pop(u, None)
                            log.error("  gcs copy %s: %s", src_key, str(e)[:160])
                    else:
                        if dst_key not in copied:
                            c["objects_copied"] += 1
                            copied.add(dst_key)

                new_images = [{"url": url_map.get(u, u)} for u in urls]
                new_thumb = url_map.get(thumb, thumb)
                changed = (new_thumb != thumb) or any(
                    url_map.get(u, u) != u for u in urls)
                if changed:
                    if len(samples) < 12:
                        samples.append({"handle": h, "img_example": new_thumb})
                    if write:
                        try:
                            _retry("POST", f"{BACKEND}/admin/products/{pid}", tok,
                                   json={"images": new_images, "thumbnail": new_thumb}).raise_for_status()
                            c["img_products_updated"] += 1
                        except Exception as e:
                            c["errors"] += 1
                            log.error("  img %s: %s", h, str(e)[:160])
                    else:
                        c["img_products_updated"] += 1

        if limit and c["products"] >= limit:
            log.info("  --limit=%d reached.", limit)
            break
        if c["products"] % 500 == 0:
            log.info("  ...%d products — %s", c["products"], c)

    # Persist the extended redirect map so the storefront keeps redirecting old slugs.
    if rebrand_handles and c["handles_rebranded"] and write:
        REDIRECT_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        REDIRECT_MAP_PATH.write_text(json.dumps(redirect_map, indent=2), encoding="utf-8")
        log.info("Redirect map: %d entries -> %s", len(redirect_map), REDIRECT_MAP_PATH)

    if img_budget_hit:
        log.warning("Image budget (--max-images=%d) hit: %d products deferred. "
                    "Re-run --write --images-only to continue.", max_images, c["img_products_deferred"])
    log.info("SCRUB (%s) done: %s", mode, json.dumps(c))
    if samples:
        log.info("Sample changes: %s", json.dumps(samples, ensure_ascii=False))
    if not write:
        print("\n[dry-run] no changes written. Re-run with --write to apply.")
    return c


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--verify", action="store_true", help="Read-only exposure audit.")
    g.add_argument("--dry-run", action="store_true", help="Scrub plan, no writes (default).")
    g.add_argument("--write", action="store_true", help="Apply the scrub.")
    ap.add_argument("--metadata-only", action="store_true")
    ap.add_argument("--images-only", action="store_true")
    ap.add_argument("--rebrand-handles", action="store_true",
                    help="Also rename leftover 'wisdom-*' product handles to leka-project-<id> "
                         "and append old->new to migration/wisdom-handle-redirects.json.")
    ap.add_argument("--limit", type=int, default=None, help="Cap products processed (smoke test).")
    ap.add_argument("--max-images", type=int, default=0,
                    help="Cap distinct image OBJECTS re-hosted this run (0 = no cap). Defers whole products past the cap.")
    ap.add_argument("--sa-key", default=None, help="Path to a GCP SA key json (else ADC).")
    args = ap.parse_args()

    if args.sa_key and Path(args.sa_key).exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.sa_key
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

    do_meta = not args.images_only
    do_images = not args.metadata_only

    tok = _admin_token()
    log.info("Authenticated against %s", BACKEND)

    if args.verify:
        run_verify(tok)
        return 0

    run_scrub(tok, write=args.write, do_meta=do_meta, do_images=do_images,
              rebrand_handles=args.rebrand_handles and do_meta,
              limit=args.limit, max_images=args.max_images)
    return 0


if __name__ == "__main__":
    sys.exit(main())
