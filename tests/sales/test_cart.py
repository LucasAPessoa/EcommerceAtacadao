"""
Tests for the cart module: /sales/cart/*
"""

from __future__ import annotations

import pytest
import httpx

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
    pytest.skip("No variants seeded")


async def _get_or_create_cart(
    client: httpx.AsyncClient, token: str
) -> dict:
    """Get current cart (creates one if missing). Returns the cart data dict."""
    resp = await client.get(
        f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ─────────────────────────────────────────────────────────────────────────────
# GET /sales/cart/
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCart:
    """GET /sales/cart/"""

    @pytest.mark.asyncio
    async def test_admin_get_or_create_cart(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Admin should be able to fetch or create a cart."""
        resp = await client.get(
            f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200, resp.text
        cart = resp.json()["data"]
        assert "id" in cart
        assert "items" in cart
        assert "user_id" in cart

    @pytest.mark.asyncio
    async def test_user_get_or_create_cart(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """cliente1 has items from seed (2 items)."""
        resp = await client.get(
            f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(user_token)
        )
        assert resp.status_code == 200, resp.text
        cart = resp.json()["data"]
        assert len(cart["items"]) >= 1

    @pytest.mark.asyncio
    async def test_cart_unauthenticated_returns_401(
        self, client: httpx.AsyncClient
    ):
        resp = await client.get(f"{API_V1_PREFIX}/sales/cart/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_getting_cart_twice_returns_same_cart(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Two consecutive GETs should return the same cart (idempotent)."""
        c1 = await client.get(
            f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(admin_token)
        )
        c2 = await client.get(
            f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(admin_token)
        )
        assert c1.json()["data"]["id"] == c2.json()["data"]["id"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /sales/cart/items
# ─────────────────────────────────────────────────────────────────────────────

class TestAddCartItem:
    """POST /sales/cart/items"""

    @pytest.mark.asyncio
    async def test_add_item_to_cart(
        self, client: httpx.AsyncClient, admin_token: str
    ):
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
    async def test_add_item_unauthenticated_returns_401(
        self, client: httpx.AsyncClient
    ):
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
        total = sum(
            i["quantity"]
            for i in cart["items"]
            if i["variant_id"] == variant_id
        )
        assert total >= 3  # at least 1 + 2


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /sales/cart/items/{item_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateCartItem:
    """PATCH /sales/cart/items/{item_id}"""

    @pytest.mark.asyncio
    async def test_update_item_quantity(
        self, client: httpx.AsyncClient, user_token: str
    ):
        cart = await _get_or_create_cart(client, user_token)
        if not cart["items"]:
            pytest.skip("No items in cliente1 cart to update")
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
        cart = await _get_or_create_cart(client, user_token)
        if not cart["items"]:
            pytest.skip("No items in cliente1 cart")
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
        cart = await _get_or_create_cart(client, user_token)
        if not cart["items"]:
            pytest.skip("No items in cart")
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
    async def test_delete_item_from_cart(
        self, client: httpx.AsyncClient, admin_token: str
    ):
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
        target = next(
            (i for i in cart["items"] if i["variant_id"] == variant_id), None
        )
        if not target:
            pytest.skip("Item not found in cart after add")
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
    async def test_clear_cart(
        self, client: httpx.AsyncClient, user_token: str
    ):
        resp = await client.delete(
            f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(user_token)
        )
        assert resp.status_code in (200, 204), resp.text

        # Verify it's empty
        follow = await client.get(
            f"{API_V1_PREFIX}/sales/cart/", headers=auth_headers(user_token)
        )
        assert follow.status_code == 200
        assert follow.json()["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_clear_cart_unauthenticated_returns_401(
        self, client: httpx.AsyncClient
    ):
        resp = await client.delete(f"{API_V1_PREFIX}/sales/cart/")
        assert resp.status_code == 401
