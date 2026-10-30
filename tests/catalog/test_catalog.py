"""
Tests for catalog: /catalog/products/* and /catalog/categories/*
"""

from __future__ import annotations

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
    @pytest.mark.parametrize("resource", READ_ONLY_RESOURCES)
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
    async def test_openapi_has_no_catalog_write(self, client: httpx.AsyncClient):
        paths = (await client.get("/openapi.json")).json()["paths"]
        for path, ops in paths.items():
            for resource in READ_ONLY_RESOURCES + ["pricing-tiers"]:
                base = f"{CATALOG}/{resource}"
                if path == f"{base}/" or path.startswith(f"{base}/"):
                    writes = {m for m in ops if m in ("post", "patch", "put", "delete")}
                    assert not writes, (path, writes)


# ─────────────────────────────────────────────────────────────────────────────
# Rotas de escrita de preço removidas (spec 008): preço só pela tabela da variação
# ─────────────────────────────────────────────────────────────────────────────


class TestRemovedPriceWrites:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("PATCH", f"product-variants/{ZERO_ID}", {"base_price": "9.90"}),
            ("POST", "pricing-tiers/", {"product_id": ZERO_ID, "min_quantity": 5}),
            ("PATCH", f"pricing-tiers/{ZERO_ID}", {"unit_price": "4.50"}),
            ("DELETE", f"pricing-tiers/{ZERO_ID}", None),
        ],
    )
    async def test_write_is_405_even_for_admin(
        self, client: httpx.AsyncClient, admin_token: str, method: str, path: str, body
    ):
        resp = await client.request(
            method, f"{CATALOG}/{path}", json=body, headers=auth_headers(admin_token)
        )
        assert resp.status_code == 405, resp.text
