"""Firestore-backed pricing config loader.

Source of truth: `pricing_config/canonical` in the `leka-product-catalogs`
Firestore database (project ai-agents-go). Editable via
`docs/forms/pricing-config.html` behind go-access-gateway.

Schema (single document):

    {
      "updated_at":  "<iso8601>",
      "updated_by":  "<email>",                # gateway-forwarded identity
      "global": {
        "thai_vat_rate":            0.07,
        "duty_rate_non_china":      0.10,
        "duty_rate_china":          0.0,
        "unmatched_landed_uplift":  1.35,
        "default_packing_factor":   0.15
      },
      "brands": {
        "vinci":    { "gross_margin": 0.35 },
        "berliner": { "gross_margin": 0.25, "exw_discount": 0.15 },
        "rampline": { "gross_margin": 0.30 },
        "wisdom":   { "gross_margin": 0.50,
                      "import_duty_rate": 0.07,
                      "default_usd_thb": 35.0 }
      },
      "logistics_tiers": [
        { "fob_eur_max": 500,    "min_pct": 0.60, "max_pct": 1.20 },
        ...
      ]
    }

Reader contract:

    cfg = get_pricing_config("vinci")    # global + brand merged
    cfg.get("gross_margin")              # → 0.35

When Firestore is unreachable (no ADC, offline, env-var disabled) this
returns `{}` and the importing module falls back to its module-level
constants. Process-cached on first hit.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

log = logging.getLogger(__name__)

FS_PROJECT = "ai-agents-go"
FS_DATABASE = "leka-product-catalogs"
FS_COLLECTION = "pricing_config"
FS_DOCUMENT = "canonical"

# Process-cached snapshot of the doc. Loaded on first call to
# get_pricing_config(); cleared by reset_cache() (used by the Flask
# POST handler so its own re-reads see the freshly written doc).
_cache: dict[str, Any] | None = None
_lock = threading.Lock()


def _load_from_firestore() -> dict[str, Any]:
    """Read pricing_config/canonical. Returns {} on any failure."""
    if os.environ.get("PRICING_CONFIG_DISABLE") == "1":
        return {}
    try:
        from google.cloud import firestore  # type: ignore
        db = firestore.Client(project=FS_PROJECT, database=FS_DATABASE)
        snap = db.collection(FS_COLLECTION).document(FS_DOCUMENT).get()
        return snap.to_dict() if snap.exists else {}
    except Exception as e:
        log.warning(
            "pricing_config load failed (non-fatal, falling back to "
            "module defaults): %s", e,
        )
        return {}


def _ensure_loaded() -> dict[str, Any]:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = _load_from_firestore()
    return _cache


def get_pricing_config(brand: str | None = None) -> dict[str, Any]:
    """Return merged pricing config.

    Brand-specific keys (e.g. brands.vinci.gross_margin) override global
    keys with the same name. Always includes `logistics_tiers` and
    `updated_at` / `updated_by` if present.

    Returns `{}` when Firestore unreachable — callers must treat all
    keys as optional and fall back to their own defaults.
    """
    snap = _ensure_loaded()
    if not snap:
        return {}

    merged: dict[str, Any] = {}
    merged.update(snap.get("global") or {})
    if brand:
        brand_keys = (snap.get("brands") or {}).get(brand) or {}
        merged.update(brand_keys)
    if "logistics_tiers" in snap:
        merged["logistics_tiers"] = snap["logistics_tiers"]
    for k in ("updated_at", "updated_by"):
        if k in snap:
            merged[k] = snap[k]
    return merged


def get_full_config() -> dict[str, Any]:
    """Return the raw doc (global + brands + tiers + audit fields).

    Used by the Flask GET handler to render the editor form.
    """
    return dict(_ensure_loaded())


def reset_cache() -> None:
    """Drop the process cache. Called after a successful POST so the
    next get_*() reads the freshly written doc."""
    global _cache
    with _lock:
        _cache = None


def write_full_config(payload: dict[str, Any], updated_by: str) -> dict[str, Any]:
    """Replace pricing_config/canonical with `payload` (sans audit).

    Stamps `updated_at` (UTC ISO) and `updated_by`. Resets the cache.
    Returns the written doc. Raises if Firestore unreachable — the
    Flask POST handler surfaces that as a 5xx.
    """
    from datetime import datetime, timezone
    from google.cloud import firestore  # type: ignore

    doc = {
        "global": payload.get("global") or {},
        "brands": payload.get("brands") or {},
        "logistics_tiers": payload.get("logistics_tiers") or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": updated_by or "unknown",
    }
    db = firestore.Client(project=FS_PROJECT, database=FS_DATABASE)
    db.collection(FS_COLLECTION).document(FS_DOCUMENT).set(doc)
    reset_cache()
    return doc
