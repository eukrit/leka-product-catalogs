"""Rebrand the Wisdom sales channel and products to 'Leka Project' in Medusa.

Idempotent and resumable. Each product's old handle and SKU are preserved
in metadata.legacy_handle / variant.metadata.legacy_sku so the change can be
rolled back, and downstream tooling (PO lookups, accounting cross-refs) can
still find products by their Wisdom item code.

Phases:
  --rename-only   Phase A1: rename Sales Channel + publishable API key title.
  --products-only Phase A2 + A3: regenerate handles + SKUs across all
                  products in the Wisdom sales channel; emit redirect map.
  (default)       Do A1 then A2+A3 in one chained pass.

Safety:
  --dry-run       Print the first 5 product diffs + counts, do not write.
  --limit N       Cap product updates (smoke testing).
  --revert        Read metadata.legacy_handle / legacy_sku and restore them.

Auth: env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD (same as
sync_vendors_to_medusa.py). Backend URL default matches the live Cloud Run
service.

Usage:
    python scripts/rebrand_wisdom_to_leka_project.py --dry-run
    python scripts/rebrand_wisdom_to_leka_project.py --rename-only
    python scripts/rebrand_wisdom_to_leka_project.py --limit=10
    python scripts/rebrand_wisdom_to_leka_project.py
    python scripts/rebrand_wisdom_to_leka_project.py --revert
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
log = logging.getLogger("rebrand_wisdom")

BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
TIMEOUT = 60
WISDOM_SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
NEW_SC_NAME = "Leka Project"
NEW_SC_DESCRIPTION = "Leka Project — house collection."
OLD_KEY_TITLE = "Wisdom Storefront"
NEW_KEY_TITLE = "Leka Project Storefront"

HANDLE_PREFIX = "leka-project"
SKU_PREFIX = "LP"
ID_ALPHABET = string.ascii_lowercase + string.digits  # nanoid-like

# Regex helpers — kill "Wisdom" / "WISDOM" / "Wisdom Toys" from titles+descriptions.
WISDOM_RE = re.compile(r"\b(WISDOM(?:\s+TOYS)?|Wisdom(?:\s+Toys)?|wisdom(?:\s+toys)?)\b")

REDIRECT_MAP_PATH = Path("migration") / "wisdom-handle-redirects.json"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _auth() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        log.error("Set LEKA_MEDUSA_ADMIN_EMAIL and LEKA_MEDUSA_ADMIN_PASSWORD.")
        sys.exit(2)
    r = requests.post(
        f"{BACKEND}/auth/user/emailpass",
        json={"email": email, "password": pw},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        log.error("Auth response missing token: %s", r.json())
        sys.exit(2)
    return tok


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _new_id(length: int = 8) -> str:
    return "".join(random.choices(ID_ALPHABET, k=length))


def _new_handle(seen: set) -> str:
    for _ in range(20):
        h = f"{HANDLE_PREFIX}-{_new_id(8)}"
        if h not in seen:
            seen.add(h)
            return h
    raise RuntimeError("Could not allocate a fresh handle in 20 tries.")


def _new_sku(seen: set) -> str:
    for _ in range(20):
        s = f"{SKU_PREFIX}-{_new_id(8).upper()}"
        if s not in seen:
            seen.add(s)
            return s
    raise RuntimeError("Could not allocate a fresh SKU.")


def _strip_wisdom(text: str | None) -> str:
    if not text:
        return text or ""
    # Replace standalone occurrences. Collapse double spaces left behind.
    out = WISDOM_RE.sub("", text)
    out = re.sub(r"\s{2,}", " ", out).strip(" -:,;")
    return out


def _request_with_retry(method: str, url: str, token: str, **kw) -> requests.Response:
    delays = [2, 5, 10, 30, 60]
    last_err: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            r = requests.request(method, url, headers=_headers(token), timeout=TIMEOUT, **kw)
            if r.status_code == 401:
                # JWT expired mid-run.
                raise PermissionError("401 from Medusa; re-auth")
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
            return r
        except (requests.RequestException, requests.HTTPError) as e:
            last_err = e
            if attempt == len(delays):
                break
            sleep_for = delays[attempt] + random.random() * 2
            log.warning("retry %d for %s %s after %.1fs: %s", attempt + 1, method, url, sleep_for, str(e)[:80])
            time.sleep(sleep_for)
    if last_err:
        raise last_err
    raise RuntimeError("retry loop fell through")


# ---------------------------------------------------------------------------
# Phase A1 — rename Sales Channel + publishable API key title
# ---------------------------------------------------------------------------
def phase_rename(token: str, dry_run: bool) -> None:
    log.info("Phase A1: rename Sales Channel %s -> %r", WISDOM_SC_ID, NEW_SC_NAME)
    r = _request_with_retry("GET", f"{BACKEND}/admin/sales-channels/{WISDOM_SC_ID}", token)
    sc = r.json().get("sales_channel", {})
    log.info("  current: name=%r description=%r", sc.get("name"), sc.get("description"))
    if sc.get("name") == NEW_SC_NAME:
        log.info("  sales channel already renamed; skipping.")
    elif dry_run:
        log.info("  [dry-run] would POST name=%r description=%r", NEW_SC_NAME, NEW_SC_DESCRIPTION)
    else:
        r = _request_with_retry(
            "POST", f"{BACKEND}/admin/sales-channels/{WISDOM_SC_ID}", token,
            json={"name": NEW_SC_NAME, "description": NEW_SC_DESCRIPTION},
        )
        r.raise_for_status()
        log.info("  sales channel renamed.")

    log.info("Phase A1: rename publishable API key %r -> %r", OLD_KEY_TITLE, NEW_KEY_TITLE)
    r = _request_with_retry(
        "GET", f"{BACKEND}/admin/api-keys", token,
        params={"type": "publishable", "limit": 200},
    )
    keys = r.json().get("api_keys", [])
    target = next((k for k in keys if k.get("title") in (OLD_KEY_TITLE, NEW_KEY_TITLE)), None)
    if not target:
        log.warning("  no publishable API key titled %r or %r found; skipping.", OLD_KEY_TITLE, NEW_KEY_TITLE)
        return
    if target.get("title") == NEW_KEY_TITLE:
        log.info("  publishable key already renamed (id=%s); skipping.", target.get("id"))
        return
    log.info("  current key id=%s title=%r", target.get("id"), target.get("title"))
    if dry_run:
        log.info("  [dry-run] would POST title=%r", NEW_KEY_TITLE)
    else:
        r = _request_with_retry(
            "POST", f"{BACKEND}/admin/api-keys/{target['id']}", token,
            json={"title": NEW_KEY_TITLE},
        )
        r.raise_for_status()
        log.info("  publishable key title updated.")


# ---------------------------------------------------------------------------
# Phase A2 + A3 — regenerate handles + SKUs, emit redirect map
# ---------------------------------------------------------------------------
def _iter_products(token: str, sc_id: str, limit_per_page: int = 100):
    offset = 0
    while True:
        r = _request_with_retry(
            "GET", f"{BACKEND}/admin/products", token,
            params={"sales_channel_id[]": sc_id, "limit": limit_per_page, "offset": offset, "fields": "+variants.metadata"},
        )
        page = r.json()
        batch = page.get("products", [])
        if not batch:
            return
        for p in batch:
            yield p
        if len(batch) < limit_per_page:
            return
        offset += limit_per_page


def phase_products(token: str, dry_run: bool, limit: int | None) -> dict:
    log.info("Phase A2/A3: regenerate handles + SKUs in SC %s", WISDOM_SC_ID)
    seen_handles: set[str] = set()
    seen_skus: set[str] = set()
    redirect_map: dict[str, str] = {}
    if REDIRECT_MAP_PATH.exists():
        try:
            redirect_map = json.loads(REDIRECT_MAP_PATH.read_text())
            for new in redirect_map.values():
                seen_handles.add(new)
            log.info("  resumed: %d existing handle redirects loaded.", len(redirect_map))
        except Exception as e:
            log.warning("  could not parse existing redirect map: %s", e)

    counts = {"processed": 0, "skipped_already_done": 0, "skipped_not_wisdom": 0,
              "title_cleaned": 0, "desc_cleaned": 0, "errors": 0}
    diffs_sample = []
    started = time.time()

    for prod in _iter_products(token, WISDOM_SC_ID):
        counts["processed"] += 1
        pid = prod["id"]
        old_handle = prod.get("handle", "")
        old_title = prod.get("title", "") or ""
        old_desc = prod.get("description", "") or ""
        old_md = dict(prod.get("metadata") or {})

        # Idempotency
        if old_md.get("legacy_handle"):
            counts["skipped_already_done"] += 1
            continue
        if not old_handle.startswith("wisdom-") and "wisdom" not in old_handle.lower():
            # not a Wisdom product (paranoia: SC filter should already guarantee this)
            counts["skipped_not_wisdom"] += 1
            continue

        new_handle = _new_handle(seen_handles)
        new_title = _strip_wisdom(old_title)
        new_desc = _strip_wisdom(old_desc)
        title_changed = new_title != old_title
        desc_changed = new_desc != old_desc

        variants = prod.get("variants", []) or []
        variant_updates = []
        for v in variants:
            vid = v["id"]
            old_sku = v.get("sku", "") or ""
            vmd = dict(v.get("metadata") or {})
            if vmd.get("legacy_sku"):
                continue
            new_sku = _new_sku(seen_skus)
            vmd["legacy_sku"] = old_sku
            variant_updates.append((vid, old_sku, new_sku, vmd))

        new_md = dict(old_md)
        new_md["legacy_handle"] = old_handle
        new_md.setdefault("source_brand_internal", "wisdom")
        # Drop Wisdom-specific source pointer from customer-visible metadata
        new_md.pop("catalog_source", None)

        if dry_run:
            if len(diffs_sample) < 5:
                diffs_sample.append({
                    "pid": pid,
                    "handle": [old_handle, new_handle],
                    "title": [old_title[:60], new_title[:60]],
                    "title_changed": title_changed,
                    "desc_changed": desc_changed,
                    "variant_sku_changes": [(vid, oldsku, newsku) for vid, oldsku, newsku, _ in variant_updates],
                })
            redirect_map[old_handle] = new_handle
            if title_changed: counts["title_cleaned"] += 1
            if desc_changed: counts["desc_cleaned"] += 1
        else:
            # Update product
            payload: dict = {"handle": new_handle, "metadata": new_md}
            if title_changed: payload["title"] = new_title
            if desc_changed: payload["description"] = new_desc
            try:
                r = _request_with_retry("POST", f"{BACKEND}/admin/products/{pid}", token, json=payload)
                r.raise_for_status()
            except Exception as e:
                log.error("  product %s update failed: %s", pid, str(e)[:200])
                counts["errors"] += 1
                continue

            # Update each variant SKU
            for vid, oldsku, newsku, vmd in variant_updates:
                try:
                    r = _request_with_retry(
                        "POST", f"{BACKEND}/admin/products/{pid}/variants/{vid}", token,
                        json={"sku": newsku, "metadata": vmd},
                    )
                    r.raise_for_status()
                except Exception as e:
                    log.error("  variant %s update failed: %s", vid, str(e)[:200])
                    counts["errors"] += 1

            redirect_map[old_handle] = new_handle
            if title_changed: counts["title_cleaned"] += 1
            if desc_changed: counts["desc_cleaned"] += 1

            # Persist redirect map every 100 successful updates so a crash doesn't lose it
            if counts["processed"] % 100 == 0:
                REDIRECT_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
                REDIRECT_MAP_PATH.write_text(json.dumps(redirect_map, indent=2))

        if counts["processed"] % 100 == 0:
            rate = counts["processed"] / max(time.time() - started, 0.001)
            log.info("  %d processed (%.1f/s) — %s", counts["processed"], rate, counts)

        if limit and counts["processed"] >= limit:
            log.info("  --limit=%d reached, stopping.", limit)
            break

    # Final redirect-map write
    REDIRECT_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    REDIRECT_MAP_PATH.write_text(json.dumps(redirect_map, indent=2))
    log.info("Redirect map: %d entries -> %s", len(redirect_map), REDIRECT_MAP_PATH)

    if dry_run:
        log.info("DRY-RUN sample diffs:")
        for d in diffs_sample:
            log.info("  %s", json.dumps(d, ensure_ascii=False))

    elapsed = time.time() - started
    log.info("Phase A2/A3 complete in %.1fs: %s", elapsed, counts)
    return counts


# ---------------------------------------------------------------------------
# --revert
# ---------------------------------------------------------------------------
def phase_revert(token: str, dry_run: bool, limit: int | None) -> dict:
    log.info("REVERT: restoring metadata.legacy_handle / legacy_sku on Wisdom SC products")
    counts = {"processed": 0, "reverted": 0, "skipped_no_legacy": 0, "errors": 0}
    started = time.time()
    for prod in _iter_products(token, WISDOM_SC_ID):
        counts["processed"] += 1
        md = dict(prod.get("metadata") or {})
        old_handle = md.get("legacy_handle")
        if not old_handle:
            counts["skipped_no_legacy"] += 1
            continue
        pid = prod["id"]
        new_md = {k: v for k, v in md.items() if k not in ("legacy_handle", "source_brand_internal")}
        if dry_run:
            log.info("  [dry-run] would revert %s -> handle=%s", pid, old_handle)
        else:
            try:
                _request_with_retry("POST", f"{BACKEND}/admin/products/{pid}", token,
                                    json={"handle": old_handle, "metadata": new_md}).raise_for_status()
            except Exception as e:
                log.error("  product %s revert failed: %s", pid, str(e)[:200])
                counts["errors"] += 1
                continue
            # Revert SKUs
            for v in prod.get("variants") or []:
                vmd = dict(v.get("metadata") or {})
                old_sku = vmd.get("legacy_sku")
                if not old_sku: continue
                vmd2 = {k: vv for k, vv in vmd.items() if k != "legacy_sku"}
                try:
                    _request_with_retry("POST", f"{BACKEND}/admin/products/{pid}/variants/{v['id']}", token,
                                        json={"sku": old_sku, "metadata": vmd2}).raise_for_status()
                except Exception as e:
                    log.error("  variant revert failed: %s", str(e)[:200])
                    counts["errors"] += 1
        counts["reverted"] += 1
        if limit and counts["reverted"] >= limit:
            break
    log.info("REVERT done in %.1fs: %s", time.time() - started, counts)
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rename-only", action="store_true", help="Only Phase A1 (SC + key title).")
    p.add_argument("--products-only", action="store_true", help="Only Phase A2/A3 (handles + SKUs + redirect map).")
    p.add_argument("--revert", action="store_true", help="Restore legacy handles/SKUs.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--seed", type=int, default=None, help="Seed RNG for reproducible handles/SKUs (testing).")
    args = p.parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    return args


def main() -> None:
    args = parse_args()
    token = _auth()
    log.info("Authenticated against %s", BACKEND)

    if args.revert:
        phase_revert(token, args.dry_run, args.limit)
        return

    if args.rename_only:
        phase_rename(token, args.dry_run)
        return

    if args.products_only:
        phase_products(token, args.dry_run, args.limit)
        return

    # Default: full pass
    phase_rename(token, args.dry_run)
    phase_products(token, args.dry_run, args.limit)


if __name__ == "__main__":
    main()
