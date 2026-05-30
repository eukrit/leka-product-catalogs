"""Re-classify the Eurotramp image audit with a smarter photo/non-photo
heuristic and write a fresh markdown report.

Why a smarter classifier?
- The first pass treated everything that wasn't a TÜV cert as a real photo.
- In practice many Medusa images for Eurotramp are *feature symbols*
  (`madeingermany_*.jpg`, `uv-lightresistant_*.jpg`), *UI icons*
  (`symbol-*`, `mediaType-*`), *placeholders* (`placeholder.jpg`), or
  *vector drawings* (`vector-*`). None of those are product photos.
- Real Eurotramp product photos follow predictable patterns:
    `<articleNo>-<productname>_<hash>_<size>.jpg`
    `productdetails-<productname>_<hash>_<size>.jpg`
    `<articleNo>-preview-<productname>_<hash>_<size>.jpg`

Reads `docs/reports/eurotramp-image-audit-<date>.json`, writes
`docs/reports/eurotramp-image-audit-<date>.md` in place (overwrites the
report from the TS pass) plus `…-classified.json` for follow-up tooling.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "docs" / "reports"


# ── Classifiers ────────────────────────────────────────────────────────────

CERT_RE = re.compile(
    r"(?<![a-z0-9])(certificate|cert|tuv|tuev|tüv|iso|ce[-_]?mark|gs[-_]?mark|compliance)(?![a-z0-9])",
    re.IGNORECASE,
)

# Feature badges (Eurotramp's `productFeatureImages.d/`): the trampoline
# product pages overlay these as bullet-point icons. They contain the
# feature wording in the filename and are reused across many products.
FEATURE_BADGE_PREFIXES = (
    "madeingermany",
    "made-in-germany",
    "uv-lightresistant",
    "uv-resistant",
    "all-seasonuse",
    "all-season",
    "water-resistant",
    "flame-retardant",
    "cold-resistant",
    "slip-resistant",
    "anti-slip",
    "suitable-for",
    "wheelchair",
    "vandal-proof",
    "vandal",
    "patented",
    "power-reduced",
    "indoor-outdoor",
    "weatherproof",
    "weather-proof",
    "bsfh-quality",
    "bsfh",
)

# Bare badge filenames (no `_` or `-` separator before extension).
FEATURE_BADGE_EXACT = {
    "patented.jpg",
    "bsfh-quality.jpg",
    "made-in-germany.jpg",
}

# UI iconography / non-photo decoration
NON_PHOTO_PREFIXES = (
    "symbol-",
    "mediatype-",
    "placeholder",
    "vector-",  # CAD line drawings
    "merchant-",  # distributor logos
    "merchant---",
    "icon-",
    "logo",
)

# Real product-photo positive signal: leading article number, or the
# `productdetail(s)-` / `<articleNo>-preview-` patterns.
ARTICLE_PREFIX_RE = re.compile(r"^e?\d{3,6}[-_]", re.IGNORECASE)


def classify(filename: str) -> str:
    """Return one of: photo | cert | feature-badge | symbol | placeholder
    | vector | merchant | unknown."""
    if not filename:
        return "unknown"
    f = filename.lower()

    if CERT_RE.search(f):
        return "cert"
    if f.startswith("placeholder"):
        return "placeholder"
    if f.startswith("vector-"):
        return "vector"
    if f.startswith("merchant-") or f.startswith("merchant---"):
        return "merchant"
    if f.startswith("symbol-"):
        return "symbol"
    if f.startswith("mediatype-"):
        return "symbol"
    if f in FEATURE_BADGE_EXACT:
        return "feature-badge"
    for p in FEATURE_BADGE_PREFIXES:
        # match prefix followed by `_` or `-` so `uv-lightresistant` (badge)
        # is caught but `uv-resistant-trampoline-photo-95001-xyz.jpg` (a
        # hypothetical real photo whose name happens to start with that
        # word) would not be — we'd still need a fix if seen.
        if f.startswith(p + "_") or f.startswith(p + "-") or f == p + ".jpg":
            return "feature-badge"
    # Article-number / productdetails / preview ⇒ real photo
    if ARTICLE_PREFIX_RE.match(f):
        return "photo"
    if "productdetails-" in f or "productdetail-" in f:
        return "photo"
    if "-preview-" in f:
        return "photo"
    return "unknown"


# ── Load + classify ────────────────────────────────────────────────────────


def newest_audit_json() -> Path:
    files = sorted(REPORTS_DIR.glob("eurotramp-image-audit-*.json"))
    files = [f for f in files if "classified" not in f.name]
    if not files:
        raise SystemExit("No audit JSON found — run audit_eurotramp_images.ts first.")
    return files[-1]


def main() -> None:
    src = newest_audit_json()
    print(f"Reading {src}")
    data = json.loads(src.read_text(encoding="utf-8"))
    rows = data["rows"]

    today = datetime.date.today().isoformat()

    enriched = []
    for r in rows:
        kinds = [classify(fn) for fn in r["image_filenames"]]
        photo_count = sum(1 for k in kinds if k == "photo")
        cert_count = sum(1 for k in kinds if k == "cert")
        unknown_count = sum(1 for k in kinds if k == "unknown")
        thumb_fn = r["thumbnail"].rsplit("/", 1)[-1] if r["thumbnail"] else ""
        thumb_kind = classify(thumb_fn) if thumb_fn else "none"
        # Backfill target = no real photo anywhere (neither in images[] nor
        # as thumbnail). If thumbnail is a photo, the storefront's
        # pickPrimaryImage already returns the right thing.
        is_backfill_target = photo_count == 0 and thumb_kind != "photo"
        enriched.append(
            {
                **r,
                "image_kinds": kinds,
                "photo_count": photo_count,
                "cert_count_strict": cert_count,
                "unknown_count": unknown_count,
                "thumb_kind": thumb_kind,
                "is_backfill_target": is_backfill_target,
            }
        )

    enriched.sort(key=lambda r: r["handle"])

    total = len(enriched)
    targets = [r for r in enriched if r["is_backfill_target"]]
    zero_imgs = [r for r in enriched if r["image_count"] == 0]
    cert_only = [
        r
        for r in enriched
        if r["image_count"] > 0
        and r["photo_count"] == 0
        and r["cert_count_strict"] > 0
    ]
    badges_only = [
        r
        for r in enriched
        if r["image_count"] > 0 and r["photo_count"] == 0 and r["cert_count_strict"] == 0
    ]
    thumb_not_photo = [r for r in enriched if r["thumb_kind"] != "photo"]
    thumb_cert = [r for r in enriched if r["thumb_kind"] == "cert"]

    # ── Write classified JSON ──────────────────────────────────────────
    classified_json = REPORTS_DIR / f"eurotramp-image-audit-{today}-classified.json"
    classified_json.write_text(
        json.dumps(
            {
                "generated_at": today,
                "source": str(src.name),
                "rows": enriched,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # ── Build markdown report ──────────────────────────────────────────
    md = REPORTS_DIR / f"eurotramp-image-audit-{today}.md"
    L: list[str] = []
    L.append(f"# Eurotramp Image Audit — {today}")
    L.append("")
    L.append(
        "Source: live Medusa backend `https://leka-medusa-backend-538978391890.asia-southeast1.run.app`"
    )
    L.append("")
    L.append("## Why this audit re-classifies images")
    L.append("")
    L.append(
        "The catalogs storefront image scorer (v0.19.2) treats anything that isn't a "
        "regex-matched cert as a candidate product photo. In practice many Medusa "
        "Eurotramp images are *feature badges* (`madeingermany_*.jpg`, "
        "`uv-lightresistant_*.jpg`), *UI symbols* (`symbol-*`), *placeholders* "
        "(`placeholder.jpg`), or *vector drawings* (`vector-*`). None of those are "
        "product photographs."
    )
    L.append("")
    L.append("This audit classifies each Medusa image as one of:")
    L.append("")
    L.append("- `photo` — leading article number, `productdetails-`, or `-preview-` (real photo)")
    L.append("- `cert` — TÜV / GS / ISO / compliance")
    L.append("- `feature-badge` — feature-wording-as-filename (made-in-germany, uv-light-resistant, …)")
    L.append("- `symbol` — `symbol-*` or `mediaType-*` UI icons")
    L.append("- `vector` — CAD line drawings (`vector-*`)")
    L.append("- `merchant` — distributor logos")
    L.append("- `placeholder` — literal `placeholder.jpg`")
    L.append("- `unknown` — anything else (conservative: treated as not-a-photo)")
    L.append("")
    L.append("**Backfill target** = `photo_count == 0` — at least one real product photo must be added to Medusa.")
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append(f"- Total Eurotramp products: **{total}**")
    L.append(f"- **Backfill targets (zero real photos in Medusa)**: **{len(targets)}**")
    L.append(f"  - of which have *only* certs/badges/symbols/etc.: {len(badges_only) + len(cert_only)}")
    L.append(f"  - of which have **no images at all**: {len(zero_imgs)}")
    L.append(f"  - of which have at least one cert image: {len(cert_only)}")
    L.append(f"- Products whose `thumbnail` is **not** a real photo: **{len(thumb_not_photo)}**")
    L.append(f"  - of which thumbnail is a cert image: **{len(thumb_cert)}**")
    L.append(f"- Products that already have ≥1 real photo: **{total - len(targets)}**")
    L.append("")

    # ── Backfill targets ──────────────────────────────────────────────
    L.append("## Backfill targets — products with zero real product photos")
    L.append("")
    L.append(
        "These products need real photographs added. Most have only feature "
        "badges + the TÜV cert + a vector drawing. The cert image will "
        "continue to win on the storefront until a real photo lands in Medusa."
    )
    L.append("")
    L.append("| handle | title | images | photo | cert | badge | symbol | vector | thumb_kind | vendor_url |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---|---|")
    for r in targets:
        kinds = r["image_kinds"]
        counts = {
            k: sum(1 for x in kinds if x == k)
            for k in ("photo", "cert", "feature-badge", "symbol", "vector")
        }
        vurl = f"[link]({r['vendor_url']})" if r["vendor_url"] else "—"
        title = r["title"].replace("|", "\\|")
        L.append(
            f"| `{r['handle']}` | {title} | {r['image_count']} | "
            f"{counts['photo']} | {counts['cert']} | {counts['feature-badge']} | "
            f"{counts['symbol']} | {counts['vector']} | {r['thumb_kind']} | {vurl} |"
        )
    L.append("")

    # ── Full audit ────────────────────────────────────────────────────
    L.append("## Full audit (all Eurotramp products)")
    L.append("")
    L.append("| handle | images | photo | cert | badge | symbol | vector | placeholder | unknown | thumb |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in enriched:
        kinds = r["image_kinds"]
        c = {
            k: sum(1 for x in kinds if x == k)
            for k in ("photo", "cert", "feature-badge", "symbol", "vector", "placeholder", "unknown")
        }
        thumb_label = r["thumb_kind"] if r["thumb_kind"] != "none" else "—"
        flag = "❌" if r["thumb_kind"] != "photo" else "✅"
        L.append(
            f"| `{r['handle']}` | {r['image_count']} | {c['photo']} | {c['cert']} | "
            f"{c['feature-badge']} | {c['symbol']} | {c['vector']} | {c['placeholder']} | "
            f"{c['unknown']} | {flag} {thumb_label} |"
        )
    L.append("")

    md.write_text("\n".join(L), encoding="utf-8")

    print(f"\n=== DONE ===")
    print(f"Total products: {total}")
    print(f"Backfill targets (no real photo): {len(targets)}")
    print(f"  of which zero images: {len(zero_imgs)}")
    print(f"  of which cert+badges only: {len(cert_only) + len(badges_only)}")
    print(f"Products with non-photo thumbnail: {len(thumb_not_photo)}")
    print(f"  of which cert thumbnail: {len(thumb_cert)}")
    print(f"Markdown: {md}")
    print(f"JSON:     {classified_json}")


if __name__ == "__main__":
    main()
