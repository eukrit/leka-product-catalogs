"""Leka Product Catalogs — Root service with health endpoint and brand registry."""
import os
from datetime import datetime, timezone
from flask import Flask, jsonify

app = Flask(__name__)

SERVICE_NAME = "leka-product-catalogs"
VERSION = "0.2.0"

# Known brands — auto-populated from Firestore brands collection at runtime
# Fallback list used when Firestore is unavailable
KNOWN_BRANDS = ["wisdom"]


def get_brands_from_firestore():
    """Fetch registered brands from Firestore brands collection."""
    try:
        from google.cloud import firestore
        db = firestore.Client(project="ai-agents-go")
        brands = []
        for doc in db.collection("brands").stream():
            data = doc.to_dict()
            brands.append({
                "slug": doc.id,
                "name": data.get("name", doc.id),
                "product_count": data.get("product_count", 0),
                "last_import": str(data.get("last_import", "")),
            })
        return brands if brands else None
    except Exception:
        return None


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/")
def index():
    brands = get_brands_from_firestore()
    if brands:
        return jsonify({
            "service": SERVICE_NAME,
            "version": VERSION,
            "architecture": "multi-brand with separate collections",
            "brands": brands,
        })
    return jsonify({
        "service": SERVICE_NAME,
        "version": VERSION,
        "brands": KNOWN_BRANDS,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
