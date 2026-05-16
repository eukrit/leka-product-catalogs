"""Leka Product Catalogs — Gateway service.

Serves:
  /                          → Collections landing page
  /vinciplay/                → Vinci Play catalog
  /health                    → Health check
  /forms/pricing-config      → Pricing-config editor UI
  /api/pricing-config (GET)  → Read pricing_config/canonical from Firestore
  /api/pricing-config (POST) → Write pricing_config/canonical to Firestore
"""
import os
import sys
from datetime import datetime, timezone
from flask import Flask, send_from_directory, jsonify, request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure `shared/` is importable when this runs from /app in Cloud Run
# (the Dockerfile copies shared/ to /app/shared/ and starts gunicorn with
# --chdir src, so /app is the parent dir).
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

app = Flask(__name__)

SERVICE_NAME = "leka-product-catalogs"
VERSION = "0.7.1"

# Brand catalog paths (relative to BASE_DIR)
BRANDS = {
    "vinciplay": {
        "name": "Vinci Play",
        "static_dir": os.path.join(BASE_DIR, "vinci-catalog", "web-app", "public"),
        "description": "Playground Equipment",
        "country": "Poland",
        "color": "#8003FF",
    },
}


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": SERVICE_NAME, "version": VERSION,
                     "timestamp": datetime.now(timezone.utc).isoformat()})


# --- Landing page ---
@app.route("/")
def landing():
    return send_from_directory(os.path.join(BASE_DIR, "src", "public"), "index.html")


@app.route("/landing/<path:path>")
def landing_static(path):
    return send_from_directory(os.path.join(BASE_DIR, "src", "public"), path)


# --- Brand catalogs ---
@app.route("/<brand>/")
def brand_index(brand):
    if brand in BRANDS:
        return send_from_directory(BRANDS[brand]["static_dir"], "index.html")
    return "Not found", 404


@app.route("/<brand>/<path:path>")
def brand_static(brand, path):
    if brand in BRANDS:
        return send_from_directory(BRANDS[brand]["static_dir"], path)
    return "Not found", 404


# --- API: brand list for landing page ---
@app.route("/api/brands")
def api_brands():
    brands = []
    for slug, info in BRANDS.items():
        # Count products from data file
        count = 0
        data_file = os.path.join(info["static_dir"], "data", "products_all.json")
        if os.path.exists(data_file):
            import json
            with open(data_file) as f:
                count = len(json.load(f))
        series_count = 0
        series_file = os.path.join(info["static_dir"], "data", "series.json")
        if os.path.exists(series_file):
            import json
            with open(series_file) as f:
                series_count = len([s for s in json.load(f) if s.get("product_count", 0) > 0])
        brands.append({
            "slug": slug,
            "name": info["name"],
            "description": info["description"],
            "country": info["country"],
            "color": info["color"],
            "product_count": count,
            "series_count": series_count,
            "url": f"/{slug}/",
        })
    return jsonify(brands)


# --- Pricing config editor (gateway-fronted; auth handled by gateway IAP) ---
# Source of truth: pricing_config/canonical in Firestore database
# `leka-product-catalogs` (project ai-agents-go). This service is deployed
# to Cloud Run with --no-allow-unauthenticated and only the gateway SA has
# roles/run.invoker — so any request that reaches us has already been
# authenticated by the gateway. We trust X-Goog-Authenticated-User-Email
# and the gateway-forwarded "X-Goco-User-Email" header for the audit field.

@app.route("/forms/pricing-config")
def pricing_config_form():
    return send_from_directory(
        os.path.join(BASE_DIR, "docs", "forms"), "pricing-config.html"
    )


@app.route("/api/pricing-config", methods=["GET"])
def api_get_pricing_config():
    from shared.pricing_config import get_full_config, reset_cache
    reset_cache()  # always serve fresh — this endpoint is low-volume
    return jsonify(get_full_config() or _empty_config())


# --- Pricing context: live FX + per-brand examples + cascade --------------

_FX_CACHE: dict = {"rates": None, "fetched_at": 0.0, "source": ""}
_FX_TTL = 3600  # 1 hour


def _get_fx() -> dict:
    """Return live FX rates {USD, EUR, SGD} as THB-per-unit. Cached 1h.
    Source: frankfurter.app (ECB-backed, no key, free)."""
    import time
    import urllib.request
    import json as _json

    now = time.time()
    if _FX_CACHE["rates"] and (now - _FX_CACHE["fetched_at"]) < _FX_TTL:
        return {**_FX_CACHE["rates"], "_source": _FX_CACHE["source"],
                "_age_seconds": int(now - _FX_CACHE["fetched_at"])}

    try:
        req = urllib.request.Request(
            "https://api.frankfurter.app/latest?base=THB&symbols=USD,EUR,SGD",
            headers={"User-Agent": "leka-catalogs-gateway/0.7"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        # frankfurter returns base=THB → e.g. {"USD": 0.029, ...} (USD per 1 THB).
        # We want THB-per-1-unit. Invert.
        rates = {ccy: round(1 / r, 4) for ccy, r in data["rates"].items()}
        _FX_CACHE["rates"] = rates
        _FX_CACHE["fetched_at"] = now
        _FX_CACHE["source"] = f"frankfurter.app {data.get('date','?')}"
        return {**rates, "_source": _FX_CACHE["source"], "_age_seconds": 0}
    except Exception as e:
        app.logger.warning("FX fetch failed: %s — using fallback", e)
        # Hardcoded fallback (loosely calibrated to mid-2026 levels).
        return {"USD": 33.0, "EUR": 36.5, "SGD": 24.0,
                "_source": "fallback (FX fetch failed)", "_age_seconds": 0}


def _logistics_band(eur_fob: float, tiers: list) -> tuple[float, float]:
    """Pick (min_pct, max_pct) for an EUR-FOB value from the tier table."""
    for t in tiers:
        cap = t.get("fob_eur_max")
        if cap is None or eur_fob <= float(cap):
            return float(t["min_pct"]), float(t["max_pct"])
    last = tiers[-1]
    return float(last["min_pct"]), float(last["max_pct"])


def _tier_label(t: dict) -> str:
    cap = t.get("fob_eur_max")
    return "EUR " + (f"≤ {int(cap)}" if cap is not None else "> last")


def _compute_cascade(brand: str, source_ccy: str, source_fob: float,
                     cfg: dict, fx: dict) -> dict:
    """Compute the full FOB → Landed → Retail (TH/SG) cascade for one SKU.

    All money in THB unless suffixed. Mirrors the flat-uplift branch of
    shared/landed_pricing.price_row() — the per-CBM path needs real
    dimensions we don't have at dashboard render time, so this is an
    approximation good for "what would this product cost under current
    config" exploration.
    """
    g = cfg.get("global") or {}
    b = (cfg.get("brands") or {}).get(brand) or {}

    # Resolve effective params for this brand.
    gm = float(b.get("gross_margin", 0.35))
    th_customer_vat = float(g.get("th_customer_vat_rate", 0.07))
    sg_customer_gst = float(g.get("sg_customer_gst_rate", 0.09))
    sg_nubo_registered = bool(g.get("sg_nubo_gst_registered", False))

    if brand == "wisdom":
        # China-origin path (FOB USD, no EU logistics cascade).
        import_duty = float(b.get("import_duty_rate", 0.07))
        thai_vat = float(g.get("thai_vat_rate", 0.07))
        usd_thb = fx.get("USD", 35.0)
        fob_thb = source_fob * usd_thb
        cif_thb = fob_thb            # FOB ≈ CIF for the simplified path
        freight_thb = 0.0
        duty_thb = round(cif_thb * import_duty, 2)
        vat_thb = round((cif_thb + duty_thb) * thai_vat, 2)
        landed_thb = round(cif_thb + duty_thb + vat_thb, 2)
        landed_thb_raw = landed_thb
        logistics_clamp = ""
        eur_fob_equiv = source_fob * usd_thb / fx.get("EUR", 36.5)
    else:
        # EU-origin path (FOB EUR — Rampline's NOK comes pre-converted).
        duty = float(g.get("duty_rate_non_china", 0.10))
        thai_vat = float(g.get("thai_vat_rate", 0.07))
        uplift = float(g.get("unmatched_landed_uplift", 1.35))
        tiers = cfg.get("logistics_tiers") or []
        eur_thb = fx.get("EUR", 36.5)
        # Berliner's source price is the list price; cost = list × (1 − EXW_DISCOUNT).
        exw_disc = float(b.get("exw_discount", 0.0)) if brand == "berliner" else 0.0
        eur_fob_effective = round(source_fob * (1 - exw_disc), 2) if exw_disc else source_fob
        fob_thb = eur_fob_effective * eur_thb
        cif_thb = fob_thb * uplift
        freight_thb = round(cif_thb - fob_thb, 2)
        duty_thb = round(cif_thb * duty, 2)
        vat_thb = round((cif_thb + duty_thb) * thai_vat, 2)
        landed_thb_raw = round(cif_thb + duty_thb + vat_thb, 2)
        # Tier clamp on logistics_pct.
        lo_pct, hi_pct = _logistics_band(eur_fob_effective, tiers)
        floor_landed = fob_thb * (1 + lo_pct)
        cap_landed = fob_thb * (1 + hi_pct)
        logistics_clamp = ""
        if landed_thb_raw < floor_landed:
            landed_thb = round(floor_landed, 2)
            logistics_clamp = "floored"
        elif landed_thb_raw > cap_landed:
            landed_thb = round(cap_landed, 2)
            logistics_clamp = "capped"
        else:
            landed_thb = landed_thb_raw
        eur_fob_equiv = eur_fob_effective

    retail_pre_tax_thb = round(landed_thb / (1 - gm), 2)
    # TH customer-facing (VAT-inclusive on the retail base).
    th_retail_thb = round(retail_pre_tax_thb * (1 + th_customer_vat), 2)
    # SG customer-facing via Nubo. GST applied only when Nubo is registered.
    sg_gst_multiplier = (1 + sg_customer_gst) if sg_nubo_registered else 1.0
    sg_retail_thb = round(retail_pre_tax_thb * sg_gst_multiplier, 2)
    sg_retail_sgd = round(sg_retail_thb / fx.get("SGD", 24.0), 2)
    th_retail_usd = round(th_retail_thb / fx.get("USD", 33.0), 2)
    th_retail_eur = round(th_retail_thb / fx.get("EUR", 36.5), 2)

    return {
        "brand": brand,
        "source_ccy": source_ccy,
        "source_fob": source_fob,
        "eur_fob_equiv": round(eur_fob_equiv, 2),
        "fob_thb": round(fob_thb, 2),
        "cif_thb": round(cif_thb, 2),
        "freight_thb": freight_thb,
        "duty_thb": duty_thb,
        "thai_import_vat_thb": vat_thb,
        "landed_thb_raw": landed_thb_raw,
        "landed_thb": landed_thb,
        "logistics_clamp": logistics_clamp,
        "gross_margin": gm,
        "retail_pre_tax_thb": retail_pre_tax_thb,
        "th_customer_vat_rate": th_customer_vat,
        "th_retail_thb": th_retail_thb,
        "th_retail_usd": th_retail_usd,
        "th_retail_eur": th_retail_eur,
        "sg_customer_gst_rate": sg_customer_gst if sg_nubo_registered else 0.0,
        "sg_nubo_gst_registered": sg_nubo_registered,
        "sg_retail_thb": sg_retail_thb,
        "sg_retail_sgd": sg_retail_sgd,
    }


def _fetch_brand_examples(brand: str, cfg: dict, fx: dict) -> list[dict]:
    """Pull one real product per logistics tier from Firestore and compute
    the cascade with current config. Returns up to len(tiers) examples."""
    from google.cloud import firestore  # type: ignore

    tiers = cfg.get("logistics_tiers") or []
    n_tiers = len(tiers)
    if n_tiers == 0:
        return []

    db_vendors = firestore.Client(project="ai-agents-go", database="vendors")
    examples_by_tier: dict[int, dict] = {}

    if brand == "rampline":
        # Variants live in an audit doc keyed by YYYY-MM-DD date; pick the
        # alphabetically-latest doc (avoid order_by which depends on an
        # index that may not exist on a named DB).
        coll = db_vendors.collection("vendors").document("rampline").collection("pricelists")
        all_docs = list(coll.stream())
        if not all_docs:
            return []
        all_docs.sort(key=lambda s: s.id, reverse=True)
        d = all_docs[0].to_dict() or {}
        variants = d.get("variants") or {}
        # Each variant already has eur_fob + net_nok pre-computed at import.
        rows = []
        for k, v in variants.items():
            eur = float(v.get("eur_fob") or 0)
            net_nok = float(v.get("net_nok") or 0)
            if eur <= 0:
                continue
            rows.append({"sku": k,
                         "name": v.get("article_code") or v.get("description") or k,
                         "eur": eur,
                         "net_nok": net_nok})
        rows.sort(key=lambda r: r["eur"])
        for r in rows:
            ti = _tier_index(r["eur"], tiers)
            if ti not in examples_by_tier:
                cascade = _compute_cascade("rampline", "EUR", r["eur"], cfg, fx)
                examples_by_tier[ti] = {
                    "tier_index": ti,
                    "tier_label": _tier_label(tiers[ti]),
                    "sku": r["sku"],
                    "name": r["name"],
                    "source_fob_native": r["net_nok"],
                    "source_native_ccy": "NOK",
                    "cascade": cascade,
                }
                if len(examples_by_tier) == n_tiers:
                    break
        return [examples_by_tier[i] for i in sorted(examples_by_tier)]

    if brand == "wisdom":
        # Per-product fob_usd, no stored landed — compute via cascade fn.
        coll = db_vendors.collection("vendors").document("wisdom").collection("products")
        docs = list(coll.limit(300).stream())
        rows = []
        usd_per_eur = fx.get("USD", 33.0) / fx.get("EUR", 36.5)
        for doc in docs:
            d = doc.to_dict() or {}
            fob = (d.get("pricing") or {}).get("fob_usd") or d.get("fob_usd")
            if not fob or float(fob) <= 0:
                continue
            eur_equiv = float(fob) * usd_per_eur
            rows.append({"sku": doc.id, "name": d.get("name") or doc.id,
                         "fob_usd": float(fob), "eur_equiv": eur_equiv})
        rows.sort(key=lambda r: r["eur_equiv"])
        for r in rows:
            ti = _tier_index(r["eur_equiv"], tiers)
            if ti not in examples_by_tier:
                cascade = _compute_cascade("wisdom", "USD", r["fob_usd"], cfg, fx)
                examples_by_tier[ti] = {
                    "tier_index": ti,
                    "tier_label": _tier_label(tiers[ti]),
                    "sku": r["sku"],
                    "name": r["name"],
                    "source_fob_native": r["fob_usd"],
                    "source_native_ccy": "USD",
                    "cascade": cascade,
                }
                if len(examples_by_tier) == n_tiers:
                    break
        return [examples_by_tier[i] for i in sorted(examples_by_tier)]

    # vinci + berliner: per-product eur_fob + stored retail_thb available.
    coll = db_vendors.collection("vendors").document(brand).collection("products")
    docs = list(coll.limit(500).stream())
    rows = []
    for doc in docs:
        d = doc.to_dict() or {}
        p = d.get("pricing") or {}
        eur = p.get("eur_fob")
        if not eur or float(eur) <= 0:
            continue
        rows.append({"sku": doc.id, "name": d.get("name") or doc.id,
                     "eur_fob": float(eur),
                     "stored_retail_thb": p.get("retail_thb")})
    rows.sort(key=lambda r: r["eur_fob"])
    for r in rows:
        ti = _tier_index(r["eur_fob"], tiers)
        if ti not in examples_by_tier:
            cascade = _compute_cascade(brand, "EUR", r["eur_fob"], cfg, fx)
            examples_by_tier[ti] = {
                "tier_index": ti,
                "tier_label": _tier_label(tiers[ti]),
                "sku": r["sku"],
                "name": r["name"],
                "source_fob_native": r["eur_fob"],
                "source_native_ccy": "EUR",
                "stored_retail_thb": r["stored_retail_thb"],
                "cascade": cascade,
            }
            if len(examples_by_tier) == n_tiers:
                break
    return [examples_by_tier[i] for i in sorted(examples_by_tier)]


def _tier_index(eur_fob: float, tiers: list) -> int:
    for i, t in enumerate(tiers):
        cap = t.get("fob_eur_max")
        if cap is None or eur_fob <= float(cap):
            return i
    return len(tiers) - 1


@app.route("/api/pricing-context")
def api_pricing_context():
    """Live FX + per-brand cost-cascade examples driven by current config."""
    from shared.pricing_config import get_full_config, reset_cache
    reset_cache()
    cfg = get_full_config() or _empty_config()
    fx = _get_fx()

    brands_out = {}
    for brand in ("vinci", "berliner", "rampline", "wisdom"):
        try:
            brands_out[brand] = _fetch_brand_examples(brand, cfg, fx)
        except Exception as e:
            app.logger.warning("examples for %s failed: %s", brand, e)
            brands_out[brand] = {"error": str(e)[:200]}

    return jsonify({
        "fx": fx,
        "config_summary": {
            "global": cfg.get("global", {}),
            "brands": cfg.get("brands", {}),
            "logistics_tiers": cfg.get("logistics_tiers", []),
        },
        "brands": brands_out,
    })


@app.route("/api/pricing-config", methods=["POST"])
def api_post_pricing_config():
    from shared.pricing_config import write_full_config

    payload = request.get_json(silent=True) or {}
    err = _validate_pricing_payload(payload)
    if err:
        return jsonify({"error": err}), 400

    user = (
        request.headers.get("X-Goco-User-Email")
        or _strip_iap_email(request.headers.get("X-Goog-Authenticated-User-Email", ""))
        or "unknown"
    )
    try:
        doc = write_full_config(payload, updated_by=user)
    except Exception as e:  # surface Firestore errors as 500 (sanitized)
        app.logger.exception("Firestore write failed")
        return jsonify({"error": "Firestore write failed", "detail": str(e)[:200]}), 500
    return jsonify(doc)


def _strip_iap_email(raw: str) -> str:
    """IAP injects 'accounts.google.com:user@x.com'. Strip the prefix."""
    return raw.split(":", 1)[-1] if ":" in raw else raw


def _empty_config() -> dict:
    """Returned by GET when Firestore has no doc yet — gives the form
    something to render so the user can save the seed values from the UI."""
    return {
        "global": {
            "thai_vat_rate": 0.07,
            "duty_rate_non_china": 0.10,
            "duty_rate_china": 0.0,
            "unmatched_landed_uplift": 1.35,
            "default_packing_factor": 0.15,
            # Customer-facing destination taxes. Independent of the
            # import VAT already in `landed_thb`.
            "th_customer_vat_rate": 0.07,    # 7% Thai sales VAT
            "sg_customer_gst_rate": 0.09,    # 9% SG GST (Nubo not yet
                                             # GST-registered → see flag)
            "sg_nubo_gst_registered": False, # When True, SG retail
                                             # includes GST. When False,
                                             # SG retail is GST-free.
        },
        "brands": {
            "vinci":    {"gross_margin": 0.35,
                         "source_pricelist_url": "C:\\Users\\Eukrit\\My Drive\\Partners Playground\\Vinci\\Vinci Play Prices\\2026-05-11 Vinci pricelist_export_1778483593.xlsx",
                         "source_pricelist_label": "Vinci pricelist 2026-05-11 (xlsx)"},
            "berliner": {"gross_margin": 0.25, "exw_discount": 0.15,
                         "source_pricelist_url": "berliner-catalog/data/pricelist_2026-01-01.csv",
                         "source_pricelist_label": "Berliner pricelist 2026-01-01 (in-repo CSV)"},
            "rampline": {"gross_margin": 0.30,
                         "source_pricelist_url": "https://drive.google.com/drive/folders/Rampline%20Price%20list%202025",
                         "source_pricelist_label": "Rampline 2025 NOK pricelist (Google Drive)"},
            "wisdom":   {"gross_margin": 0.50, "import_duty_rate": 0.07,
                         "default_usd_thb": 35.0,
                         "source_pricelist_url": "wisdom-catalog/data/",
                         "source_pricelist_label": "Wisdom Excel catalogs (in-repo)"},
        },
        "logistics_tiers": [
            {"fob_eur_max": 500,    "min_pct": 0.80, "max_pct": 2.50},
            {"fob_eur_max": 2000,   "min_pct": 0.60, "max_pct": 1.80},
            {"fob_eur_max": 10000,  "min_pct": 0.45, "max_pct": 1.20},
            {"fob_eur_max": None,   "min_pct": 0.35, "max_pct": 0.80},
        ],
    }


def _validate_pricing_payload(p: dict) -> str | None:
    """Cheap range-checks. Returns error string on failure, None on success.
    The Firestore doc is small and edited rarely — we just want to catch
    obvious typos like a 35% margin entered as 35 instead of 0.35."""
    if not isinstance(p, dict):
        return "Payload must be an object"
    g = p.get("global") or {}
    for k, lo, hi in [
        ("thai_vat_rate", 0, 1),
        ("duty_rate_non_china", 0, 1),
        ("duty_rate_china", 0, 1),
        ("default_packing_factor", 0, 1),
        ("unmatched_landed_uplift", 1, 5),
        ("th_customer_vat_rate", 0, 1),
        ("sg_customer_gst_rate", 0, 1),
    ]:
        if k in g and not (lo <= float(g[k]) <= hi):
            return f"global.{k} out of range [{lo}, {hi}]"
    for brand, b in (p.get("brands") or {}).items():
        for k in ("gross_margin", "exw_discount", "import_duty_rate"):
            if k in b and not (0 <= float(b[k]) < 1):
                return f"brands.{brand}.{k} must be in [0, 1)"
    return None


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
