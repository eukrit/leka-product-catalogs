"""Rampline brand-CI enrichment: vendors/rampline/brand_ci/latest → Medusa.

Reads `vendors/rampline-catalog/parsed/brand_ci.json` (palette + fonts +
logos extracted from rampline.com by step3) and writes a canonical brand
tokens object to the Rampline Sales Channel metadata in Medusa.

The storefront can read these tokens to render brand-aware product pages
(border colors, accent strokes, the official Rampline logo) instead of
the generic Leka theme.

Output shape on Sales Channel metadata:
    brand_ci: {
        primary_color, secondary_color, accent_color, text_color,
        background_color, surface_color,
        primary_logo_url,
        fonts: ["…"],
        source: "vendors/rampline/brand_ci/latest",
        extracted_at: "…",
    }

Idempotent: re-runs are no-ops unless the source brand_ci.json changed.

Usage:
    python rampline-catalog/enrich_brand_ci.py --dry-run
    python rampline-catalog/enrich_brand_ci.py --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_DIR = REPO_ROOT / "rampline-catalog" / "data" / "build_runs"

DEFAULT_BRAND_CI = (
    REPO_ROOT.parent / "vendors" / "rampline-catalog" / "parsed" / "brand_ci.json"
)

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
RAMPLINE_SALES_CHANNEL_ID = "sc_01KNQAA448RY0YPR51FNPM2TVA"
PROXY_LOGO_BASE = "https://catalogs.leka.studio/api/i/rampline/design-system/logos"
TIMEOUT = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_brand_ci")


def _first_hex(palette, role: str) -> str:
    """Return the highest-occurrence hex for a given role, or "" if none."""
    cands = []
    for entry_role, entries in (palette or {}).items():
        if entry_role != role:
            continue
        if isinstance(entries, list):
            cands.extend(entries)
        elif isinstance(entries, dict):
            cands.append(entries)
    if not cands:
        return ""
    cands.sort(key=lambda c: -(c.get("occurrences") or 0))
    return (cands[0].get("hex") or "").strip()


def build_tokens(brand_ci: dict) -> dict:
    palette = brand_ci.get("palette") or {}
    # palette can be either {role: [entry, ...]} or {role: count}. Normalize.
    role_lists: dict = {}
    if palette and isinstance(next(iter(palette.values())), list):
        role_lists = palette
    elif "logos" in brand_ci or "css_variables" in brand_ci:
        # palette is a counts dict like {primary:2, secondary:3}; fall back to
        # extracting from css_variables.
        for c in (brand_ci.get("css_variables") or {}).get("colors", []) or []:
            role_lists.setdefault(c.get("role") or "unassigned", []).append(c)

    primary_logo_url = ""
    for lg in (brand_ci.get("logos") or []):
        if lg.get("role") == "primary" and lg.get("sha") and lg.get("ext"):
            primary_logo_url = f"{PROXY_LOGO_BASE}/{lg['sha']}.{lg['ext']}"
            break

    fonts: list[str] = []
    typo = brand_ci.get("typography") or {}
    for f in (typo.get("families") or typo.get("fonts") or []):
        name = f if isinstance(f, str) else (f.get("family") or f.get("name") or "")
        if name and name not in fonts:
            fonts.append(name)
    if not fonts and isinstance(brand_ci.get("fonts"), list):
        fonts = [f for f in brand_ci["fonts"] if isinstance(f, str)]

    return {
        "primary_color":    _first_hex(role_lists, "primary"),
        "secondary_color":  _first_hex(role_lists, "secondary"),
        "accent_color":     _first_hex(role_lists, "accent"),
        "text_color":       _first_hex(role_lists, "text"),
        "background_color": _first_hex(role_lists, "background"),
        "surface_color":    _first_hex(role_lists, "surface"),
        "neutral_color":    _first_hex(role_lists, "neutral"),
        "primary_logo_url": primary_logo_url,
        "fonts":            fonts[:6],
        "source":           "vendors/rampline/brand_ci/latest",
        "extracted_at":     brand_ci.get("extracted_at") or "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-ci", type=Path, default=DEFAULT_BRAND_CI)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("Specify --dry-run or --apply")

    log.info("Loading brand-CI: %s", args.brand_ci)
    bci = json.loads(args.brand_ci.read_text(encoding="utf-8"))
    tokens = build_tokens(bci)
    tokens_with_meta = {**tokens, "synced_at": datetime.now(timezone.utc).isoformat()}
    log.info("Tokens:")
    for k, v in tokens.items():
        log.info("  %-18s %s", k + ":", v)

    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD")
    if not (email and pw):
        raise SystemExit("Set LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD")
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    token = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    # Fetch existing metadata
    sc = s.get(
        f"{BACKEND}/admin/sales-channels/{RAMPLINE_SALES_CHANNEL_ID}",
        params={"fields": "id,name,metadata"}, timeout=TIMEOUT,
    ).json()["sales_channel"]
    existing_brand = (sc.get("metadata") or {}).get("brand_ci")
    if existing_brand == tokens_with_meta:
        log.info("brand_ci already up to date — no-op")
        return

    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name = f"brand_ci_{'dryrun' if args.dry_run else 'applied'}_{stamp}"
    out = RUN_LOG_DIR / f"{name}.json"
    out.write_text(json.dumps({
        "timestamp": stamp,
        "dry_run": args.dry_run,
        "sales_channel_id": RAMPLINE_SALES_CHANNEL_ID,
        "tokens": tokens_with_meta,
        "previous_brand_ci": existing_brand,
    }, indent=2, default=str), encoding="utf-8")
    log.info("Run log: %s", out)

    if args.dry_run:
        log.info("DRY RUN — no Medusa writes")
        return

    body = {"metadata": {**(sc.get("metadata") or {}), "brand_ci": tokens_with_meta}}
    r = s.post(f"{BACKEND}/admin/sales-channels/{RAMPLINE_SALES_CHANNEL_ID}",
               json=body, timeout=TIMEOUT)
    r.raise_for_status()
    log.info("✓ wrote brand_ci to Sales Channel metadata")


if __name__ == "__main__":
    main()
