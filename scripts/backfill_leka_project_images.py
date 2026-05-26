"""Backfill missing product images on the live `leka-project` Medusa sales channel.

The Wisdom → Leka Project rebrand (v2.17.0) left 2,226 of 5,062 products with
empty `images[]` and `null` thumbnail. Root cause: the original import deliberately
left these blank because the `products_wisdom` Firestore docs have empty `images[]`
and `image_verified: False` / `None`.

This script restores real images where provable, and falls back to a Leka-branded
placeholder so the storefront has no blank cards. Three phases — each idempotent
and resumable.

  --verify           Phase A — for each imageless product whose `item_code` exactly
                     equals the leading token of one or more
                     `gs://ai-agents-go-vendors/leka-project/<code>_*` objects,
                     download the representative image, call Gemini 2.5 Flash with
                     `{title, image}`, and accept only when the model returns
                     `matches=True, confidence>=THRESHOLD`. Checkpoint each decision
                     in Firestore `image_backfill_verify/{sha1(code)}`.

  --make-placeholder Phase B — render a 1024×1024 Leka-branded "Image coming soon"
                     PNG with Pillow and upload once to
                     `gs://ai-agents-go-vendors/leka-project/_placeholder/leka-coming-soon.png`.
                     Skipped if the object already exists (use --force to re-render).

  --attach           Phase C — POST `images[]` + `thumbnail` to live Medusa products.
                     Verified products get their real image set + `metadata.image_status
                     = "backfilled"`; everything else gets the placeholder URL +
                     `metadata.image_status = "placeholder"`. Add `--dry-run` to print
                     the plan without writing.

  --audit            Phase D — re-enumerate the Store API for the SC; print the count
                     of products still rendering blank (expect 0 after --attach).

Auth: ADC for GCP (Rule 12b); Medusa admin creds pulled from Secret Manager secrets
`medusa-admin-email` / `medusa-admin-password` at runtime.

Examples:
  python scripts/backfill_leka_project_images.py --verify --limit 20      # smoke
  python scripts/backfill_leka_project_images.py --verify                 # full
  python scripts/backfill_leka_project_images.py --make-placeholder
  python scripts/backfill_leka_project_images.py --attach --dry-run
  python scripts/backfill_leka_project_images.py --attach
  python scripts/backfill_leka_project_images.py --audit
"""
from __future__ import annotations

import argparse
import hashlib
import io
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

import requests  # noqa: E402
from google import genai  # noqa: E402
from google.cloud import firestore, secretmanager, storage  # noqa: E402
from google.genai import types as genai_types  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("backfill_leka_project")

# ---------------------------------------------------------------------------
# Constants

PROJECT = "ai-agents-go"
BUCKET = "ai-agents-go-vendors"
DST_PREFIX = "leka-project/"
FIRESTORE_DB = "leka-product-catalogs"

MEDUSA_BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
SC_ID = "sc_01KNKTHC0B7KFEDSZ3NNM49JQW"  # "Leka Project" (formerly Wisdom)
STORE_PK = "pk_b7d7b7412262b05054450cd08213cd3d7d3432616ffff885e4c8a57e1b596e53"

PROXY_PREFIX = "https://catalogs.leka.studio/api/i/leka-project/"
PLACEHOLDER_OBJECT = "_placeholder/leka-coming-soon.png"
PLACEHOLDER_URL = PROXY_PREFIX + PLACEHOLDER_OBJECT
PLACEHOLDER_LOCAL_COPY = Path("docs/assets/leka-coming-soon.png")

VERIFY_COLLECTION = "image_backfill_verify"
WISDOM_COLLECTION = "products_wisdom"

# Gemini routing — mirror scripts/strip_wisdom_logos.py
GEMINI_LOCATION = "global"
VERIFY_MODEL = "gemini-2.5-flash"
VERIFY_CONFIDENCE_THRESHOLD = 0.70
VERIFY_CONCURRENCY = 4  # Vertex global location quota note: keep <=4
VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {"type": "boolean"},
        "confidence": {"type": "number"},
        "depicted": {"type": "string"},
    },
    "required": ["matches", "confidence", "depicted"],
}

# Leka Design System
LEKA_CREAM = (255, 249, 230)
LEKA_NAVY = (24, 37, 87)
LEKA_PURPLE = (128, 3, 255)
LEKA_AMBER = (255, 169, 0)

TIMEOUT = 60
IMAGE_EXT_OK = {"jpg", "jpeg", "png", "webp"}

# ---------------------------------------------------------------------------
# Auth helpers

def _adc_check() -> None:
    import google.auth
    try:
        _, project = google.auth.default()
        log.info(f"ADC ok (project={project})")
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
# Store API enumeration

def iter_imageless_products(pk: str):
    """Yield {id, handle, title, code} for every leka-project SC product missing images."""
    offset = 0
    while True:
        r = requests.get(
            f"{MEDUSA_BACKEND}/store/products",
            headers={"x-publishable-api-key": pk},
            params={
                "limit": 100,
                "offset": offset,
                "fields": "id,handle,title,thumbnail,images.url,variants.metadata,metadata",
            },
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            if (p.get("images") or []) or p.get("thumbnail"):
                continue
            if p.get("handle") == "test-swing":
                continue
            vs = p.get("variants") or []
            code = (vs[0].get("metadata") or {}).get("legacy_sku") if vs else None
            if not code:
                lh = (p.get("metadata") or {}).get("legacy_handle", "")
                code = lh.replace("wisdom-", "") if lh else None
            yield {
                "id": p["id"],
                "handle": p.get("handle"),
                "title": p.get("title") or p.get("handle") or "",
                "code": code,
            }
        offset += 100


# ---------------------------------------------------------------------------
# Bucket index

def index_leka_project_objects(storage_client: storage.Client) -> dict[str, list[str]]:
    """Map item_code -> sorted list of relative paths under leka-project/.

    Match rule: object filename = `<code>_*`. Item codes contain no underscore,
    so split('_', 1)[0] is unambiguous.
    """
    by_code: dict[str, list[str]] = {}
    for blob in storage_client.list_blobs(BUCKET, prefix=DST_PREFIX):
        if blob.name.endswith("/"):
            continue
        rel = blob.name[len(DST_PREFIX):]
        if rel.startswith("_placeholder/"):
            continue
        fn = rel.rsplit("/", 1)[-1]
        if "_" not in fn:
            continue
        ext = fn.rsplit(".", 1)[-1].lower()
        if ext not in IMAGE_EXT_OK:
            continue
        code = fn.split("_", 1)[0]
        by_code.setdefault(code, []).append(rel)

    # Sort each list: catalog/ first (representative img0), then others.
    def key(p: str):
        folder = p.split("/", 1)[0]
        prio = 0 if folder == "catalog" else (1 if folder == "verified" else 2)
        return (prio, p)
    for c in by_code:
        by_code[c].sort(key=key)
    return by_code


def representative_path(paths: list[str], code: str) -> str:
    """Prefer catalog/<code>_img0.<ext>, else the first sorted path."""
    for p in paths:
        if p.startswith(f"catalog/{code}_img0."):
            return p
    return paths[0]


# ---------------------------------------------------------------------------
# Phase A — Gemini verify

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
    """Ask Gemini whether the image depicts the product titled `title`."""
    prompt = (
        "You are verifying that a product photo matches a product title.\n"
        f'Product title: "{title}"\n\n'
        "Look at the image. Decide if the image plausibly depicts the SAME PRODUCT as "
        "the title (same kind of toy / playground equipment / accessory). Catalog "
        "photos may show the product alone, in a scene, or with packaging — that's fine.\n\n"
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


def _mime_for(ext: str) -> str:
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
    }.get(ext.lower(), "application/octet-stream")


def verify_one(p: dict, paths: list[str], storage_client: storage.Client,
               fs_client: firestore.Client, gem: genai.Client, force: bool) -> dict:
    code = p["code"]
    sha = hashlib.sha1(code.encode()).hexdigest()
    doc_ref = fs_client.collection(VERIFY_COLLECTION).document(sha)
    if not force:
        snap = doc_ref.get()
        if snap.exists:
            d = snap.to_dict() or {}
            if d.get("decision") in ("accept", "reject", "error"):
                d["_cached"] = True
                return d
    rep = representative_path(paths, code)
    ext = rep.rsplit(".", 1)[-1].lower()
    mime = _mime_for(ext)
    try:
        data = storage_client.bucket(BUCKET).blob(DST_PREFIX + rep).download_as_bytes()
    except Exception as e:
        rec = {"code": code, "decision": "error", "stage": "download",
               "error": str(e)[:300], "rep_path": rep,
               "decided_at": firestore.SERVER_TIMESTAMP}
        doc_ref.set(rec)
        return rec
    try:
        parsed = _gemini_verify(gem, data, mime, p["title"])
    except Exception as e:
        rec = {"code": code, "decision": "error", "stage": "gemini",
               "error": str(e)[:300], "rep_path": rep,
               "decided_at": firestore.SERVER_TIMESTAMP}
        doc_ref.set(rec)
        return rec
    matches = bool(parsed.get("matches"))
    conf = float(parsed.get("confidence") or 0.0)
    decision = "accept" if (matches and conf >= VERIFY_CONFIDENCE_THRESHOLD) else "reject"
    rec = {
        "code": code, "title": p["title"], "rep_path": rep,
        "decision": decision, "matches": matches, "confidence": conf,
        "depicted": (parsed.get("depicted") or "")[:300],
        "num_paths": len(paths),
        "decided_at": firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(rec)
    return rec


def cmd_verify(args) -> None:
    _adc_check()
    storage_client = storage.Client(project=PROJECT)
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    gem = genai.Client(vertexai=True, project=PROJECT, location=GEMINI_LOCATION)

    log.info("Indexing leka-project/ bucket objects...")
    by_code = index_leka_project_objects(storage_client)
    log.info("  %d distinct item codes have hosted images", len(by_code))

    log.info("Enumerating imageless products from Store API...")
    imageless = list(iter_imageless_products(STORE_PK))
    log.info("  %d imageless products", len(imageless))

    cands = [p for p in imageless if p["code"] and p["code"] in by_code]
    log.info("  %d candidates with exact-code bucket match", len(cands))

    if args.limit:
        cands = cands[: args.limit]
        log.info("--limit applied: verifying %d", len(cands))

    counts = {"accept": 0, "reject": 0, "error": 0, "cached": 0}
    started = time.time()

    def work(p):
        return verify_one(p, by_code[p["code"]], storage_client, fs_client, gem, args.force)

    with ThreadPoolExecutor(max_workers=VERIFY_CONCURRENCY) as ex:
        futures = {ex.submit(work, p): p for p in cands}
        for i, fut in enumerate(as_completed(futures), 1):
            p = futures[fut]
            try:
                rec = fut.result()
            except Exception as e:
                log.error("  %s unexpected: %s", p["code"], e)
                counts["error"] += 1
                continue
            if rec.get("_cached"):
                counts["cached"] += 1
            else:
                counts[rec.get("decision", "error")] += 1
            if i % 25 == 0 or i == len(cands):
                rate = i / max(time.time() - started, 0.001)
                log.info("  %4d/%d (%.1f/s) %s", i, len(cands), rate, counts)

    log.info("Verify done in %.1fs: %s", time.time() - started, counts)


# ---------------------------------------------------------------------------
# Phase B — placeholder

def _load_font(size: int) -> ImageFont.ImageFont:
    # Try common Windows / Linux locations for Manrope or a clean sans fallback.
    candidates = [
        r"C:\Windows\Fonts\Manrope-Bold.ttf",
        r"C:\Windows\Fonts\Manrope-SemiBold.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def render_placeholder() -> bytes:
    W = H = 1024
    img = Image.new("RGB", (W, H), LEKA_CREAM)
    draw = ImageDraw.Draw(img)
    # Rounded inner card on navy stroke, 16px-feel framing (Leka radius)
    pad = 96
    card = (pad, pad, W - pad, H - pad)
    draw.rounded_rectangle(card, radius=64, fill=LEKA_CREAM, outline=LEKA_NAVY, width=6)
    # Purple accent dot, top-left of card
    r = 36
    cx, cy = card[0] + 80, card[1] + 80
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=LEKA_PURPLE)
    # Title + subtitle, centered
    title_font = _load_font(96)
    sub_font = _load_font(44)
    micro_font = _load_font(28)
    title = "Leka Project"
    sub = "Image coming soon"
    micro = "catalogs.leka.studio"
    tw, th = _text_size(draw, title, title_font)
    sw, sh = _text_size(draw, sub, sub_font)
    mw, mh = _text_size(draw, micro, micro_font)
    cx_t = W // 2
    cy_t = H // 2 - 40
    draw.text((cx_t - tw // 2, cy_t - th), title, font=title_font, fill=LEKA_NAVY)
    draw.text((cx_t - sw // 2, cy_t + 28), sub, font=sub_font, fill=LEKA_PURPLE)
    # Amber underline
    underline_w = max(sw, tw) // 2
    uy = cy_t + 28 + sh + 24
    draw.rectangle((cx_t - underline_w // 2, uy, cx_t + underline_w // 2, uy + 6),
                   fill=LEKA_AMBER)
    # Micro footer
    draw.text((cx_t - mw // 2, H - pad - 60), micro, font=micro_font, fill=LEKA_NAVY)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def cmd_make_placeholder(args) -> None:
    _adc_check()
    storage_client = storage.Client(project=PROJECT)
    bucket = storage_client.bucket(BUCKET)
    blob = bucket.blob(DST_PREFIX + PLACEHOLDER_OBJECT)
    if blob.exists() and not args.force:
        log.info("Placeholder already at gs://%s/%s%s (use --force to overwrite)",
                 BUCKET, DST_PREFIX, PLACEHOLDER_OBJECT)
        return
    png = render_placeholder()
    blob.upload_from_string(png, content_type="image/png")
    log.info("Uploaded placeholder (%d bytes) -> gs://%s/%s%s",
             len(png), BUCKET, DST_PREFIX, PLACEHOLDER_OBJECT)
    PLACEHOLDER_LOCAL_COPY.parent.mkdir(parents=True, exist_ok=True)
    PLACEHOLDER_LOCAL_COPY.write_bytes(png)
    log.info("Local copy: %s", PLACEHOLDER_LOCAL_COPY)
    # Quick proxy probe
    try:
        r = requests.get(PLACEHOLDER_URL, timeout=30)
        log.info("Proxy probe %s -> %s %s",
                 PLACEHOLDER_URL, r.status_code, r.headers.get("content-type"))
    except Exception as e:
        log.warning("Proxy probe failed (proxy may be cold): %s", e)


# ---------------------------------------------------------------------------
# Phase C — attach to Medusa

def _path_to_proxy(rel: str) -> str:
    return PROXY_PREFIX + rel


def cmd_attach(args) -> None:
    _adc_check()
    storage_client = storage.Client(project=PROJECT)
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)

    # Build decision index from Firestore checkpoints.
    decisions: dict[str, dict] = {}
    for d in fs_client.collection(VERIFY_COLLECTION).stream():
        doc = d.to_dict() or {}
        c = doc.get("code")
        if c:
            decisions[c] = doc
    log.info("Loaded %d verify decisions from Firestore", len(decisions))

    by_code = index_leka_project_objects(storage_client)
    imageless = list(iter_imageless_products(STORE_PK))
    log.info("Imageless products to attach: %d", len(imageless))

    # Confirm placeholder exists.
    placeholder_blob = storage_client.bucket(BUCKET).blob(DST_PREFIX + PLACEHOLDER_OBJECT)
    if not placeholder_blob.exists():
        log.error("Placeholder missing — run --make-placeholder first.")
        sys.exit(2)

    tok = None if args.dry_run else _medusa_admin_token()
    counts = {"backfilled": 0, "placeholder": 0, "skipped": 0, "errors": 0}
    started = time.time()
    todo = imageless if not args.limit else imageless[: args.limit]

    for i, p in enumerate(todo, 1):
        code = p["code"]
        rec = decisions.get(code) if code else None
        if rec and rec.get("decision") == "accept" and code in by_code:
            urls = [_path_to_proxy(rel) for rel in by_code[code]]
            status_tag = "backfilled"
        else:
            urls = [PLACEHOLDER_URL]
            status_tag = "placeholder"

        payload = {
            "images": [{"url": u} for u in urls],
            "thumbnail": urls[0],
            "metadata": {
                "image_status": status_tag,
                "image_status_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        }

        if args.dry_run:
            counts[status_tag] += 1
            if i <= 5:
                log.info("  [dry] %s (%s) -> %s [%d urls]",
                         code, p["handle"], status_tag, len(urls))
            continue

        try:
            r = _retry("POST", f"{MEDUSA_BACKEND}/admin/products/{p['id']}", tok,
                       json_body=payload)
            r.raise_for_status()
            counts[status_tag] += 1
        except Exception as e:
            log.error("  %s update failed: %s", p["id"], str(e)[:200])
            counts["errors"] += 1

        if i % 100 == 0 or i == len(todo):
            rate = i / max(time.time() - started, 0.001)
            log.info("  %d/%d (%.1f/s) %s", i, len(todo), rate, counts)

    log.info("Attach done in %.1fs: %s", time.time() - started, counts)


# ---------------------------------------------------------------------------
# Phase D — audit

def cmd_audit(args) -> None:
    blanks = 0
    placeholder_count = 0
    backfilled = 0
    total = 0
    offset = 0
    while True:
        r = requests.get(
            f"{MEDUSA_BACKEND}/store/products",
            headers={"x-publishable-api-key": STORE_PK},
            params={"limit": 100, "offset": offset,
                    "fields": "id,handle,thumbnail,images.url,metadata"},
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            break
        for p in batch:
            total += 1
            imgs = p.get("images") or []
            th = p.get("thumbnail")
            if not imgs and not th:
                blanks += 1
                continue
            tag = (p.get("metadata") or {}).get("image_status")
            if tag == "placeholder":
                placeholder_count += 1
            elif tag == "backfilled":
                backfilled += 1
        offset += 100
    log.info("Audit: %d total | %d blank | %d placeholder | %d backfilled",
             total, blanks, placeholder_count, backfilled)
    if blanks:
        log.warning("AUDIT NOT CLEAN: %d products still blank", blanks)
        sys.exit(1)


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--make-placeholder", action="store_true")
    ap.add_argument("--attach", action="store_true")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="--attach only: print plan without writing")
    ap.add_argument("--force", action="store_true",
                    help="--verify: re-verify cached codes; --make-placeholder: overwrite")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    chosen = sum([args.verify, args.make_placeholder, args.attach, args.audit])
    if chosen == 0:
        ap.print_help()
        sys.exit(2)
    if chosen > 1:
        log.error("Pick one phase at a time.")
        sys.exit(2)

    if args.verify:
        cmd_verify(args)
    elif args.make_placeholder:
        cmd_make_placeholder(args)
    elif args.attach:
        cmd_attach(args)
    elif args.audit:
        cmd_audit(args)


if __name__ == "__main__":
    main()
