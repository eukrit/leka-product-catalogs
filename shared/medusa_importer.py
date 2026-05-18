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

    def _patch(self, path: str, data: dict) -> dict:
        """Medusa v2 admin updates use POST against /admin/<resource>/:id with the partial body."""
        resp = self.session.post(f"{self.base_url}{path}", json=data)
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

    def get_or_create_category(self, name: str, handle: str, parent_category_id: str = None) -> str:
        """Get existing category by handle or create new one. Returns category ID.

        Pass `parent_category_id` to create a child category under an existing parent.
        Medusa v2 supports nested categories via `parent_category_id`.
        """
        resp = self._get("/admin/product-categories", {"handle": handle, "limit": 1})
        categories = resp.get("product_categories", [])
        if categories:
            return categories[0]["id"]

        payload = {
            "name": name,
            "handle": handle,
            "is_active": True,
            "is_internal": False,
        }
        if parent_category_id:
            payload["parent_category_id"] = parent_category_id

        result = self._post("/admin/product-categories", payload)
        return result["product_category"]["id"]

    def add_categories_to_product(self, product_id: str, category_ids: list) -> dict:
        """Append category links to an existing product. Idempotent — Medusa de-dupes existing links."""
        return self._patch(
            f"/admin/products/{product_id}",
            {"categories": [{"id": cid} for cid in category_ids]},
        )

    def set_product_collection(self, product_id: str, collection_id: Optional[str]) -> dict:
        """Set (or clear) the collection link on an existing product."""
        return self._patch(
            f"/admin/products/{product_id}",
            {"collection_id": collection_id},
        )

    def list_products_by_category(self, category_id: str, limit: int = 200) -> list:
        """Return all products linked to a category id (paginated)."""
        out = []
        offset = 0
        while True:
            resp = self._get(
                "/admin/products",
                {"category_id[]": category_id, "limit": limit, "offset": offset, "fields": "id,handle"},
            )
            batch = resp.get("products", [])
            out.extend(batch)
            if len(batch) < limit:
                return out
            offset += limit

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

    def get_product_with_variants(self, handle: str) -> dict | None:
        """Return the full product dict (including variants) for a given handle, or None."""
        try:
            resp = self._get(
                "/admin/products",
                {"handle": handle, "limit": 1, "fields": "id,handle,variants"},
            )
            products = resp.get("products", [])
            return products[0] if products else None
        except Exception:
            return None

    def get_variant_by_sku(self, sku: str) -> tuple[str | None, str | None]:
        """Return (product_id, variant_id) for a given current SKU, or (None, None).

        Note: For Wisdom/Leka Project products post-rebrand, the SKU on the
        variant is the new `LP-XXXXXXXX` nanoid form. To look up by the
        original Wisdom item_code, use `build_legacy_sku_index()` instead.
        """
        try:
            resp = self._get(
                "/admin/products",
                {"sku": sku, "limit": 1, "fields": "id,variants.id,variants.sku"},
            )
            products = resp.get("products", [])
            if not products:
                # Fallback: legacy direct-handle lookup (pre-rebrand products).
                handle = f"wisdom-{sku.lower().replace(' ', '-')}"
                product = self.get_product_with_variants(handle)
                if not product:
                    return None, None
                variants = product.get("variants", [])
                return (product["id"], variants[0]["id"]) if variants else (None, None)
            p = products[0]
            variants = p.get("variants", [])
            match = next((v for v in variants if v.get("sku") == sku), variants[0] if variants else None)
            return (p["id"], match["id"]) if match else (None, None)
        except Exception:
            return None, None

    def build_legacy_sku_index(self, sales_channel_id: str) -> dict[str, tuple[str, str]]:
        """Page through a sales channel and index variants by `metadata.legacy_sku`.

        Used post-rebrand: Wisdom item codes survive in
        `variants[].metadata.legacy_sku` even though the current SKU is now
        `LP-XXXXXXXX`. Returns `{legacy_sku: (product_id, variant_id)}`.
        """
        index: dict[str, tuple[str, str]] = {}
        offset = 0
        limit = 100
        while True:
            try:
                resp = self._get("/admin/products", {
                    "sales_channel_id[]": sales_channel_id,
                    "limit": limit,
                    "offset": offset,
                    "fields": "id,variants.id,variants.sku,variants.metadata",
                })
            except Exception:
                break
            batch = resp.get("products", [])
            if not batch:
                break
            for p in batch:
                pid = p["id"]
                for v in p.get("variants", []) or []:
                    vid = v["id"]
                    md = v.get("metadata") or {}
                    legacy = md.get("legacy_sku")
                    if legacy:
                        index[str(legacy).strip()] = (pid, vid)
                    cur = v.get("sku")
                    if cur and cur not in index:
                        index[cur] = (pid, vid)
            if len(batch) < limit:
                break
            offset += limit
        return index

    def update_variant_prices(
        self,
        product_id: str,
        variant_id: str,
        prices: list[dict],
    ) -> dict:
        """Replace the price list on a variant.

        Args:
            product_id:  Medusa product ID.
            variant_id:  Medusa variant ID.
            prices:      List of {amount: int (in smallest unit), currency_code: str}.

        Returns the updated variant dict.
        """
        resp = self.session.post(
            f"{self.base_url}/admin/products/{product_id}/variants/{variant_id}",
            json={"prices": prices},
        )
        resp.raise_for_status()
        return resp.json()

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
