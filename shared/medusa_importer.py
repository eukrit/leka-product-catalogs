"""
Shared Medusa Admin API import helpers.

Used by brand-specific importers (wisdom, vinci) to write products
to Medusa Commerce v2 via the Admin API.
"""
import os
import json
import time
import requests
from typing import Optional


class MedusaImporter:
    """Client for Medusa Admin API product operations."""

    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = (base_url or os.environ.get("MEDUSA_BACKEND_URL", "http://localhost:9000")).rstrip("/")
        self.api_key = api_key or os.environ.get("MEDUSA_ADMIN_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "x-medusa-access-token": self.api_key,
        })

    def _post(self, path: str, data: dict) -> dict:
        resp = self.session.post(f"{self.base_url}{path}", json=data)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, params: dict = None) -> dict:
        resp = self.session.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def create_product(
        self,
        title: str,
        handle: str,
        description: str = "",
        status: str = "published",
        metadata: dict = None,
        images: list = None,
        category_ids: list = None,
        collection_id: str = None,
        tag_ids: list = None,
        variant: dict = None,
    ) -> dict:
        """Create a product with a single variant."""
        data: dict = {
            "title": title,
            "handle": handle,
            "description": description,
            "status": status,
            "metadata": metadata or {},
        }

        if images:
            data["images"] = [{"url": img} for img in images]
        if category_ids:
            data["categories"] = [{"id": cid} for cid in category_ids]
        if collection_id:
            data["collection_id"] = collection_id
        if tag_ids:
            data["tags"] = [{"id": tid} for tid in tag_ids]
        if variant:
            data["variants"] = [variant]

        return self._post("/admin/products", data)

    def get_or_create_category(self, name: str, handle: str) -> str:
        """Get existing category by handle or create new one. Returns category ID."""
        resp = self._get("/admin/product-categories", {"handle": handle, "limit": 1})
        categories = resp.get("product_categories", [])
        if categories:
            return categories[0]["id"]

        result = self._post("/admin/product-categories", {
            "name": name,
            "handle": handle,
            "is_active": True,
            "is_internal": False,
        })
        return result["product_category"]["id"]

    def get_or_create_collection(self, title: str, handle: str) -> str:
        """Get existing collection by handle or create new one. Returns collection ID."""
        resp = self._get("/admin/collections", {"handle": [handle], "limit": 1})
        collections = resp.get("collections", [])
        if collections:
            return collections[0]["id"]

        result = self._post("/admin/collections", {
            "title": title,
            "handle": handle,
        })
        return result["collection"]["id"]

    def get_or_create_tag(self, value: str) -> str:
        """Get existing tag or create new one. Returns tag ID."""
        resp = self._get("/admin/product-tags", {"value": [value], "limit": 1})
        tags = resp.get("product_tags", [])
        if tags:
            return tags[0]["id"]

        result = self._post("/admin/product-tags", {"value": value})
        return result["product_tag"]["id"]

    def batch_import(
        self,
        products: list,
        batch_size: int = 50,
        delay: float = 0.1,
    ) -> int:
        """Import a list of product dicts. Returns count of successfully imported products."""
        count = 0
        errors = 0
        for i, product_data in enumerate(products):
            try:
                self.create_product(**product_data)
                count += 1
                if count % batch_size == 0:
                    print(f"  Imported {count} / {len(products)}")
                    time.sleep(delay)
            except requests.HTTPError as e:
                errors += 1
                handle = product_data.get("handle", "unknown")
                print(f"  Error importing {handle}: {e.response.status_code} {e.response.text[:200]}")
            except Exception as e:
                errors += 1
                print(f"  Error: {e}")

        print(f"  Done: {count} imported, {errors} errors")
        return count
