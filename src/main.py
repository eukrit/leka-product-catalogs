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
VERSION = "0.6.0"

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
        },
        "brands": {
            "vinci":    {"gross_margin": 0.35},
            "berliner": {"gross_margin": 0.25, "exw_discount": 0.15},
            "rampline": {"gross_margin": 0.30},
            "wisdom":   {"gross_margin": 0.50, "import_duty_rate": 0.07,
                         "default_usd_thb": 35.0},
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
