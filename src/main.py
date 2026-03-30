"""Leka Product Catalogs — Root service with health endpoint."""
import os
import json
from datetime import datetime, timezone
from flask import Flask, jsonify

app = Flask(__name__)

SERVICE_NAME = "leka-product-catalogs"
VERSION = "0.1.0"


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/")
def index():
    return jsonify({
        "service": SERVICE_NAME,
        "version": VERSION,
        "brands": ["wisdom"],
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
