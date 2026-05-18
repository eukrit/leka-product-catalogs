"""Delete Berliner Medusa duplicates created by the GM-25 re-push.

The earlier `push_pricelist_to_medusa.py` looked up matches by `item_code`
only. Name-only rows (no SKU) fell through to CREATE on every run, producing
`-2`/`-3`/... suffixed handles. This deletes ONLY products that match all of:
  1. created_at >= --since   (cutoff just before the GM-25 push)
  2. handle ends in -<n> where n >= 2
  3. de-suffixed base handle exists in the same SC
  4. base handle's product is older than this one  (sanity check)

Real product SKU.NN patterns (e.g. Spaceball L.02 → handle berliner-spaceball-l-02,
existing since first scrape) are NOT matched because they predate --since.

Usage:
    LEKA_MEDUSA_ADMIN_EMAIL=... LEKA_MEDUSA_ADMIN_PASSWORD=... \\
    python berliner-catalog/delete_duplicate_products.py --since 2026-05-13T16:00:00Z [--dry-run]
"""
from __future__ import annotations
import argparse, logging, os, re, sys, time
import requests

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SC = "sc_01KNQAA3QDYHP15Y9K4PPRMDF0"
TIMEOUT = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("berliner_dedup")


def auth() -> str:
    r = requests.post(
        f"{BACKEND}/auth/user/emailpass",
        json={"email": os.environ["LEKA_MEDUSA_ADMIN_EMAIL"],
              "password": os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["token"]


def list_all(token: str) -> list[dict]:
    out, offset, limit = [], 0, 100
    while True:
        r = requests.get(
            f"{BACKEND}/admin/products",
            params={"sales_channel_id[]": SC, "limit": limit, "offset": offset,
                    "fields": "id,handle,title,created_at"},
            headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        prods = data.get("products", [])
        if not prods:
            break
        out.extend(prods)
        offset += limit
        if offset >= data.get("count", 0):
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since", required=True,
                    help="ISO timestamp. Only delete products created at or after this. e.g. 2026-05-13T16:00:00Z")
    args = ap.parse_args()

    from datetime import datetime
    since_dt = datetime.fromisoformat(args.since.replace("Z", "+00:00"))

    token = auth()
    prods = list_all(token)
    log.info("Fetched %d Berliner products", len(prods))

    by_handle = {p["handle"]: p for p in prods}
    to_delete: list[dict] = []
    suffix_re = re.compile(r"^(.*)-(\d+)$")
    for p in prods:
        m = suffix_re.match(p["handle"])
        if not m:
            continue
        base, suffix_num = m.group(1), int(m.group(2))
        if suffix_num < 2:
            continue
        if base not in by_handle:
            continue
        # Filter by creation time
        created_raw = p.get("created_at") or ""
        try:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except ValueError:
            log.warning("Skipping %s (bad created_at: %s)", p["handle"], created_raw)
            continue
        if created_dt < since_dt:
            continue
        # Sanity: base must be older
        base_prod = by_handle[base]
        try:
            base_dt = datetime.fromisoformat((base_prod.get("created_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if base_dt >= created_dt:
            log.warning("Skipping %s — base %s isn't older (base=%s vs this=%s)",
                        p["handle"], base, base_dt, created_dt)
            continue
        to_delete.append({"id": p["id"], "handle": p["handle"], "base": base, "title": p["title"]})

    log.info("Found %d suffixed duplicates whose base handle exists", len(to_delete))
    for d in to_delete[:10]:
        log.info("  -> DELETE %s (base=%s)", d["handle"], d["base"])
    if not to_delete:
        return 0

    if args.dry_run:
        log.info("DRY RUN — no deletes.")
        return 0

    t0 = time.time()
    deleted = errors = 0
    for i, d in enumerate(to_delete, start=1):
        r = requests.delete(
            f"{BACKEND}/admin/products/{d['id']}",
            headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT,
        )
        if r.status_code >= 400:
            log.warning("DELETE %s failed: %s %s", d["handle"], r.status_code, r.text[:200])
            errors += 1
        else:
            deleted += 1
        if i % 100 == 0:
            token = auth()
            log.info("progress %d/%d (deleted=%d errors=%d, %.1f/s)",
                     i, len(to_delete), deleted, errors, i / (time.time() - t0))
    log.info("done: deleted=%d errors=%d", deleted, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
