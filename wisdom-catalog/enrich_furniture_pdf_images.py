"""Enrich Wisdom / Leka Project products with images from the 2025-08-11
Furniture Catalog.

Pipeline (run after wisdom-catalog/extract_furniture_pdf_images.py --extract):

  A. --upload          push wisdom-catalog/data/pdf_images/*.jpg to
                       gs://ai-agents-go-vendors/wisdom/furniture_2025/<filename>
                       (the bucket the storefront image proxy reads). Idempotent.

  B. --write-firestore merge images into vendors/wisdom/products[].images.
                       PRECEDENCE (mirrors foursoft-catalog/enrich_pdf_images.py
                       v2.43.0): keep real WEB / higher-res images already on
                       the doc; only ADD when images=[] OR when all existing
                       images have source containing "borrowed" / "base_design".

  C. --verify          Gemini 2.5 Flash @ threshold 0.70 — for each newly-
                       written furniture image, fetch via the proxy URL, ask
                       Gemini whether it depicts the same product as the
                       Medusa title. Decisions saved to:
                         * Firestore image_backfill_verify/{sha1(code)}
                           (same collection v2.34.0 used).
                         * Per-image image_verified + image_match_score
                           on the vendor doc.
                       Cost ceiling: pause at $18 projected.

  D. --sync-medusa     For every Medusa placeholder product whose vendor
                       doc now has a VERIFIED furniture image, POST the
                       images + thumbnail to /admin/products/{id} and set
                       metadata.image_status="backfilled_furniture".

Usage:
    python wisdom-catalog/enrich_furniture_pdf_images.py --upload --dry-run
    python wisdom-catalog/enrich_furniture_pdf_images.py --upload
    python wisdom-catalog/enrich_furniture_pdf_images.py --write-firestore --dry-run --limit-codes 25
    python wisdom-catalog/enrich_furniture_pdf_images.py --write-firestore
    python wisdom-catalog/enrich_furniture_pdf_images.py --verify --limit 25
    python wisdom-catalog/enrich_furniture_pdf_images.py --verify
    python wisdom-catalog/enrich_furniture_pdf_images.py --sync-medusa --dry-run
    python wisdom-catalog/enrich_furniture_pdf_images.py --sync-medusa
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests
from google import genai
from google.cloud import firestore, secretmanager, storage
from google.genai import types as genai_types

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_furniture")

# ---------------------------------------------------------------------------
# Constants

PROJECT = "ai-agents-go"
VENDORS_DB = "vendors"
CHECKPOINT_DB = "leka-product-catalogs"
BUCKET = "ai-agents-go-vendors"
GCS_PREFIX = "wisdom/furniture_2025"
PROXY_BASE = "https://catalogs.leka.studio/api/i/wisdom/furniture_2025"

REPO_ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = REPO_ROOT / "wisdom-catalog" / "data" / "pdf_images"
MAP_JSON = REPO_ROOT / "wisdom-catalog" / "data" / "pdf_images_map.json"

# Medusa
MEDUSA_BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"  # Leka Project sales channel
STORE_PK = "pk_b7d7b7412262b05054450cd08213cd3d7d3432616ffff885e4c8a57e1b596e53"

# Tags
SOURCE_TAG = "catalog_pdf_furniture_2025_spatial_v2"
CATALOG_NAME = "furniture_2025"
SYNC_STATUS_TAG = "backfilled_furniture"

# Gemini
GEMINI_LOCATION = "global"
VERIFY_MODEL = "gemini-2.5-flash"
VERIFY_CONFIDENCE_THRESHOLD = 0.70
VERIFY_CONCURRENCY = 4
VERIFY_COLLECTION = "image_backfill_verify"
VERIFY_COST_PER_CALL = 0.0093  # empirical from v2.34
VERIFY_COST_CEILING_USD = 18.0
VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {"type": "boolean"},
        "confidence": {"type": "number"},
        "depicted": {"type": "string"},
    },
    "required": ["matches", "confidence", "depicted"],
}

# Precedence
REAL_WEB_SOURCE_HINTS = ("medusa_reverse_import", "wisdom_web", "4soft_web")
BORROWED_HINTS = ("borrowed", "base_design")


def handle_for(code: str) -> str:
    """Vendors doc-id slug. Mirrors how rows were created by the original
    migrate_leka_to_vendors.py pipeline — lowercase, non-alnum -> '-'."""
    slug = re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")
    return f"wisdom-{slug}"

TIMEOUT = 60

# ---------------------------------------------------------------------------
# Auth helpers (mirrored from scripts/backfill_leka_project_images.py:121-175)

def _adc_check() -> None:
    import google.auth
    try:
        _, project = google.auth.default()
        log.info("ADC ok (project=%s)", project)
    except Exception as e:
        log.error("ADC failure: %s — run `gcloud auth application-default login`", e)
        sys.exit(2)


def _sm_secret(name: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{PROJECT}/secrets/{name}/versions/latest"
    return client.access_secret_version(name=path).payload.data.decode().strip()


def _medusa_admin_token() -> str:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL") or _sm_secret("medusa-admin-email")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD") or _sm_secret("medusa-admin-password")
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
# Phase A — upload to GCS

def load_mapping() -> dict:
    """Returns code -> list of {filename, page, distance, image_w, image_h, ...}."""
    if not MAP_JSON.exists():
        log.error("Mapping JSON missing: %s — run extract --extract first.", MAP_JSON)
        sys.exit(2)
    return json.loads(MAP_JSON.read_text(encoding="utf-8"))


def cmd_upload(args) -> None:
    _adc_check()
    mapping = load_mapping()
    sc = storage.Client(project=PROJECT)
    bucket = sc.bucket(BUCKET)
    seen_files: set[str] = set()
    for code, imgs in mapping.items():
        for img in imgs:
            seen_files.add(img["filename"])
    if args.limit_codes:
        codes = sorted(mapping.keys())[: args.limit_codes]
        seen_files = {img["filename"] for c in codes for img in mapping[c]}
        log.info("--limit-codes %d → %d files", args.limit_codes, len(seen_files))
    else:
        log.info("Uploading %d unique files", len(seen_files))

    counts = {"uploaded": 0, "exists": 0, "missing_local": 0, "errors": 0}
    started = time.time()
    for i, fname in enumerate(sorted(seen_files), 1):
        local = IMG_DIR / fname
        if not local.exists():
            counts["missing_local"] += 1
            log.warning("missing local: %s", fname)
            continue
        blob = bucket.blob(f"{GCS_PREFIX}/{fname}")
        if blob.exists():
            counts["exists"] += 1
            continue
        if args.dry_run:
            counts["uploaded"] += 1
            if i <= 5:
                log.info("  [dry] would upload %s -> gs://%s/%s/%s",
                         fname, BUCKET, GCS_PREFIX, fname)
            continue
        try:
            blob.upload_from_filename(str(local), content_type="image/jpeg")
            counts["uploaded"] += 1
        except Exception as e:
            counts["errors"] += 1
            log.error("upload failed %s: %s", fname, str(e)[:200])
        if i % 100 == 0 or i == len(seen_files):
            rate = i / max(time.time() - started, 0.001)
            log.info("  %d/%d (%.1f/s) %s", i, len(seen_files), rate, counts)
    log.info("Upload done in %.1fs: %s", time.time() - started, counts)


# ---------------------------------------------------------------------------
# Phase B — write to vendors/wisdom/products

def proxy_url(filename: str) -> str:
    return f"{PROXY_BASE}/{filename}"


def existing_images_intent(images: list) -> str:
    """Classify the doc's current images[]: 'empty', 'borrowed_only', or 'real'."""
    if not images:
        return "empty"
    real = False
    for img in images:
        if not isinstance(img, dict):
            continue
        src = (img.get("source") or "").lower()
        if any(t in src for t in BORROWED_HINTS):
            continue
        if "furniture_2025" in src:
            # Already has a furniture image — treat as real to be idempotent
            real = True
        else:
            real = True
    return "real" if real else "borrowed_only"


def title_for(vdoc: dict) -> str:
    return (
        vdoc.get("title")
        or vdoc.get("description")
        or vdoc.get("gemini_description")
        or vdoc.get("item_code")
        or ""
    )


def cmd_write_firestore(args) -> None:
    _adc_check()
    mapping = load_mapping()
    db = firestore.Client(project=PROJECT, database=VENDORS_DB)
    col = db.collection("vendors").document("wisdom").collection("products")
    counts = {"wrote_new": 0, "added_to_borrowed": 0, "skipped_real": 0,
              "skipped_already_furniture": 0, "missing_vendor_doc": 0, "errors": 0}
    started = time.time()
    codes = sorted(mapping.keys())
    if args.limit_codes:
        codes = codes[: args.limit_codes]
        log.info("--limit-codes %d", args.limit_codes)

    for i, code in enumerate(codes, 1):
        imgs = mapping[code]
        # Sort by distance asc, take MAX 2
        imgs = sorted(imgs, key=lambda x: x.get("distance", 1e9))[:2]
        doc_id = handle_for(code)
        doc_ref = col.document(doc_id)
        snap = doc_ref.get()
        if not snap.exists:
            counts["missing_vendor_doc"] += 1
            continue
        data = snap.to_dict() or {}
        existing = data.get("images") or []
        intent = existing_images_intent(existing)
        # Idempotency: if doc already has furniture_2025 images, skip
        if any(isinstance(img, dict) and "furniture_2025" in (img.get("source") or "")
               for img in existing):
            counts["skipped_already_furniture"] += 1
            continue
        if intent == "real":
            counts["skipped_real"] += 1
            continue
        title = title_for(data)
        # Build new image entries
        new_entries = []
        for j, img in enumerate(imgs):
            new_entries.append({
                "url": proxy_url(img["filename"]),
                "alt_text": f"{title or code} from {CATALOG_NAME} p{img['page']}",
                "is_primary": (j == 0 and intent == "empty"),
                "source": SOURCE_TAG,
                "catalog": CATALOG_NAME,
                "page": img["page"],
                "distance": round(float(img.get("distance", 0.0)), 2),
                "image_match_score": None,
                "image_verified": False,
            })
        if intent == "borrowed_only":
            # Strip borrowed/base_design entries, replace with furniture
            filtered = [img for img in existing
                        if not (isinstance(img, dict)
                                and any(t in (img.get("source") or "").lower()
                                        for t in BORROWED_HINTS))]
            # Demote any pre-existing is_primary on filtered set
            for e in filtered:
                if isinstance(e, dict):
                    e["is_primary"] = False
            new_list = new_entries + filtered
            counts["added_to_borrowed"] += 1
        else:
            new_list = new_entries
            counts["wrote_new"] += 1

        if args.dry_run:
            if i <= 5:
                log.info("  [dry] %s (intent=%s) +%d furniture images, new len=%d",
                         code, intent, len(new_entries), len(new_list))
            continue
        try:
            doc_ref.update({
                "images": new_list,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            })
        except Exception as e:
            counts["errors"] += 1
            log.error("update %s failed: %s", code, str(e)[:200])
        if i % 100 == 0 or i == len(codes):
            log.info("  %d/%d %s", i, len(codes), counts)

    log.info("Write done in %.1fs: %s", time.time() - started, counts)


# ---------------------------------------------------------------------------
# Phase C — Gemini verify

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _tolerant_json(text: str) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_OBJ_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _gemini_verify(gem: genai.Client, img_bytes: bytes, mime: str, title: str) -> dict:
    prompt = (
        "You are verifying that a product photo matches a product title.\n"
        f'Product title: "{title}"\n\n'
        "Look at the image. Decide if the image plausibly depicts the SAME PRODUCT as "
        "the title (same kind of furniture / kids' play product / accessory).\n\n"
        "Return JSON matching the schema:\n"
        "  matches    — true only if the image clearly shows the same kind of product as the title.\n"
        "  confidence — your confidence in the answer, 0.0 to 1.0.\n"
        "  depicted   — short noun phrase describing what the image actually shows.\n"
        "Be strict: if the image shows a different category of item from the title, "
        "return matches=false."
    )
    delays = [2, 5, 15, 45, 90]
    last: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            resp = gem.models.generate_content(
                model=VERIFY_MODEL,
                contents=[
                    genai_types.Part.from_bytes(data=img_bytes, mime_type=mime),
                    prompt,
                ],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VERIFY_SCHEMA,
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )
            parsed = _tolerant_json(resp.text or "")
            if "matches" in parsed:
                return parsed
            if attempt == len(delays):
                break
            time.sleep(0.5 + random.random())
        except Exception as e:
            last = e
            msg = str(e)
            transient = any(t in msg for t in (
                "429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE",
                "DEADLINE_EXCEEDED", "504", "500",
            ))
            if not transient:
                raise
            if attempt == len(delays):
                break
            time.sleep(min(delays[attempt] + random.random() * 2, 90.0))
    if last:
        raise last
    return {}


def _verify_one(item: dict, fs: firestore.Client, gem: genai.Client, force: bool) -> dict:
    code = item["code"]
    url = item["url"]
    title = item["title"]
    sha = hashlib.sha1(code.encode()).hexdigest()
    doc_ref = fs.collection(VERIFY_COLLECTION).document(sha)
    if not force:
        snap = doc_ref.get()
        if snap.exists:
            d = snap.to_dict() or {}
            if d.get("decision") in ("accept", "reject", "error") and d.get("source", "").startswith("furniture"):
                d["_cached"] = True
                return d
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.content
        mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
    except Exception as e:
        rec = {"code": code, "decision": "error", "stage": "download",
               "error": str(e)[:300], "source": "furniture_2025",
               "url": url, "decided_at": firestore.SERVER_TIMESTAMP}
        doc_ref.set(rec)
        return rec
    try:
        parsed = _gemini_verify(gem, data, mime, title)
    except Exception as e:
        rec = {"code": code, "decision": "error", "stage": "gemini",
               "error": str(e)[:300], "source": "furniture_2025",
               "url": url, "decided_at": firestore.SERVER_TIMESTAMP}
        doc_ref.set(rec)
        return rec
    matches = bool(parsed.get("matches"))
    conf = float(parsed.get("confidence") or 0.0)
    decision = "accept" if (matches and conf >= VERIFY_CONFIDENCE_THRESHOLD) else "reject"
    rec = {
        "code": code, "title": title, "url": url,
        "decision": decision, "matches": matches, "confidence": conf,
        "depicted": (parsed.get("depicted") or "")[:300],
        "source": "furniture_2025",
        "decided_at": firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(rec)
    return rec


def cmd_verify(args) -> None:
    _adc_check()
    fs = firestore.Client(project=PROJECT, database=CHECKPOINT_DB)
    vendors_fs = firestore.Client(project=PROJECT, database=VENDORS_DB)
    gem = genai.Client(vertexai=True, project=PROJECT, location=GEMINI_LOCATION)

    # Gather verify candidates: every vendors/wisdom/products doc with a
    # furniture_2025-sourced image, take the PRIMARY (or first) furniture image.
    col = vendors_fs.collection("vendors").document("wisdom").collection("products")
    items: list[dict] = []
    for d in col.stream():
        data = d.to_dict() or {}
        code = data.get("item_code") or d.id.replace("wisdom-", "")
        imgs = data.get("images") or []
        furniture_imgs = [img for img in imgs
                          if isinstance(img, dict)
                          and "furniture_2025" in (img.get("source") or "")]
        if not furniture_imgs:
            continue
        # Pick primary if marked, else first
        primary = next((img for img in furniture_imgs if img.get("is_primary")),
                       furniture_imgs[0])
        items.append({
            "code": code,
            "doc_id": d.id,
            "url": primary["url"],
            "title": title_for(data),
        })
    log.info("Verify candidates: %d", len(items))
    if args.limit:
        items = items[: args.limit]
        log.info("--limit %d", args.limit)

    projected_cost = len(items) * VERIFY_COST_PER_CALL
    log.info("Projected Vertex cost: $%.2f (%.4f/call x %d)",
             projected_cost, VERIFY_COST_PER_CALL, len(items))
    if projected_cost > VERIFY_COST_CEILING_USD and not args.force_cost:
        log.error("Projected cost $%.2f > ceiling $%.2f — pass --force-cost to override.",
                  projected_cost, VERIFY_COST_CEILING_USD)
        sys.exit(2)

    counts = {"accept": 0, "reject": 0, "error": 0, "cached": 0}
    started = time.time()

    def work(it):
        return _verify_one(it, fs, gem, args.force)

    with ThreadPoolExecutor(max_workers=VERIFY_CONCURRENCY) as ex:
        futures = {ex.submit(work, it): it for it in items}
        for i, fut in enumerate(as_completed(futures), 1):
            it = futures[fut]
            try:
                rec = fut.result()
            except Exception as e:
                log.error("  %s unexpected: %s", it["code"], e)
                counts["error"] += 1
                continue
            if rec.get("_cached"):
                counts["cached"] += 1
            else:
                counts[rec.get("decision", "error")] += 1
            if i % 25 == 0 or i == len(items):
                rate = i / max(time.time() - started, 0.001)
                log.info("  %4d/%d (%.1f/s) %s", i, len(items), rate, counts)

    log.info("Verify done in %.1fs: %s", time.time() - started, counts)

    # Reflect verify decisions back into vendors doc image entries
    log.info("Updating vendors docs with verify results...")
    updated = 0
    for it in items:
        sha = hashlib.sha1(it["code"].encode()).hexdigest()
        snap = fs.collection(VERIFY_COLLECTION).document(sha).get()
        if not snap.exists:
            continue
        d = snap.to_dict() or {}
        if d.get("source") != "furniture_2025":
            continue
        verified = (d.get("decision") == "accept")
        score = float(d.get("confidence") or 0.0)
        doc_ref = vendors_fs.collection("vendors").document("wisdom").collection("products").document(it["doc_id"])
        doc_snap = doc_ref.get()
        if not doc_snap.exists:
            continue
        data = doc_snap.to_dict() or {}
        imgs = data.get("images") or []
        any_change = False
        for img in imgs:
            if isinstance(img, dict) and "furniture_2025" in (img.get("source") or ""):
                if img.get("image_verified") != verified or img.get("image_match_score") != score:
                    img["image_verified"] = verified
                    img["image_match_score"] = score
                    any_change = True
        if any_change and not args.dry_run:
            doc_ref.update({"images": imgs,
                            "updatedAt": firestore.SERVER_TIMESTAMP})
            updated += 1
    log.info("Vendor docs updated with verify results: %d", updated)


# ---------------------------------------------------------------------------
# Phase D — sync to Medusa

def iter_placeholder_products(pk: str):
    offset = 0
    while True:
        r = requests.get(
            f"{MEDUSA_BACKEND}/store/products",
            headers={"x-publishable-api-key": pk},
            params={"limit": 100, "offset": offset,
                    "fields": "id,handle,title,thumbnail,images.url,variants.metadata,metadata"},
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            th = p.get("thumbnail") or ""
            meta = p.get("metadata") or {}
            if meta.get("image_status") == "placeholder" or "leka-coming-soon" in th:
                yield p
        offset += 100


def code_for_medusa(p: dict) -> str | None:
    vs = p.get("variants") or []
    code = (vs[0].get("metadata") or {}).get("legacy_sku") if vs else None
    if not code:
        lh = (p.get("metadata") or {}).get("legacy_handle", "")
        code = lh.replace("wisdom-", "") if lh else None
    return code


def cmd_sync_medusa(args) -> None:
    _adc_check()
    vendors_fs = firestore.Client(project=PROJECT, database=VENDORS_DB)
    fs = firestore.Client(project=PROJECT, database=CHECKPOINT_DB)
    col = vendors_fs.collection("vendors").document("wisdom").collection("products")

    # Build code -> [accepted furniture URLs] index
    code_to_urls: dict[str, list[str]] = {}
    code_to_titles: dict[str, str] = {}
    for d in col.stream():
        data = d.to_dict() or {}
        code = data.get("item_code") or d.id.replace("wisdom-", "")
        imgs = data.get("images") or []
        accepted = [img["url"] for img in imgs
                    if isinstance(img, dict)
                    and "furniture_2025" in (img.get("source") or "")
                    and img.get("image_verified") is True]
        if accepted:
            code_to_urls[code] = accepted
            code_to_titles[code] = title_for(data)
    log.info("Codes with verified furniture imagery: %d", len(code_to_urls))

    tok = None if args.dry_run else _medusa_admin_token()
    counts = {"flipped": 0, "skipped_no_furniture": 0, "skipped_no_code": 0,
              "errors": 0}
    started = time.time()
    iso_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    n = 0
    for p in iter_placeholder_products(STORE_PK):
        n += 1
        if args.limit and counts["flipped"] >= args.limit:
            break
        code = code_for_medusa(p)
        if not code:
            counts["skipped_no_code"] += 1
            continue
        urls = code_to_urls.get(code)
        if not urls:
            counts["skipped_no_furniture"] += 1
            continue
        payload = {
            "images": [{"url": u} for u in urls],
            "thumbnail": urls[0],
            "metadata": {
                "image_status": SYNC_STATUS_TAG,
                "image_status_at": iso_now,
            },
        }
        if args.dry_run:
            counts["flipped"] += 1
            if counts["flipped"] <= 5:
                log.info("  [dry] %s (%s) -> %d furniture URLs",
                         code, p.get("handle"), len(urls))
            continue
        try:
            r = _retry("POST", f"{MEDUSA_BACKEND}/admin/products/{p['id']}", tok,
                       json_body=payload)
            r.raise_for_status()
            counts["flipped"] += 1
        except Exception as e:
            counts["errors"] += 1
            log.error("  %s update failed: %s", p["id"], str(e)[:200])
        if counts["flipped"] % 25 == 0 and counts["flipped"]:
            log.info("  scanned=%d flipped=%d", n, counts["flipped"])

    log.info("Sync done in %.1fs: scanned=%d %s",
             time.time() - started, n, counts)


# ---------------------------------------------------------------------------
# Main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--write-firestore", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--sync-medusa", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="--verify: re-verify cached codes")
    ap.add_argument("--force-cost", action="store_true",
                    help="--verify: override $18 cost ceiling")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--limit-codes", type=int, default=None)
    args = ap.parse_args()

    chosen = sum([args.upload, args.write_firestore, args.verify, args.sync_medusa])
    if chosen == 0:
        ap.print_help()
        sys.exit(2)
    if chosen > 1:
        log.error("Pick one phase at a time.")
        sys.exit(2)

    if args.upload:
        cmd_upload(args)
    elif args.write_firestore:
        cmd_write_firestore(args)
    elif args.verify:
        cmd_verify(args)
    elif args.sync_medusa:
        cmd_sync_medusa(args)


if __name__ == "__main__":
    main()
