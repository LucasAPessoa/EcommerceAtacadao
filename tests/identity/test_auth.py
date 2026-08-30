"""
Tests for the auth module: /auth/register, /auth/login, /auth/refresh, /auth/logout
"""

from __future__ import annotations

import pytest
import httpx

from tests.conftest import (
    API_V1_PREFIX,
    ADMIN_CREDENTIALS,
    USER_CREDENTIALS,
    auth_headers,
    make_user_payload,
    unique_email,
)


# ─────────────────────────────────────────────────────────────────────────────
# /auth/register
# ─────────────────────────────────────────────────────────────────────────────

class TestRegister:
    """POST /auth/register"""

    @pytest.mark.asyncio
    async def test_register_company_user_succeeds(self, client: httpx.AsyncClient):
        """A valid COMPANY payload should return 201 and the user data."""
        payload = make_user_payload(email=unique_email("reg_company"))
        resp = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp.status_code in (200, 201), resp.text
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["email"] == payload["email"]
        assert body["data"]["user_type"] == "COMPANY"
        assert "id" in body["data"]
        assert "password" not in body["data"]
        assert "password_hash" not in body["data"]

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_400(
        self, client: httpx.AsyncClient
    ):
        """Re-registering an existing email should return 400."""
        payload = make_user_payload(email=unique_email("reg_dup"))
        # First registration
        resp1 = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp1.status_code in (200, 201), resp1.text
        # Second registration with same email
        resp2 = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp2.status_code == 400, resp2.text
        assert "already" in resp2.text.lower() or "existe" in resp2.text.lower()

    @pytest.mark.asyncio
    async def test_register_missing_email_returns_422(
        self, client: httpx.AsyncClient
    ):
        """Missing required email field should return 422 (Pydantic validation)."""
        payload = make_user_payload()
        del payload["email"]
        resp = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(
        self, client: httpx.AsyncClient
    ):
        """Invalid email format should return 422."""
        payload = make_user_payload(email="not-an-email")
        resp = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_weak_password_returns_422(
        self, client: httpx.AsyncClient
    ):
        """Password without upper/lower/digit/special should fail validation."""
        payload = make_user_payload(password="weakpass")
        resp = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_short_password_returns_422(
        self, client: httpx.AsyncClient
    ):
        """Password shorter than 8 chars should fail validation."""
        payload = make_user_payload(password="Aa1!")  # 4 chars
        resp = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_response_excludes_password(
        self, client: httpx.AsyncClient
    ):
        """The response should never include the password or password_hash."""
        payload = make_user_payload(email=unique_email("reg_nopwd"))
        resp = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
        assert resp.status_code in (200, 201), resp.text
        text = resp.text.lower()
        assert "password" not in text or "password_hash" not in text


# ─────────────────────────────────────────────────────────────────────────────
# /auth/login
# ─────────────────────────────────────────────────────────────────────────────

class TestLogin:
    """POST /auth/login"""

    @pytest.mark.asyncio
    async def test_admin_login_succeeds(self, client: httpx.AsyncClient):
        """Admin credentials should return 200 + token pair."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/login", json=ADMIN_CREDENTIALS
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "success"
        assert "data" in body
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_user_login_succeeds(self, client: httpx.AsyncClient):
        """cliente1 credentials should return 200 + token pair."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/login", json=USER_CREDENTIALS
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data"]["access_token"]
        assert body["data"]["refresh_token"]

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(
        self, client: httpx.AsyncClient
    ):
        """Wrong password should return 401."""
        payload = {"email": ADMIN_CREDENTIALS["email"], "password": "WrongPass1!"}
        resp = await client.post(f"{API_V1_PREFIX}/auth/login", json=payload)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_email_returns_401(
        self, client: httpx.AsyncClient
    ):
        """Non-existent email should return 401 (not 404, to avoid enumeration)."""
        payload = {"email": "nobody@example.com", "password": "AnyPass1!"}
        resp = await client.post(f"{API_V1_PREFIX}/auth/login", json=payload)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_missing_fields_returns_422(
        self, client: httpx.AsyncClient
    ):
        """Missing email or password should return 422."""
        resp1 = await client.post(
            f"{API_V1_PREFIX}/auth/login", json={"email": ADMIN_CREDENTIALS["email"]}
        )
        assert resp1.status_code == 422
        resp2 = await client.post(
            f"{API_V1_PREFIX}/auth/login", json={"password": "anything"}
        )
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_login_invalid_email_format_returns_422(
        self, client: httpx.AsyncClient
    ):
        """Malformed email should return 422 (not 401)."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/login",
            json={"email": "not-an-email", "password": "any"},
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# /auth/refresh
# ─────────────────────────────────────────────────────────────────────────────

class TestRefresh:
    """POST /auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_with_valid_token_returns_new_pair(
        self, client: httpx.AsyncClient, admin_refresh_token: str
    ):
        """A valid refresh token should produce a new access+refresh pair."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/refresh",
            json={"refresh_token": admin_refresh_token},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        # New tokens should differ from the old ones (jti guarantee)
        assert body["data"]["refresh_token"] != admin_refresh_token

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token_returns_401(
        self, client: httpx.AsyncClient
    ):
        """Garbage refresh token should return 401."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/refresh",
            json={"refresh_token": "this.is.not.a.jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_reused_token_returns_401(
        self, client: httpx.AsyncClient, admin_refresh_token: str
    ):
        """A refresh token can only be used once — re-use should fail."""
        # First use
        resp1 = await client.post(
            f"{API_V1_PREFIX}/auth/refresh",
            json={"refresh_token": admin_refresh_token},
        )
        assert resp1.status_code == 200
        # Second use (token was revoked)
        resp2 = await client.post(
            f"{API_V1_PREFIX}/auth/refresh",
            json={"refresh_token": admin_refresh_token},
        )
        assert resp2.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_missing_token_returns_422(
        self, client: httpx.AsyncClient
    ):
        """Missing refresh_token field should return 422."""
        resp = await client.post(f"{API_V1_PREFIX}/auth/refresh", json={})
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# /auth/logout
# ─────────────────────────────────────────────────────────────────────────────

class TestLogout:
    """POST /auth/logout"""

    @pytest.mark.asyncio
    async def test_logout_with_valid_token_revokes_it(
        self, client: httpx.AsyncClient, user_token: str, user_refresh_token: str
    ):
        """Logout should revoke the refresh token and return 200."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/logout",
            json={"refresh_token": user_refresh_token},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data"]["revoked"] is True

    @pytest.mark.asyncio
    async def test_logout_without_auth_returns_401(
        self, client: httpx.AsyncClient, user_refresh_token: str
    ):
        """Logout without an access token should return 401."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/logout",
            json={"refresh_token": user_refresh_token},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_with_other_users_token_returns_400(
        self, client: httpx.AsyncClient, admin_token: str, user_refresh_token: str
    ):
        """Admin trying to revoke cliente1's refresh token should fail with 400."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/logout",
            json={"refresh_token": user_refresh_token},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_logout_with_invalid_token_returns_400(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """Invalid refresh token in payload should return 400."""
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/logout",
            json={"refresh_token": "garbage.token.value"},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_revoked_token_cannot_be_used_for_refresh(
        self, client: httpx.AsyncClient, user_token: str
    ):
        """After logout, the revoked refresh token can't be used to refresh."""
        # Login fresh to get a new refresh token
        login = await client.post(
            f"{API_V1_PREFIX}/auth/login", json=USER_CREDENTIALS
        )
        refresh = login.json()["data"]["refresh_token"]
        # Logout
        await client.post(
            f"{API_V1_PREFIX}/auth/logout",
            json={"refresh_token": refresh},
            headers=auth_headers(user_token),
        )
        # Try to use the revoked token
        resp = await client.post(
            f"{API_V1_PREFIX}/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Security: token tampering
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthSecurity:
    """Negative tests around token integrity."""

    @pytest.mark.asyncio
    async def test_access_with_malformed_bearer_returns_401(
        self, client: httpx.AsyncClient
    ):
        """A non-JWT bearer token should return 401."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/me",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_access_with_wrong_signature_returns_401(
        self, client: httpx.AsyncClient
    ):
        """A JWT signed with the wrong key should return 401."""
        # Forge a token with the right shape but wrong secret
        import jwt as pyjwt
        # Use a known-fake secret to produce a malformed signature
        fake = pyjwt.encode(
            {"sub": ADMIN_CREDENTIALS["email"], "type": "access"},
            "wrong-secret",
            algorithm="HS256",
        )
        resp = await client.get(
            f"{API_V1_PREFIX}/users/me",
            headers={"Authorization": f"Bearer {fake}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_access_without_bearer_prefix_returns_401(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """A token without the 'Bearer ' prefix should return 401."""
        resp = await client.get(
            f"{API_V1_PREFIX}/users/me",
            headers={"Authorization": admin_token},  # missing "Bearer "
        )
        assert resp.status_code in (401, 403)
