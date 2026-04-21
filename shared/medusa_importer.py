"""
Shared Medusa Admin API import helpers.

Used by brand-specific importers (wisdom, vinci, vortex) to write
products to Medusa Commerce v2 via the Admin API.

Auth — Medusa v2 accepts a Bearer token in the Authorization header.
The token can be either a short-lived user JWT (POST /auth/user/emailpass
returns one) or a long-lived Secret API Key (POST /admin/api-keys with
type=secret). Pass either via `api_key=` or MEDUSA_ADMIN_API_KEY env.

If MEDUSA_ADMIN_EMAIL / MEDUSA_ADMIN_PASSWORD are set (and api_key is
empty), the client auto-logs in and uses the returned JWT.
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

        # Fallback: auto-login with admin email/password if no key was provided.
        if not self.api_key:
            email = os.environ.get("MEDUSA_ADMIN_EMAIL")
            password = os.environ.get("MEDUSA_ADMIN_PASSWORD")
            if email and password:
                self.api_key = self._login_with_password(email, password)

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })

    def _login_with_password(self, email: str, password: str) -> str:
        """POST /auth/user/emailpass → JWT token string."""
        resp = requests.post(
            f"{self.base_url}/auth/user/emailpass",
            json={"email": email, "password": password},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"Login succeeded but no token in response: {data}")
        return token

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
        sales_channel_ids: list = None,
    ) -> dict:
        """Create a product with a single variant.

        Medusa v2 requires every variant to reference a product-level
        `options` entry. If the caller passes a variant without declaring
        options, we inject a default "Style → Standard" option so the
        payload validates.
        """
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
            # Ensure the variant has the option map Medusa v2 expects.
            v = dict(variant)
            if "options" not in v:
                v["options"] = {"Style": "Standard"}
            data["options"] = [{"title": "Style", "values": ["Standard"]}]
            data["variants"] = [v]

        if sales_channel_ids:
            data["sales_channels"] = [{"id": scid} for scid in sales_channel_ids]

        return self._post("/admin/products", data)

    def find_product_by_handle(self, handle: str) -> Optional[str]:
        """Return product ID if a product with this handle exists, else None."""
        try:
            resp = self._get("/admin/products", {"handle": handle, "limit": 1})
            products = resp.get("products", [])
            return products[0]["id"] if products else None
        except Exception:
            return None

    def get_or_create_sales_channel(self, name: str, description: str = "") -> str:
        """Get existing sales channel by name or create a new one. Returns sales_channel ID."""
        resp = self._get("/admin/sales-channels", {"name": name, "limit": 1})
        channels = resp.get("sales_channels", [])
        if channels:
            return channels[0]["id"]

        result = self._post("/admin/sales-channels", {
            "name": name,
            "description": description,
            "is_disabled": False,
        })
        return result["sales_channel"]["id"]

    def create_publishable_api_key(self, title: str, sales_channel_id: str) -> dict:
        """Get-or-create a publishable API key by title. Returns {id, token}.

        Idempotent: if a publishable key with the same title already exists,
        reuse it instead of minting a duplicate.
        """
        # 0) Look for existing key with this title
        try:
            existing = self._get("/admin/api-keys", {"type": "publishable", "limit": 100})
            for k in existing.get("api_keys", []):
                if k.get("title") == title:
                    return {"id": k["id"], "token": k.get("token") or k.get("redacted") or ""}
        except Exception:
            pass

        # 1) Create the key
        result = self._post("/admin/api-keys", {"title": title, "type": "publishable"})
        key = result.get("api_key") or result.get("publishable_api_key")
        key_id = key["id"]
        token = key.get("token") or key.get("redacted") or ""

        # 2) Link to sales channel (Medusa v2: POST /admin/api-keys/:id/sales-channels with {add})
        try:
            self._post(f"/admin/api-keys/{key_id}/sales-channels", {
                "add": [sales_channel_id],
            })
        except requests.HTTPError as e:
            # The exact path varies across 2.x minor versions. Not fatal — the key still works
            # once linked manually via the admin UI. Log and continue.
            print(f"  (warning: could not auto-link publishable key to sales channel: {e.response.status_code})")
        return {"id": key_id, "token": token}

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
        skip_existing: bool = True,
    ) -> int:
        """Import a list of product dicts. Returns count of successfully imported products.

        If skip_existing=True (default), a product whose handle already exists
        in Medusa is skipped rather than retried — makes re-runs idempotent.
        """
        count = 0
        skipped = 0
        errors = 0
        for i, product_data in enumerate(products):
            handle = product_data.get("handle", "unknown")
            try:
                if skip_existing and self.find_product_by_handle(handle):
                    skipped += 1
                    if skipped % batch_size == 0:
                        print(f"  Skipped {skipped} existing (progress {i+1}/{len(products)})")
                    continue
                self.create_product(**product_data)
                count += 1
                if count % batch_size == 0:
                    print(f"  Imported {count} new / {len(products)} total (skipped {skipped})")
                    time.sleep(delay)
            except requests.HTTPError as e:
                errors += 1
                print(f"  Error importing {handle}: {e.response.status_code} {e.response.text[:200]}")
            except Exception as e:
                errors += 1
                print(f"  Error: {e}")

        print(f"  Done: {count} imported, {skipped} skipped (existed), {errors} errors")
        return count
