"""AI-enrich the Wisdom / Leka Project catalog with category + specs from product photos.

Why
---
~43% of the 5,062 Leka Project (ex-Wisdom) products on Medusa show a placeholder
image and have empty `metadata.specifications`. The Excel pricelist they were
imported from had only: SKU, title (EN + CN), L×W×H, FOB, page. The PDP at
`leka-website/catalogs/src/app/[brand]/[handle]/product-detail.tsx` reads
several fields that don't exist: `metadata.materials[]`, `metadata.specifications.age_group`,
`...num_users`, `...indoor_outdoor`, plus a real `description`.

What this does
--------------
For each Wisdom-origin product on live Medusa, send `{title, dimensions, thumbnail}`
to Gemini 2.5 Pro with a strict JSON schema and ask it to infer:
  - category (single token from a fixed taxonomy — incl. "toys" as its own bucket)
  - subcategory (free text, e.g. "rocking horse", "wooden block set")
  - age_min_years / age_max_years (ints)
  - materials (array, e.g. ["wood","steel"])
  - num_users_min / num_users_max (ints)
  - indoor_outdoor ("indoor"|"outdoor"|"both")
  - description (1-3 sentences, marketing-quality)
  - confidence (0.0-1.0)

Decisions are checkpointed to Firestore `wisdom_enrichment/{sha1(legacy_sku)}`.
Resumable: rerunning skips cached docs unless --force.

Cost guess (5,062 products, ~250 input image tokens + ~200 output tokens each):
  Gemini 2.5 Pro @ ~$1.25 / 1M input + ~$5.00 / 1M output → ~$5-7 total.

Usage
-----
    python scripts/enrich_wisdom_with_ai.py --limit 20            # smoke test
    python scripts/enrich_wisdom_with_ai.py                       # full pass
    python scripts/enrich_wisdom_with_ai.py --force --limit 20    # rebuild cache
    python scripts/enrich_wisdom_with_ai.py --report              # summary stats

Then run `scripts/apply_wisdom_enrichment.py` to push results to Medusa.
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

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ai-agents-go")

import requests  # noqa: E402
from google import genai  # noqa: E402
from google.cloud import firestore  # noqa: E402
from google.genai import types as genai_types  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("enrich_wisdom")

PROJECT = "ai-agents-go"
FIRESTORE_DB = "leka-product-catalogs"
ENRICHMENT_COLLECTION = "wisdom_enrichment"

MEDUSA_BACKEND = os.environ.get(
    "LEKA_MEDUSA_BACKEND",
    "https://leka-medusa-backend-538978391890.asia-southeast1.run.app",
)
STORE_PK = "pk_b7d7b7412262b05054450cd08213cd3d7d3432616ffff885e4c8a57e1b596e53"
REGION_ID = "reg_01KNKVD0TNN5G0HG3CSTF7JGWN"  # Asia-Pacific (for storefront field expansion)

GEMINI_LOCATION = "global"
MODEL = "gemini-2.5-flash"  # Pro is too verbose for our schema and hits MAX_TOKENS
CONCURRENCY = 4
TIMEOUT = 60
MAX_OUTPUT_TOKENS = 4096

CATEGORY_VOCAB = [
    "toys",                      # small/portable play items (rocking horses, dolls, ride-ons under ~1.5m)
    "playground_equipment",      # large outdoor structures, slides, climbers, swings
    "kids_furniture",            # shelves, trolleys, tables, chairs, storage
    "arts_crafts",               # paper, paint, glue, scissors, beads, markers
    "educational_manipulatives", # counting, sorting, matching, stacking, fine-motor sets
    "music_instruments",         # drums, tambourines, xylophones, shakers
    "role_play",                 # play kitchens, dress-up, doctor sets, market stalls
    "sports_outdoor",            # balls, hoops, sports gear
    "infant_toddler",            # 0-3 specific gear, soft play
    "water_play",                # buckets, water tables, splash gear
    "sand_play",                 # sand boxes, molds, sand tools
    "climbing",                  # standalone climbing frames, walls
    "ride_on",                   # bikes, trikes, scooters, push cars
    "books_media",               # books, posters, learning cards
    "safety_accessories",        # corner protectors, mats, signage, swing chains
    "other",                     # uncategorisable
]

ENRICHMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORY_VOCAB},
        "subcategory": {"type": "string"},
        "age_min_years": {"type": "integer"},
        "age_max_years": {"type": "integer"},
        "materials": {"type": "array", "items": {"type": "string"}},
        "num_users_min": {"type": "integer"},
        "num_users_max": {"type": "integer"},
        "indoor_outdoor": {"type": "string", "enum": ["indoor", "outdoor", "both", "unknown"]},
        "description": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "category", "subcategory", "age_min_years", "age_max_years",
        "materials", "num_users_min", "num_users_max", "indoor_outdoor",
        "description", "confidence",
    ],
}

PLACEHOLDER_TOKEN = "leka-coming-soon"


def _adc_check() -> None:
    import google.auth
    try:
        _, proj = google.auth.default()
        log.info("ADC ok (project=%s)", proj)
    except Exception as e:
        log.error("ADC failure: %s -- run gcloud auth application-default login", e)
        sys.exit(2)


def iter_wisdom_products():
    """Yield {id, handle, title, sku, thumbnail, length, width, height, weight,
    volume_cbm, description_cn, has_placeholder} for every Wisdom-origin product."""
    offset = 0
    while True:
        r = requests.get(
            f"{MEDUSA_BACKEND}/store/products",
            headers={"x-publishable-api-key": STORE_PK},
            params={
                "limit": 100,
                "offset": offset,
                "region_id": REGION_ID,
                "fields": "id,handle,title,thumbnail,metadata,variants.length,variants.width,variants.height,variants.weight,variants.metadata",
            },
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            return
        for p in batch:
            meta = p.get("metadata") or {}
            if meta.get("source_brand_internal") != "wisdom":
                continue
            v0 = (p.get("variants") or [None])[0] or {}
            sku = (v0.get("metadata") or {}).get("legacy_sku") or ""
            if not sku:
                continue
            th = p.get("thumbnail") or ""
            yield {
                "id": p["id"],
                "handle": p.get("handle") or "",
                "title": p.get("title") or "",
                "sku": sku,
                "thumbnail": th,
                "has_placeholder": PLACEHOLDER_TOKEN in th,
                "length": v0.get("length"),
                "width": v0.get("width"),
                "height": v0.get("height"),
                "weight": v0.get("weight"),
                "volume_cbm": meta.get("volume_cbm"),
                "description_cn": meta.get("description_cn"),
                "catalog_page": meta.get("catalog_page"),
            }
        offset += 100


def build_prompt(p: dict) -> str:
    dims_bits = []
    if p.get("length") and p.get("width") and p.get("height"):
        dims_bits.append(f"L{p['length']}cm x W{p['width']}cm x H{p['height']}cm")
    if p.get("weight"):
        dims_bits.append(f"{p['weight']}kg")
    if p.get("volume_cbm"):
        dims_bits.append(f"vol={p['volume_cbm']} m^3")
    dims = "; ".join(dims_bits) or "unknown"
    has_img = "yes" if not p.get("has_placeholder") else "no (placeholder)"
    cn = p.get("description_cn") or ""
    sku = p.get("sku", "")
    title = p.get("title", "")
    return f"""You are classifying products in a Chinese OEM kids/playground catalog (brand "Wisdom").

Use the title, Chinese name, dimensions, and image (if a real photo) to infer category and specs.

Product SKU: {sku}
English title: {title}
Chinese name: {cn}
Dimensions: {dims}
Real photo available: {has_img}

CATEGORY GUIDANCE (be decisive — pick the BEST fit, not the safest):
- "toys" = small/portable play items kids physically hold, push, sit on, or carry around. Includes rocking horses (Dino Rocker, Pony Rocker etc), plush animals, dolls, small push-cars, push-along animals, small play sets that fit on a table or floor. If a kid could carry it or take it home, it's a toy. Strong signal: dimensions ALL under ~120cm.
- "playground_equipment" = LARGE FIXED outdoor structures, slides, multi-station playgrounds, large swings, climbers > 1.5m, picnic benches for playgrounds, spring riders that are concreted into the ground, see-saws, large arch climbers, stepping stones meant to be installed in a playground.
- "kids_furniture" = shelves, trolleys, tables, chairs, sofas, storage cabinets, library islands (for classroom/nursery use).
- "arts_crafts" = paper, paint, glue, beads, scissors, markers, tape, paint smocks, modelling supplies, crepe paper, glitter.
- "educational_manipulatives" = counting/sorting/matching/stacking sets, fine-motor wooden trays, tabletop block sets, sensory boards, puzzles. (Outdoor or oversized block sets -> playground_equipment.)
- "music_instruments" = tambourines, drums, shakers, xylophones, kid music gear.
- "role_play" = play kitchens, play markets, dress-up kits, doctor/vet sets, play food, kitchen accessory sets, household-pretend items.
- "infant_toddler" = soft play mats, 0-3 specific developmental gear.
- "sand_play" / "water_play" = themed tools, molds, and small tables for sand/water activity. (Large fixed water platforms -> playground_equipment.)
- "ride_on" = LARGE ride-on vehicles built for outdoor/serious use: pedal cars, kid bikes (with pedals), scooters with kickboards, large pedal-trikes. If it's a small rocker, push-car, or animal-shape ride toy -> "toys".
- "safety_accessories" = corner protectors, rubber mats, signage, swing seats, chains, hardware.

EDGE CASES:
- A "Rocker" or "Spring Rider" name -> "toys" if it's free-standing/portable (sits on a base, can be moved); "playground_equipment" if it has a ground-mount post.
- A "Climber" name -> "playground_equipment" if outdoor metal/large; "educational_manipulatives" if it's a small wooden tabletop puzzle.
- Tabletop blocks/puzzles -> "educational_manipulatives". Floor or outdoor blocks -> "playground_equipment".

DESCRIPTION: 1-3 sentences, marketing-quality but factual. Mention key materials, intended use, and a unique selling point if visible.

AGE: best guess in years (age_min_years / age_max_years). If unknown, use 3 and 12.

NUM_USERS: how many kids can play with this at once. If unclear, use 1 and 1.

CONFIDENCE: 0.5-0.7 if guessing from name only; 0.7-0.9 if photo confirms category; 0.9+ only when both title and photo are crystal-clear.

Return JSON matching the schema."""


def _tolerant_json(text: str) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _fetch_thumb(url: str) -> tuple[bytes | None, str]:
    """Fetch product thumbnail bytes + mime; on failure or placeholder, return (None, '')."""
    if not url or PLACEHOLDER_TOKEN in url:
        return None, ""
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return None, ""
        ct = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return r.content, ct
    except Exception:
        return None, ""


def _gemini_enrich(gem: genai.Client, prompt: str, img_bytes: bytes | None,
                   img_mime: str) -> dict:
    delays = [2, 5, 15, 45, 90]
    parts: list = [prompt]
    if img_bytes:
        parts = [genai_types.Part.from_bytes(data=img_bytes, mime_type=img_mime), prompt]
    last: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            resp = gem.models.generate_content(
                model=MODEL,
                contents=parts,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ENRICHMENT_SCHEMA,
                    temperature=0.2,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                ),
            )
            parsed = _tolerant_json(resp.text or "")
            # Require at least the most critical fields; truncated/empty responses
            # frequently miss `description` even when `category` was emitted.
            if parsed.get("category") and parsed.get("description"):
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


def enrich_one(p: dict, fs_client: firestore.Client, gem: genai.Client,
               force: bool) -> dict:
    sku = p["sku"]
    sha = hashlib.sha1(sku.encode()).hexdigest()
    doc_ref = fs_client.collection(ENRICHMENT_COLLECTION).document(sha)
    if not force:
        snap = doc_ref.get()
        if snap.exists:
            d = snap.to_dict() or {}
            if d.get("status") in ("ok", "error"):
                d["_cached"] = True
                return d

    img_bytes, mime = _fetch_thumb(p.get("thumbnail", ""))
    prompt = build_prompt(p)
    try:
        parsed = _gemini_enrich(gem, prompt, img_bytes, mime or "image/jpeg")
    except Exception as e:
        rec = {
            "sku": sku, "status": "error", "error": str(e)[:300],
            "decided_at": firestore.SERVER_TIMESTAMP,
        }
        doc_ref.set(rec)
        return rec

    if not parsed.get("category") or not parsed.get("description"):
        rec = {
            "sku": sku, "status": "error",
            "error": "missing required fields after retries",
            "raw_keys": sorted(parsed.keys()),
            "decided_at": firestore.SERVER_TIMESTAMP,
        }
        doc_ref.set(rec)
        return rec

    rec = {
        "sku": sku,
        "handle": p.get("handle"),
        "product_id": p["id"],
        "title": p.get("title"),
        "status": "ok",
        "had_image": img_bytes is not None,
        "category": parsed.get("category"),
        "subcategory": (parsed.get("subcategory") or "")[:120],
        "age_min_years": parsed.get("age_min_years"),
        "age_max_years": parsed.get("age_max_years"),
        "materials": parsed.get("materials") or [],
        "num_users_min": parsed.get("num_users_min"),
        "num_users_max": parsed.get("num_users_max"),
        "indoor_outdoor": parsed.get("indoor_outdoor"),
        "description": (parsed.get("description") or "")[:1500],
        "confidence": float(parsed.get("confidence") or 0.0),
        "decided_at": firestore.SERVER_TIMESTAMP,
        "model": MODEL,
    }
    doc_ref.set(rec)
    return rec


def cmd_enrich(args) -> None:
    _adc_check()
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    gem = genai.Client(vertexai=True, project=PROJECT, location=GEMINI_LOCATION)

    log.info("Enumerating Wisdom products from live Medusa Store API...")
    products = list(iter_wisdom_products())
    log.info("  %d Wisdom-origin products", len(products))

    if args.limit:
        products = products[: args.limit]
        log.info("--limit applied: enriching %d", len(products))

    counts = {"ok": 0, "error": 0, "cached": 0}
    cat_counts: dict[str, int] = {}
    started = time.time()

    def work(p):
        return enrich_one(p, fs_client, gem, args.force)

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(work, p): p for p in products}
        for i, fut in enumerate(as_completed(futures), 1):
            p = futures[fut]
            try:
                rec = fut.result()
            except Exception as e:
                log.error("  %s unexpected: %s", p.get("sku"), str(e)[:200])
                counts["error"] += 1
                continue
            if rec.get("_cached"):
                counts["cached"] += 1
            else:
                counts[rec.get("status", "error")] += 1
            cat = rec.get("category")
            if cat:
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            if i % 25 == 0 or i == len(products):
                rate = i / max(time.time() - started, 0.001)
                log.info("  %4d/%d (%.1f/s) %s", i, len(products), rate, counts)

    log.info("Enrich done in %.1fs: %s", time.time() - started, counts)
    if cat_counts:
        log.info("Category counts:")
        for c, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
            log.info("  %-28s %d", c, n)


def cmd_report(args) -> None:
    _adc_check()
    fs_client = firestore.Client(project=PROJECT, database=FIRESTORE_DB)
    cat: dict[str, int] = {}
    ages: list[int] = []
    conf: list[float] = []
    n_ok = n_err = n_no_img = 0
    for d in fs_client.collection(ENRICHMENT_COLLECTION).stream():
        doc = d.to_dict() or {}
        if doc.get("status") == "error":
            n_err += 1
            continue
        n_ok += 1
        if not doc.get("had_image"):
            n_no_img += 1
        c = doc.get("category") or "?"
        cat[c] = cat.get(c, 0) + 1
        if doc.get("age_min_years") is not None:
            ages.append(int(doc["age_min_years"]))
        if doc.get("confidence") is not None:
            conf.append(float(doc["confidence"]))
    log.info("Enriched: ok=%d error=%d (of which no_image=%d)", n_ok, n_err, n_no_img)
    if conf:
        log.info("Mean confidence: %.2f", sum(conf) / len(conf))
    log.info("Category distribution:")
    for c, n in sorted(cat.items(), key=lambda x: -x[1]):
        log.info("  %-28s %d", c, n)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="re-enrich cached SKUs")
    ap.add_argument("--report", action="store_true", help="just print summary stats")
    args = ap.parse_args()

    if args.report:
        cmd_report(args)
    else:
        cmd_enrich(args)


if __name__ == "__main__":
    main()
