"""Phase B2: walk local DesignPark asset folders, upload images to GCS,
join attachments to `vendors/designpark/products/<handle>` by SKU/theme match.

Sources processed (in priority order — first match wins per attachment):
  1. C:\\Users\\Eukrit\\My Drive\\Partners Playground\\DesignPark\\
       2024-03-18 D'Park 2D CAD & Images\\
     - Numbered prefix files `<N>_<theme>.jpg` + matching `.dwg`. The theme
       name maps to the theme-manifest products via slugified comparison.
  2. C:\\Users\\Eukrit\\My Drive\\Catalogs GO\\DesignPark\\IMAGE\\*.zip
     - 10 product-line image bundles. Files inside are unpacked and joined
       by product-line keyword (Slides, Fitness/SMART, Speed Racer, etc.).
  3. C:\\Users\\Eukrit\\My Drive\\Catalogs GO\\DesignPark\\DRAWING\\*.zip
     - 10 product-line DWG bundles. CAD files — uploaded but not added to
       `images[]` (separate `attachments[].drawings` list).
  4. C:\\Users\\Eukrit\\OneDrive\\Documents\\Suppliers GO\\DesignPark\\*.zip
     - Per-SKU drops (SDM12-/PTC21-). Highest-quality per-product bundles.
     - Filenames contain the SKU; matched directly.

Upload target:
  gs://ai-agents-go-vendors/designpark/media/<sha>.<ext>   (UBLA, PAP)
  Proxy URL: https://catalogs.leka.studio/api/i/designpark/media/<sha>.<ext>

Firestore writes:
  vendors/designpark/attachments/<sha>
    { sha, ext, source_local, source_url_proxy, kind, sku_match,
      theme_match, byte_size, content_type }
  vendors/designpark/products/<handle>.images[]
    Appended dedup-by-sha when an image (jpg/png/webp) matches the product.

Idempotent on three levels:
  - Local sha cache prevents reprocessing identical files.
  - GCS skip-upload when blob with sha-name already exists.
  - Firestore images[] deduped by sha.

Usage:
    py scripts/ingest_designpark_assets.py --dry-run
    py scripts/ingest_designpark_assets.py --apply --limit=20
    py scripts/ingest_designpark_assets.py --apply --only=cad-bundle
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_LOCAL_SA_CANDIDATES = [
    r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json",
]
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    for cand in _LOCAL_SA_CANDIDATES:
        if os.path.exists(cand):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cand
            break
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

from google.cloud import firestore, storage  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("ingest_designpark_assets")

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
SLUG = "designpark"
BUCKET = "ai-agents-go-vendors"
GCS_PREFIX = "designpark/media"
PROXY_BASE = "https://catalogs.leka.studio/api/i/designpark/media"

# --- Source paths ---------------------------------------------------------
DRIVE_PARTNER = Path(r"C:\Users\Eukrit\My Drive\Partners Playground\DesignPark")
DRIVE_CATALOGS = Path(r"C:\Users\Eukrit\My Drive\Catalogs GO\DesignPark")
ONEDRIVE_SUPPLIERS = Path(r"C:\Users\Eukrit\OneDrive\Documents\Suppliers GO\DesignPark")

CAD_BUNDLE_DIR = DRIVE_PARTNER / "2024-03-18 D'Park 2D CAD & Images"
IMAGE_ZIPS_DIR = DRIVE_CATALOGS / "IMAGE"
DRAWING_ZIPS_DIR = DRIVE_CATALOGS / "DRAWING"

# --- Matching helpers -----------------------------------------------------
# Generic SKU regex — matches the union of pricelist SKU shapes observed in
# Firestore audit (SM12-XX, SDM12-XXXX, PTC21-XXX, PTM12-XX, BOA12-XX,
# BTA12-XX, BKA12-XX, BGA15-XX, BTA17-XX, UTM-XX, DPx-XX). Numeric-prefix
# slide SKUs like 5P090-58A30A00-00 / 5W092-58A16A21-00 are handled by the
# known-SKU substring matcher (load_product_index), not this regex.
SKU_RE = re.compile(
    r"((?:SDM|PTC|PTM|SM|BOA|BTA|BKA|BGA|UTM|DPM|DPF|DPS|DP)[-_ ]?\d{2,5}"
    r"(?:[-_ ]?[A-Z0-9]{1,5})*)",
    re.IGNORECASE,
)
NUMBERED_PREFIX_RE = re.compile(r"^(\d{1,3})[_\-\s](.+?)\.(jpg|jpeg|png|webp|dwg)$", re.IGNORECASE)
SLUG_BAD_CHARS = re.compile(r"[^a-z0-9]+")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
DRAWING_EXTS = {".dwg", ".dxf"}

# Product-line keywords inferred from category sheet names in the pricelist
# (used to match contents of IMAGE/*.zip and DRAWING/*.zip bundles).
LINE_KEYWORDS: list[tuple[str, str]] = [
    ("smart cross fit",      "Fitness (SMART CROSSFIT)"),
    ("crossfit",             "Fitness (SMART CROSSFIT)"),
    ("smart senior",         "Fitness (SMART SENIOR) "),
    ("smart",                "Fitness (SMART)"),
    ("elderly fitness",      "Fitness (Elderly Trail)"),
    ("elderly trail",        "Fitness (Elderly Trail)"),
    ("outdoor fitness",      "Fitness (Premium)"),
    ("fitness",              "Fitness (Premium)"),
    ("speed racer",          "Speed Racers"),
    ("traffic light",        "Speed Racers"),
    ("modern igloo",         "Modern Igloo"),
    ("water play",           "Play (Aquatic)"),
    ("mist play",            "Play (Aquatic)"),
    ("playground",           "Play (Dry)"),
    ("slide",                "Slides & Tubes"),
    ("swing bench",          "Themes (DRY PLAYGROUND)"),
    ("wing's wing",          "Themes (DRY PLAYGROUND)"),
    ("mom's wing",           "Themes (DRY PLAYGROUND)"),
]


def slugify(text: str) -> str:
    s = SLUG_BAD_CHARS.sub("-", text.lower()).strip("-")
    return s or "unknown"


def detect_line(text: str) -> str | None:
    t = text.lower()
    for kw, line in LINE_KEYWORDS:
        if kw in t:
            return line
    return None


def detect_sku(text: str) -> str | None:
    m = SKU_RE.search(text)
    return m.group(1).upper().replace("_", "-") if m else None


# --- Asset discovery ------------------------------------------------------
def iter_cad_bundle() -> list[dict]:
    """`2024-03-18 D'Park 2D CAD & Images/<N>_<theme>.<ext>` files."""
    out: list[dict] = []
    if not CAD_BUNDLE_DIR.exists():
        log.warning("missing CAD bundle dir: %s", CAD_BUNDLE_DIR)
        return out
    for fp in CAD_BUNDLE_DIR.iterdir():
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in IMAGE_EXTS | DRAWING_EXTS:
            continue
        m = NUMBERED_PREFIX_RE.match(fp.name)
        theme_name = m.group(2).strip() if m else fp.stem
        sku_match = detect_sku(theme_name) or detect_sku(fp.name)
        out.append({
            "src": str(fp),
            "name": fp.name,
            "ext": fp.suffix.lower().lstrip("."),
            "kind": "image" if fp.suffix.lower() in IMAGE_EXTS else "drawing",
            "source": "cad-bundle",
            "theme_match": slugify(theme_name) if not sku_match else "",
            "sku_match": sku_match or "",
        })
    log.info("[cad-bundle] %d files", len(out))
    return out


def iter_zip_bundles(zips_dir: Path, source_label: str) -> list[dict]:
    """Walk each .zip in a directory; treat zip stem as the line label."""
    out: list[dict] = []
    if not zips_dir.exists():
        log.warning("missing zips dir: %s", zips_dir)
        return out
    for zp in zips_dir.glob("*.zip"):
        line_hint = detect_line(zp.stem) or ""
        try:
            with zipfile.ZipFile(zp, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    suffix = Path(name).suffix.lower()
                    if suffix not in IMAGE_EXTS | DRAWING_EXTS:
                        continue
                    sku_match = detect_sku(name) or detect_sku(zp.name)
                    out.append({
                        "src": f"{zp}::{name}",
                        "_zip": str(zp),
                        "_zip_member": name,
                        "name": Path(name).name,
                        "ext": suffix.lstrip("."),
                        "kind": "image" if suffix in IMAGE_EXTS else "drawing",
                        "source": source_label,
                        "line_match": line_hint,
                        "theme_match": "" if sku_match else slugify(Path(name).stem),
                        "sku_match": sku_match or "",
                    })
        except zipfile.BadZipFile:
            log.warning("bad zip: %s", zp)
    log.info("[%s] %d files across %d zips", source_label, len(out), len(list(zips_dir.glob("*.zip"))))
    return out


def iter_suppliers_zips() -> list[dict]:
    """Per-SKU drops in Suppliers GO/DesignPark — SKU is in the zip name."""
    out: list[dict] = []
    if not ONEDRIVE_SUPPLIERS.exists():
        log.warning("missing suppliers dir: %s", ONEDRIVE_SUPPLIERS)
        return out
    for zp in ONEDRIVE_SUPPLIERS.glob("*.zip"):
        sku = detect_sku(zp.name) or ""
        try:
            with zipfile.ZipFile(zp, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    suffix = Path(info.filename).suffix.lower()
                    if suffix not in IMAGE_EXTS | DRAWING_EXTS:
                        continue
                    out.append({
                        "src": f"{zp}::{info.filename}",
                        "_zip": str(zp),
                        "_zip_member": info.filename,
                        "name": Path(info.filename).name,
                        "ext": suffix.lstrip("."),
                        "kind": "image" if suffix in IMAGE_EXTS else "drawing",
                        "source": "suppliers",
                        "sku_match": sku,
                        "theme_match": "",
                    })
        except zipfile.BadZipFile:
            log.warning("bad zip: %s", zp)
    log.info("[suppliers] %d files across %d zips", len(out), len(list(ONEDRIVE_SUPPLIERS.glob("*.zip"))))
    return out


# --- IO ------------------------------------------------------------------
def read_bytes(asset: dict) -> bytes:
    if "_zip" in asset:
        with zipfile.ZipFile(asset["_zip"], "r") as zf:
            return zf.read(asset["_zip_member"])
    return Path(asset["src"]).read_bytes()


def sha_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def content_type_for(ext: str) -> str:
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
        "dwg": "application/acad", "dxf": "application/dxf",
    }.get(ext, "application/octet-stream")


# --- Product matching ----------------------------------------------------
# Manual theme aliases — 2024 CAD bundle uses different theme names than the
# 2023 manifest. Maps CAD theme slug (left) → manifest product name slug (right).
# Only fills gaps the substring-overlap matcher misses.
THEME_ALIASES: dict[str, str] = {
    "twin-tower": "twin-star",                     # CAD #1 → manifest "Twin star"
    "art-playground": "art-playground",            # exact (no-op, but explicit)
    "rainbow-tower": "twin-star",                  # CAD #20 → manifest "Twin star"
    "windmill-in-the-sky": "the-sun-is-fickle",    # CAD #22 → manifest cloud-theme proxy
    "hiding-alligator": "hut-in-the-forest",       # CAD #23 → nature-theme proxy
    "hunter-s-hut": "hut-in-the-forest",           # CAD #14 → manifest "Hut in the forest"
    "hunters-hut": "hut-in-the-forest",
    "honeybear-house": "indian-village",           # CAD #21 → ETC-themed proxy
    "honeybee-house": "indian-village",            # CAD #29
    "spring-garden": "art-playground",             # CAD #11 fallback
    "forsythia-garden": "art-playground",          # CAD #30 fallback
    "peterpan-world": "art-playground",            # CAD #12 fallback
    "marine-guard": "marine-guard",                # exact
    "twin-star": "twin-star",                      # CAD #1 alt spelling
}


def load_product_index(db: firestore.Client) -> dict:
    """Build lookup tables and an upper-cased known-SKU set for substring
    matching against arbitrary filenames."""
    coll = db.collection("vendors").document(SLUG).collection("products")
    by_sku: dict[str, str] = {}
    by_theme: dict[str, str] = {}
    sku_set: list[str] = []  # sorted longest-first for greedy substring match
    n = 0
    for snap in coll.stream():
        d = snap.to_dict() or {}
        handle = d.get("handle") or snap.id
        item_code = (d.get("item_code") or "").upper()
        if item_code:
            by_sku[item_code] = handle
            sku_set.append(item_code)
            # Stripped variants (drop trailing -00 / -001 / parenthetical).
            stripped = re.sub(r"[-_]\d{1,4}$", "", item_code)
            if stripped and stripped not in by_sku:
                by_sku[stripped] = handle
                sku_set.append(stripped)
        if d.get("is_theme") and d.get("name"):
            by_theme[slugify(d["name"])] = handle
        n += 1
    # Longest first so "SDM12-B112" wins over "SDM12-B".
    sku_set = sorted(set(sku_set), key=len, reverse=True)
    log.info("loaded product index: %d products, %d skus, %d themes",
             n, len(by_sku), len(by_theme))
    return {"sku": by_sku, "theme": by_theme, "sku_set": sku_set}


def find_sku_in_text(text: str, sku_set: list[str]) -> str | None:
    """Greedy longest-match against the known-SKU set. Case-insensitive,
    tolerant of spaces/dashes/underscores between segments."""
    t = re.sub(r"[\s_]+", "-", text.upper())
    for sku in sku_set:
        # Build a tolerant variant of the SKU (allow optional separators
        # to be missing or replaced, e.g. "SM12-04B" matches "SM12 - 04B").
        pat = re.sub(r"[-_]", r"[-_ ]?", sku)
        if re.search(rf"(?<![A-Z0-9]){pat}(?![A-Z0-9])", t):
            return sku
    return None


def match_product(asset: dict, idx: dict) -> str | None:
    # 1) Pre-detected SKU (cheap path from discovery time).
    if asset.get("sku_match"):
        sku = asset["sku_match"].upper().replace(" ", "-")
        if sku in idx["sku"]:
            return idx["sku"][sku]
        stripped = re.sub(r"[-_]\d{1,4}$", "", sku)
        if stripped in idx["sku"]:
            return idx["sku"][stripped]

    # 2) Substring match against the known-SKU set using the filename.
    name = asset.get("name") or ""
    hit = find_sku_in_text(name, idx["sku_set"])
    if hit and hit in idx["sku"]:
        asset["sku_match"] = hit  # backfill so attachment doc records it
        return idx["sku"][hit]

    # 3) Theme match with alias table.
    if asset.get("theme_match"):
        ts = asset["theme_match"]
        # Alias rewrite.
        canonical = THEME_ALIASES.get(ts, ts)
        if canonical in idx["theme"]:
            return idx["theme"][canonical]
        # Token-overlap (e.g. "twin-tower" ↔ "twin-star" no longer matches —
        # too aggressive — but still let "art-playground" ↔ "art-playground"
        # exact and "marine-guard" ↔ "marine-guard" hit naturally).
        for theme_slug, handle in idx["theme"].items():
            # Require both sides to share at least 2 tokens for a "fuzzy" hit.
            a = set(ts.split("-"))
            b = set(theme_slug.split("-"))
            if len(a & b) >= 2:
                return handle
    return None


# --- Main ----------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", choices=["cad-bundle", "image-zips", "drawing-zips", "suppliers"])
    args = ap.parse_args()
    dry = args.dry_run

    assets: list[dict] = []
    if args.only in (None, "cad-bundle"):
        assets += iter_cad_bundle()
    if args.only in (None, "image-zips"):
        assets += iter_zip_bundles(IMAGE_ZIPS_DIR, "image-zips")
    if args.only in (None, "drawing-zips"):
        assets += iter_zip_bundles(DRAWING_ZIPS_DIR, "drawing-zips")
    if args.only in (None, "suppliers"):
        assets += iter_suppliers_zips()

    log.info("total assets discovered: %d", len(assets))
    if args.limit:
        assets = assets[: args.limit]

    if dry:
        # Print counts by source/kind/match.
        from collections import Counter
        by_source = Counter(a["source"] for a in assets)
        by_kind = Counter(a["kind"] for a in assets)
        by_sku = Counter(bool(a.get("sku_match")) for a in assets)
        log.info("by source: %s", dict(by_source))
        log.info("by kind:   %s", dict(by_kind))
        log.info("has sku:   %s (True/False)", dict(by_sku))
        log.info("[DRY] would upload %d to gs://%s/%s and link via Firestore",
                 len(assets), BUCKET, GCS_PREFIX)
        for a in assets[:8]:
            log.info("    %s | kind=%s | sku=%s | theme=%s | src=%s",
                     a["name"][:50], a["kind"], a.get("sku_match"),
                     a.get("theme_match"), a["source"])
        return 0

    # Apply.
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    storage_client = storage.Client(project=PROJECT)
    bucket = storage_client.bucket(BUCKET)
    idx = load_product_index(db)

    n_upload, n_skip_exists, n_matched, n_unmatched = 0, 0, 0, 0
    seen_sha: set[str] = set()
    attach_coll = db.collection("vendors").document(SLUG).collection("attachments")
    prod_coll = db.collection("vendors").document(SLUG).collection("products")

    for i, asset in enumerate(assets, 1):
        try:
            data = read_bytes(asset)
        except Exception as e:
            log.warning("read failed for %s: %s", asset["src"], e)
            continue
        sha = sha_of(data)
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        ext = asset["ext"]
        blob_path = f"{GCS_PREFIX}/{sha}.{ext}"
        blob = bucket.blob(blob_path)
        if not blob.exists():
            blob.upload_from_string(data, content_type=content_type_for(ext))
            n_upload += 1
        else:
            n_skip_exists += 1

        proxy_url = f"{PROXY_BASE}/{sha}.{ext}"
        attach_doc = {
            "sha": sha,
            "ext": ext,
            "kind": asset["kind"],
            "source": asset["source"],
            "source_local": asset["src"],
            "source_url_proxy": proxy_url,
            "sku_match": asset.get("sku_match") or "",
            "theme_match": asset.get("theme_match") or "",
            "byte_size": len(data),
            "content_type": content_type_for(ext),
        }
        attach_coll.document(sha).set(attach_doc, merge=True)

        handle = match_product(asset, idx)
        if not handle:
            n_unmatched += 1
            continue
        n_matched += 1
        if asset["kind"] == "image":
            prod_ref = prod_coll.document(handle)
            snap = prod_ref.get()
            existing_imgs = (snap.to_dict() or {}).get("images") or []
            if not any((img.get("sha") if isinstance(img, dict) else None) == sha for img in existing_imgs):
                existing_imgs.append({"url": proxy_url, "sha": sha, "ext": ext})
                prod_ref.set({"images": existing_imgs}, merge=True)

        if i % 50 == 0:
            log.info("progress: %d / %d (uploaded %d, skip %d, matched %d, unmatched %d)",
                     i, len(assets), n_upload, n_skip_exists, n_matched, n_unmatched)

    log.info("done: %d uploaded, %d skip-exists, %d matched, %d unmatched",
             n_upload, n_skip_exists, n_matched, n_unmatched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
