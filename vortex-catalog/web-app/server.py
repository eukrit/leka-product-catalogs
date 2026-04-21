"""Vortex Aquatics Catalog — Flask server for Cloud Run."""
import os
from flask import Flask, send_from_directory, jsonify

app = Flask(__name__, static_folder="public", static_url_path="")


@app.route("/")
def index():
    return send_from_directory("public", "index.html")


@app.route("/health")
def health():
    from datetime import datetime, timezone
    return jsonify({"status": "ok", "brand": "vortex", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("public", path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8082))
    app.run(host="0.0.0.0", port=port, debug=True)
