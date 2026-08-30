"""Testes black-box das consultas e do cancelamento de pedidos."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import API_V1_PREFIX, auth_headers


class TestListOrders:
    @pytest.mark.asyncio
    async def test_user_lists_own_orders(self, client: httpx.AsyncClient, user_token: str) -> None:
        response = await client.get(
            f"{API_V1_PREFIX}/sales/orders/", headers=auth_headers(user_token)
        )
        assert response.status_code == 200, response.text
        assert isinstance(response.json()["data"], list)

    @pytest.mark.asyncio
    async def test_admin_lists_all_orders(
        self, client: httpx.AsyncClient, admin_token: str
    ) -> None:
        response = await client.get(
            f"{API_V1_PREFIX}/sales/orders/", headers=auth_headers(admin_token)
        )
        assert response.status_code == 200, response.text
        assert isinstance(response.json()["data"], list)

    @pytest.mark.asyncio
    async def test_user_does_not_see_other_users_orders(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ) -> None:
        first = await client.get(f"{API_V1_PREFIX}/sales/orders/", headers=auth_headers(user_token))
        second = await client.get(
            f"{API_V1_PREFIX}/sales/orders/", headers=auth_headers(user2_token)
        )
        first_ids = {order["id"] for order in first.json()["data"]}
        second_ids = {order["id"] for order in second.json()["data"]}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_list_unauthenticated_returns_401(self, client: httpx.AsyncClient) -> None:
        response = await client.get(f"{API_V1_PREFIX}/sales/orders/")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_supports_pagination(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        response = await client.get(
            f"{API_V1_PREFIX}/sales/orders/?skip=0&limit=1",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) <= 1


class TestOrderDetail:
    @pytest.mark.asyncio
    async def test_user_gets_own_order(self, client: httpx.AsyncClient, user_token: str) -> None:
        listing = await client.get(
            f"{API_V1_PREFIX}/sales/orders/", headers=auth_headers(user_token)
        )
        orders = listing.json()["data"]
        if not orders:
            pytest.skip("Nenhum pedido preparado para o usuário")

        order_id = orders[0]["id"]
        response = await client.get(
            f"{API_V1_PREFIX}/sales/orders/{order_id}",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["id"] == order_id
        assert "items" in data
        assert "transactions" in data
        assert "total_amount" in data

    @pytest.mark.asyncio
    async def test_user_cannot_get_other_users_order(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ) -> None:
        listing = await client.get(
            f"{API_V1_PREFIX}/sales/orders/", headers=auth_headers(user_token)
        )
        orders = listing.json()["data"]
        if not orders:
            pytest.skip("Nenhum pedido preparado para o usuário")

        response = await client.get(
            f"{API_V1_PREFIX}/sales/orders/{orders[0]['id']}",
            headers=auth_headers(user2_token),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_nonexistent_order_returns_404(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        missing_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(
            f"{API_V1_PREFIX}/sales/orders/{missing_id}",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 404


class TestOrderImmutability:
    @pytest.mark.asyncio
    async def test_direct_order_creation_is_not_available(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        response = await client.post(
            f"{API_V1_PREFIX}/sales/orders/",
            json={},
            headers=auth_headers(user_token),
        )
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_direct_item_edit_is_not_available(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        missing_id = "00000000-0000-0000-0000-000000000000"
        response = await client.patch(
            f"{API_V1_PREFIX}/sales/orders/{missing_id}/items/{missing_id}",
            json={"quantity": 2},
            headers=auth_headers(user_token),
        )
        assert response.status_code == 405


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_pending_order_releases_checkout(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        listing = await client.get(
            f"{API_V1_PREFIX}/sales/orders/", headers=auth_headers(user_token)
        )
        pending = next(
            (order for order in listing.json()["data"] if order["status"] == "PENDING_PAYMENT"),
            None,
        )
        if pending is None:
            pytest.skip("Nenhum pedido pendente preparado para cancelamento")

        response = await client.post(
            f"{API_V1_PREFIX}/sales/orders/{pending['id']}/cancel",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "CANCELED"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order_returns_404(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        missing_id = "00000000-0000-0000-0000-000000000000"
        response = await client.post(
            f"{API_V1_PREFIX}/sales/orders/{missing_id}/cancel",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 404
