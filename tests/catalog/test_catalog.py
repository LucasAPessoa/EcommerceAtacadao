"""
Tests for catalog: /catalog/products/* and /catalog/categories/*
"""

from __future__ import annotations

import pytest
import httpx

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

    @pytest.mark.asyncio
    async def test_list_supports_pagination(
        self, client: httpx.AsyncClient
    ):
        resp = await client.get(
            f"{API_V1_PREFIX}/catalog/products/?skip=0&limit=5"
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) <= 5

    @pytest.mark.asyncio
    async def test_list_includes_variants(
        self, client: httpx.AsyncClient
    ):
        """Each product should expose its variants."""
        resp = await client.get(f"{API_V1_PREFIX}/catalog/products/")
        products = resp.json()["data"]
        any_with_variants = any(p.get("variants") for p in products)
        assert any_with_variants, "Expected at least one product with variants"


class TestProductByCode:
    """GET /catalog/products/{code}"""

    @pytest.mark.asyncio
    async def test_get_product_by_code_succeeds(
        self, client: httpx.AsyncClient
    ):
        # Get any product's code
        listing = await client.get(f"{API_V1_PREFIX}/catalog/products/")
        products = listing.json()["data"]
        if not products:
            pytest.skip("No products seeded")
        code = products[0]["code"]

        resp = await client.get(f"{API_V1_PREFIX}/catalog/products/{code}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["code"] == code

    @pytest.mark.asyncio
    async def test_get_nonexistent_product_returns_404(
        self, client: httpx.AsyncClient
    ):
        resp = await client.get(
            f"{API_V1_PREFIX}/catalog/products/NO-SUCH-CODE-XYZ"
        )
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
        resp = await client.get(
            f"{API_V1_PREFIX}/catalog/categories/?skip=0&limit=2"
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# /catalog/products/  (admin-only create)
# ─────────────────────────────────────────────────────────────────────────────

class TestProductAdmin:
    """Admin-only product mutations."""

    @pytest.mark.asyncio
    async def test_regular_user_cannot_create_product(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """SECURITY: cliente1 should NOT be able to create a product."""
        resp = await client.post(
            f"{API_V1_PREFIX}/catalog/products/",
            json={
                "code": "TEST-001",
                "name": "Hack Product",
                "description": "Should not work",
                "category_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=auth_headers(user_token),
        )
        assert resp.status_code in (403, 401), resp.text

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_create_product(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            f"{API_V1_PREFIX}/catalog/products/",
            json={"code": "TEST-002", "name": "Anon Product"},
        )
        assert resp.status_code in (401, 403), resp.text
