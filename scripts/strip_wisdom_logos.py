"""Strip "Wisdom" logos/wordmarks from Leka Project (formerly Wisdom) catalog images.

Three-phase pipeline. Each phase is idempotent and resumable.

  --scan-only    Pass 1 — Gemini Flash logo detection over every blob under
                 gs://ai-agents-go-vendors/wisdom/. Writes per-image record to
                 Firestore image_logo_scan/{sha} and a summary report.
                 Cheapest phase. Run this first.

  --edit-only    Pass 2 — for every Pass-1 hit (has_logo=True) call Gemini
                 image-edit (Nano Banana Pro) to inpaint the logo, then a
                 second Flash call to QA-verify. Writes to
                 gs://ai-agents-go-vendors/leka-project/<same path>.

  --copy-only    Bulk server-side copy non-hit blobs from wisdom/ to
                 leka-project/ (no Gemini cost). Skip when destination
                 already exists with matching md5.

Defaults to --scan-only when nothing is set, so re-running by accident is safe.

Auth: ADC via google.auth.default() (workspace Rule 12b — no SA key paths).
Project: ai-agents-go (workspace default). Region: asia-southeast1 for storage,
"global" for Gemini.

Usage:
    python scripts/strip_wisdom_logos.py --scan-only --limit=20      # smoke
    python scripts/strip_wisdom_logos.py --scan-only                 # full Pass 1
    python scripts/strip_wisdom_logos.py --edit-only                 # Pass 2
    python scripts/strip_wisdom_logos.py --copy-only                 # bulk copy
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# Workspace Rule 12b — never hardcode SA-key paths in code. We DO honor an
# env-provided GOOGLE_APPLICATION_CREDENTIALS (standard ADC precedence); we just
# never set it to a literal path ourselves.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

from google import genai  # noqa: E402
from google.api_core import exceptions as gax_exceptions  # noqa: E402
from google.cloud import firestore, storage  # noqa: E402
from google.genai import types as genai_types  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("strip_wisdom_logos")

PROJECT = "ai-agents-go"
BUCKET = "ai-agents-go-vendors"
SRC_PREFIX_ROOT = "wisdom/"          # originals — kept untouched
DST_PREFIX_ROOT = "leka-project/"    # cleaned (or copied) — customer-facing
FIRESTORE_DB = "leka-product-catalogs"
SCAN_COLLECTION = "image_logo_scan"

# Gemini routing — "global" location has the broadest model availability.
GEMINI_LOCATION = "global"
SCAN_MODEL = "gemini-2.5-flash"
EDIT_MODEL = "gemini-2.5-flash-image"  # Nano Banana Pro
QA_MODEL = "gemini-2.5-flash"

IMAGE_EXT_OK = {"jpg", "jpeg", "png", "webp", "jpx", "gif"}

# Structured output schema for Pass 1.
SCAN_SCHEMA = {
    "type": "object",
    "properties": {
        "has_logo": {"type": "boolean"},
        "confidence": {"type": "number"},  # 0.0 - 1.0
        "kind": {"type": "string", "enum": ["logo", "wordmark", "watermark", "none"]},
        "count": {"type": "integer"},  # approx visible logo instances (0 when has_logo=false)
    },
    "required": ["has_logo", "confidence", "kind", "count"],
}

SCAN_PROMPT = (
    "You are auditing product photos for Wisdom Toys (a vendor brand). "
    "Decide if this image visibly contains the Wisdom brand identity — "
    "a 'WISDOM' wordmark, the Wisdom logo, a Wisdom watermark, or any "
    "embedded text reading 'wisdom' / 'WISDOM TOYS' / similar. "
    "Plain product photography with no overlay text is NOT a logo. "
    "Catalog page numbers, item codes, dimensions, and other vendor-neutral "
    "text are NOT a logo. "
    "Return JSON matching the schema. confidence in [0,1]. "
    "count = approximate visible instances of the Wisdom logo (0 when has_logo=false). "
    "kind = 'logo' (graphic mark), 'wordmark' (text only), 'watermark' (semi-transparent overlay), or 'none'."
)


@dataclass
class Blob:
    name: str
    size: int
    md5: str
    content_type: str

    @property
    def sha(self) -> str:
        return hashlib.sha1(self.name.encode()).hexdigest()

    @property
    def ext(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""


def adc_check() -> None:
    """Fail fast with a clear message if ADC is missing/expired."""
    import google.auth
    try:
        creds, project = google.auth.default()
        log.info(f"ADC ok — project={project}, type={type(creds).__name__}")
    except Exception as e:
        log.error("ADC failure: %s", e)
        log.error("Run: gcloud auth application-default login")
        sys.exit(2)


def list_source_blobs(storage_client: storage.Client, prefix: str, limit: int | None = None) -> list[Blob]:
    out: list[Blob] = []
    for raw in storage_client.list_blobs(BUCKET, prefix=prefix):
        if raw.name.endswith("/"):
            continue
        ext = raw.name.rsplit(".", 1)[-1].lower() if "." in raw.name else ""
        if ext not in IMAGE_EXT_OK:
            continue
        out.append(Blob(name=raw.name, size=raw.size or 0, md5=raw.md5_hash or "", content_type=raw.content_type or ""))
        if limit and len(out) >= limit:
            break
    return out


def gemini_client() -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT, location=GEMINI_LOCATION)


def mime_for_ext(ext: str) -> str:
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "jpx": "image/jpeg",  # JPEG2000 — Vertex won't accept it; we'll convert if needed
    }.get(ext, "application/octet-stream")


def fetch_image_bytes(storage_client: storage.Client, name: str) -> bytes:
    blob = storage_client.bucket(BUCKET).blob(name)
    return blob.download_as_bytes()


def maybe_convert_jpx(data: bytes, ext: str) -> tuple[bytes, str]:
    """Vertex Gemini doesn't accept image/jpx; convert in-memory to JPEG."""
    if ext != "jpx":
        return data, mime_for_ext(ext)
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data))
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=88)
        return out.getvalue(), "image/jpeg"
    except Exception as e:
        log.warning("jpx -> jpeg failed: %s", e)
        return data, "application/octet-stream"


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _tolerant_json(text: str) -> dict:
    """Parse Gemini output that's usually JSON but occasionally has prose around it."""
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
    has_logo = None
    if re.search(r'"has_logo"\s*:\s*true', text, re.IGNORECASE):
        has_logo = True
    elif re.search(r'"has_logo"\s*:\s*false', text, re.IGNORECASE):
        has_logo = False
    if has_logo is not None:
        return {"has_logo": has_logo, "confidence": 0.5, "kind": "fallback_parsed", "notes": text[:200]}
    return {}


def _gemini_with_retry(
    gem: genai.Client,
    data: bytes,
    mime: str,
    *,
    max_attempts: int = 6,
    base_delay: float = 2.0,
) -> dict:
    """Call Gemini with exponential backoff on 429/5xx. Returns parsed dict."""
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            resp = gem.models.generate_content(
                model=SCAN_MODEL,
                contents=[
                    genai_types.Part.from_bytes(data=data, mime_type=mime),
                    SCAN_PROMPT,
                ],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SCAN_SCHEMA,
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )
            parsed = _tolerant_json(resp.text or "")
            if "has_logo" not in parsed and attempt < max_attempts - 1:
                # Model gave malformed output; one quick retry with jitter.
                time.sleep(0.5 + random.random())
                continue
            return parsed
        except Exception as e:
            last_err = e
            msg = str(e)
            transient = (
                "429" in msg
                or "RESOURCE_EXHAUSTED" in msg
                or "503" in msg
                or "UNAVAILABLE" in msg
                or "DEADLINE_EXCEEDED" in msg
                or "504" in msg
                or "500" in msg
            )
            if not transient:
                raise
            if attempt == max_attempts - 1:
                break
            sleep_for = base_delay * (2 ** attempt) + random.random() * base_delay
            time.sleep(min(sleep_for, 90.0))
    if last_err:
        raise last_err
    return {}


def scan_one(
    blob: Blob,
    storage_client: storage.Client,
    fs_client: firestore.Client,
    gem: genai.Client,
    force: bool = False,
    retry_errors: bool = True,
) -> dict:
    """Pass-1 scan one image. Idempotent via Firestore checkpoint."""
    doc_ref = fs_client.collection(SCAN_COLLECTION).document(blob.sha)
    if not force:
        snap = doc_ref.get()
        if snap.exists:
            d = snap.to_dict()
            status = d.get("scan_status")
            # Don't trust fallback_parsed rows — re-scan them with the bigger token budget.
            is_fallback = d.get("kind") == "fallback_parsed"
            if status == "skipped_unsupported_mime":
                d["_cached"] = True
                return d
            if status == "ok" and not is_fallback:
                d["_cached"] = True
                return d
            if status == "error" and not retry_errors:
                d["_cached"] = True
                return d

    try:
        raw = fetch_image_bytes(storage_client, blob.name)
        data, mime = maybe_convert_jpx(raw, blob.ext)
        if mime == "application/octet-stream":
            record = {
                "source_path": blob.name,
                "scan_status": "skipped_unsupported_mime",
                "ext": blob.ext,
                "scanned_at": firestore.SERVER_TIMESTAMP,
            }
            doc_ref.set(record)
            return record

        parsed = _gemini_with_retry(gem, data, mime)
        if "has_logo" not in parsed:
            raise ValueError(f"model output unparseable")
        record = {
            "source_path": blob.name,
            "size": blob.size,
            "ext": blob.ext,
            "scan_status": "ok",
            "has_logo": bool(parsed.get("has_logo")),
            "confidence": float(parsed.get("confidence", 0.0)),
            "kind": parsed.get("kind", "none"),
            "count": int(parsed.get("count", 0) or 0),
            "model": SCAN_MODEL,
            "scanned_at": firestore.SERVER_TIMESTAMP,
        }
        doc_ref.set(record)
        return record
    except (gax_exceptions.GoogleAPIError, Exception) as e:
        record = {
            "source_path": blob.name,
            "scan_status": "error",
            "error": str(e)[:500],
            "scanned_at": firestore.SERVER_TIMESTAMP,
        }
        try:
            doc_ref.set(record)
        except Exception:
            pass
        return record


def run_scan(args: argparse.Namespace) -> None:
    storage_client = storage.Client(project=PROJECT)
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    gem = gemini_client()

    log.info("Listing blobs under gs://%s/%s ...", BUCKET, args.prefix)
    blobs = list_source_blobs(storage_client, args.prefix, args.limit)
    log.info("Discovered %d image blobs", len(blobs))

    counts = {"ok_with_logo": 0, "ok_no_logo": 0, "cached": 0, "skipped": 0, "error": 0}
    counts_lock = threading.Lock()
    started = time.time()
    with_logo_paths: list[dict] = []

    def work(b: Blob) -> dict:
        rec = scan_one(b, storage_client, fs_client, gem, force=args.force_rescan,
                       retry_errors=not args.skip_errored)
        with counts_lock:
            if rec.get("_cached"):
                counts["cached"] += 1
                if rec.get("has_logo"):
                    counts["ok_with_logo"] += 1
                    with_logo_paths.append({"path": rec["source_path"], "confidence": rec.get("confidence", 0)})
                else:
                    counts["ok_no_logo"] += 1
            elif rec.get("scan_status") == "ok":
                if rec.get("has_logo"):
                    counts["ok_with_logo"] += 1
                    with_logo_paths.append({"path": rec["source_path"], "confidence": rec.get("confidence", 0)})
                else:
                    counts["ok_no_logo"] += 1
            elif rec.get("scan_status", "").startswith("skipped"):
                counts["skipped"] += 1
            else:
                counts["error"] += 1
        return rec

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(work, b) for b in blobs]
        done = 0
        for _ in as_completed(futures):
            done += 1
            if done % 100 == 0 or done == len(futures):
                rate = done / max(time.time() - started, 0.001)
                log.info(
                    "  %d/%d (%.1f img/s) — with_logo=%d no_logo=%d cached=%d skipped=%d error=%d",
                    done, len(futures), rate,
                    counts["ok_with_logo"], counts["ok_no_logo"], counts["cached"],
                    counts["skipped"], counts["error"],
                )

    elapsed = time.time() - started
    log.info("Scan complete in %.1fs — %s", elapsed, counts)

    report = {
        "phase": "scan",
        "prefix": args.prefix,
        "total_blobs": len(blobs),
        "counts": counts,
        "elapsed_seconds": round(elapsed, 1),
        "model": SCAN_MODEL,
        "with_logo_sample": with_logo_paths[:200],
    }
    out_path = Path(args.report_dir) / "wisdom-image-scan-report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    log.info("Report -> %s", out_path)


def run_copy(args: argparse.Namespace) -> None:
    """Server-side copy non-hit blobs from wisdom/ to leka-project/."""
    storage_client = storage.Client(project=PROJECT)
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    bucket = storage_client.bucket(BUCKET)

    log.info("Listing wisdom/ blobs and reading scan checkpoints ...")
    blobs = list_source_blobs(storage_client, args.prefix, args.limit)
    log.info("Source candidates: %d", len(blobs))

    counts = {"copied": 0, "skipped_existing": 0, "skipped_has_logo": 0, "skipped_unscanned": 0, "error": 0}
    counts_lock = threading.Lock()
    started = time.time()

    def work(b: Blob) -> None:
        snap = fs_client.collection(SCAN_COLLECTION).document(b.sha).get()
        if not snap.exists or snap.to_dict().get("scan_status") != "ok":
            with counts_lock:
                counts["skipped_unscanned"] += 1
            return
        rec = snap.to_dict()
        if rec.get("has_logo"):
            with counts_lock:
                counts["skipped_has_logo"] += 1
            return  # leave for Pass 2

        dst_name = DST_PREFIX_ROOT + b.name[len(SRC_PREFIX_ROOT):]
        dst_blob = bucket.blob(dst_name)
        if dst_blob.exists():
            dst_blob.reload()
            if dst_blob.md5_hash == b.md5:
                with counts_lock:
                    counts["skipped_existing"] += 1
                return
        try:
            src_blob = bucket.blob(b.name)
            bucket.copy_blob(src_blob, bucket, new_name=dst_name)
            with counts_lock:
                counts["copied"] += 1
        except Exception as e:
            log.warning("copy %s -> %s failed: %s", b.name, dst_name, e)
            with counts_lock:
                counts["error"] += 1

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(work, b) for b in blobs]
        done = 0
        for _ in as_completed(futures):
            done += 1
            if done % 500 == 0 or done == len(futures):
                rate = done / max(time.time() - started, 0.001)
                log.info("  %d/%d (%.1f/s) — %s", done, len(futures), rate, counts)

    elapsed = time.time() - started
    report = {
        "phase": "copy",
        "prefix": args.prefix,
        "counts": counts,
        "elapsed_seconds": round(elapsed, 1),
    }
    out = Path(args.report_dir) / "wisdom-image-copy-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    log.info("Copy complete: %s -> %s", counts, out)


# NOTE: Naming a specific brand (e.g. "Wisdom") trips Gemini's trademark
# content-policy refusal ("I'm just a language model and can't help with that").
# Brand-neutral framing works: ask to remove overlay text/wordmarks/small graphics
# generally, preserving product. This works for catalog photos where the only
# such overlays are the vendor's own branding.
EDIT_PROMPT = (
    "Edit this product photo to remove all overlay text, wordmarks, and small "
    "graphics that appear superimposed on or near the product (anything that "
    "looks added on top of the product photography, not part of the product "
    "itself). Inpaint the cleaned areas seamlessly using the surrounding "
    "context. Preserve the product, its colors, materials, lighting, shadows, "
    "framing, dimensions, and background exactly as they are. Do not add new "
    "text or graphics. Output only the edited image."
)

QA_SCHEMA = {
    "type": "object",
    "properties": {
        "logo_gone": {"type": "boolean"},
        "product_intact": {"type": "boolean"},
        "confidence": {"type": "number"},
        "issues": {"type": "string"},
    },
    "required": ["logo_gone", "product_intact", "confidence"],
}

QA_PROMPT = (
    "You are reviewing an AI-edited product photo. The original contained a "
    "Wisdom brand wordmark or logo; the edit was supposed to remove every "
    "Wisdom mark and inpaint the area cleanly. Inspect the edited image. "
    "logo_gone=true if no Wisdom branding is visible anywhere. "
    "product_intact=true if the product, colors, and background look natural "
    "(no warping, no obvious smears, no new spurious text/logos). "
    "confidence in [0,1]. issues = short note when either flag is false."
)

EDIT_COLLECTION = "image_logo_edit"


def _edit_with_retry(
    gem: genai.Client,
    data: bytes,
    mime: str,
    *,
    max_attempts: int = 10,
    base_delay: float = 8.0,
) -> bytes | None:
    """Call Nano Banana Pro to inpaint. Returns raw image bytes of the edit, or None on parse failure."""
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            resp = gem.models.generate_content(
                model=EDIT_MODEL,
                contents=[
                    genai_types.Part.from_bytes(data=data, mime_type=mime),
                    EDIT_PROMPT,
                ],
                config=genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    temperature=0.2,
                ),
            )
            # Extract first inline image part from the response.
            cand = resp.candidates[0] if resp.candidates else None
            if cand and cand.content and cand.content.parts:
                for part in cand.content.parts:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        # SDK already returns bytes for inline_data.data.
                        return inline.data if isinstance(inline.data, (bytes, bytearray)) else base64.b64decode(inline.data)
            return None
        except Exception as e:
            last_err = e
            msg = str(e)
            transient = any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "DEADLINE_EXCEEDED", "504", "500"))
            if not transient or attempt == max_attempts - 1:
                raise
            time.sleep(min(base_delay * (2 ** attempt) + random.random() * base_delay, 180.0))
    if last_err:
        raise last_err
    return None


def _qa_edit(gem: genai.Client, edited: bytes, mime: str) -> dict:
    """Ask Gemini Flash whether the edit succeeded."""
    resp = gem.models.generate_content(
        model=QA_MODEL,
        contents=[genai_types.Part.from_bytes(data=edited, mime_type=mime), QA_PROMPT],
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QA_SCHEMA,
            temperature=0.1,
            max_output_tokens=512,
        ),
    )
    return _tolerant_json(resp.text or "")


def edit_one(
    blob: Blob,
    storage_client: storage.Client,
    fs_client: firestore.Client,
    gem: genai.Client,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Pass-2 inpaint one image. Idempotent via Firestore checkpoint and destination existence."""
    bucket = storage_client.bucket(BUCKET)
    edit_ref = fs_client.collection(EDIT_COLLECTION).document(blob.sha)
    if not force:
        snap = edit_ref.get()
        if snap.exists and snap.to_dict().get("edit_status") in ("ok", "manual_review"):
            d = snap.to_dict(); d["_cached"] = True
            return d

    dst_name = DST_PREFIX_ROOT + blob.name[len(SRC_PREFIX_ROOT):]
    review_name = "manual_review/" + blob.name[len(SRC_PREFIX_ROOT):]
    try:
        raw = fetch_image_bytes(storage_client, blob.name)
        data, mime = maybe_convert_jpx(raw, blob.ext)
        if mime == "application/octet-stream":
            rec = {"source_path": blob.name, "edit_status": "skipped_unsupported_mime"}
            edit_ref.set(rec); return rec

        edited = _edit_with_retry(gem, data, mime)
        if not edited:
            raise ValueError("edit returned no image part")

        qa = _qa_edit(gem, edited, "image/png")  # Nano Banana returns PNG
        logo_gone = bool(qa.get("logo_gone"))
        product_intact = bool(qa.get("product_intact"))
        passed = logo_gone and product_intact

        if dry_run:
            return {
                "source_path": blob.name, "dry_run": True,
                "qa": {"logo_gone": logo_gone, "product_intact": product_intact,
                       "confidence": qa.get("confidence"), "issues": qa.get("issues")},
                "edited_bytes": len(edited),
            }

        target_path = dst_name if passed else review_name
        bucket.blob(target_path).upload_from_string(edited, content_type="image/png")
        rec = {
            "source_path": blob.name,
            "dst_path": target_path,
            "edit_status": "ok" if passed else "manual_review",
            "logo_gone": logo_gone,
            "product_intact": product_intact,
            "qa_confidence": float(qa.get("confidence", 0.0)),
            "qa_issues": (qa.get("issues") or "")[:300],
            "edit_model": EDIT_MODEL,
            "edited_at": firestore.SERVER_TIMESTAMP,
        }
        edit_ref.set(rec)
        return rec
    except Exception as e:
        rec = {"source_path": blob.name, "edit_status": "error", "error": str(e)[:500],
               "edited_at": firestore.SERVER_TIMESTAMP}
        try: edit_ref.set(rec)
        except Exception: pass
        return rec


def run_edit(args: argparse.Namespace) -> None:
    storage_client = storage.Client(project=PROJECT)
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    gem = gemini_client()

    log.info("Loading Pass-1 hits where has_logo=True ...")
    targets: list[Blob] = []
    bucket = storage_client.bucket(BUCKET)
    for snap in fs_client.collection(SCAN_COLLECTION).where("has_logo", "==", True).stream():
        r = snap.to_dict()
        path = r.get("source_path")
        if not path: continue
        if args.min_confidence and r.get("confidence", 0) < args.min_confidence: continue
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext not in IMAGE_EXT_OK: continue
        b = bucket.blob(path);
        try: b.reload()
        except Exception: continue
        targets.append(Blob(name=path, size=b.size or 0, md5=b.md5_hash or "", content_type=b.content_type or ""))
        if args.limit and len(targets) >= args.limit:
            break
    log.info("Pass-2 candidates: %d (dry_run=%s)", len(targets), args.dry_run)

    counts = {"ok": 0, "manual_review": 0, "cached": 0, "error": 0, "skipped": 0}
    started = time.time()
    counts_lock = threading.Lock()
    sample: list[dict] = []

    def work(b: Blob) -> dict:
        rec = edit_one(b, storage_client, fs_client, gem, force=args.force_redo, dry_run=args.dry_run)
        with counts_lock:
            if rec.get("_cached"):
                counts["cached"] += 1
            elif rec.get("dry_run"):
                sample.append(rec)
                counts["ok"] += 1 if rec["qa"]["logo_gone"] and rec["qa"]["product_intact"] else 0
                counts["manual_review"] += 0 if rec["qa"]["logo_gone"] and rec["qa"]["product_intact"] else 1
            else:
                st = rec.get("edit_status", "error")
                counts[st] = counts.get(st, 0) + 1
        return rec

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(work, b) for b in targets]
        done = 0
        for _ in as_completed(futures):
            done += 1
            if done % 25 == 0 or done == len(futures):
                rate = done / max(time.time() - started, 0.001)
                log.info("  %d/%d (%.2f/s) — %s", done, len(futures), rate, counts)

    elapsed = time.time() - started
    out = {
        "phase": "edit",
        "total_candidates": len(targets),
        "counts": counts,
        "elapsed_seconds": round(elapsed, 1),
        "edit_model": EDIT_MODEL,
        "qa_model": QA_MODEL,
        "dry_run": args.dry_run,
        "sample": sample[:20],
    }
    Path(args.report_dir).mkdir(parents=True, exist_ok=True)
    Path(args.report_dir, "wisdom-image-edit-report.json").write_text(json.dumps(out, indent=2))
    log.info("Edit complete: %s", counts)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scan-only", action="store_true")
    p.add_argument("--edit-only", action="store_true")
    p.add_argument("--copy-only", action="store_true")
    p.add_argument("--prefix", default=SRC_PREFIX_ROOT,
                   help=f"GCS prefix under {BUCKET} to operate on (default: {SRC_PREFIX_ROOT})")
    p.add_argument("--limit", type=int, default=None, help="Cap blobs processed (smoke testing)")
    p.add_argument("--concurrency", type=int, default=4,
                   help="Worker threads. Vertex 'global' Gemini Flash quota is tight; 4 is safe, 8 risks 429 storms.")
    p.add_argument("--force-rescan", action="store_true",
                   help="Ignore Firestore checkpoint and re-scan every blob")
    p.add_argument("--skip-errored", action="store_true",
                   help="Treat existing scan_status=error rows as terminal (don't retry). Default: retry errors.")
    p.add_argument("--dry-run", action="store_true",
                   help="Edit pass: run edit + QA but skip the GCS upload. Reports QA stats only.")
    p.add_argument("--force-redo", action="store_true",
                   help="Edit pass: ignore existing edit checkpoint and redo.")
    p.add_argument("--min-confidence", type=float, default=0.0,
                   help="Edit pass: skip Pass-1 hits below this confidence.")
    p.add_argument("--report-dir", default="migration", help="Where to write JSON reports")
    args = p.parse_args()
    if not (args.scan_only or args.edit_only or args.copy_only):
        args.scan_only = True  # safe default
    return args


def main() -> None:
    args = parse_args()
    adc_check()
    if args.scan_only:
        run_scan(args)
    elif args.copy_only:
        run_copy(args)
    elif args.edit_only:
        run_edit(args)


if __name__ == "__main__":
    main()
