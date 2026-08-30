"""
Tests for the addresses module: /addresses/* (CRUD + default)
"""

from __future__ import annotations

import pytest
import httpx

from tests.conftest import (
    API_V1_PREFIX,
    auth_headers,
    unique_email,
    make_user_payload,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_address_payload(
    zip_code: str = "01310100",
    street: str = "Avenida Paulista",
    number: str = "1000",
    city: str = "São Paulo",
    state: str = "SP",
    is_default: bool = False,
) -> dict:
    return {
        "zip_code": zip_code,
        "street": street,
        "number": number,
        "complement": "Apto 101",
        "neighborhood": "Bela Vista",
        "city": city,
        "state": state,
        "is_default": is_default,
    }


# ─────────────────────────────────────────────────────────────────────────────
# /addresses/  (list + create)
# ─────────────────────────────────────────────────────────────────────────────

class TestAddressesListCreate:
    """GET /addresses/ and POST /addresses/"""

    @pytest.mark.asyncio
    async def test_list_user_addresses(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """cliente1 should be able to list their own addresses (seeded 1)."""
        resp = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user_token)
        )
        assert resp.status_code == 200, resp.text
        addrs = resp.json()["data"]
        assert isinstance(addrs, list)
        # cliente1 has a default address from seed
        assert len(addrs) >= 1

    @pytest.mark.asyncio
    async def test_list_unauthenticated_returns_401(
        self, client: httpx.AsyncClient
    ):
        resp = await client.get(f"{API_V1_PREFIX}/addresses/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_address_succeeds(
        self, client: httpx.AsyncClient, user_token: str
    ):
        payload = make_address_payload(street="Rua Nova Teste")
        resp = await client.post(
            f"{API_V1_PREFIX}/addresses/",
            json=payload,
            headers=auth_headers(user_token),
        )
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()["data"]
        assert "id" in data
        assert data["street"] == "Rua Nova Teste"
        assert data["zip_code"] == "01310100"

    @pytest.mark.asyncio
    async def test_create_address_missing_required_fields_returns_422(
        self, client: httpx.AsyncClient, user_token: str
    ):
        # Missing zip_code, street, city, state
        resp = await client.post(
            f"{API_V1_PREFIX}/addresses/",
            json={"number": "1"},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_address_invalid_state_length_returns_422(
        self, client: httpx.AsyncClient, user_token: str
    ):
        payload = make_address_payload(state="SPX")  # 3 chars, max 2
        resp = await client.post(
            f"{API_V1_PREFIX}/addresses/",
            json=payload,
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_address_unauthenticated_returns_401(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            f"{API_V1_PREFIX}/addresses/", json=make_address_payload()
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_user_only_sees_own_addresses(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ):
        """SECURITY: cliente1 should not see cliente2's addresses (and vice-versa)."""
        # cliente1 creates an address
        create = await client.post(
            f"{API_V1_PREFIX}/addresses/",
            json=make_address_payload(street="Rua do Cliente 1"),
            headers=auth_headers(user_token),
        )
        assert create.status_code in (200, 201)
        cliente1_addr_id = create.json()["data"]["id"]

        # cliente2 lists their addresses
        list2 = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user2_token)
        )
        assert list2.status_code == 200
        cliente2_ids = {a["id"] for a in list2.json()["data"]}
        assert cliente1_addr_id not in cliente2_ids


# ─────────────────────────────────────────────────────────────────────────────
# /addresses/{id}  (get / patch / delete)
# ─────────────────────────────────────────────────────────────────────────────

class TestAddressById:
    """GET/PATCH/DELETE /addresses/{address_id}"""

    @pytest.mark.asyncio
    async def test_get_own_address(
        self, client: httpx.AsyncClient, user_token: str
    ):
        # Get the seeded default address
        listing = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user_token)
        )
        addr_id = listing.json()["data"][0]["id"]

        resp = await client.get(
            f"{API_V1_PREFIX}/addresses/{addr_id}",
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["id"] == addr_id

    @pytest.mark.asyncio
    async def test_get_other_users_address_returns_404_or_403(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ):
        """SECURITY: cliente2 should not be able to fetch cliente1's address."""
        listing = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user_token)
        )
        addr_id = listing.json()["data"][0]["id"]

        resp = await client.get(
            f"{API_V1_PREFIX}/addresses/{addr_id}",
            headers=auth_headers(user2_token),
        )
        assert resp.status_code in (403, 404), resp.text

    @pytest.mark.asyncio
    async def test_get_nonexistent_address_returns_404(
        self, client: httpx.AsyncClient, user_token: str
    ):
        fake = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(
            f"{API_V1_PREFIX}/addresses/{fake}",
            headers=auth_headers(user_token),
        )
        assert resp.status_code in (403, 404), resp.text

    @pytest.mark.asyncio
    async def test_get_with_invalid_uuid_returns_422(
        self, client: httpx.AsyncClient, user_token: str
    ):
        resp = await client.get(
            f"{API_V1_PREFIX}/addresses/not-a-uuid",
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_address(
        self, client: httpx.AsyncClient, user_token: str
    ):
        listing = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user_token)
        )
        addr_id = listing.json()["data"][0]["id"]

        resp = await client.patch(
            f"{API_V1_PREFIX}/addresses/{addr_id}",
            json={"number": "9999", "complement": "Sala 50"},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["number"] == "9999"
        assert data["complement"] == "Sala 50"

    @pytest.mark.asyncio
    async def test_patch_other_users_address_returns_404_or_403(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ):
        listing = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user_token)
        )
        addr_id = listing.json()["data"][0]["id"]

        resp = await client.patch(
            f"{API_V1_PREFIX}/addresses/{addr_id}",
            json={"number": "hacked"},
            headers=auth_headers(user2_token),
        )
        assert resp.status_code in (403, 404), resp.text

    @pytest.mark.asyncio
    async def test_delete_address(
        self, client: httpx.AsyncClient, user_token: str
    ):
        # Create a fresh one to delete
        create = await client.post(
            f"{API_V1_PREFIX}/addresses/",
            json=make_address_payload(street="Rua a Deletar"),
            headers=auth_headers(user_token),
        )
        assert create.status_code in (200, 201)
        addr_id = create.json()["data"]["id"]

        resp = await client.delete(
            f"{API_V1_PREFIX}/addresses/{addr_id}",
            headers=auth_headers(user_token),
        )
        assert resp.status_code in (200, 204), resp.text

    @pytest.mark.asyncio
    async def test_delete_other_users_address_returns_404_or_403(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ):
        listing = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user_token)
        )
        addr_id = listing.json()["data"][0]["id"]

        resp = await client.delete(
            f"{API_V1_PREFIX}/addresses/{addr_id}",
            headers=auth_headers(user2_token),
        )
        assert resp.status_code in (403, 404), resp.text


# ─────────────────────────────────────────────────────────────────────────────
# /addresses/{id}/default
# ─────────────────────────────────────────────────────────────────────────────

class TestAddressDefault:
    """POST /addresses/{address_id}/default"""

    @pytest.mark.asyncio
    async def test_set_default_address(
        self, client: httpx.AsyncClient, user_token: str
    ):
        # Create a new (non-default) address
        create = await client.post(
            f"{API_V1_PREFIX}/addresses/",
            json=make_address_payload(street="Novo Endereço", is_default=False),
            headers=auth_headers(user_token),
        )
        assert create.status_code in (200, 201)
        new_id = create.json()["data"]["id"]

        # Mark as default
        resp = await client.post(
            f"{API_V1_PREFIX}/addresses/{new_id}/default",
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_default"] is True

    @pytest.mark.asyncio
    async def test_set_default_for_other_users_address_fails(
        self, client: httpx.AsyncClient, user_token: str, user2_token: str
    ):
        listing = await client.get(
            f"{API_V1_PREFIX}/addresses/", headers=auth_headers(user_token)
        )
        addr_id = listing.json()["data"][0]["id"]

        resp = await client.post(
            f"{API_V1_PREFIX}/addresses/{addr_id}/default",
            headers=auth_headers(user2_token),
        )
        assert resp.status_code in (403, 404), resp.text
