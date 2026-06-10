"""Hide `leka-project` ("Leka Project" brand) products that have no real photo
or only a low-resolution image.

Background
----------
The Wisdom → Leka Project rebrand left thousands of products without real
vendor photos. `scripts/backfill_leka_project_images.py` (v2.34.0) attached a
Leka-branded *"Image coming soon"* placeholder to every blank product
(`metadata.image_status == "placeholder"`) and real photos to the rest
(`metadata.image_status == "backfilled"`). Some of the real photos that did
get attached are tiny (e.g. 100 px PDF embeds — see CHANGELOG note "PDF embeds
are 100px"), which look broken on the storefront product cards.

This script *hides* the products that still have no usable photo so the
storefront only shows products with a proper image. "Hide" means flipping the
Medusa product `status` from `published` to `draft`: the storefront
(`eukrit/leka-website` → `catalogs.leka.studio`) reads the Store API, which
only returns **published** products, so a draft product silently drops off the
catalog with no storefront code change required.

A product is hidden when EITHER:

  * **no_image**       — `metadata.image_status == "placeholder"`, or the
                         product has no `images[]` and no `thumbnail` at all.
  * **low_resolution** — its representative image's longest edge is smaller
                         than `--min-dimension` (default 400 px). Measured by
                         downloading the thumbnail (or first image) through the
                         public proxy and reading the dimensions with Pillow.

Every change is idempotent, reversible, and tagged on the product metadata:

    metadata.hidden_by      = "image-quality-filter"
    metadata.hidden_reason  = "no_image" | "low_resolution"
    metadata.hidden_at      = ISO-8601 UTC
    metadata.hidden_dims    = "<w>x<h>"   (low_resolution only)

`--restore` re-publishes only the products this script hid (matched on
`metadata.hidden_by == "image-quality-filter"`) and clears those keys, so a
bad threshold is a one-command undo.

Phases (pick exactly one)
-------------------------
  --hide       Flag + set matching products to `status="draft"`. Add
               `--dry-run` to print the plan without writing.
  --restore    Re-publish every product previously hidden by this script.
  --audit      Read-only: report how many SC products are published / draft /
               no-image / low-res at the current threshold (no writes).

Auth: ADC for nothing here (no GCP needed — image bytes come through the public
proxy). Medusa admin creds come from Secret Manager `leka-medusa-admin-email` /
`leka-medusa-admin-password`, or the env vars `LEKA_MEDUSA_ADMIN_EMAIL` /
`LEKA_MEDUSA_ADMIN_PASSWORD` (mirrors backfill_leka_project_images.py).

Examples:
  python scripts/hide_leka_project_lowres_products.py --audit
  python scripts/hide_leka_project_lowres_products.py --hide --dry-run
  python scripts/hide_leka_project_lowres_products.py --hide --dry-run --limit 50
  python scripts/hide_leka_project_lowres_products.py --hide
  python scripts/hide_leka_project_lowres_products.py --hide --min-dimension 800
  python scripts/hide_leka_project_lowres_products.py --restore
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("hide_leka_project_lowres")

# ---------------------------------------------------------------------------
# Constants

PROJECT = "ai-agents-go"

MEDUSA_BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
# "Leka Project" sales channel (formerly Wisdom) — same id used by
# scripts/backfill_leka_project_images.py.
SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"

# Marker written to product metadata so --restore only touches what we hid.
HIDDEN_BY = "image-quality-filter"

# Default low-resolution cutoff: a product image whose longest edge is under
# this many pixels renders blurry on the storefront cards. Overridable with
# --min-dimension.
DEFAULT_MIN_DIMENSION = 400

# Products to never touch regardless of image state.
SKIP_HANDLES = {"test-swing"}

IMG_CONCURRENCY = 8
TIMEOUT = 60

# ---------------------------------------------------------------------------
# Auth helpers (mirror scripts/backfill_leka_project_images.py)


def _sm_secret(name: str) -> str:
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{PROJECT}/secrets/{name}/versions/latest"
    return client.access_secret_version(name=path).payload.data.decode().strip()


def _medusa_admin_token() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL") or _sm_secret("leka-medusa-admin-email")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD") or _sm_secret("leka-medusa-admin-password")
    r = requests.post(
        f"{MEDUSA_BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        log.error("admin auth returned no token: %s", r.text[:200])
        sys.exit(2)
    log.info("Medusa admin auth OK (%s)", email)
    return tok


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _retry(method: str, url: str, tok: str | None, *, json_body=None, params=None,
           max_attempts: int = 5) -> requests.Response:
    delays = [2, 5, 15, 45]
    last: Exception | None = None
    for attempt in range(max_attempts):
        try:
            headers = _hdr(tok) if tok else None
            r = requests.request(method, url, headers=headers, json=json_body,
                                  params=params, timeout=TIMEOUT)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
            return r
        except (requests.RequestException, requests.HTTPError) as e:
            last = e
            if attempt == len(delays):
                break
            time.sleep(delays[attempt] + random.random() * 2)
    raise last if last else RuntimeError("retry exhausted")


# ---------------------------------------------------------------------------
# Admin enumeration — we use the admin API (not the Store API) so we can also
# see products that are already `draft` (Store API only returns published).


def iter_sc_products(tok: str):
    """Yield every product in the leka-project SC with the fields we need."""
    offset = 0
    fields = "id,handle,title,status,thumbnail,images.url,metadata"
    while True:
        r = _retry(
            "GET", f"{MEDUSA_BACKEND}/admin/products", tok,
            params={
                "limit": 100,
                "offset": offset,
                "sales_channel_id[]": SC_ID,
                "fields": fields,
            },
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        yield from batch
        offset += 100


def representative_image_url(p: dict) -> str | None:
    """Thumbnail if set, else the first images[] url."""
    if p.get("thumbnail"):
        return p["thumbnail"]
    imgs = p.get("images") or []
    if imgs:
        return imgs[0].get("url")
    return None


# ---------------------------------------------------------------------------
# Image dimension probe


def image_dimensions(url: str) -> tuple[int, int] | None:
    """Download the image through the public proxy and return (w, h).

    Returns None on any failure (network / decode) so the caller can decide to
    leave the product alone rather than hide it on a transient error.
    """
    from PIL import Image  # lazy: only needed for the dimension probe

    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        with Image.open(io.BytesIO(r.content)) as im:
            return im.size  # (width, height)
    except Exception as e:  # noqa: BLE001 — any failure → "unknown", skip hiding
        log.debug("dimension probe failed for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Classification


def classify(p: dict, min_dim: int, dims_cache: dict) -> tuple[str | None, str | None]:
    """Return (reason, dims_str). reason is None when the product should stay.

    no_image       — placeholder or genuinely blank.
    low_resolution — real image whose longest edge < min_dim.
    None           — keep (good image, or image whose size could not be read —
                     we never hide on an unreadable/transient probe).
    """
    if p.get("handle") in SKIP_HANDLES:
        return None, None

    meta = p.get("metadata") or {}
    if meta.get("image_status") == "placeholder":
        return "no_image", None

    url = representative_image_url(p)
    if not url:
        return "no_image", None

    size = dims_cache.get(url)
    if size is None:
        return None, None  # could not measure — leave it published
    w, h = size
    if max(w, h) < min_dim:
        return "low_resolution", f"{w}x{h}"
    return None, None


def _prefetch_dimensions(prods: list[dict]) -> dict:
    """Probe dimensions for every product that has a real (non-placeholder)
    image, in parallel. Placeholder/blank products are skipped (no need)."""
    to_probe: dict[str, None] = {}
    for p in prods:
        meta = p.get("metadata") or {}
        if meta.get("image_status") == "placeholder":
            continue
        url = representative_image_url(p)
        if url:
            to_probe.setdefault(url, None)

    log.info("Probing dimensions for %d distinct image URLs...", len(to_probe))
    results: dict[str, tuple[int, int] | None] = {}
    started = time.time()
    with ThreadPoolExecutor(max_workers=IMG_CONCURRENCY) as ex:
        futures = {ex.submit(image_dimensions, u): u for u in to_probe}
        for i, fut in enumerate(as_completed(futures), 1):
            u = futures[fut]
            results[u] = fut.result()
            if i % 200 == 0 or i == len(to_probe):
                rate = i / max(time.time() - started, 0.001)
                log.info("  probed %d/%d (%.1f/s)", i, len(to_probe), rate)
    return results


# ---------------------------------------------------------------------------
# Medusa write


def _update_product(tok: str, pid: str, status: str, metadata: dict) -> None:
    payload = {"status": status, "metadata": metadata}
    r = _retry("POST", f"{MEDUSA_BACKEND}/admin/products/{pid}", tok, json_body=payload)
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Phases


def cmd_hide(args) -> None:
    tok = None if args.dry_run else _medusa_admin_token()
    read_tok = tok or _medusa_admin_token()  # need a token to read the admin API

    log.info("Enumerating leka-project SC products (admin API)...")
    prods = list(iter_sc_products(read_tok))
    log.info("  %d products in SC", len(prods))

    published = [p for p in prods if p.get("status") == "published"]
    log.info("  %d currently published (candidates to hide)", len(published))

    dims_cache = _prefetch_dimensions(published)

    counts = {"no_image": 0, "low_resolution": 0, "kept": 0, "errors": 0}
    examples: dict[str, list[str]] = {"no_image": [], "low_resolution": []}
    started = time.time()
    done = 0
    todo = published if not args.limit else published[: args.limit]

    for p in todo:
        reason, dims = classify(p, args.min_dimension, dims_cache)
        if reason is None:
            counts["kept"] += 1
            continue

        meta = dict(p.get("metadata") or {})
        meta.update({
            "hidden_by": HIDDEN_BY,
            "hidden_reason": reason,
            "hidden_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        if dims:
            meta["hidden_dims"] = dims

        if len(examples[reason]) < 8:
            examples[reason].append(
                f"{p.get('handle')} ({dims})" if dims else str(p.get("handle")))

        if args.dry_run:
            counts[reason] += 1
            continue

        try:
            _update_product(tok, p["id"], "draft", meta)
            counts[reason] += 1
        except Exception as e:  # noqa: BLE001
            log.error("  %s hide failed: %s", p.get("handle"), str(e)[:200])
            counts["errors"] += 1

        done += 1
        if done % 100 == 0:
            rate = done / max(time.time() - started, 0.001)
            log.info("  hidden %d (%.1f/s) %s", done, rate, counts)

    verb = "WOULD hide" if args.dry_run else "hid"
    log.info("Done in %.1fs. %s %d products (%d no_image, %d low_resolution); "
             "kept %d; errors %d.",
             time.time() - started, verb,
             counts["no_image"] + counts["low_resolution"],
             counts["no_image"], counts["low_resolution"],
             counts["kept"], counts["errors"])
    for reason, ex in examples.items():
        if ex:
            log.info("  e.g. %s: %s", reason, ", ".join(ex))
    if args.dry_run:
        log.info("Dry run — no products were changed. Re-run without --dry-run "
                 "to apply.")


def cmd_restore(args) -> None:
    tok = None if args.dry_run else _medusa_admin_token()
    read_tok = tok or _medusa_admin_token()

    log.info("Enumerating leka-project SC products (admin API)...")
    prods = list(iter_sc_products(read_tok))

    targets = [
        p for p in prods
        if (p.get("metadata") or {}).get("hidden_by") == HIDDEN_BY
    ]
    log.info("  %d products were hidden by this script", len(targets))

    counts = {"restored": 0, "errors": 0}
    for p in targets:
        meta = dict(p.get("metadata") or {})
        # Setting keys to None deletes them from Medusa v2 metadata.
        for k in ("hidden_by", "hidden_reason", "hidden_at", "hidden_dims"):
            meta[k] = None

        if args.dry_run:
            counts["restored"] += 1
            continue
        try:
            _update_product(tok, p["id"], "published", meta)
            counts["restored"] += 1
        except Exception as e:  # noqa: BLE001
            log.error("  %s restore failed: %s", p.get("handle"), str(e)[:200])
            counts["errors"] += 1

    verb = "WOULD restore" if args.dry_run else "restored"
    log.info("%s %d products; errors %d.", verb, counts["restored"], counts["errors"])


def cmd_audit(args) -> None:
    tok = _medusa_admin_token()
    log.info("Enumerating leka-project SC products (admin API)...")
    prods = list(iter_sc_products(tok))
    total = len(prods)
    published = [p for p in prods if p.get("status") == "published"]
    draft = [p for p in prods if p.get("status") == "draft"]
    hidden_by_us = [p for p in prods
                    if (p.get("metadata") or {}).get("hidden_by") == HIDDEN_BY]

    dims_cache = _prefetch_dimensions(published)
    no_image = low_res = unknown = good = 0
    for p in published:
        reason, _ = classify(p, args.min_dimension, dims_cache)
        if reason == "no_image":
            no_image += 1
        elif reason == "low_resolution":
            low_res += 1
        else:
            # distinguish "good" from "couldn't measure"
            url = representative_image_url(p)
            meta = p.get("metadata") or {}
            if meta.get("image_status") != "placeholder" and url \
                    and dims_cache.get(url) is None:
                unknown += 1
            else:
                good += 1

    log.info("Audit @ min-dimension=%d px:", args.min_dimension)
    log.info("  total in SC ............ %d", total)
    log.info("  published .............. %d", len(published))
    log.info("  draft (hidden) ......... %d  (of which %d by this script)",
             len(draft), len(hidden_by_us))
    log.info("  --- of the published ---")
    log.info("  would hide: no_image ... %d", no_image)
    log.info("  would hide: low_res .... %d", low_res)
    log.info("  good (keep) ............ %d", good)
    log.info("  unmeasurable (keep) .... %d", unknown)


# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hide", action="store_true",
                    help="Set matching products to draft (hide from storefront).")
    ap.add_argument("--restore", action="store_true",
                    help="Re-publish products previously hidden by this script.")
    ap.add_argument("--audit", action="store_true",
                    help="Read-only report; no writes.")
    ap.add_argument("--dry-run", action="store_true",
                    help="--hide/--restore: print the plan without writing.")
    ap.add_argument("--min-dimension", type=int, default=DEFAULT_MIN_DIMENSION,
                    help=f"Longest-edge px below which an image counts as low "
                         f"resolution (default {DEFAULT_MIN_DIMENSION}).")
    ap.add_argument("--limit", type=int, default=None,
                    help="--hide only: cap how many products to process (smoke test).")
    args = ap.parse_args()

    chosen = sum([args.hide, args.restore, args.audit])
    if chosen == 0:
        ap.print_help()
        sys.exit(2)
    if chosen > 1:
        log.error("Pick one phase at a time (--hide | --restore | --audit).")
        sys.exit(2)

    if args.hide:
        cmd_hide(args)
    elif args.restore:
        cmd_restore(args)
    elif args.audit:
        cmd_audit(args)


if __name__ == "__main__":
    main()
