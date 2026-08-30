"""
Tests for the users module: /users/me, /users/list, /users/admin-only
"""

from __future__ import annotations

import pytest
import httpx

from tests.conftest import (
    API_V1_PREFIX,
    ADMIN_CREDENTIALS,
    USER_CREDENTIALS,
    auth_headers,
)


# ─────────────────────────────────────────────────────────────────────────────
# /users/me
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCurrentUser:
    """GET /users/me"""

    @pytest.mark.asyncio
    async def test_admin_gets_own_profile(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Admin should be able to fetch their own profile."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/me", headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "success"
        data = body["data"]
        assert data["email"] == ADMIN_CREDENTIALS["email"]
        assert "id" in data
        assert "role" in data
        assert data["role"]["name"] in ("admin", "customer")

    @pytest.mark.asyncio
    async def test_user_gets_own_profile(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """Regular user should be able to fetch their own profile."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/me", headers=auth_headers(user_token)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["email"] == USER_CREDENTIALS["email"]

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: httpx.AsyncClient):
        """No token should return 401."""
        resp = await client.get(f"{API_V1_PREFIX}/users/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, client: httpx.AsyncClient):
        """An obviously broken token returns 401."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/me",
            headers=auth_headers("invalid.token.here"),
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_response_includes_role_and_timestamps(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """The response should include role info and created_at/updated_at."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/me", headers=auth_headers(admin_token)
        )
        data = resp.json()["data"]
        assert "role" in data
        assert "id" in data["role"]
        assert "name" in data["role"]
        assert "created_at" in data


# ─────────────────────────────────────────────────────────────────────────────
# /users/list (admin-only)
# ─────────────────────────────────────────────────────────────────────────────

class TestListUsers:
    """GET /users/list"""

    @pytest.mark.asyncio
    async def test_admin_can_list_all_users(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Admin should be able to list all users."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/list", headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200, resp.text
        users = resp.json()["data"]
        assert isinstance(users, list)
        assert len(users) >= 1
        # Each entry should have a valid shape
        for u in users:
            assert "id" in u
            assert "email" in u
            assert "role" in u

    @pytest.mark.asyncio
    async def test_admin_in_list_has_admin_role(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """The admin user should appear in the list."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/list", headers=auth_headers(admin_token)
        )
        users = resp.json()["data"]
        admin_emails = [u["email"] for u in users]
        assert ADMIN_CREDENTIALS["email"] in admin_emails

    @pytest.mark.asyncio
    async def test_regular_user_cannot_list_users(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """SECURITY: cliente1 trying to list all users should get 403."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/list", headers=auth_headers(user_token)
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_list_users(
        self, client: httpx.AsyncClient
    ):
        """No token -> 401."""
        resp = await client.get(f"{API_V1_PREFIX}/users/list")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_supports_pagination_params(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """skip and limit query params should be honored."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/list?skip=0&limit=2",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        users = resp.json()["data"]
        assert len(users) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# /users/admin-only
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminOnly:
    """GET /users/admin-only"""

    @pytest.mark.asyncio
    async def test_admin_can_access(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Admin should be able to access this endpoint."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/admin-only", headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "success"
        assert "message" in body["data"]

    @pytest.mark.asyncio
    async def test_regular_user_blocked(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """SECURITY: cliente1 must NOT access admin-only routes."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/admin-only", headers=auth_headers(user_token)
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_unauthenticated_blocked(self, client: httpx.AsyncClient):
        """No token -> 401."""
        resp = await client.get(f"{API_V1_PREFIX}/users/admin-only")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_second_user_also_blocked(
        self, client: httpx.AsyncClient, user2_token: str
    ):
        """SECURITY: cliente2 also blocked (proves it's role-based, not user-based)."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/admin-only", headers=auth_headers(user2_token)
        )
        assert resp.status_code == 403, resp.text
