"""Tests for the Lappset hero_white consumer guard in sync_vendors_to_medusa.

No network: exercises the pure payload/guard functions only. Ensures a Lappset
product is only published with its canonical clean-white hero as images[0]/
thumbnail, and that metadata.hero_white_gcs is propagated to Medusa.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sync_vendors_to_medusa as sv  # noqa: E402

HERO_URL = "https://catalogs.leka.studio/api/i/lappset/hero_white/abc123.png"
HERO_GCS = "gs://ai-agents-go-vendors/lappset/hero_white/abc123.png"


def _lappset_doc(images):
    return {
        "handle": "f24102m", "name": "Maximilian", "item_code": "F24102M",
        "slug": "lappset", "status": "active",
        "category": "multi-play", "pricing": {"retail_thb": 100.0},
        "images": images, "hero_white_gcs": HERO_GCS,
    }


def _white_images():
    return [{"url": HERO_URL, "alt_text": "Maximilian", "is_primary": True,
             "source": "hero_white", "view_type": "render"}]


def test_guard_accepts_normalized_white_hero():
    assert sv._lappset_hero_ok(_lappset_doc(_white_images())) is True


def test_guard_rejects_raw_webapi_hero():
    raw = [{"url": "https://webapi.lappset.com/server/api/v1/file/1/2_image_png",
            "source": "website"}]
    assert sv._lappset_hero_ok(_lappset_doc(raw)) is False


def test_guard_rejects_empty_images():
    assert sv._lappset_hero_ok(_lappset_doc([])) is False


def test_guard_rejects_hero_white_source_but_wrong_url():
    # source tag present but URL is not the hero_white proxy path → reject.
    bad = [{"url": "https://catalogs.leka.studio/api/i/lappset/media/abc.png",
            "source": "hero_white"}]
    assert sv._lappset_hero_ok(_lappset_doc(bad)) is False


def test_guard_accepts_documented_fallback_original():
    # Environment photo with no white source: proxy-served original + flagged.
    doc = {
        "handle": "220597", "name": "Parkour area 5", "slug": "lappset",
        "images": [{"url": "https://catalogs.leka.studio/api/i/lappset/media/xyz.png",
                    "source": "original", "is_primary": True}],
        "hero_white": {"needs_fallback": True, "method": "rgb_passthrough"},
    }
    assert sv._lappset_hero_ok(doc) is True


def test_guard_rejects_original_without_fallback_flag():
    # source=original but NOT flagged needs_fallback → reject (un-normalized).
    doc = {
        "handle": "x", "name": "X", "slug": "lappset",
        "images": [{"url": "https://catalogs.leka.studio/api/i/lappset/media/xyz.png",
                    "source": "original"}],
    }
    assert sv._lappset_hero_ok(doc) is False


def test_create_payload_uses_hero_white_as_thumbnail_and_metadata():
    payload = sv._build_create_payload("lappset", "sc_test", _lappset_doc(_white_images()))
    assert payload["thumbnail"] == HERO_URL
    assert payload["images"][0]["url"] == HERO_URL
    assert payload["metadata"]["hero_white_gcs"] == HERO_GCS


def test_update_payload_propagates_hero_white_metadata():
    out = sv._build_update_payload(_lappset_doc(_white_images()))
    assert out["metadata"]["hero_white_gcs"] == HERO_GCS


def test_hero_white_metadata_absent_for_other_brands():
    # A brand doc with no hero_white_gcs must not inject a None key.
    doc = {"handle": "x", "name": "X", "pricing": {}, "images": []}
    payload = sv._build_create_payload("wisdom", "sc_w", doc)
    assert "hero_white_gcs" not in payload["metadata"]
