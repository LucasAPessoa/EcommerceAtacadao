"""
Tests for the cart module: /sales/cart/*
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from tests.conftest import API_V1_PREFIX, auth_headers

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_first_variant_id(client: httpx.AsyncClient) -> str:
    """Return a variant_id from the catalog, or skip if none exist."""
    resp = await client.get(f"{API_V1_PREFIX}/catalog/products/")
    assert resp.status_code == 200, resp.text
    products = resp.json()["data"]
    for p in products:
        for v in p.get("variants", []):
            return v["id"]
    raise AssertionError("O catálogo de teste deve conter ao menos uma variação ativa")


async def _get_or_create_cart(client: httpx.AsyncClient, token: str) -> dict:
    """Get current cart (creates one if missing). Returns the cart data dict."""
    resp = await client.get(f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _ensure_cart_has_item(client: httpx.AsyncClient, token: str) -> dict:
    """Arrange an item without relying on mutable seed state from prior runs."""
    cart = await _get_or_create_cart(client, token)
    if cart["items"]:
        return cart
    variant_id = await _get_first_variant_id(client)
    response = await client.post(
        f"{API_V1_PREFIX}/sales/cart/items",
        json={"variant_id": variant_id, "quantity": 1},
        headers=auth_headers(token),
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


# ─────────────────────────────────────────────────────────────────────────────
# GET /sales/cart/
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCart:
    """GET /sales/cart/"""

    @pytest.mark.asyncio
    async def test_admin_get_or_create_cart(self, client: httpx.AsyncClient, admin_token: str):
        """Admin should be able to fetch or create a cart."""
        resp = await client.get(f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(admin_token))
        assert resp.status_code == 200, resp.text
        cart = resp.json()["data"]
        assert "id" in cart
        assert "items" in cart
        assert "user_id" in cart

    @pytest.mark.asyncio
    async def test_user_get_or_create_cart(self, client: httpx.AsyncClient, user_token: str):
        """Fetching a cart must not depend on mutable seed contents."""
        resp = await client.get(f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(user_token))
        assert resp.status_code == 200, resp.text
        cart = resp.json()["data"]
        assert "id" in cart
        assert "items" in cart
        assert "user_id" in cart

    @pytest.mark.asyncio
    async def test_cart_unauthenticated_returns_401(self, client: httpx.AsyncClient):
        resp = await client.get(f"{API_V1_PREFIX}/sales/cart/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_getting_cart_twice_returns_same_cart(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Two consecutive GETs should return the same cart (idempotent)."""
        c1 = await client.get(f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(admin_token))
        c2 = await client.get(f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(admin_token))
        assert c1.json()["data"]["id"] == c2.json()["data"]["id"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /sales/cart/items
# ─────────────────────────────────────────────────────────────────────────────


class TestAddCartItem:
    """POST /sales/cart/items"""

    @pytest.mark.asyncio
    async def test_add_item_to_cart(self, client: httpx.AsyncClient, admin_token: str):
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": variant_id, "quantity": 1},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code in (200, 201), resp.text
        cart = resp.json()["data"]
        item_ids = {i["variant_id"] for i in cart["items"]}
        assert variant_id in item_ids

    @pytest.mark.asyncio
    async def test_add_item_unauthenticated_returns_401(self, client: httpx.AsyncClient):
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": "00000000-0000-0000-0000-000000000000", "quantity": 1},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_add_item_with_zero_quantity_returns_422(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": variant_id, "quantity": 0},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_item_with_negative_quantity_returns_422(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": variant_id, "quantity": -5},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_item_with_invalid_variant_returns_404(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={
                "variant_id": "00000000-0000-0000-0000-000000000000",
                "quantity": 1,
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code in (400, 404), resp.text

    @pytest.mark.asyncio
    async def test_add_item_with_missing_fields_returns_422(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"quantity": 1},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_adding_same_variant_twice_merges_or_dups(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Adding the same variant twice should either merge quantities or create
        a duplicate — either is acceptable as long as the cart stays consistent."""
        variant_id = await _get_first_variant_id(client)
        await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": variant_id, "quantity": 1},
            headers=auth_headers(admin_token),
        )
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": variant_id, "quantity": 2},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code in (200, 201)
        cart = resp.json()["data"]
        # Just confirm the variant is still in the cart and total quantity is sane
        total = sum(i["quantity"] for i in cart["items"] if i["variant_id"] == variant_id)
        assert total >= 3  # at least 1 + 2


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /sales/cart/items/{item_id}
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateCartItem:
    """PATCH /sales/cart/items/{item_id}"""

    @pytest.mark.asyncio
    async def test_update_item_quantity(self, client: httpx.AsyncClient, user_token: str):
        cart = await _ensure_cart_has_item(client, user_token)
        item_id = cart["items"][0]["id"]

        resp = await client.patch(
            f"{API_V1_PREFIX}/sales/cart/items/{item_id}",
            json={"quantity": 5},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        item = next((i for i in items if i["id"] == item_id), None)
        assert item is not None
        assert item["quantity"] == 5

    @pytest.mark.asyncio
    async def test_update_other_users_item_returns_404(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ):
        cart = await _ensure_cart_has_item(client, user_token)
        item_id = cart["items"][0]["id"]

        resp = await client.patch(
            f"{API_V1_PREFIX}/sales/cart/items/{item_id}",
            json={"quantity": 99},
            headers=auth_headers(user2_token),
        )
        assert resp.status_code in (403, 404), resp.text

    @pytest.mark.asyncio
    async def test_update_item_with_zero_quantity_returns_422(
        self, client: httpx.AsyncClient, user_token: str
    ):
        cart = await _ensure_cart_has_item(client, user_token)
        item_id = cart["items"][0]["id"]

        resp = await client.patch(
            f"{API_V1_PREFIX}/sales/cart/items/{item_id}",
            json={"quantity": 0},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /sales/cart/items/{item_id}
# ─────────────────────────────────────────────────────────────────────────────


class TestDeleteCartItem:
    """DELETE /sales/cart/items/{item_id}"""

    @pytest.mark.asyncio
    async def test_delete_item_from_cart(self, client: httpx.AsyncClient, admin_token: str):
        variant_id = await _get_first_variant_id(client)
        # Add an item
        await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": variant_id, "quantity": 1},
            headers=auth_headers(admin_token),
        )
        # Fetch the cart
        cart = await _get_or_create_cart(client, admin_token)
        # Find the item we just added
        target = next((i for i in cart["items"] if i["variant_id"] == variant_id), None)
        assert target is not None, "O item adicionado deve ser devolvido pelo carrinho"
        item_id = target["id"]

        resp = await client.delete(
            f"{API_V1_PREFIX}/sales/cart/items/{item_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code in (200, 204), resp.text

    @pytest.mark.asyncio
    async def test_delete_nonexistent_item_returns_404(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        fake = "00000000-0000-0000-0000-000000000000"
        resp = await client.delete(
            f"{API_V1_PREFIX}/sales/cart/items/{fake}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code in (403, 404), resp.text


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /sales/cart/  (clear entire cart)
# ─────────────────────────────────────────────────────────────────────────────


class TestClearCart:
    """DELETE /sales/cart/"""

    @pytest.mark.asyncio
    async def test_clear_cart(self, client: httpx.AsyncClient, user_token: str):
        resp = await client.delete(f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(user_token))
        assert resp.status_code in (200, 204), resp.text

        # Verify it's empty
        follow = await client.get(f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(user_token))
        assert follow.status_code == 200
        assert follow.json()["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_clear_cart_unauthenticated_returns_401(self, client: httpx.AsyncClient):
        resp = await client.delete(f"{API_V1_PREFIX}/sales/cart/")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Limite de estoque (back #119)
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def limited_variant_id():
    """Variação própria com estoque 5; grava só em DB localhost/postgres (como pending_order)."""
    import os
    from decimal import Decimal
    from urllib.parse import urlparse
    from uuid import uuid4

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.catalog import Product, ProductVariant
    from src.models.sales import CartItem

    host = urlparse(settings.DATABASE_URL.replace("+asyncpg", "")).hostname
    if host not in {"localhost", "127.0.0.1", "postgres"} and (
        os.environ.get("ALLOW_TEST_DB_WRITES") != "1"
    ):
        pytest.fail(
            f"fixture escreve no banco ({host}); use localhost/CI ou ALLOW_TEST_DB_WRITES=1."
        )
    # Engine própria sem pool: cada teste roda em um event loop diferente.
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    suffix = uuid4().hex[:12]
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Produto estoque {suffix}", is_active=True)
        session.add(product)
        await session.flush()
        variant = ProductVariant(
            product_id=product.id,
            bling_sku=f"STK-{suffix}",
            variation_name="Unica",
            base_price=Decimal("10.00"),
            stock_quantity=5,
        )
        session.add(variant)
        await session.commit()
        variant_id, product_id = variant.id, product.id

    yield str(variant_id)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(CartItem).where(CartItem.variant_id == variant_id))
        await session.execute(delete(ProductVariant).where(ProductVariant.id == variant_id))
        await session.execute(delete(Product).where(Product.id == product_id))
        await session.commit()
    await engine.dispose()


class TestCartStockLimit:
    @pytest.mark.asyncio
    async def test_add_above_stock_returns_409_with_available(
        self, client: httpx.AsyncClient, user_token: str, limited_variant_id: str
    ):
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": limited_variant_id, "quantity": 99999},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["available"] == 5
        assert "Estoque insuficiente" in body["detail"]

    @pytest.mark.asyncio
    async def test_add_with_item_in_cart_returns_remaining_available(
        self, client: httpx.AsyncClient, user_token: str, limited_variant_id: str
    ):
        add = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": limited_variant_id, "quantity": 2},
            headers=auth_headers(user_token),
        )
        assert add.status_code == 201, add.text
        resp = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": limited_variant_id, "quantity": 4},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["available"] == 3
        ok = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": limited_variant_id, "quantity": 3},
            headers=auth_headers(user_token),
        )
        assert ok.status_code == 201, ok.text

    @pytest.mark.asyncio
    async def test_patch_above_stock_returns_409_with_available(
        self, client: httpx.AsyncClient, user_token: str, limited_variant_id: str
    ):
        add = await client.post(
            f"{API_V1_PREFIX}/sales/cart/items",
            json={"variant_id": limited_variant_id, "quantity": 2},
            headers=auth_headers(user_token),
        )
        assert add.status_code == 201, add.text
        item = next(i for i in add.json()["data"]["items"] if i["variant_id"] == limited_variant_id)
        resp = await client.patch(
            f"{API_V1_PREFIX}/sales/cart/items/{item['id']}",
            json={"quantity": 6},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["available"] == 5
        ok = await client.patch(
            f"{API_V1_PREFIX}/sales/cart/items/{item['id']}",
            json={"quantity": 5},
            headers=auth_headers(user_token),
        )
        assert ok.status_code == 200, ok.text
