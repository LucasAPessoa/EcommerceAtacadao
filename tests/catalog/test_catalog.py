"""
Tests for catalog: /catalog/products/* and /catalog/categories/*
"""

from __future__ import annotations

import random

import httpx
import pytest

from tests.conftest import API_V1_PREFIX, auth_headers

# ─────────────────────────────────────────────────────────────────────────────
# /catalog/products/
# ─────────────────────────────────────────────────────────────────────────────


class TestProductsList:
    """GET /catalog/products/"""

    @pytest.mark.asyncio
    async def test_list_products_public(self, client: httpx.AsyncClient):
        """Catalog listing should be public (no auth required)."""
        resp = await client.get(f"{API_V1_PREFIX}/catalog/products/")
        assert resp.status_code == 200, resp.text
        products = resp.json()["data"]
        assert isinstance(products, list)
        assert len(products) >= 1
        for p in products:
            assert "id" in p
            assert "code" in p
            assert "name" in p
            assert "variants" in p
            assert "categories" in p
            assert isinstance(p["categories"], list)

    @pytest.mark.asyncio
    async def test_list_supports_pagination(self, client: httpx.AsyncClient):
        resp = await client.get(f"{API_V1_PREFIX}/catalog/products/?skip=0&limit=5")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) <= 5

    @pytest.mark.asyncio
    async def test_list_includes_variants(self, client: httpx.AsyncClient):
        """Each product should expose its variants."""
        resp = await client.get(f"{API_V1_PREFIX}/catalog/products/")
        products = resp.json()["data"]
        any_with_variants = any(p.get("variants") for p in products)
        assert any_with_variants, "Expected at least one product with variants"


class TestProductByCode:
    """GET /catalog/products/code/{code}"""

    @pytest.mark.asyncio
    async def test_get_product_by_code_succeeds(self, client: httpx.AsyncClient):
        # Get any product's code
        listing = await client.get(f"{API_V1_PREFIX}/catalog/products/")
        products = listing.json()["data"]
        assert products, "O catálogo de teste deve conter ao menos um produto"
        code = products[0]["code"]

        resp = await client.get(f"{API_V1_PREFIX}/catalog/products/code/{code}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["code"] == code

    @pytest.mark.asyncio
    async def test_get_nonexistent_product_returns_404(self, client: httpx.AsyncClient):
        resp = await client.get(f"{API_V1_PREFIX}/catalog/products/code/NO-SUCH-CODE-XYZ")
        assert resp.status_code == 404, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# /catalog/categories/
# ─────────────────────────────────────────────────────────────────────────────


class TestCategories:
    """GET /catalog/categories/"""

    @pytest.mark.asyncio
    async def test_list_categories_public(self, client: httpx.AsyncClient):
        resp = await client.get(f"{API_V1_PREFIX}/catalog/categories/")
        assert resp.status_code == 200, resp.text
        cats = resp.json()["data"]
        assert isinstance(cats, list)
        # Seed has 4 categories
        assert len(cats) >= 1
        for c in cats:
            assert "id" in c
            assert "name" in c

    @pytest.mark.asyncio
    async def test_list_supports_pagination(self, client: httpx.AsyncClient):
        resp = await client.get(f"{API_V1_PREFIX}/catalog/categories/?skip=0&limit=2")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) <= 2


# Catálogo somente leitura (spec 003)
# ─────────────────────────────────────────────────────────────────────────────

READ_ONLY_RESOURCES = [
    "categories",
    "products",
    "product-variants",
    "product-images",
    "product-listings",
    "listing-images",
    "listing-attributes",
]
ZERO_ID = "00000000-0000-0000-0000-000000000000"
CATALOG = f"{API_V1_PREFIX}/catalog"


class TestCatalogReadOnly:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("resource", READ_ONLY_RESOURCES)
    async def test_get_list_is_200(self, client: httpx.AsyncClient, resource: str):
        resp = await client.get(f"{CATALOG}/{resource}/")
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resource", READ_ONLY_RESOURCES)
    async def test_get_detail_is_200_when_data_exists(
        self, client: httpx.AsyncClient, resource: str
    ):
        items = (await client.get(f"{CATALOG}/{resource}/")).json()["data"]
        if not items:
            # recurso sem dados no seed: id inexistente deve ser 404, não 405
            resp = await client.get(f"{CATALOG}/{resource}/{ZERO_ID}")
            assert resp.status_code == 404, resp.text
            return
        resp = await client.get(f"{CATALOG}/{resource}/{items[0]['id']}")
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resource", READ_ONLY_RESOURCES)
    async def test_post_is_405_for_admin(
        self, client: httpx.AsyncClient, admin_token: str, resource: str
    ):
        resp = await client.post(
            f"{CATALOG}/{resource}/", json={}, headers=auth_headers(admin_token)
        )
        assert resp.status_code == 405, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resource", [r for r in READ_ONLY_RESOURCES if r != "product-variants"]
    )
    async def test_patch_is_405_for_admin(
        self, client: httpx.AsyncClient, admin_token: str, resource: str
    ):
        resp = await client.patch(
            f"{CATALOG}/{resource}/{ZERO_ID}", json={}, headers=auth_headers(admin_token)
        )
        assert resp.status_code == 405, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resource", READ_ONLY_RESOURCES)
    async def test_delete_is_405_for_admin(
        self, client: httpx.AsyncClient, admin_token: str, resource: str
    ):
        resp = await client.delete(
            f"{CATALOG}/{resource}/{ZERO_ID}", headers=auth_headers(admin_token)
        )
        assert resp.status_code == 405, resp.text

    @pytest.mark.asyncio
    async def test_post_product_is_405_without_auth(self, client: httpx.AsyncClient):
        resp = await client.post(f"{CATALOG}/products/", json={"code": "TEST-002"})
        assert resp.status_code == 405, resp.text

    @pytest.mark.asyncio
    async def test_post_product_is_405_for_regular_user(
        self, client: httpx.AsyncClient, user_token: str
    ):
        resp = await client.post(
            f"{CATALOG}/products/", json={"code": "TEST-001"}, headers=auth_headers(user_token)
        )
        assert resp.status_code == 405, resp.text

    @pytest.mark.asyncio
    async def test_openapi_has_no_catalog_write_except_variant_price(
        self, client: httpx.AsyncClient
    ):
        paths = (await client.get("/openapi.json")).json()["paths"]
        for path, ops in paths.items():
            for resource in READ_ONLY_RESOURCES:
                base = f"{CATALOG}/{resource}"
                if path == f"{base}/" or path.startswith(f"{base}/"):
                    writes = {m for m in ops if m in ("post", "patch", "put", "delete")}
                    if resource == "product-variants" and path == f"{base}/{{item_id}}":
                        assert writes == {"patch"}, path
                    else:
                        assert not writes, (path, writes)


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /catalog/product-variants/{id}  (preço) e pricing-tiers
# ─────────────────────────────────────────────────────────────────────────────


class TestVariantPrice:
    @staticmethod
    async def _first_variant(client: httpx.AsyncClient) -> dict:
        items = (await client.get(f"{CATALOG}/product-variants/")).json()["data"]
        assert items, "seed sem variações"
        return items[0]

    @pytest.mark.asyncio
    async def test_admin_updates_price_and_get_reflects(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        variant = await self._first_variant(client)
        url = f"{CATALOG}/product-variants/{variant['id']}"
        original = variant["base_price"]
        try:
            resp = await client.patch(
                url, json={"base_price": "9.90"}, headers=auth_headers(admin_token)
            )
            assert resp.status_code == 200, resp.text
            assert float(resp.json()["data"]["base_price"]) == 9.90
            got = await client.get(url)
            assert float(got.json()["data"]["base_price"]) == 9.90
        finally:
            await client.patch(
                url, json={"base_price": str(original)}, headers=auth_headers(admin_token)
            )
        restored = await client.get(url)
        assert float(restored.json()["data"]["base_price"]) == float(original)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"base_price": "9.90", "stock_quantity": 5},
            {"base_price": "9.90", "variation_name": "x"},
            {"base_price": "-1"},
        ],
    )
    async def test_invalid_body_is_422(
        self, client: httpx.AsyncClient, admin_token: str, body: dict
    ):
        variant = await self._first_variant(client)
        resp = await client.patch(
            f"{CATALOG}/product-variants/{variant['id']}",
            json=body,
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_regular_user_is_403(self, client: httpx.AsyncClient, user_token: str):
        variant = await self._first_variant(client)
        resp = await client.patch(
            f"{CATALOG}/product-variants/{variant['id']}",
            json={"base_price": "9.90"},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_without_token_is_401(self, client: httpx.AsyncClient):
        variant = await self._first_variant(client)
        resp = await client.patch(
            f"{CATALOG}/product-variants/{variant['id']}", json={"base_price": "9.90"}
        )
        assert resp.status_code == 401, resp.text

    @pytest.mark.asyncio
    async def test_unknown_variant_is_404(self, client: httpx.AsyncClient, admin_token: str):
        resp = await client.patch(
            f"{CATALOG}/product-variants/{ZERO_ID}",
            json={"base_price": "9.90"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404, resp.text


class TestPricingTiersAdmin:
    @pytest.mark.asyncio
    async def test_admin_crud(self, client: httpx.AsyncClient, admin_token: str):
        headers = auth_headers(admin_token)
        product = (await client.get(f"{CATALOG}/products/")).json()["data"][0]
        created = await client.post(
            f"{CATALOG}/pricing-tiers/",
            json={
                "product_id": product["id"],
                "min_quantity": random.randint(10_000, 10_000_000),
                "unit_price": "5.00",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        tier_id = created.json()["data"]["id"]
        patched = await client.patch(
            f"{CATALOG}/pricing-tiers/{tier_id}",
            json={"unit_price": "4.50"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert float(patched.json()["data"]["unit_price"]) == 4.50
        deleted = await client.delete(f"{CATALOG}/pricing-tiers/{tier_id}", headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert (await client.get(f"{CATALOG}/pricing-tiers/{tier_id}")).status_code == 404

    @pytest.mark.asyncio
    async def test_regular_user_cannot_write(self, client: httpx.AsyncClient, user_token: str):
        resp = await client.delete(
            f"{CATALOG}/pricing-tiers/{ZERO_ID}", headers=auth_headers(user_token)
        )
        assert resp.status_code == 403, resp.text
