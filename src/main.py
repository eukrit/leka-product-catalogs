"""Leka Product Catalogs — Gateway service.

Serves:
  /                → Collections landing page
  /vinciplay/      → Vinci Play catalog
  /health          → Health check
"""
import os
from datetime import datetime, timezone
from flask import Flask, send_from_directory, jsonify

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

SERVICE_NAME = "leka-product-catalogs"
VERSION = "0.5.0"

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
