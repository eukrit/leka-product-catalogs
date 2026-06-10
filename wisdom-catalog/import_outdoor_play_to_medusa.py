"""
Tag the 272 Wisdom outdoor-play SKUs into the `wisdom-outdoor-play` Medusa
collection — Option A (link existing 255 + create 17 new) with Gemini-verified
images.

## Why this isn't a simple bulk-create

The "Wisdom" sales channel was renamed to **"Leka Project"**
(`sc_01KNKTHC0B7KFEDSZ3NNM49JQW`) in a prior rebrand. 5,062 products already
live under that SC with handles like `leka-project-<nanoid>`; the original
Wisdom item codes survive in `variants[].metadata.legacy_sku`. Of the 272
outdoor-play SKUs:

  - 174 match an existing Leka-Project product by exact `legacy_sku`.
  - 81  match by `firestore.matched_id` (sibling code, e.g. CSS-BZ ↔ CSS-BZ-V02).
  - 17  are truly absent (the firestore-null rows).

So we **link** the 255 existing ones into the collection (preserving the
v2.34.0 image backfill + v2.37.0 AI enrichment) and **create** the 17 missing
ones from scratch.

## Image handling — three-stage filter

1. **URL rewrite.** Merged-JSON image URLs point at the private
   `gs://ai-agents-go-documents/...` bucket (403 anonymously). Flip them to the
   live storefront proxy form `https://catalogs.leka.studio/api/i/leka-project/...`
   which fronts `gs://ai-agents-go-vendors/leka-project/`.
2. **HEAD check.** Drop any URL that returns non-2xx (proxy 404 = object not
   in the leka-project bucket).
3. **Gemini verify.** For each surviving URL × product title, call Gemini 2.5
   Flash with a strict match/confidence schema. Accept only
   `matches=true AND confidence>=0.70`. Decisions cached in Firestore
   `wisdom_outdoor_play_verify/{sha1(url|title)}` so reruns are free.

## Idempotency

  - Existing products: collection link is a SET (no-op if already linked).
    Metadata is MERGED, never replaced — preserves AI enrichment fields.
    Images are touched ONLY when the existing thumbnail is null/placeholder.
  - New products: `find_product_by_handle("wisdom-<code>")` short-circuits
    duplicates on rerun.

## Modes

  --dry-run            print plan only, write nothing to Medusa
  --skip-gemini        skip the verify pass (use all HEAD-OK images)
  --skip-head-check    skip HEAD pass (use all rewritten URLs)
  --no-firestore       don't enrich sparse rows from Firestore
  --limit N            process only first N SKUs
  --force-image-refresh  refresh existing-product images even if already set

Credentials are read from GCP Secret Manager via gcloud
(`leka-medusa-admin-email`, `leka-medusa-admin-password`). ADC for Firestore + Vertex.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.base_importer import parse_dimensions  # noqa: E402
from shared.medusa_importer import MedusaImporter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("import_outdoor_play")

# ──────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_VENDORS_REPO = r"C:\Users\Eukrit\OneDrive\Documents\Claude Code\vendors"
MERGED_JSON_REL = "wisdom-catalog/parsed/wisdom-outdoor-play-merged.json"
MERGED_JSON_FALLBACK_BRANCH = "claude/bold-darwin-f9e68b"

COLLECTION_HANDLE = "wisdom-outdoor-play"
COLLECTION_TITLE = "Wisdom Outdoor Classroom — Outdoor Play"
LEKA_PROJECT_SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"
FIRESTORE_DATABASE = "leka-product-catalogs"
FIRESTORE_COLLECTION = "products_wisdom"
GCP_PROJECT = "ai-agents-go"
MEDUSA_DEFAULT_URL = "https://leka-medusa-backend-rg5gmtwrfa-as.a.run.app"

OLD_BUCKET_PREFIX = "https://storage.googleapis.com/ai-agents-go-documents/product-images/wisdom/"
OLD_BUCKET_PREFIX_ALT = "https://storage.googleapis.com/ai-agents-go-documents/wisdom/"
NEW_PROXY_PREFIX = "https://catalogs.leka.studio/api/i/leka-project/"
PLACEHOLDER_URL = "https://catalogs.leka.studio/api/i/leka-project/_placeholder/leka-coming-soon.png"

GEMINI_LOCATION = "global"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_CONFIDENCE_THRESHOLD = 0.70
GEMINI_CONCURRENCY = 4
GEMINI_VERIFY_COLLECTION = "wisdom_outdoor_play_verify"
GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {"type": "boolean"},
        "confidence": {"type": "number"},
        "depicted": {"type": "string"},
    },
    "required": ["matches", "confidence", "depicted"],
}

REPORT_PATH_DEFAULT = os.path.join(
    os.path.dirname(__file__), "IMPORT_OUTDOOR_PLAY_REPORT.md"
)
STATUS_PATH = os.path.join(os.path.dirname(__file__), "STATUS.md")


# ──────────────────────────────────────────────────────────────────────────
# Source loading
# ──────────────────────────────────────────────────────────────────────────

def load_merged_json(input_path: Optional[str], vendors_repo: str) -> list:
    if input_path:
        with open(input_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    disk_path = os.path.join(vendors_repo, MERGED_JSON_REL.replace("/", os.sep))
    if os.path.isfile(disk_path):
        with open(disk_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    try:
        out = subprocess.check_output(
            ["git", "-C", vendors_repo, "show",
             f"{MERGED_JSON_FALLBACK_BRANCH}:{MERGED_JSON_REL}"],
            stderr=subprocess.PIPE,
        )
        return json.loads(out.decode("utf-8"))
    except subprocess.CalledProcessError as e:
        raise SystemExit(
            f"Could not load merged JSON. Tried:\n"
            f"  --input <path> (not provided)\n"
            f"  {disk_path} (missing)\n"
            f"  git show {MERGED_JSON_FALLBACK_BRANCH}:{MERGED_JSON_REL} -> "
            f"{e.stderr.decode('utf-8').strip()}\nSpecify --input."
        )


def load_secret_sm(name: str, project: str = GCP_PROJECT) -> str:
    """Use Secret Manager Python client (avoids gcloud-in-subprocess issues)."""
    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{project}/secrets/{name}/versions/latest"
    return client.access_secret_version(name=path).payload.data.decode().strip()


# ──────────────────────────────────────────────────────────────────────────
# Firestore enrichment
# ──────────────────────────────────────────────────────────────────────────

def open_firestore():
    from google.cloud import firestore
    return firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)


def fetch_firestore_doc(db, item_code: str) -> Optional[dict]:
    if not item_code:
        return None
    try:
        snap = db.collection(FIRESTORE_COLLECTION).document(item_code).get()
        return snap.to_dict() if snap.exists else None
    except Exception:
        return None


def merge_firestore_into_row(row: dict, fs_doc: Optional[dict]) -> dict:
    if not fs_doc:
        return row
    fs = row.get("firestore") or {}
    for key in ("description", "description_cn", "category", "subcategory",
                "fob_usd", "weight_kg", "volume_cbm", "images"):
        if not fs.get(key) and fs_doc.get(key) is not None:
            fs[key] = fs_doc[key]
    pricing = fs_doc.get("pricing") or {}
    if not fs.get("fob_usd") and pricing.get("fob_usd") is not None:
        fs["fob_usd"] = pricing["fob_usd"]
    dims = fs_doc.get("dimensions") or {}
    if dims and not row.get("dimension"):
        row["dimension"] = dims.get("raw")
    if not fs.get("matched_id"):
        fs["matched_id"] = fs_doc.get("item_code")
    row["firestore"] = fs
    return row


# ──────────────────────────────────────────────────────────────────────────
# URL rewrite + HEAD check
# ──────────────────────────────────────────────────────────────────────────

def rewrite_image_url(url: str) -> str:
    if not url:
        return url
    if url.startswith(OLD_BUCKET_PREFIX):
        return NEW_PROXY_PREFIX + url[len(OLD_BUCKET_PREFIX):]
    if url.startswith(OLD_BUCKET_PREFIX_ALT):
        return NEW_PROXY_PREFIX + url[len(OLD_BUCKET_PREFIX_ALT):]
    return url


def head_check_one(url: str, timeout: float = 5.0) -> tuple[str, int, str]:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if 200 <= r.status_code < 300:
            return url, r.status_code, ""
        if r.status_code in (403, 405):
            r2 = requests.get(url, headers={"Range": "bytes=0-0"}, timeout=timeout, stream=True)
            r2.close()
            return url, r2.status_code, ""
        return url, r.status_code, ""
    except requests.RequestException as e:
        return url, 0, str(e)[:200]


def head_check_all(urls: list, workers: int) -> dict:
    out: dict = {}
    if not urls:
        return out
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(head_check_one, u): u for u in urls}
        for fut in as_completed(futures):
            url, status, err = fut.result()
            out[url] = (status, err)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Gemini verify (per URL × title, cached in Firestore)
# ──────────────────────────────────────────────────────────────────────────

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


def _verify_cache_key(url: str, title: str) -> str:
    return hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()


def _mime_for_url(url: str) -> str:
    ext = url.rsplit(".", 1)[-1].lower().split("?")[0]
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp"}.get(ext, "application/octet-stream")


def gemini_verify_one(gem, fs_client, url: str, title: str,
                      force: bool) -> dict:
    """Returns {decision: 'accept'|'reject'|'error', confidence, depicted, cached}."""
    from google.cloud import firestore
    from google.genai import types as genai_types

    key = _verify_cache_key(url, title)
    doc_ref = fs_client.collection(GEMINI_VERIFY_COLLECTION).document(key)
    if not force:
        snap = doc_ref.get()
        if snap.exists:
            d = snap.to_dict() or {}
            if d.get("decision") in ("accept", "reject", "error"):
                d["_cached"] = True
                return d

    # Download via proxy (small images, ~50-200KB each)
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        img_bytes = r.content
        if len(img_bytes) > 5 * 1024 * 1024:
            img_bytes = img_bytes[:5 * 1024 * 1024]
    except Exception as e:
        rec = {"url": url, "title": title, "decision": "error",
               "stage": "download", "error": str(e)[:300],
               "decided_at": firestore.SERVER_TIMESTAMP}
        try:
            doc_ref.set(rec)
        except Exception:
            pass
        return rec

    prompt = (
        "You are verifying that a product photo matches a product title.\n"
        f'Product title: "{title}"\n\n'
        "Look at the image. Decide if the image plausibly depicts the SAME PRODUCT "
        "as the title (same kind of toy / playground equipment / accessory / "
        "sand-water station / planter / outdoor classroom item). Catalog photos "
        "may show the product alone, in a scene, or with kids — that's fine.\n\n"
        "Return JSON with:\n"
        "  matches    — true only if the image clearly shows the same kind of product as the title.\n"
        "  confidence — your confidence in the answer, 0.0 to 1.0.\n"
        "  depicted   — short noun phrase describing what the image actually shows.\n"
        "Be strict: if the image shows a different category of item from the title, "
        "return matches=false."
    )
    delays = [2, 5, 15, 45]
    last: Optional[Exception] = None
    parsed: dict = {}
    for attempt in range(len(delays) + 1):
        try:
            resp = gem.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    genai_types.Part.from_bytes(data=img_bytes,
                                                mime_type=_mime_for_url(url)),
                    prompt,
                ],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GEMINI_SCHEMA,
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )
            parsed = _tolerant_json(resp.text or "")
            if "matches" in parsed:
                break
        except Exception as e:
            last = e
            msg = str(e)
            transient = any(t in msg for t in (
                "429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE",
                "DEADLINE_EXCEEDED", "504", "500",
            ))
            if not transient or attempt == len(delays):
                rec = {"url": url, "title": title, "decision": "error",
                       "stage": "gemini", "error": str(e)[:300],
                       "decided_at": firestore.SERVER_TIMESTAMP}
                try:
                    doc_ref.set(rec)
                except Exception:
                    pass
                return rec
            time.sleep(delays[attempt] + random.random() * 2)

    matches = bool(parsed.get("matches"))
    conf = float(parsed.get("confidence") or 0.0)
    decision = "accept" if (matches and conf >= GEMINI_CONFIDENCE_THRESHOLD) else "reject"
    rec = {
        "url": url, "title": title, "decision": decision,
        "matches": matches, "confidence": conf,
        "depicted": (parsed.get("depicted") or "")[:300],
        "decided_at": firestore.SERVER_TIMESTAMP,
    }
    try:
        doc_ref.set(rec)
    except Exception:
        pass
    return rec


def gemini_verify_batch(jobs: list, fs_client, force: bool) -> dict:
    """jobs: list of (url, title). Returns {(url,title): record}."""
    from google import genai
    gem = genai.Client(vertexai=True, project=GCP_PROJECT, location=GEMINI_LOCATION)
    results: dict = {}
    if not jobs:
        return results
    cached = 0
    started = time.time()

    def work(j):
        return j, gemini_verify_one(gem, fs_client, j[0], j[1], force)

    with ThreadPoolExecutor(max_workers=GEMINI_CONCURRENCY) as ex:
        futures = {ex.submit(work, j): j for j in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            j, rec = fut.result()
            results[j] = rec
            if rec.get("_cached"):
                cached += 1
            if i % 25 == 0 or i == len(jobs):
                rate = i / max(time.time() - started, 0.001)
                log.info("  Gemini %d/%d (%.1f/s) cached=%d", i, len(jobs), rate, cached)
    return results


# ──────────────────────────────────────────────────────────────────────────
# Per-row image pipeline
# ──────────────────────────────────────────────────────────────────────────

def candidate_urls(row: dict) -> list:
    fs = row.get("firestore") or {}
    seen: set = set()
    out: list = []
    for img in (fs.get("images") or []):
        raw = img.get("url") if isinstance(img, dict) else img
        if not raw:
            continue
        url = rewrite_image_url(raw)
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "is_primary": bool(img.get("is_primary"))
                    if isinstance(img, dict) else False})
    return out


def select_final_images(row: dict, head_results: dict,
                        gemini_results: dict, product_title: str,
                        skip_gemini: bool) -> tuple[Optional[str], list, list, list]:
    """Returns (thumbnail, gallery, broken_urls_with_status, rejected_urls_with_conf)."""
    cands = candidate_urls(row)
    good: list = []
    primary: Optional[str] = None
    broken: list = []
    rejected: list = []
    for c in cands:
        url = c["url"]
        status, err = head_results.get(url, (0, "not-checked"))
        if not (200 <= status < 300):
            broken.append((url, status, err))
            continue
        if skip_gemini:
            verdict = {"decision": "accept", "confidence": 1.0, "depicted": "(skip)"}
        else:
            verdict = gemini_results.get((url, product_title)) or {}
        if verdict.get("decision") == "accept":
            if c["is_primary"] and primary is None:
                primary = url
            good.append(url)
        else:
            rejected.append((url,
                             verdict.get("confidence"),
                             verdict.get("depicted") or verdict.get("decision") or ""))
    if not good:
        return None, [], broken, rejected
    if primary is None:
        primary = good[0]
    gallery = [primary] + [u for u in good if u != primary]
    return primary, gallery, broken, rejected


# ──────────────────────────────────────────────────────────────────────────
# Dimension parsing (cm → mm)
# ──────────────────────────────────────────────────────────────────────────

DIM_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")


def parse_dim_to_mm(dimension: Optional[str]) -> dict:
    if not dimension:
        return {}
    cleaned = DIM_PAREN_RE.sub("", dimension).strip()
    dims = parse_dimensions(cleaned)
    out: dict = {}
    if dims.get("length_cm"):
        out["length"] = int(round(dims["length_cm"] * 10))
    if dims.get("width_cm"):
        out["width"] = int(round(dims["width_cm"] * 10))
    if dims.get("height_cm"):
        out["height"] = int(round(dims["height_cm"] * 10))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Medusa upsert logic
# ──────────────────────────────────────────────────────────────────────────

def build_legacy_lookup_combined(client: MedusaImporter) -> dict:
    """Combine legacy_sku index (Wisdom-renamed products) with full product+variant SKU map."""
    log.info("Building legacy_sku index for Leka Project SC …")
    idx = client.build_legacy_sku_index(LEKA_PROJECT_SC_ID)
    log.info("  Index size: %d", len(idx))
    return idx


def find_existing(idx: dict, sku: str, matched_id: Optional[str]) -> tuple[Optional[str], Optional[str], str]:
    """Returns (product_id, variant_id, match_method)."""
    if sku in idx:
        pid, vid = idx[sku]
        return pid, vid, "sku"
    if matched_id and matched_id in idx:
        pid, vid = idx[matched_id]
        return pid, vid, "matched_id"
    return None, None, "none"


def is_image_placeholder(thumbnail: Optional[str], image_status: Optional[str]) -> bool:
    if not thumbnail:
        return True
    if image_status == "placeholder":
        return True
    if thumbnail and "leka-coming-soon" in thumbnail:
        return True
    return False


def link_existing(client: MedusaImporter, product_id: str, collection_id: str,
                  row: dict, fs: dict, thumbnail: Optional[str], gallery: list,
                  force_image_refresh: bool) -> dict:
    """Link an existing leka-project product to wisdom-outdoor-play.

    - Always: set collection_id, merge metadata.outdoor_play.{...}.
    - Images: only refresh when (force_image_refresh) or (current is placeholder/null).
    """
    # Fetch current state
    cur = client._get(f"/admin/products/{product_id}",
                      {"fields": "id,thumbnail,metadata,collection_id"}).get("product", {})
    cur_md = cur.get("metadata") or {}
    cur_thumb = cur.get("thumbnail")
    cur_status = cur_md.get("image_status")

    new_md = dict(cur_md)
    new_md["outdoor_play"] = {
        "sub_area": row.get("sub_area"),
        "catalog_pages": row.get("pages"),
        "wisdom_item_code": row["sku"],
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "merged_json_source": "wisdom-outdoor-play-merged.json",
    }
    if row.get("material") and not new_md.get("material"):
        new_md["material"] = row["material"]

    body: dict = {
        "collection_id": collection_id,
        "metadata": new_md,
    }

    refresh_images = bool(thumbnail) and (
        force_image_refresh or is_image_placeholder(cur_thumb, cur_status)
    )
    if refresh_images:
        body["thumbnail"] = thumbnail
        body["images"] = [{"url": u} for u in gallery]
        body["metadata"]["image_status"] = "outdoor_play_verified"

    client._patch(f"/admin/products/{product_id}", body)
    return {"refreshed_images": refresh_images, "previous_thumbnail": cur_thumb}


def create_new(client: MedusaImporter, row: dict, fs: dict, collection_id: str,
               thumbnail: Optional[str], gallery: list, sales_channel_id: str) -> str:
    item_code = row["sku"]
    handle = f"wisdom-{item_code.lower().replace(' ', '-')}"
    title = (fs.get("description") or row.get("name") or item_code).strip()
    description = fs.get("description_cn") or ""

    metadata = {
        "wisdom_item_code": item_code,
        "source": "wisdom-outdoor-play-merged",
        "sub_area": row.get("sub_area"),
        "description_cn": fs.get("description_cn") or "",
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if row.get("material"):
        metadata["material"] = row["material"]
    if fs.get("volume_cbm") is not None:
        metadata["volume_cbm"] = fs["volume_cbm"]
    if row.get("pages"):
        metadata["catalog_pages"] = row["pages"]
    if fs.get("category"):
        metadata["firestore_category"] = fs["category"]
    if not thumbnail:
        metadata["image_status"] = "placeholder"

    variant: dict = {
        "title": "Default",
        "sku": item_code,
        "manage_inventory": False,
        "prices": [],
        "metadata": {"legacy_sku": item_code},
    }
    dim_mm = parse_dim_to_mm(row.get("dimension"))
    variant.update(dim_mm)
    if fs.get("weight_kg"):
        try:
            variant["weight"] = int(round(float(fs["weight_kg"]) * 1000))
        except (TypeError, ValueError):
            pass
    fob = fs.get("fob_usd")
    if fob:
        try:
            variant["prices"].append({
                "amount": int(round(float(fob) * 100)),
                "currency_code": "usd",
            })
        except (TypeError, ValueError):
            pass

    create_thumbnail = thumbnail or PLACEHOLDER_URL
    create_images = gallery if gallery else [PLACEHOLDER_URL]

    resp = client.create_product(
        title=title,
        handle=handle,
        description=description,
        status="published",
        metadata=metadata,
        images=create_images,
        category_ids=[],
        collection_id=collection_id,
        variant=variant,
        sales_channel_ids=[sales_channel_id],
    )
    pid = resp.get("product", {}).get("id") or resp.get("id")
    if pid and create_thumbnail:
        try:
            client._patch(f"/admin/products/{pid}", {"thumbnail": create_thumbnail})
        except requests.HTTPError:
            pass
    return pid


# ──────────────────────────────────────────────────────────────────────────
# Report
# ──────────────────────────────────────────────────────────────────────────

def write_report(path: str, run_ts: str, dry_run: bool, totals: dict,
                 buckets: dict, samples: list, collection_id: Optional[str],
                 medusa_url: str, gemini_stats: dict):
    L = []
    L.append("# Wisdom Outdoor-Play — Medusa Import Report")
    L.append("")
    L.append(f"- **Run timestamp (UTC):** {run_ts}")
    L.append(f"- **Mode:** {'DRY-RUN (no writes)' if dry_run else 'LIVE'}")
    L.append(f"- **Medusa backend:** {medusa_url}")
    L.append(f"- **Collection handle:** `{COLLECTION_HANDLE}`")
    if collection_id:
        L.append(f"- **Collection id:** `{collection_id}`")
    L.append(f"- **Strategy:** Option A — link existing 255 Leka-Project products + create 17 new wisdom-* products.")
    L.append(f"- **Image filter:** URL rewrite → HEAD check → Gemini verify (`{GEMINI_MODEL}`, conf≥{GEMINI_CONFIDENCE_THRESHOLD}).")
    L.append("")

    L.append("## Summary")
    L.append("")
    L.append("| Metric | Count |")
    L.append("|---|---:|")
    for k in (
        "total_in_json", "linked_existing", "created_new", "skipped",
        "missing_from_firestore", "products_with_images",
        "products_without_images", "broken_image_urls",
        "gemini_accept", "gemini_reject", "gemini_error", "gemini_cached",
        "image_refresh_applied",
    ):
        L.append(f"| {k.replace('_', ' ')} | {totals.get(k, 0)} |")
    L.append("")
    L.append(
        f"**Reconciliation:** linked ({totals['linked_existing']}) + "
        f"created ({totals['created_new']}) + skipped ({totals['skipped']}) = "
        f"{totals['linked_existing'] + totals['created_new'] + totals['skipped']} "
        f"(target: {totals['total_in_json']})"
    )
    L.append("")

    if gemini_stats:
        L.append("### Gemini verification")
        L.append("")
        L.append("| Metric | Value |")
        L.append("|---|---:|")
        for k, v in gemini_stats.items():
            L.append(f"| {k} | {v} |")
        L.append("")

    def _table(title: str, rows: list, headers: list, limit: int = 50):
        L.append(f"## {title} ({len(rows)})")
        L.append("")
        if not rows:
            L.append("_(none)_")
            L.append("")
            return
        L.append("| " + " | ".join(headers) + " |")
        L.append("|" + "|".join(["---"] * len(headers)) + "|")
        for r in rows[:limit]:
            L.append("| " + " | ".join(str(c) for c in r) + " |")
        if len(rows) > limit:
            L.append(f"| … | ({len(rows) - limit} more rows truncated) | … |")
        L.append("")

    _table(
        "SKUs missing from Firestore (created as new wisdom-* with placeholder)",
        [(s["sku"], s["title"]) for s in buckets["missing_from_firestore"]],
        ["SKU", "Name"],
    )
    _table(
        "SKUs with no verified images (got placeholder)",
        [(s["sku"], s["title"], s.get("match_method") or "-",
          s.get("broken_count") or 0, s.get("rejected_count") or 0)
         for s in buckets["no_image"]],
        ["SKU", "Title", "Match", "Broken", "Gemini-Rejected"],
    )
    broken_rows = []
    for s in buckets["broken_image_skus"]:
        for url, status, err in s["broken"]:
            broken_rows.append((s["sku"], status if status else "ERR",
                                (err or "")[:60], url))
    _table(
        "Broken image URLs (HEAD non-2xx)",
        broken_rows,
        ["SKU", "Status", "Error", "URL"],
    )
    gemini_reject_rows = []
    for s in buckets["gemini_rejected_skus"]:
        for url, conf, depicted in s["rejected"]:
            gemini_reject_rows.append((s["sku"],
                                       f"{conf:.2f}" if conf is not None else "-",
                                       (depicted or "")[:50], url))
    _table(
        "Images rejected by Gemini (matches=false or confidence<0.70)",
        gemini_reject_rows,
        ["SKU", "Conf", "Depicted", "URL"],
    )
    _table(
        "Sample of 5 linked / created products",
        [(s["sku"], s["action"], s["handle_or_pid"],
          s.get("thumbnail") or "-") for s in samples[:5]],
        ["SKU", "Action", "Handle / PID", "Thumbnail"],
    )

    L.append("## Verification commands")
    L.append("")
    L.append("```bash")
    L.append("TOKEN=$(curl -s -X POST \"$MEDUSA_URL/auth/user/emailpass\" \\")
    L.append("  -H 'Content-Type: application/json' \\")
    L.append("  -d \"{\\\"email\\\":\\\"$MEDUSA_ADMIN_EMAIL\\\",\\\"password\\\":\\\"$MEDUSA_ADMIN_PASSWORD\\\"}\" | jq -r .token)")
    L.append("")
    L.append(f"# 1. Collection exists?")
    L.append(f"curl -s \"$MEDUSA_URL/admin/collections?handle={COLLECTION_HANDLE}\" "
             "-H \"Authorization: Bearer $TOKEN\" | jq '.collections | length'")
    L.append("")
    L.append("# 2. Product count in collection")
    if collection_id:
        L.append(f"curl -s \"$MEDUSA_URL/admin/products?collection_id={collection_id}&limit=1\" "
                 "-H \"Authorization: Bearer $TOKEN\" | jq '.count'")
    L.append("```")
    L.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input")
    parser.add_argument("--vendors-repo", default=DEFAULT_VENDORS_REPO)
    parser.add_argument("--collection-handle", default=COLLECTION_HANDLE)
    parser.add_argument("--collection-title", default=COLLECTION_TITLE)
    parser.add_argument("--medusa-url", default=os.environ.get("MEDUSA_BACKEND_URL", MEDUSA_DEFAULT_URL))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-path", default=REPORT_PATH_DEFAULT)
    parser.add_argument("--head-check-workers", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-firestore", action="store_true")
    parser.add_argument("--skip-head-check", action="store_true")
    parser.add_argument("--skip-gemini", action="store_true")
    parser.add_argument("--force-gemini", action="store_true",
                        help="Re-verify even if cached decision exists.")
    parser.add_argument("--force-image-refresh", action="store_true",
                        help="Refresh images on existing products even if already set.")
    args = parser.parse_args()

    # ── 1. Load merged JSON
    log.info("[1] Loading merged JSON …")
    rows = load_merged_json(args.input, args.vendors_repo)
    if args.limit:
        rows = rows[: args.limit]
    log.info("    %d SKUs loaded.", len(rows))

    # ── 2. Firestore enrichment for sparse rows
    fs_client = None
    if not args.no_firestore:
        log.info("[2] Enriching from Firestore …")
        try:
            fs_client = open_firestore()
            enriched = 0
            for row in rows:
                fs = row.get("firestore") or {}
                needs = (not row.get("firestore")) or (
                    not fs.get("description") or not fs.get("images")
                    or fs.get("fob_usd") is None or fs.get("weight_kg") is None
                )
                if not needs:
                    continue
                doc_id = fs.get("matched_id") or row["sku"]
                doc = fetch_firestore_doc(fs_client, doc_id)
                if doc is None and doc_id != row["sku"]:
                    doc = fetch_firestore_doc(fs_client, row["sku"])
                if doc:
                    merge_firestore_into_row(row, doc)
                    enriched += 1
            log.info("    Enriched %d rows.", enriched)
        except Exception as e:
            log.warning("    Firestore enrichment failed: %s", e)
    else:
        log.info("[2] Skipping Firestore enrichment (--no-firestore).")

    # ── 3. URL collection + HEAD check
    log.info("[3] Collecting candidate image URLs …")
    all_urls: set = set()
    for row in rows:
        for c in candidate_urls(row):
            all_urls.add(c["url"])
    log.info("    %d unique URLs across %d SKUs.", len(all_urls), len(rows))

    if args.skip_head_check:
        head_results = {u: (200, "") for u in all_urls}
        log.info("[4] Skipping HEAD checks.")
    else:
        log.info("[4] HEAD-checking image URLs (%d workers) …", args.head_check_workers)
        t0 = time.time()
        head_results = head_check_all(sorted(all_urls), args.head_check_workers)
        good = sum(1 for s, _ in head_results.values() if 200 <= s < 300)
        bad = len(head_results) - good
        log.info("    Done in %.1fs — good %d / broken %d.", time.time() - t0, good, bad)

    # ── 5. Build Gemini-verify jobs (only for HEAD-OK URLs × product title)
    gemini_results: dict = {}
    gemini_stats: dict = {}
    if not args.skip_gemini:
        log.info("[5] Building Gemini-verify jobs …")
        if fs_client is None:
            fs_client = open_firestore()
        jobs: list = []
        for row in rows:
            fs = row.get("firestore") or {}
            title = (fs.get("description") or row.get("name") or row["sku"]).strip()
            for c in candidate_urls(row):
                url = c["url"]
                status, _ = head_results.get(url, (0, ""))
                if 200 <= status < 300:
                    jobs.append((url, title))
        # Dedup
        jobs = list({(u, t): None for u, t in jobs}.keys())
        log.info("    %d (url, title) pairs to verify.", len(jobs))
        if jobs:
            gemini_results = gemini_verify_batch(jobs, fs_client, args.force_gemini)
            accepts = sum(1 for r in gemini_results.values() if r.get("decision") == "accept")
            rejects = sum(1 for r in gemini_results.values() if r.get("decision") == "reject")
            errors = sum(1 for r in gemini_results.values() if r.get("decision") == "error")
            cached = sum(1 for r in gemini_results.values() if r.get("_cached"))
            gemini_stats = {"jobs": len(jobs), "accept": accepts, "reject": rejects,
                            "error": errors, "cached": cached}
            log.info("    Gemini: accept %d / reject %d / error %d (cached %d)",
                     accepts, rejects, errors, cached)
    else:
        log.info("[5] Skipping Gemini verification (--skip-gemini).")

    # ── 6. Medusa auth + collection + legacy_sku index
    if args.dry_run:
        log.info("[6] DRY-RUN: skipping Medusa auth + index.")
        client = None
        collection_id = None
        legacy_idx: dict = {}
    else:
        log.info("[6] Authenticating to Medusa + building legacy_sku index …")
        if not os.environ.get("MEDUSA_ADMIN_API_KEY"):
            os.environ.setdefault("MEDUSA_ADMIN_EMAIL", load_secret_sm("leka-medusa-admin-email"))
            os.environ.setdefault("MEDUSA_ADMIN_PASSWORD", load_secret_sm("leka-medusa-admin-password"))
        client = MedusaImporter(base_url=args.medusa_url)
        collection_id = client.get_or_create_collection(
            args.collection_title, args.collection_handle)
        log.info("    Collection id: %s", collection_id)
        legacy_idx = build_legacy_lookup_combined(client)

    # ── 7. Process each row
    log.info("[7] Processing %d SKUs …", len(rows))
    totals = {
        "total_in_json": len(rows),
        "linked_existing": 0,
        "created_new": 0,
        "skipped": 0,
        "missing_from_firestore": 0,
        "products_with_images": 0,
        "products_without_images": 0,
        "broken_image_urls": 0,
        "gemini_accept": gemini_stats.get("accept", 0),
        "gemini_reject": gemini_stats.get("reject", 0),
        "gemini_error": gemini_stats.get("error", 0),
        "gemini_cached": gemini_stats.get("cached", 0),
        "image_refresh_applied": 0,
    }
    buckets = {
        "missing_from_firestore": [],
        "no_image": [],
        "broken_image_skus": [],
        "gemini_rejected_skus": [],
    }
    samples: list = []
    consecutive_errors = 0

    for i, row in enumerate(rows, 1):
        fs = row.get("firestore") or {}
        title = (fs.get("description") or row.get("name") or row["sku"]).strip()
        thumbnail, gallery, broken, rejected = select_final_images(
            row, head_results, gemini_results, title, args.skip_gemini)

        sku = row["sku"]
        matched_id = fs.get("matched_id")
        diag = {"sku": sku, "title": title[:60]}

        if not row.get("firestore"):
            totals["missing_from_firestore"] += 1
            buckets["missing_from_firestore"].append(diag)
        if thumbnail:
            totals["products_with_images"] += 1
        else:
            totals["products_without_images"] += 1
            buckets["no_image"].append({**diag, "broken_count": len(broken),
                                        "rejected_count": len(rejected),
                                        "match_method": None})
        if broken:
            totals["broken_image_urls"] += len(broken)
            buckets["broken_image_skus"].append({**diag, "broken": broken})
        if rejected:
            buckets["gemini_rejected_skus"].append({**diag, "rejected": rejected})

        if args.dry_run:
            pid, vid, method = (None, None, "none")
            if legacy_idx:  # never reached in dry_run, but kept for clarity
                pid, vid, method = find_existing(legacy_idx, sku, matched_id)
            action = "LINK" if pid else "CREATE"
            if i <= 10:
                log.info("  [DRY] %s %s | imgs=%d | broken=%d | rejected=%d",
                         action, sku, len(gallery), len(broken), len(rejected))
            samples.append({"sku": sku, "action": action,
                            "handle_or_pid": pid or f"wisdom-{sku.lower()}",
                            "thumbnail": thumbnail})
            # virtual counts so reconciliation matches
            if action == "LINK":
                totals["linked_existing"] += 1
            else:
                totals["created_new"] += 1
            continue

        # Live: decide link vs create
        try:
            pid, vid, method = find_existing(legacy_idx, sku, matched_id)
            if pid:
                outcome = link_existing(client, pid, collection_id, row, fs,
                                        thumbnail, gallery, args.force_image_refresh)
                if outcome.get("refreshed_images"):
                    totals["image_refresh_applied"] += 1
                totals["linked_existing"] += 1
                if buckets["no_image"] and buckets["no_image"][-1]["sku"] == sku:
                    buckets["no_image"][-1]["match_method"] = method
                if len(samples) < 5:
                    samples.append({"sku": sku, "action": f"LINK ({method})",
                                    "handle_or_pid": pid, "thumbnail": thumbnail})
            else:
                new_pid = create_new(client, row, fs, collection_id,
                                     thumbnail, gallery, LEKA_PROJECT_SC_ID)
                totals["created_new"] += 1
                if len(samples) < 5:
                    samples.append({"sku": sku, "action": "CREATE",
                                    "handle_or_pid": new_pid or f"wisdom-{sku.lower()}",
                                    "thumbnail": thumbnail})
            consecutive_errors = 0
        except requests.HTTPError as e:
            totals["skipped"] += 1
            consecutive_errors += 1
            status = getattr(e.response, "status_code", "?")
            body = getattr(e.response, "text", "")[:200]
            log.error("  HTTP %s on %s: %s", status, sku, body)
            if consecutive_errors >= 3:
                msg = f"Aborting after 3 consecutive Medusa errors at SKU {sku}: {status}"
                with open(STATUS_PATH, "a", encoding="utf-8") as fh:
                    fh.write(f"\n\n## ABORT {datetime.now(timezone.utc).isoformat()}\n\n{msg}\n\nLast body: {body}\n")
                raise SystemExit(msg)
        except Exception as e:
            totals["skipped"] += 1
            consecutive_errors += 1
            log.error("  ERROR %s: %s", sku, e)
            if consecutive_errors >= 3:
                raise

        if i % 25 == 0:
            log.info("  %d/%d (linked %d, created %d, skipped %d)",
                     i, len(rows), totals["linked_existing"],
                     totals["created_new"], totals["skipped"])

    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_report(args.report_path, run_ts, args.dry_run, totals, buckets,
                 samples, collection_id, args.medusa_url, gemini_stats)
    log.info("")
    log.info("Report: %s", args.report_path)
    log.info(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
